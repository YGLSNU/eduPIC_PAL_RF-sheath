"""Publish recoverable snapshots and completed results to the authorized GitHub repository."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import argparse
import fcntl
import json
import os
import shutil
import subprocess
import time
import numpy as np
os.environ.setdefault('MPLCONFIGDIR', '/workspace/edupic-results/.mpl-cache')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from analyze_scan import archive, summarize_case
from stopping import save_json, sha, checkpoint

UPLOAD = Path('/workspace/edupic-results-upload')
BRANCH = 'results/2026-11-19-20mTorr-top-powered'
REPO = 'https://github.com/YGLSNU/eduPIC_PAL_RF-sheath'
FINAL = ['criteria_met', 'extinguished', 'measurement_limit_reached', 'total_cycle_limit_reached', 'paused_at_checkpoint', 'paused_error']


def publish(root):
    with (root / 'publish.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return _publish_locked(root)


def _publish_locked(root):
    assert subprocess.check_output(['git', 'branch', '--show-current'], cwd=UPLOAD, text=True).strip() == BRANCH
    dest = UPLOAD / 'results' / root.name; dest.mkdir(parents=True, exist_ok=True)
    for name in ['config.json', 'criteria.json', 'source-eduPIC.cc', 'LICENSE']:
        shutil.copyfile(root / name, dest / (root.name + '_' + name))
    for p in root.glob('*.py'):
        shutil.copyfile(p, dest / (root.name + '_' + p.name))
    seed = dest / (root.name + '_initial_state.zip')
    if not seed.exists():
        archive(seed, [(root / 'reflected_initial_cycle0.bin', 'picdata.bin'),
                       (root / 'config.json', 'config.json'), (root / 'source-eduPIC.cc', 'source-eduPIC.cc'),
                       (root / 'LICENSE', 'LICENSE')])
    rows, manifest, summaries = [], [], []
    fig, axs = plt.subplots(1, 3, figsize=(15, 4.4), layout='constrained')
    statuses = []
    for ax, voltage in zip(axs, [100, 250, 300]):
        case = root / f'2026-11-19_Ar_20mTorr_{voltage}V_13.56MHz_25mm_topRF'
        key = case.name; target = dest / key; target.mkdir(exist_ok=True)
        state = json.loads((case / 'status.json').read_text()); statuses.append(state)
        for name in ['status.json', 'history.dat', 'assessment.json', 'assessments.jsonl', 'boundary_verification.log', 'error.log']:
            if (case / name).exists():
                shutil.copyfile(case / name, target / (key + '_' + name))
        saved = state['checkpoint_cycle']
        restart = target / (key + '_restart.zip')
        latest = case / 'latest_checkpoint.bin' if (case / 'latest_checkpoint.bin').exists() else case / 'input_cycle0.bin'
        # Read a stable completed block, rather than a file the solver is writing.
        if state.get('latest_block'):
            latest = case / state['latest_block'] / 'picdata.bin'
        snapshot = checkpoint(latest)
        assert snapshot['cycle'] == saved
        resume = target / (key + '_RESUME.md')
        resume.write_text(f'''# {key} 재시작

저장된 RF 주기: {saved}. 압력 20 mTorr, 전압 {voltage} V peak, 상부 RF / 하부 접지.

ZIP을 별도 폴더에 풀고 아래 명령으로 동일 조건에서 20주기를 추가 측정할 수 있습니다.

```sh
g++ -std=c++11 -O3 -DEDUPIC_VOLTAGE_V={voltage}.0 source-eduPIC.cc -o edupic
./edupic 20 m
```

`picdata.bin`을 유지해야 이어서 계산됩니다. `0` 인수는 새 초기화를 뜻하므로 재시작에 사용하지 않습니다.
새 진단 출력은 덮어쓰므로 기존 DAT/PNG/CSV는 별도 폴더에 보관하세요.
입자 위치·속도·시간은 보존되지만 원본 코드는 난수 상태를 저장하지 않아 개별 궤적의 비트 단위 재현은 보장하지 않습니다.
자동 수렴 판정을 그대로 이어가려면 측정 블록과 전체 컨트롤러 작업 폴더도 필요합니다. 이 ZIP만으로도 물리 상태의 연속 계산은 가능합니다.
''')
        pre_extinction = None
        if state['status'] == 'extinguished':
            resume.write_text(resume.read_text() + '\n**이 최종 체크포인트는 입자가 없는 상태입니다. 플라즈마 조건을 바꿔 연구하려면 소멸 전 체크포인트 또는 초기 상태 ZIP을 사용하세요.**\n')
            candidates = [(p.parent, json.loads(p.read_text())) for p in (case / 'warmup').glob('*/block.json')]
            candidates = [(p, m) for p, m in candidates if m['output_checkpoint']['electrons'] > 0]
            if candidates:
                before, m = max(candidates, key=lambda pair: pair[1]['output_checkpoint']['cycle'])
                cp = m['output_checkpoint']
                note = target / (key + '_BEFORE_EXTINCTION.md')
                note.write_text(f'''# 소멸 전 상태: {key}

RF {cp['cycle']}주기, 전자 {cp['electrons']}개·이온 {cp['ions']}개의 계산 입자입니다.
이는 과도구간의 입자 상태이며 수렴된 정상 방전으로 해석하지 않습니다.

```sh
g++ -std=c++11 -O3 -DEDUPIC_VOLTAGE_V={voltage}.0 source-eduPIC.cc -o edupic
./edupic 20 m
```

압력을 바꾸려면 빌드 명령에 `-DEDUPIC_PRESSURE_MTORR=원하는값`을 지정하고 새 조건에서 다시 안정화해야 합니다.
빈 최종 상태에 전압만 변경해서는 전자 충돌 이온화가 다시 시작되지 않으므로, 이 소멸 전 상태 또는 더 조밀한 초기 상태를 사용하세요.
''')
                pre_extinction = target / (key + '_before_extinction_restart.zip')
                archive(pre_extinction, [(before / 'picdata.bin', 'picdata.bin'),
                                        (root / 'source-eduPIC.cc', 'source-eduPIC.cc'),
                                        (root / 'config.json', 'config.json'), (root / 'LICENSE', 'LICENSE'),
                                        (note, 'RESUME.md')])
        entries = [(latest, 'picdata.bin'), (root / 'source-eduPIC.cc', 'source-eduPIC.cc'),
                   (root / 'config.json', 'config.json'), (root / 'criteria.json', 'criteria.json'),
                   (root / 'LICENSE', 'LICENSE'), (resume, 'RESUME.md')]
        if (case / 'history.dat').exists():
            entries.append((case / 'history.dat', 'history_before_restart.dat'))
        archive(restart, entries)
        status_label = {'running': '계산 중', 'criteria_met': '수렴 기준 만족·종료', 'extinguished': '입자 소멸·종료',
                        'measurement_limit_reached': '측정 상한 도달·기준 미달', 'paused_error': '오류로 중단',
                        'paused_at_checkpoint': '체크포인트에서 중단', 'total_cycle_limit_reached': '주기 상한 도달·기준 미달'}[state['status']]
        ready = (case / 'finalized.json').exists()
        if state['status'] in FINAL and state['status'] != 'paused_error' and saved > 0:
            signature = json.loads((case / 'finalized.json').read_text()) if ready else {}
            if signature != {'checkpoint_cycle': saved, 'status': state['status']}:
                summarize_case(root, case)
            for p in (case / 'final_output').rglob('*'):
                if p.is_file():
                    q = target / p.relative_to(case / 'final_output'); q.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(p, q)
            if (target / (key + '_summary.json')).exists():
                summaries.append(json.loads((target / (key + '_summary.json')).read_text()))
            epoch = state['measurement_epoch']
            for block in sorted((case / 'measurements' / f'epoch{epoch:03d}').glob('*/block.json')):
                zpath = target / (key + '_' + block.parent.name + '.zip')
                if not zpath.exists():
                    archive(zpath, [(p, p.name) for p in block.parent.iterdir() if p.is_file()])
        base = f'{REPO}/raw/refs/heads/{BRANCH}/results/{root.name}/{key}/'
        link = f'[결과·그림]({key}/FINAL_REPORT.md)' if (target / 'FINAL_REPORT.md').exists() else f'[저장 상태]({key}/)'
        rows.append(f'| {voltage} V peak | {status_label} | {saved:,} | {state.get("completed_measurement_cycles",0)} | {link} · [재시작 ZIP]({base}{restart.name}) |')
        if pre_extinction:
            rows[-1] = rows[-1][:-2] + f' · [소멸 전 상태]({base}{pre_extinction.name}) |'
        manifest.append(dict(voltage_peak_V=voltage, status=state['status'], checkpoint=snapshot,
                             restart_file=str(restart.relative_to(dest)), restart_sha256=sha(restart)))
        if (case / 'history.dat').exists():
            hist = np.loadtxt(case / 'history.dat', ndmin=2)
            hist = hist[hist[:, 0] <= saved]
            ax.plot(hist[:, 0], hist[:, 1], label='Electrons')
            ax.plot(hist[:, 0], hist[:, 2], label='Ar+ ions')
            if state.get('measurement_start_cycle'):
                ax.axvspan(state['measurement_start_cycle'], saved, color='green', alpha=.12)
        ax.set(title=f'{voltage} V peak | saved cycle {saved}', xlabel='RF cycles after condition change', ylabel='Superparticles')
        ax.grid(alpha=.2)
        if ax.lines:
            ax.legend(fontsize=8)
    fig.suptitle('Ar 20 mTorr | 13.56 MHz | 25 mm | upper RF / lower ground\nUploaded checkpoint history; not a live process monitor')
    fig.savefig(dest / (root.name + '_progress.png'), dpi=140); plt.close(fig)
    updated = datetime.now(ZoneInfo('Asia/Seoul')).isoformat()
    save_json(dest / (root.name + '_manifest.json'), {'updated_at_Asia_Seoul': updated, 'cases': manifest})
    if summaries:
        save_json(dest / (root.name + '_comparison.json'), summaries)
        columns = ['voltage_peak_V','pressure_mTorr','total_cycles','measurement_cycles','center_density_e','center_density_i',
                   'mean_power_e','mean_power_i','mean_ion_energy_upper_powered_eV','mean_ion_energy_lower_grounded_eV','binned_jE_total_W_m2']
        import csv
        with (dest / (root.name + '_comparison.csv')).open('w') as f:
            writer = csv.DictWriter(f, fieldnames=['status', *columns], extrasaction='ignore'); writer.writeheader(); writer.writerows(summaries)
    readme = f'''# 2026-11-19: Ar 20 mTorr, 상부 RF 전극 전압 비교

공통 조건: **20 mTorr**, Ar 350 K, 13.56 MHz, 전극 간격 25 mm.
상부 x=25 mm에 정현파 전압을 인가하고 하부 x=0 mm를 접지했습니다. 표의 전압은 RMS가 아닌 최대 진폭입니다.

마지막 업로드: {updated}. 이 페이지는 저장된 상태이며 실시간 실행 상태가 아닙니다.

| 전압 | 상태 | 새 조건 누적 RF 주기 | 현재 측정 주기 | 결과와 다운로드 |
|---|---|---:|---:|---|
{chr(10).join(rows)}

![입자 수 변화]({root.name}_progress.png)

## 수렴·중단 기준

최근 600주기 입자 수를 200주기씩 나눈 세 평균의 범위가 1% 미만이고 선형 변화가 2% 미만이면 측정을 시작합니다.
20주기 단위로 측정하고 최소 100주기부터 검사하며, 다음 기준을 두 번 연속 만족하면 종료합니다.

- 전자·이온 평균/중심 밀도, 평균 전력, 밀도 공간분포: 불확실성 지표와 전후반 변화 각각 3% 이내.
- 전자·이온 heating: 40×40으로 평균한 맵의 전체 L2 기준 5% 이내.
- 최근 600주기 입자 수 안정성 기준도 계속 만족해야 합니다.

기존 실행과 같은 Student-t 블록 통계와 양의 시간상관 보정을 사용하며, 충분한 블록이 쌓이면 40주기 재집계도 확인합니다.
이 기준은 탐색적 통계 안정성 기준으로 전체 물리·수치 오차를 보장하지 않습니다. 상한이나 오류로 멈춘 경우 수렴으로 표시하지 않습니다.

## 계산과 재현

기존 수렴 입자 분포를 x→L−x, vx→−vx로 반전한 뒤 새 조건의 초기값으로 사용했습니다.
새 조건 적용 시 RF 주기 번호는 0부터 다시 세었고, 모든 초기 과도구간은 최종 평균에서 제외합니다.
압력은 입력·파일명·보고서에서 mTorr로 표시하며, 중성기체 밀도 계산에서만 SI로 변환합니다.
원본 격자 400점, RF 주기당 4000 시간 간격, 입자 가중치 70000 및 충돌·표면 물리는 유지했습니다.
모든 조건은 클라우드 작업 환경에서 계산되며 GitHub에는 코드·로그·결과·재시작 파일을 보관합니다.

원본 코드의 위상 평균 jE 진단을 유지했습니다. 측정 VI 입력, self-bias 회로, 형상 비대칭 등은 이번 변경에 포함하지 않습니다.
'''
    (dest / 'README.md').write_text(readme)
    index = UPLOAD / 'results/README.md'
    text = index.read_text() if index.exists() else '# Simulation results\n'
    lines = [line for line in text.splitlines() if root.name not in line]
    lines.extend(['', f'- [2026-11-19: 20 mTorr, 상부 RF, 100·250·300 V 비교]({root.name}/README.md)'])
    index.write_text('\n'.join(lines) + '\n')
    subprocess.run(['git', 'add', '--', 'results/' + root.name, 'results/README.md'], cwd=UPLOAD, check=True)
    if subprocess.run(['git', 'diff', '--cached', '--quiet'], cwd=UPLOAD).returncode:
        label = ', '.join(f'{s["voltage_peak_V"]}V:{s["checkpoint_cycle"]}' for s in statuses)
        subprocess.run(['git', 'commit', '-m', 'Save 20 mTorr voltage scan checkpoints (' + label + ')'], cwd=UPLOAD, check=True)
    subprocess.run(['git', 'push', 'origin', 'HEAD:refs/heads/' + BRANCH], cwd=UPLOAD, check=True, timeout=180)
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPLOAD, text=True).strip()
    save_json(root / 'last_github_backup.json', {'commit': head, 'at_Asia_Seoul': updated, 'cases': manifest})
    if (root / 'publish_error.json').exists():
        (root / 'publish_error.json').unlink()
    print('PUBLISHED', head, flush=True)
    return statuses


def main():
    p = argparse.ArgumentParser(); p.add_argument('root', type=Path); p.add_argument('--watch', action='store_true')
    args = p.parse_args(); last = {}
    while True:
        states = [json.loads(p.read_text()) for p in sorted(args.root.glob('2026*/status.json'))]
        signature = {s['voltage_peak_V']: (s['checkpoint_cycle'], s['status']) for s in states}
        changed = not last or any(v not in last or status != last[v][1] or cycle >= last[v][0] + 100 for v, (cycle, status) in signature.items())
        if changed or not args.watch:
            try:
                publish(args.root); last = signature
            except Exception as exc:
                save_json(args.root / 'publish_error.json', {'error': str(exc), 'at': datetime.now().isoformat()})
                print('PUBLISH_ERROR', repr(exc), flush=True)
                if not args.watch:
                    raise
        if not args.watch or (len(states) == 3 and all(s['status'] in FINAL for s in states) and last == signature):
            return
        time.sleep(30)


if __name__ == '__main__':
    main()
