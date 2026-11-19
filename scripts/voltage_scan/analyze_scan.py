"""Plots and reusable data for completed or explicitly limited voltage-scan cases."""
from pathlib import Path
import argparse
import json
import os
import re
import shutil
import zipfile
import numpy as np
os.environ.setdefault('MPLCONFIGDIR', '/workspace/edupic-results/.mpl-cache')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from stopping import XT, X, read_arrays, observables, save_json, sha, checkpoint, assess_blocks

LABELS = {
    'pot': ('Potential', 'V', 1, 'RdBu_r'),
    'efield': ('Electric field', 'kV/m', 1000, 'RdBu_r'),
    'ne': ('Electron density', 'm$^{-3}$', 1, 'viridis'),
    'ni': ('Ion density', 'm$^{-3}$', 1, 'viridis'),
    'je': ('Electron conduction current density', 'A/m$^2$', 1, 'RdBu_r'),
    'ji': ('Ion conduction current density', 'A/m$^2$', 1, 'RdBu_r'),
    'powere': ('Electron energy transfer: binned j_e E', 'W/m$^3$', 1, 'RdBu_r'),
    'poweri': ('Ion energy transfer: binned j_i E', 'W/m$^3$', 1, 'RdBu_r'),
    'meanee': ('Mean electron energy', 'eV', 1, 'viridis'),
    'meanei': ('Mean ion energy', 'eV', 1, 'viridis'),
    'ioniz': ('Ionization rate', 'm$^{-3}$ s$^{-1}$', 1, 'viridis')}


