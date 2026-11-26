#!/usr/bin/env python3
"""Read-only BRH event review; no solver launch or change to stopping rules."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import argparse
import hashlib
import json
import os
import shutil

os.environ.setdefault('MPLCONFIGDIR', '/tmp/brh-final-review-mpl')
os.environ.setdefault('XDG_CACHE_HOME', '/tmp/brh-final-review-cache')
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def put(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def variation(values):
    return float(2.3 * np.std(values, ddof=1) / np.sqrt(len(values))) if len(values) > 1 else None


def ratio_variation(numerator, denominator):
    if len(numerator) < 2 or denominator.sum() < 2 or np.count_nonzero(denominator) < 2:
        return None
    residual = numerator - numerator.sum() / denominator.sum() * denominator
    return float(2.3 * np.sqrt(len(residual) / (len(residual) - 1) * np.sum(residual ** 2)) / denominator.sum())


def review(root, out):
    out.mkdir(parents=True, exist_ok=True)
    cfg = json.loads((root / 'config.json').read_text())
    frequency = cfg['frequency_Hz']
    area = cfg['fictive_area_m2']
    weight = cfg['weight']
    charge = 1.60217662e-19
    rows, inputs = [], []
    for gap in cfg['gaps_mm']:
        directory = Path(cfg['case_sources'].get(str(gap), {}).get('path', root / f'{gap}mm'))
        state_path = directory / 'status.json'
        state = json.loads(state_path.read_text())
        row = {'gap_mm': gap, 'status': state['status'], 'measured_RF': state.get('measured_RF', 0)}
        if not state.get('measurement_summary_path') or row['measured_RF'] == 0:
            rows.append(row)
            continue
        summary_path = Path(state['measurement_summary_path'])
        summary = json.loads(summary_path.read_text())
        source = Path(summary['pooled_data_path'])
        raw = source / 'upper_returns.npy'
        if raw.exists():
            events = pd.DataFrame(np.load(raw))
        else:
            raw = source / 'brh_roundtrips.csv.gz'
            events = pd.read_csv(raw, float_precision='round_trip')
            events = events.loc[events.side == 1].copy()
        events = events.sort_values(['uid', 'start_t_s', 'end_t_s']).reset_index(drop=True)
        assert not events.duplicated(['uid', 'start_t_s', 'end_t_s']).any()
        assert len(events) == summary['powered_side_returns']
        good = (events.near_fundamental > 0) & ((events.n_elastic + events.n_excitation + events.n_ionization) == 0)
        touching = (events.uid == events.uid.shift()) & np.isclose(events.start_t_s, events.end_t_s.shift(), rtol=0, atol=1e-12)
        continuing = good & good.shift(fill_value=False) & touching
        start = good & ~continuing
        events['observed_run'] = start.cumsum()
        selected = events.loc[good].copy()
        selected['observed_return_index'] = selected.groupby('observed_run').cumcount() + 1
        selected['strict_second_plus'] = selected.observed_return_index >= 2
        sizes = selected.groupby('observed_run').size()
        runs = sizes[sizes >= 2]
        strict = events.loc[continuing].copy()
        # A new collision-free chain is a subset of the existing near-1T
        # consecutive-return diagnostic, never a new simulation criterion.
        assert np.all(strict.consecutive_returns >= 2)
        assert len(strict) == int((runs - 1).sum())
        assert np.max(abs(selected.W_field_eV + selected.dK_collision_parent_eV - selected.dK_staggered_eV).to_numpy(), initial=0) < 1e-6
        assert np.max(abs(selected.dK_collision_parent_eV).to_numpy(), initial=0) < 1e-6
        selected.to_csv(out / f'{gap}mm_collisionfree_returns.csv.gz', index=False, compression={'method': 'gzip', 'mtime': 0})
        native = Path(state['pooled_native_path']) / 'particle_balance.csv'
        balance = pd.read_csv(native)
        balance = balance.loc[balance.RF_cycle.between(summary['first_RF'], summary['last_RF'])].copy()
        assert len(balance) == summary['measured_RF']
        assert np.array_equal(balance.RF_cycle, np.arange(summary['first_RF'], summary['last_RF'] + 1))
        mean_power = float(balance.e_field_work_J.sum() / (area * summary['duration_s']))
        check_power = summary['all_fieldwork_eV'] * weight * charge / (area * summary['duration_s'])
        assert np.isclose(mean_power, check_power, rtol=1e-7, atol=1e-9)
        row.update(RF_first=summary['first_RF'], RF_last=summary['last_RF'], measured_RF=summary['measured_RF'],
                   background_criteria_passed=summary['background_and_BRH_assessment'].get('background_passed', False),
                   all_upper_returns=len(events), near_1T_returns=int((events.near_fundamental > 0).sum()),
                   collisionfree_near_1T_returns=len(selected), collisionfree_observed_runs_ge2=len(runs),
                   collisionfree_returns_in_runs_ge2=int(runs.sum()), collisionfree_second_plus_returns=len(strict),
                   collisionfree_observed_runs_per_1000RF=float(len(runs) * 1000 / summary['measured_RF']),
                   maximum_observed_collisionfree_streak=int(sizes.max()) if len(sizes) else 0,
                   strict_distinct_UIDs=int(strict.uid.nunique()), strict_negative_work_returns=int((strict.W_field_eV < 0).sum()),
                   original_collision_inclusive_candidate_returns=summary['candidate_returns'],
                   strict_second_plus_percent_of_upper_returns=float(len(strict) / len(events) * 100) if len(events) else None,
                   strict_mean_signed_work_eV=float(strict.W_field_eV.mean()) if len(strict) else None,
                   strict_mean_net_dK_eV=float(strict.dK_staggered_eV.mean()) if len(strict) else None,
                   electron_net_field_power_Wm2=mean_power)
        probability = summary['sample_inclusion_probability']
        row['strict_selected_work_power_Wm2_estimate'] = float(strict.W_field_eV.sum() * weight * charge / (area * summary['duration_s'] * probability))
        for width in [20, 40]:
            count = len(balance) // width
            powers = balance.e_field_work_J.to_numpy()[:count * width].reshape(count, width).mean(axis=1) * frequency / area
            row[f'power_{width}RF_variation_Wm2'] = variation(powers)
            row[f'power_{width}RF_variation_used_RF'] = count * width
            # Assign each complete return to its end-time bin. The mean includes
            # whole return work, and these are exploratory batch indicators.
            t0 = (summary['first_RF'] - 1) / frequency
            index = np.floor((strict.end_t_s.to_numpy() - t0) * frequency / width).astype(int)
            keep = (index >= 0) & (index < count)
            numerator = np.bincount(index[keep], weights=strict.W_field_eV.to_numpy()[keep], minlength=count)
            denominator = np.bincount(index[keep], minlength=count)
            row[f'strict_work_{width}RF_variation_eV'] = ratio_variation(numerator, denominator)
        rows.append(row)
        inputs.append({'gap_mm': gap, 'summary_path': str(summary_path), 'summary_SHA256': sha(summary_path),
                       'raw_event_path': str(raw), 'raw_event_SHA256': sha(raw),
                       'native_balance_path': str(native), 'native_balance_SHA256': sha(native),
                       'RF_first': summary['first_RF'], 'RF_last': summary['last_RF'],
                       'sample_inclusion_probability': probability})
    data = pd.DataFrame(rows)
    data.to_csv(out / 'collisionfree_gap_summary.csv', index=False)
    measured = data.loc[data.measured_RF > 0]
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.5))
    for _, row in measured.iterrows():
        gap = row.gap_mm
        complete = row.status != 'running'
        color = 'tab:blue' if complete else 'tab:gray'
        axes[0].plot(gap, row.collisionfree_observed_runs_per_1000RF, 'o', color=color, markerfacecolor=color if complete else 'none')
        pwidth = max(row.power_20RF_variation_Wm2, row.power_40RF_variation_Wm2)
        axes[1].errorbar(gap, row.electron_net_field_power_Wm2, yerr=pwidth, fmt='o', color=color, capsize=3)
        if pd.notna(row.strict_mean_signed_work_eV):
            widths = [row.strict_work_20RF_variation_eV, row.strict_work_40RF_variation_eV]
            finite = [w for w in widths if pd.notna(w)]
            axes[2].errorbar(gap, row.strict_mean_signed_work_eV, yerr=max(finite) if finite else None, fmt='o', color=color, markerfacecolor=color if finite else 'none', capsize=3)
            if not finite:
                axes[2].annotate(f'N={int(row.collisionfree_second_plus_returns)}', (gap, row.strict_mean_signed_work_eV), xytext=(3, 7), textcoords='offset points', fontsize=8)
    axes[0].set(ylabel='Observed collision-free runs >=2 / 1000 RF', title='Near 1T; sampled complete upper returns')
    axes[1].set(ylabel='Electron net field power (W/m2)', title='All electrons; exact native field-kick work')
    axes[2].set(ylabel='Selected signed work per return (eV)', title='Collision-free second+ returns; sparse data')
    axes[2].axhline(0, color='k', lw=.6)
    peak = measured.loc[measured.gap_mm.isin([45, 50])]
    if len(peak) == 2:
        inset = axes[1].inset_axes([.49, .12, .46, .40])
        for _, row in peak.iterrows():
            inset.errorbar(row.gap_mm, row.electron_net_field_power_Wm2, yerr=max(row.power_20RF_variation_Wm2, row.power_40RF_variation_Wm2), fmt='o', capsize=3)
        inset.set(xlim=(43, 52), xticks=[45, 50], title='45 vs 50 mm')
        inset.tick_params(labelsize=7);inset.title.set_fontsize(9);inset.grid(alpha=.2)
    for ax in axes:
        ax.set(xlabel='Gap (mm)');ax.grid(alpha=.2)
    fig.suptitle('Observed counts and signed heating are different observables; 2.3SE batch indicators, not total error')
    fig.tight_layout();fig.savefig(out / 'collisionfree_gap_review.png', dpi=150, bbox_inches='tight');plt.close(fig)
    terminal = measured.loc[measured.status != 'running']
    maximum = terminal.collisionfree_observed_runs_ge2.max()
    maxima = terminal.loc[terminal.collisionfree_observed_runs_ge2 == maximum, 'gap_mm'].astype(int).tolist()
    method = {'generated_Asia_Seoul': datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),
              'root': str(root), 'analysis_SHA256': sha(Path(__file__)), 'inputs': inputs,
              'config_SHA256': sha(root / 'config.json'), 'control_source_SHA256': cfg['control_source_SHA256'],
              'conditions': {k: cfg[k] for k in ['gas', 'pressure_mTorr', 'temperature_K', 'frequency_Hz', 'voltage_peak_V', 'weight', 'fictive_area_m2']},
              'definition': 'Original near_fundamental flag (|tau/T-1|<=0.1), zero elastic/excitation/ionization counts over every complete upper return, same UID and contiguous end/start times (atol1e-12s), >=2 consecutive qualifying observed returns. Second+ count excludes first return in each observed run.',
              'max_observed_run_count_gaps_among_terminal_measurements_mm': maxima,
              'max_observed_run_count': int(maximum), 'BRH_heating_peak_established': False,
              'scope': 'Diagnostic postfilter only. Does not change the solver, original collision-inclusive BRH criteria, epochs, RF limits, or approved gaps. 80mm remains partial until its status is terminal. Extinct cases are undefined, not zero-filled.',
              'selection': 'Original hashed UID sample; complete upper-side round trips only. Observed finite-window runs may be censored and are not electron lifetime counts. Counts do not prove a population heating maximum.',
              'variation': 'Max of 20/40RF exploratory 2.3SE batch indicators; incomplete final batch omitted only from variation, not the overall point mean. Ratio work indicator uses per-batch centered numerator/denominator residuals and requires events in >=2 batches; otherwise unknown. End-time bin assignment includes whole return work. Correlation, rare tails, grid and model error remain separate.',
              'power': 'Global net power is native electron field-kick work/time/area, cross-checked against all-electron diagnostic work; distinct from legacy phase-mean <j><E>. Selected-work power divides by original UID inclusion probability and is not an attributed BRH heating increment.'}
    put(out / 'analysis_provenance.json', method)
    if Path(__file__).resolve() != (out / 'review_collisionfree.py').resolve():
        shutil.copy2(__file__, out / 'review_collisionfree.py')
    lines = ['# 무충돌 약1RF 연속 왕복과 signed 전력', '',
             '기존 BRH 원자료를 다시 읽은 보조 분석입니다. 솔버·기존 수렴 기준·측정 상한·승인 gap은 변경하지 않습니다.', '',
             '종료된 측정 조건 중 관측 연속 구간 수 최대: ' + ', '.join(map(str, maxima)) + f' mm ({int(maximum)}개). **BRH 순가열 최대점은 미확정입니다.**', '',
             '![관측 수와 전력의 구분](collisionfree_gap_review.png)', '',
             '| gap mm | 상태 | 측정 RF | 관측 연속 구간 ≥2 | 두 번째 이후 왕복 수 | 음의 field work 수 |',
             '|---:|---|---:|---:|---:|---:|']
    for _, row in data.iterrows():
        if row.measured_RF == 0:
            lines.append(f'| {int(row.gap_mm)} | {row.status} | 0 | — | — | — |')
        else:
            lines.append(f'| {int(row.gap_mm)} | {row.status} | {int(row.measured_RF)} | {int(row.collisionfree_observed_runs_ge2)} | {int(row.collisionfree_second_plus_returns)} | {int(row.strict_negative_work_returns)} |')
    if len(peak) == 2:
        lines += ['', '전체 전자 field-kick 순전력의 근접한 두 점:']
        for _, row in peak.iterrows():
            width = max(row.power_20RF_variation_Wm2, row.power_40RF_variation_Wm2)
            lines.append(f'- {int(row.gap_mm)} mm: {row.electron_net_field_power_Wm2:.4f} W/m², 탐색적 변동 지표 ±{width:.4f} W/m².')
        lines += ['', '45·50 mm의 전력 차이는 이 변동 지표보다 작습니다. 전체 전자 흡수 전력의 근접점과 특정 BRH 과정에 기인한 순가열 최대점을 구분합니다.']
    lines += ['', '약1RF: 원래 |τ/T−1|≤0.1 flag를 그대로 사용합니다. 모든 관측 왕복에서 탄성·여기·이온화 충돌 수가 0이고 같은 UID의 출발/도착 시간이 이어져야 합니다. 한 연속 구간에서 관측 왕복 3개는 구간1개·두 번째 이후 사건2개입니다.', '',
              '필터를 통과한 사건 수도 적고 signed work에는 음의 기여가 있습니다. 20/40RF 막대는 탐색적 변동 지표이며 전체 오차·정상 수렴·peak 신뢰도를 보증하지 않습니다. 전체 전자 전력과 선택된 왕복의 전기장 일을 구분합니다. 80 mm가 running이면 부분 자료입니다. 20/25 mm 소멸은 관측 수 0으로 비교하지 않습니다.', '',
              '[요약 CSV](collisionfree_gap_summary.csv) · [정의·원자료 SHA256·해석 범위](analysis_provenance.json) · [재현 분석 코드](review_collisionfree.py)', '']
    lines += [f'- [{int(row.gap_mm)} mm 무충돌 관측 왕복 원자료](%dmm_collisionfree_returns.csv.gz)' % row.gap_mm for _, row in measured.iterrows()]
    (out / 'README.md').write_text('\n'.join(lines) + '\n')
    print(json.dumps({'terminal_max_gaps_mm': maxima, 'observed_runs': int(maximum), 'heating_peak_established': False, 'output': str(out)}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    review(args.root.resolve(), args.output.resolve())
