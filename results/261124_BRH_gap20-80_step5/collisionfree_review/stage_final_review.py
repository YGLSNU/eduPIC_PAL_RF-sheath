#!/usr/bin/env python3
"""Attach the read-only review after all approved BRH cases actually stop.

Does not publish, modify a solver/configuration, or stop any process. Use the
repository's publish_run.py after this script's full report audit succeeds.
"""
from pathlib import Path
import argparse
import json
import shutil
import subprocess
import sys

from review_collisionfree import review, sha, put

TERMINAL = {'criteria_met', 'measurement_limit_reached', 'total_cycle_limit_reached', 'extinguished'}


def check(root, export):
    cfg = json.loads((root / 'config.json').read_text())
    if cfg['gaps_mm'] != list(range(20, 81, 5)):
        raise ValueError('This helper is scoped only to the approved 20-80mm BRH scan')
    states = []
    for gap in cfg['gaps_mm']:
        directory = Path(cfg['case_sources'].get(str(gap), {}).get('path', root / f'{gap}mm'))
        state = json.loads((directory / 'status.json').read_text())
        if state['status'] not in TERMINAL:
            raise ValueError(f'Not ready: {gap}mm is {state["status"]}; no final report changes made')
        states.append(state)
    # The existing publisher must finish its final upload before the supplement
    # is attached, so a subsequent periodic export cannot overwrite it.
    p = root / 'publisher.json'
    if p.exists():
        pid = json.loads(p.read_text())['pid']
        command = Path(f'/proc/{pid}/cmdline')
        if command.exists() and b'scripts/brh_scan/watch_publish.py' in command.read_bytes():
            raise ValueError('Existing BRH publisher is still finishing its final snapshot; recheck after it exits')
    metadata = json.loads((export / 'run.json').read_text())
    cases = {row['gap_mm']: row for row in metadata['cases']}
    for state in states:
        row = cases[state['gap_mm']]
        if row['status'] != state['status'] or row['measurement_rf'] != state.get('measured_RF', 0):
            raise ValueError(f'Export is stale for {state["gap_mm"]}mm; regenerate the original export first')
    return metadata


def stage(root, export, output, repo):
    metadata = check(root, export)
    review(root, output)
    provenance = json.loads((output / 'analysis_provenance.json').read_text())
    if any(s['RF_last'] != next(c['total_rf'] for c in metadata['cases'] if c['gap_mm'] == s['gap_mm']) for s in provenance['inputs']):
        raise ValueError('Supplement RF windows differ from the final export')
    dest = export / 'collisionfree_review'
    dest.mkdir(exist_ok=True)
    files = ['README.md', 'collisionfree_gap_summary.csv', 'analysis_provenance.json',
             'collisionfree_gap_review.png', 'review_collisionfree.py']
    files += [p.name for p in sorted(output.glob('*mm_collisionfree_returns.csv.gz'))]
    for name in files:
        shutil.copy2(output / name, dest / name)
    if Path(__file__).resolve() != (dest / 'stage_final_review.py').resolve():
        shutil.copy2(__file__, dest / 'stage_final_review.py')
    sys.path.insert(0, str(repo / 'scripts/results'))
    from catalog import validate, refresh_files, render_report
    from audit_coverage import audit
    section_id = 'collisionfree_1T_review'
    metadata['sections'] = [s for s in metadata['sections'] if s['id'] != section_id]
    maxima = ', '.join(map(str, provenance['max_observed_run_count_gaps_among_terminal_measurements_mm']))
    text = f'전체 승인 gap 종료 후 원자료 재검토. 무충돌 약1RF 왕복이 관측상 연속2회 이상인 구간 수 최대는 {maxima} mm입니다. 이 관측 수와 전체 전자 순전력·선택된 왕복의 signed 일을 구분하며 BRH 가열 peak는 미확정입니다. [정의·표·원자료·한계](collisionfree_review/README.md).'
    metadata['sections'].append({'id': section_id, 'title': '무충돌 연속 왕복과 순가열', 'data_status': 'available',
                                 'text': text, 'images': [{'path': 'collisionfree_review/collisionfree_gap_review.png', 'caption': text}]})
    metadata['downloads'] = [d for d in metadata['downloads'] if not d['path'].startswith('collisionfree_review/')]
    metadata['downloads'] += [{'label': '무충돌 보조 분석 '+name, 'path': 'collisionfree_review/'+name} for name in files]
    marker = ' 최종 무충돌 보조 분석:'
    prior = metadata.get('supplemental_analysis', {}).get('collisionfree', {}).get('prior_recovery_summary', metadata['summary'].split(marker)[0])
    metadata['supplemental_analysis'] = {'collisionfree': {'provenance': 'collisionfree_review/analysis_provenance.json',
                                                         'analysis_SHA256': provenance['analysis_SHA256'],
                                                         'heating_peak_established': False,
                                                         'prior_recovery_summary': prior}}
    metadata['report_updated'] = provenance['generated_Asia_Seoul']
    metadata['summary'] = (
        '승인된 20–80 mm(5 mm 간격) 스캔의 모든 조건이 종료되었습니다. '
        '20·25 mm는 전자 소멸, 30–80 mm는 각각 측정 1,000 RF 상한·전체 수렴 기준 미충족입니다. '
        '80 mm의 최종 저장점은 누적 3,200 RF, 측정 RF 2201–3200입니다. '
        '종료된 조건을 재계산하지 않고 미완료 체크포인트에서 이어갔으며 기존 물리 소스·수렴 기준·측정 상한을 유지했습니다. '
        '100·120 mm는 중단 상태를 유지하고, 승인되지 않은 47.5·52.5 mm는 실행하지 않았습니다. '
        '복구 이전 개별 native 블록이 없어 복원한 누적 평균·원시 counts와 재개 후 블록의 변동 지표를 구분합니다. '
        '기본 1T 후보 표는 충돌을 포함하므로 별도 무충돌 연속 왕복 분석과 대상을 구분합니다.'
        + marker + text.split(' [정의')[0]
    )
    validate(metadata)
    refresh_files(export, metadata)
    markdown = render_report(metadata)
    assert not audit(metadata, markdown)['failures']
    put(export / 'run.json', metadata)
    (export / 'README.md').write_text(markdown)
    refresh_files(export, metadata)
    subprocess.run([sys.executable, str(repo / 'scripts/results/verify_reports.py'), '--export', str(export)], check=True)
    put(root / 'final_supplement_staged.json', {'export': str(export), 'review': str(dest),
                                              'provenance_SHA256': sha(dest / 'analysis_provenance.json'),
                                              'published': False, 'note': 'Publish with original publish_run.py, then verify final80mm restart and supplement downloads before notifying user.'})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('export', type=Path)
    parser.add_argument('--review-output', type=Path, default=Path(__file__).parent / 'final_review')
    parser.add_argument('--repo', type=Path, default=Path('/workspace/work/brh-code'))
    parser.add_argument('--check-only', action='store_true')
    args = parser.parse_args()
    try:
        if args.check_only:
            check(args.root.resolve(), args.export.resolve())
            print('All approved cases terminal and final base export ready')
        else:
            stage(args.root.resolve(), args.export.resolve(), args.review_output.resolve(), args.repo.resolve())
    except ValueError as exc:
        print(str(exc))
        raise SystemExit(2)
