"""Copy final plots, data and restart bundle into the already authorized result branch."""
from pathlib import Path
import json
import shutil
import subprocess
from adaptive_common import ROOT, KEY

def finalize(dest):
    state=json.loads((ROOT/'status.json').read_text())
    assert state['status'] in ['criteria_met','measurement_limit_reached','paused_at_checkpoint']
    subprocess.run(['python',str(ROOT/'analyze_adaptive.py')],cwd=ROOT,check=True)
    out=ROOT/'final_output'
    for source in out.rglob('*'):
        if source.is_file():
            target=dest/source.relative_to(out)
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(source,target)
    shutil.copyfile(ROOT/'analyze_adaptive.py',dest/(KEY+'_analyze_adaptive.py'))
    shutil.copyfile(ROOT/'finalize_results.py',dest/(KEY+'_finalize_results.py'))
    last=state['checkpoint_cycle']
    base='https://github.com/YGLSNU/eduPIC_PAL_RF-sheath/raw/refs/heads/results/2026-11-17-default-incomplete/results/'+KEY+'/'
    intro=f'''# 추가 측정 결과: {state['completed_measurement_cycles']} RF주기

상태: **{'정한 통계 기준을 만족하여 자동 종료' if state['status']=='criteria_met' else state['status']}**.
1,705주기 상태에서 이어서 1,706–{last:,}주기를 새로 측정했습니다.

- [결과 요약 ZIP 다운로드]({base}{KEY}_summary.zip): 보고서, 그림, PDF, CSV, 합산 DAT.
- [마지막 {last:,}주기 재시작 ZIP 다운로드]({base}{KEY}_restart_cycle{last}.zip): 체크포인트, 원본 소스·조건, 재시작 설명.
- [전체 그림 PDF]({KEY}_all_plots.pdf) / [CSV](csv/) / [합산 DAT](aggregate_dat/).
- [구간별 원본 결과·체크포인트](README.md#구간별-원본과-재시작-파일).

## Heating·이온화·전자 에너지

![전자·이온 heating, 이온화율, 전자 에너지]({KEY}_heating.png)

## 전위·전기장·전자와 이온 밀도

![전위, 전기장, 밀도]({KEY}_fields_density.png)

## 밀도와 에너지 분포

![밀도와 에너지 분포]({KEY}_distributions.png)

## 입자 수·블록별 전력·통계 변화

![수렴과 통계 변화]({KEY}_convergence.png)

## 마지막 중단 판정

![중단 지표]({KEY}_stopping_criteria.png)

'''
    (dest/'FINAL_REPORT.md').write_text(intro+'\n'+(out/(KEY+'_report.md')).read_text())
    return out

if __name__=='__main__':
    finalize(Path('/workspace/edupic-results-upload/results')/KEY)