def archive(target, files):
    temp = target.with_suffix(target.suffix + '.tmp')
    with zipfile.ZipFile(temp, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for p, name in files:
            z.write(p, name)
    with zipfile.ZipFile(temp) as z:
        assert z.testzip() is None
    assert temp.stat().st_size < 95_000_000, 'Split archive before GitHub file-size limit'
    temp.replace(target)


def pooled(arrays):
    stacks = {k: np.array([a[k] for a in arrays]) for k in XT}
    pool = {k: v.mean(axis=0) for k, v in stacks.items()}
    for s in ['e', 'i']:
        pool['power' + s + '_mean_of_blocks'] = pool['power' + s].copy()
        pool['power' + s] = pool['j' + s] * pool['efield']
        num = (stacks['meane' + s] * stacks['n' + s]).sum(axis=0)
        den = stacks['n' + s].sum(axis=0)
        pool['meane' + s] = np.divide(num, den, out=np.zeros_like(num), where=den > 0)
    pool['density'] = np.column_stack([X, pool['ne'].mean(axis=1), pool['ni'].mean(axis=1)])
    pool['eepf_equal_block_mean'] = np.mean([a['eepf'] for a in arrays], axis=0)
    pool['ifed_equal_block_mean'] = np.mean([a['ifed'] for a in arrays], axis=0)
    return pool


def summarize_case(root, case):
    key = case.name
    state = json.loads((case / 'status.json').read_text())
    assert state['status'] in ['criteria_met', 'measurement_limit_reached', 'paused_at_checkpoint',
                               'total_cycle_limit_reached', 'extinguished']
    out = case / 'final_output'; out.mkdir(exist_ok=True)
    epoch = state.get('measurement_epoch', 0)
    blocks = sorted(p.parent for p in (case / 'measurements' / f'epoch{epoch:03d}').glob('*/block.json'))
    history = np.loadtxt(case / 'history.dat', ndmin=2)
    np.savetxt(out / (key + '_particle_counts.csv'), history, delimiter=',', fmt='%d',
               header='RF_cycle,electron_superparticles,ion_superparticles', comments='')
    summary = dict(voltage_peak_V=state['voltage_peak_V'], pressure_mTorr=20, status=state['status'],
                   total_cycles=state['checkpoint_cycle'], measurement_cycles=len(blocks) * 20,
                   solver_wall_seconds=state['elapsed_solver_seconds'], final_checkpoint=checkpoint(case / 'latest_checkpoint.bin'))
    if not blocks:
        summary['first_zero_electron_cycle'] = next((int(row[0]) for row in history if row[1] == 0), None)
        summary['first_zero_ion_cycle'] = next((int(row[0]) for row in history if row[2] == 0), None)
        if state['status'] == 'extinguished':
            # Exactly empty particle state; these zeros are not a sampled plasma average.
            for name in ['mean_density_e', 'mean_density_i', 'center_density_e', 'center_density_i', 'mean_power_e', 'mean_power_i']:
                summary[name] = 0.0
            summary['zero_observable_definition'] = 'Deduced from the exactly empty final particle state, not a steady-discharge measurement.'
        save_json(out / (key + '_summary.json'), summary)
        fig, axs = plt.subplots(1, 2, figsize=(12, 4.8), layout='constrained')
        for ax in axs:
            ax.plot(history[:, 0], history[:, 1], label='Electrons')
            ax.plot(history[:, 0], history[:, 2], label='Ar+ ions')
            ax.set(xlabel='RF cycles after condition change', ylabel='Superparticles')
            ax.grid(alpha=.2); ax.legend()
        if summary['first_zero_electron_cycle']:
            axs[0].set_xlim(0, min(history[-1, 0], summary['first_zero_electron_cycle'] + 80))
            axs[0].axvline(summary['first_zero_electron_cycle'], color='gray', ls='--')
        axs[0].set_title('Discharge decay')
        axs[1].set_yscale('symlog', linthresh=1)
        axs[1].set_title('Residual-ion loss to the empty state')
        fig.suptitle(f'Ar 20 mTorr | {state["voltage_peak_V"]} V peak | upper RF / lower ground\n{state["status"]}: no steady plasma measurement')
        figure = key + '_extinction.png'; fig.savefig(out / figure, dpi=150)
        with PdfPages(out / (key + '_all_plots.pdf')) as pdf:
            pdf.savefig(fig)
        plt.close(fig)
        (out / 'FINAL_REPORT.md').write_text(f'''# {key}

상태: **{state['status']} — 정상 방전의 통계 수렴으로 판정하지 않았습니다.**

| 항목 | 결과 |
|---|---:|
| 전자 입자가 처음 0이 된 RF 주기 | {summary['first_zero_electron_cycle']} |
| 이온 입자가 처음 0이 된 RF 주기 | {summary['first_zero_ion_cycle']} |
| 마지막 저장 RF 주기 | {state['checkpoint_cycle']} |
| 마지막 전자·이온 입자 수 | {summary['final_checkpoint']['electrons']} · {summary['final_checkpoint']['ions']} |
| 정상 방전 측정 주기 | 0 |

20 mTorr, {state['voltage_peak_V']} V peak, 13.56 MHz, Ar 350 K, 간격 25 mm 조건입니다.
원래 수렴 입자 분포를 상하 반전해 시작했으나, 새 조건에서 입자 수가 감소했습니다.
최종 입자가 모두 없는 상태에서는 플라즈마 밀도와 입자 jE가 0입니다. 이는 빈 입자 상태에서 직접 따라오는 값이며 정상 방전의 측정 평균이 아닙니다.
전자·이온 에너지 분포는 정규화할 입자가 없어 정의할 수 없으므로, 정상상태 heating·EEPF·IFEDF 그림을 만들지 않았습니다.

이 결과는 현재 1D 모델, 원래 입자 가중치, 충돌 및 완전 흡수 표면 조건에 대한 결과입니다.
실제 실험의 방전 유지 한계로 바로 해석할 수는 없습니다. 다른 조건을 연구하려면 최종 빈 상태 대신 소멸 전 또는 초기 입자 체크포인트를 사용해야 합니다.

![입자 소멸 과정]({figure})
''')
        for name in ['criteria.json', 'config.json', 'source-eduPIC.cc', 'LICENSE']:
            shutil.copyfile(root / name, out / (key + '_' + name))
        for name in ['status.json', 'boundary_verification.log']:
            shutil.copyfile(case / name, out / (key + '_' + name))
        archive(out / (key + '_summary.zip'), [(p, key + '/' + p.name) for p in out.iterdir() if p.is_file() and p.suffix != '.zip'])
        save_json(case / 'finalized.json', {'checkpoint_cycle': state['checkpoint_cycle'], 'status': state['status']})
        return out
    criteria = json.loads((root / 'criteria.json').read_text())
    assessment = assess_blocks(blocks, history, criteria)
    if state['status'] == 'criteria_met':
        assert assessment['passed'] and state['consecutive_passes'] >= 2
        assert assessment == json.loads((case / 'assessment.json').read_text())
    arrays = [read_arrays(p) for p in blocks]
    pool = pooled(arrays)
    metrics = observables(pool)
    for k, v in metrics.items():
        if np.ndim(v) == 0:
            summary[k] = float(v)
    ifed = pool['ifed_equal_block_mean']
    summary['mean_ion_energy_upper_powered_eV'] = float(np.sum(ifed[:, 0] * ifed[:, 1]))
    summary['mean_ion_energy_lower_grounded_eV'] = float(np.sum(ifed[:, 0] * ifed[:, 2]))
    summary['binned_jE_total_W_m2'] = float(np.trapezoid((pool['powere'] + pool['poweri']).mean(axis=1), X))
    summary['binned_jE_total_W_fictive_1cm2'] = summary['binned_jE_total_W_m2'] * 1e-4
    summary['measurement_cycles_inclusive'] = [json.loads((blocks[0] / 'block.json').read_text())['cycles_inclusive'][0], state['checkpoint_cycle']]
    summary['assessment'] = assessment
    summary['numerical_checks'] = [json.loads((p / 'validation.json').read_text()) for p in blocks]
    save_json(out / (key + '_summary.json'), summary)
    raw = out / 'aggregate_dat'; raw.mkdir(exist_ok=True)
    csv = out / 'csv'; csv.mkdir(exist_ok=True)
    for k, a in pool.items():
        suffix = '_xt' if k in XT or 'mean_of_blocks' in k else ''
        np.savetxt(raw / (key + '_' + k + suffix + '.dat'), a, fmt='%.9e')
        if suffix:
            np.savetxt(csv / (key + '_' + k + suffix + '.csv'), np.column_stack([X, a]), delimiter=',', fmt='%.9e',
                       header='position_m,' + ','.join(f'phase_{j:03d}' for j in range(200)), comments='')
        else:
            header = {'density': 'position_m,electron_density_m-3,ion_density_m-3',
                      'eepf_equal_block_mean': 'energy_eV,EEPF_eV-3per2',
                      'ifed_equal_block_mean': 'energy_eV,upper_powered_IFEDF_eV-1,lower_grounded_IFEDF_eV-1'}[k]
            np.savetxt(csv / (key + '_' + k + '.csv'), a, delimiter=',', fmt='%.9e', header=header, comments='')
    np.savetxt(csv / (key + '_phase_coordinates.csv'),
               np.column_stack([np.arange(200), (np.arange(200) * 20 + 10.5) / 4000]),
               delimiter=',', header='phase_bin,sample_mean_t_over_T', comments='', fmt='%.9e')
    plt.rcParams.update({'font.size': 10, 'figure.dpi': 145})
    start, end = summary['measurement_cycles_inclusive']
    title = f'Ar 20 mTorr | {state["voltage_peak_V"]} V peak | 13.56 MHz | 25 mm\nUpper powered / lower grounded; RF cycles {start}-{end} ({len(blocks)*20} measured)'
    figures = []
    with PdfPages(out / (key + '_all_plots.pdf')) as pdf:
        def finish(fig, name):
            fig.suptitle(title, fontsize=12)
            filename = key + '_' + name + '.png'
            fig.savefig(out / filename); pdf.savefig(fig); plt.close(fig)
            figures.append((name, filename))
        for name, fields in [('heating', ['powere', 'poweri', 'ioniz', 'meanee']),
                             ('fields_density', ['pot', 'efield', 'ne', 'ni']),
                             ('currents_ionenergy', ['je', 'ji', 'meanei'])]:
            fig, axs = plt.subplots(2, 2, figsize=(12, 8), layout='constrained')
            for ax, field in zip(axs.ravel(), fields):
                label, unit, scale, cmap = LABELS[field]
                a = pool[field] / scale
                lim = max(float(np.max(np.abs(a))), 1e-30)
                options = dict(vmin=-lim, vmax=lim) if cmap == 'RdBu_r' else {}
                im = ax.imshow(a, origin='lower', aspect='auto', extent=[0, 1, 0, 25], cmap=cmap, **options)
                ax.set(xlabel='RF phase t/T', ylabel='Position from lower electrode (mm)', title=label,
                       yticks=[0, 5, 10, 15, 20, 25], yticklabels=['0 GND', '5', '10', '15', '20', '25 RF'])
                fig.colorbar(im, ax=ax, label=unit, fraction=.046, pad=.03)
            for ax in axs.ravel()[len(fields):]:
                ax.set_visible(False)
            finish(fig, name)
        fig, axs = plt.subplots(1, 3, figsize=(14, 4.8), layout='constrained')
        axs[0].plot(X * 1000, pool['density'][:, 1], label='Electrons')
        axs[0].plot(X * 1000, pool['density'][:, 2], label='Ar+ ions')
        axs[0].set(xlabel='x (mm): 0 lower GND; 25 upper RF', ylabel='Density (m$^{-3}$)', title='Time-averaged density')
        eepf = pool['eepf_equal_block_mean']; mask = eepf[:, 1] > 0
        axs[1].semilogy(eepf[mask, 0], eepf[mask, 1], label='Equal-block mean EEPF')
        axs[1].axvline(summary['numerical_checks'][0]['cfl_energy_eV'], ls='--', color='gray', label='CFL energy')
        axs[1].set(xlabel='Energy (eV)', ylabel='EEPF (eV$^{-3/2}$)', title='Central 10% of gap')
        axs[2].plot(ifed[:, 0], ifed[:, 1], label='Upper powered')
        axs[2].plot(ifed[:, 0], ifed[:, 2], label='Lower grounded')
        axs[2].set(xlabel='Ion energy (eV)', ylabel='IFEDF (eV$^{-1}$)', title='Equal-block mean distributions')
        for ax in axs:
            ax.legend(fontsize=8); ax.grid(alpha=.2)
        finish(fig, 'distributions')
        fig, axs = plt.subplots(2, 2, figsize=(12, 8), layout='constrained')
        for ax in axs[0]:
            ax.plot(history[:, 0], history[:, 1], label='Electrons')
            ax.plot(history[:, 0], history[:, 2], label='Ar+ ions')
            ax.axvspan(start, end, color='green', alpha=.12, label='Final measurement')
            ax.set(xlabel='RF cycles since condition change', ylabel='Superparticles'); ax.legend(fontsize=8)
        axs[0, 1].set_xlim(max(0, end - 700), end + 5)
        for s, label in [('e', 'Electron'), ('i', 'Ion')]:
            axs[1, 0].plot([json.loads((p / 'block.json').read_text())['cycles_inclusive'][1] for p in blocks],
                           [a['power' + s].mean() for a in arrays], 'o-', label=label)
        axs[1, 0].set(xlabel='Block end cycle', ylabel='Block mean binned jE (W/m$^3$)'); axs[1, 0].legend()
        indicators = assessment['indicators']; keys = list(indicators)
        xx = np.arange(len(keys)); width = .36
        axs[1, 1].bar(xx - width/2, [indicators[k]['relative_uncertainty_indicator']*100 for k in keys], width, label='Uncertainty')
        axs[1, 1].bar(xx + width/2, [indicators[k]['first_last_half_relative_change']*100 for k in keys], width, label='Half-to-half change')
        for j, k in enumerate(keys):
            axs[1, 1].plot([j-.45, j+.45], [indicators[k]['tolerance']*100]*2, color='black')
        axs[1, 1].set_xticks(xx, [k.replace('_', '\n') for k in keys], fontsize=6)
        axs[1, 1].set_ylabel('Relative indicator (%)'); axs[1, 1].legend(fontsize=8)
        finish(fig, 'convergence')
    rows = '\n'.join(f'| {k} | {v:.7g} |' for k, v in summary.items() if isinstance(v, (int, float)))
    images = '\n\n'.join(f'![{name}]({file})' for name, file in figures)
    report = f'''# {key}

상태: **{state['status']}**. 새 조건 적용 후 {state['checkpoint_cycle']}주기까지 계산했습니다.
최종 평균 구간은 **{start}–{end}주기, 총 {len(blocks)*20}주기**입니다. 이전 과도구간은 평균에 포함하지 않았습니다.

압력 **20 mTorr**, 전압 **{state['voltage_peak_V']} V peak**, Ar 350 K, 13.56 MHz, 간격 25 mm.
그림 아래쪽 x=0 mm는 접지, 위쪽 x=25 mm는 전압 인가 전극입니다.

| 항목 | 값 |
|---|---:|
{rows}

## 해석과 재사용

- 밀도·평균 전력·밀도 분포 3%, 40×40 heating 맵 5%의 불확실성 지표와 전후반 변화 기준을 사용합니다.
- 최근 600주기의 200주기 평균 세 개의 범위가 1% 미만이고 선형 변화가 2% 미만이어야 합니다. 최종 판정은 두 번 연속 통과해야 합니다.
- 이는 고정된 기존 격자·입자 가중치에서의 탐색적 통계 기준이며, 물리 모델 오차나 모든 픽셀·분포 꼬리의 오차를 보장하지 않습니다.
- Heating은 기존 코드와 같은 위상 평균 전도전류와 전기장의 곱입니다. 총 단자 VI 전력이나 순간 jE의 평균과 구분해야 합니다.
- EEPF와 IFEDF는 동일 길이 측정 블록의 정규화된 분포를 평균했습니다. 원래 입자 사건별 히스토그램을 합친 분포는 아닙니다.
- 전력 W 값에 사용한 면적은 원본 코드의 가상 면적 1 cm²입니다. 실제 장비의 전체 인가 전력으로 해석하지 마세요.
- 원본 DAT, CSV, 조건·소스·블록별 검사값과 재시작 파일을 함께 보관합니다.

{images}
'''
    (out / 'FINAL_REPORT.md').write_text(report)
    for name in ['criteria.json', 'config.json', 'source-eduPIC.cc', 'LICENSE']:
        shutil.copyfile(root / name, out / (key + '_' + name))
    for name in ['status.json', 'assessment.json', 'assessments.jsonl', 'boundary_verification.log']:
        if (case / name).exists():
            shutil.copyfile(case / name, out / (key + '_' + name))
    for script in root.glob('*.py'):
        shutil.copyfile(script, out / (key + '_' + script.name))
    files = [(p, key + '/' + str(p.relative_to(out))) for p in out.rglob('*') if p.is_file() and p.suffix != '.zip']
    archive(out / (key + '_summary.zip'), files)
    (case / 'finalized.json').write_text(json.dumps({'checkpoint_cycle': end, 'status': state['status']}) + '\n')
    return out


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('root', type=Path); p.add_argument('--voltage', type=int, nargs='+', default=[100, 250, 300])
    args = p.parse_args()
    for v in args.voltage:
        case = args.root / f'2026-11-19_Ar_20mTorr_{v}V_13.56MHz_25mm_topRF'
        print(summarize_case(args.root, case))
