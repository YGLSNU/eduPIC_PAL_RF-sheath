"""Add side-by-side comparisons after the automatic publisher has finished."""
from pathlib import Path
import argparse
import json
import os
import shutil
import numpy as np
os.environ.setdefault('MPLCONFIGDIR', '/workspace/edupic-results/.mpl-cache')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def compare(root, dest):
    cases, rows = [], []
    for voltage in [100, 250, 300]:
        case = root / f'2026-11-19_Ar_20mTorr_{voltage}V_13.56MHz_25mm_topRF'
        state = json.loads((case / 'status.json').read_text())
        assert state['status'] != 'running'
        key = case.name
        path = case / 'final_output' / (key + '_summary.json')
        summary = json.loads(path.read_text()) if path.exists() else state
        raw = case / 'final_output/aggregate_dat'
        arrays = {}
        for field, suffix in [('density', ''), ('powere', '_xt'), ('poweri', '_xt'), ('ifed_equal_block_mean', '')]:
            p = raw / (key + '_' + field + suffix + '.dat')
            if p.exists():
                arrays[field] = np.loadtxt(p)
        cases.append((voltage, state['status'], summary, arrays))
        def fmt(name):
            return f'{summary[name]:.4g}' if name in summary else '—'
        label = {'criteria_met': '기준 만족', 'extinguished': '입자 소멸', 'measurement_limit_reached': '기준 미달·측정 상한',
                 'total_cycle_limit_reached': '기준 미달·주기 상한', 'paused_error': '오류 중단', 'paused_at_checkpoint': '중단'}[state['status']]
        rows.append(f'| {voltage} | {label} | {state["checkpoint_cycle"]} | {state.get("completed_measurement_cycles",0)} | '
                    f'{fmt("center_density_e")} | {fmt("center_density_i")} | {fmt("mean_power_e")} | {fmt("mean_power_i")} |')
    out = root / 'comparison_output'; out.mkdir(exist_ok=True)
    if all(status == 'extinguished' for _, status, _, _ in cases):
        fig, axs = plt.subplots(1, 2, figsize=(12, 5), layout='constrained')
        cutoff = 0
        extinction_rows = []
        extinction_values = []
        for voltage, status, summary, arrays in cases:
            case = root / f'2026-11-19_Ar_20mTorr_{voltage}V_13.56MHz_25mm_topRF'
            hist = np.loadtxt(case / 'history.dat', ndmin=2)
            for ax, col in zip(axs, [1, 2]):
                ax.plot(hist[:, 0], hist[:, col] * 70000 / (1e-4 * .025), label=f'{voltage} V peak')
                ax.set_yscale('symlog', linthresh=70000 / (1e-4 * .025))
                ax.grid(alpha=.2); ax.legend()
            e_zero = summary.get('first_zero_electron_cycle')
            i_zero = summary.get('first_zero_ion_cycle')
            cutoff = max(cutoff, e_zero or hist[-1, 0])
            extinction_rows.append(f'| {voltage} | {e_zero} | {i_zero} | {summary["total_cycles"]} | {summary["solver_wall_seconds"]/60:.2f} |')
            extinction_values.append([voltage, 20, e_zero, i_zero, summary['total_cycles'], summary['solver_wall_seconds']])
        axs[0].set(title='Volume-averaged electron density', xlabel='RF cycles after condition change', ylabel='Density (m$^{-3}$)', xlim=(0, cutoff + 80))
        axs[1].set(title='Volume-averaged ion density', xlabel='RF cycles after condition change', ylabel='Density (m$^{-3}$)')
        fig.suptitle('Ar 20 mTorr | upper RF / lower ground | no sustained plasma in these production runs\nVolume averages calculated from particle counts and the original particle weight')
        name = root.name + '_comparison_decay.png'
        fig.savefig(out / name, dpi=150); plt.close(fig); shutil.copyfile(out / name, dest / name)
        table = root.name + '_extinction_summary.csv'
        np.savetxt(out / table, extinction_values, delimiter=',', fmt='%.9g', comments='',
                   header='voltage_peak_V,pressure_mTorr,first_zero_electron_RF_cycle,first_zero_ion_RF_cycle,last_saved_RF_cycle,solver_wall_seconds')
        shutil.copyfile(out / table, dest / table)
        section = f'''\n## 최종 조건별 비교

세 조건 모두 정상 방전의 통계 수렴 기준에 도달하기 전에 전자 입자가 소멸했습니다.
이후 남은 이온이 모두 빠져나간 빈 상태까지 계산하고 종료했습니다.
따라서 정상상태 heating·EEPF·IFEDF 측정값은 없습니다. 최종 빈 상태의 밀도와 입자 jE는 0입니다.

| 전압 V peak | 전자 수가 0이 된 주기 | 이온 수가 0이 된 주기 | 마지막 저장 주기 | 조건별 계산 시간 분 |
|---:|---:|---:|---:|---:|
{chr(10).join(extinction_rows)}

[비교표 CSV 다운로드]({table})

아래 그림의 밀도는 입자 수 × 입자 가중치 ÷ 계산 영역 부피로 구한 공간평균 밀도입니다.
입자 수가 적은 구간에서는 한 계산 입자 단위의 계단 변화가 나타납니다.

![조건별 방전 감쇠 비교]({name})
'''
        readme = dest / 'README.md'
        readme.write_text(readme.read_text().split('\n## 최종 조건별 비교')[0] + section)
        print(readme)
        return
    plt.rcParams.update({'font.size': 10, 'figure.dpi': 150})
    fig, axs = plt.subplots(2, 2, figsize=(12, 8), layout='constrained')
    colors = ['#2878b5', '#dd8b23', '#a83942']
    for (v, status, summary, a), color in zip(cases, colors):
        if 'density' not in a:
            continue
        label = f'{v} V' + (' (criteria not met)' if status != 'criteria_met' else '')
        density = a['density']; x = density[:, 0] * 1000
        axs[0, 0].plot(x, density[:, 1], color=color, label=label)
        axs[0, 1].plot(x, density[:, 2], color=color, label=label)
        axs[1, 0].plot(x, a['powere'].mean(axis=1), color=color, label=label)
        ifed = a['ifed_equal_block_mean']
        axs[1, 1].plot(ifed[:, 0], ifed[:, 1], color=color, label=label+' upper RF')
        axs[1, 1].plot(ifed[:, 0], ifed[:, 2], color=color, ls='--', label=label+' lower GND')
    for ax, title, ylabel in zip(axs.ravel(), ['Electron density', 'Ion density', 'Phase-averaged electron energy transfer', 'Ion flux energy distributions'],
                                 ['Density (m$^{-3}$)', 'Density (m$^{-3}$)', 'Binned j_e E (W/m$^3$)', 'IFEDF (eV$^{-1}$)']):
        ax.set(title=title, ylabel=ylabel, xlabel='Position (mm): 0 lower GND; 25 upper RF')
        if ax.lines:
            ax.legend(fontsize=8)
        ax.grid(alpha=.2)
    axs[1, 1].set_xlabel('Ion energy (eV)')
    fig.suptitle('Ar 20 mTorr | 13.56 MHz | 25 mm | upper electrode driven\nEach curve uses its own saved measurement window')
    profile_name = root.name + '_comparison_profiles.png'
    fig.savefig(out / profile_name); plt.close(fig)
    available = [a['powere'] for _, _, _, a in cases if 'powere' in a]
    heating_name = root.name + '_comparison_heating.png'
    if available:
        lim = max(float(np.max(np.abs(a))) for a in available)
        fig, axs = plt.subplots(1, 3, figsize=(14, 5), layout='constrained')
        im = None
        for ax, (v, status, summary, a) in zip(axs, cases):
            ax.set(title=f'{v} V peak\n{status}', xlabel='RF phase t/T', ylabel='Position (mm)',
                   yticks=[0, 5, 10, 15, 20, 25], yticklabels=['0 GND', '5', '10', '15', '20', '25 RF'])
            if 'powere' in a:
                im = ax.imshow(a['powere'], origin='lower', aspect='auto', extent=[0, 1, 0, 25],
                               cmap='RdBu_r', vmin=-lim, vmax=lim)
            else:
                ax.text(.5, .5, 'No steady measurement', ha='center', transform=ax.transAxes)
        fig.colorbar(im, ax=axs, label='Electron energy transfer: binned j_e E (W/m$^3$)', fraction=.03, pad=.02)
        fig.suptitle('20 mTorr voltage comparison | common color scale | upper RF / lower ground')
        fig.savefig(out / heating_name); plt.close(fig)
    for p in out.iterdir():
        shutil.copyfile(p, dest / p.name)
    section = f'''\n## 최종 조건별 비교

중앙 밀도는 전극 간격 중앙 10% 영역의 평균이며, 전력밀도는 기존 코드의 위상 평균 jE 정의를 사용합니다.
각 조건의 최종 측정 구간은 조건별 보고서에 기록했습니다.

| 전압 V peak | 상태 | 총 RF 주기 | 측정 주기 | 중앙 전자 밀도 m⁻³ | 중앙 이온 밀도 m⁻³ | 전자 전력밀도 W/m³ | 이온 전력밀도 W/m³ |
|---:|---|---:|---:|---:|---:|---:|---:|
{chr(10).join(rows)}

![밀도·heating·이온 에너지 비교]({profile_name})
'''
    if available:
        section += f'\n![공통 색상 범위의 전자 heating 비교]({heating_name})\n'
    readme = dest / 'README.md'
    readme.write_text(readme.read_text().split('\n## 최종 조건별 비교')[0] + section)
    print(readme)


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('root', type=Path); p.add_argument('destination', type=Path)
    args = p.parse_args(); compare(args.root, args.destination)
