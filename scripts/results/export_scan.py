#!/usr/bin/env python3
"""Adapt existing checkpointed scan outputs to short names and standard reports."""
from pathlib import Path
from datetime import datetime
import json,shutil,sys,zipfile

def archive(path,entries):
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as z:
        for p,name in entries:
            if p.exists():z.write(p,name)
    with zipfile.ZipFile(path) as z:assert z.testzip() is None

def export(root,out,branch='results/20mTorr-topRF'):
    from catalog import STANDARD_SECTIONS
    from plot_phase import plt,save
    import numpy as np
    root=Path(root);out=Path(out)
    states=[(p,json.loads((p/'status.json').read_text())) for p in sorted(root.iterdir()) if p.is_dir() and (p/'status.json').exists()]
    if not states:raise ValueError('No saved case statuses')
    config=json.loads((root/'config.json').read_text());vs=sorted(s['voltage_peak_V'] for _,s in states)
    day=datetime.fromisoformat(min(s['started_at_Asia_Seoul'] for _,s in states)).date()
    gap=float(config.get('gap_m',.025))*1000
    slug=config.get('result_id',f'{day:%y%m%d}_gap{gap:g}_V{min(vs)}-{max(vs)}')
    conditions={'gas':'Ar','pressure_mTorr':config.get('pressure_mTorr',20),'temperature_K':config.get('gas_temperature_K',350),
                'frequency_MHz':config.get('frequency_Hz',13.56e6)/1e6,'gap_mm':gap,'voltage_peak_V':vs,
                'electrodes':'상부 x=L RF / 하부 x=0 접지','grid_points':config.get('grid_points',400),
                'steps_per_RF':config.get('electron_steps_per_RF',4000),'weight':config.get('weight',70000)}
    statuses={s['status'] for _,s in states}
    status=next(iter(statuses)) if len(statuses)==1 else 'incomplete'
    m={'schema_version':1,'id':slug,'branch':branch,'date':day.isoformat(),'title':f'gap{gap:g} mm 전압 비교','status':status,
       'changed_conditions':f'gap{gap:g} mm, '+','.join(str(v) for v in vs)+' V peak','conditions':conditions,
       'source':{'description':'상부 RF C/eduPIC.cc 계열, C++11 컴파일','revision':config.get('source_sha256','보관 소스 참조'),
                 'initialization':config.get('initialization','공통 입력 체크포인트, 과도구간 제외')},
       'summary':'마지막으로 완전히 저장된 상태와 실제 종료 이유입니다.','measurement_note':'조건별 정확한 측정 구간은 상세 기록을 따릅니다.',
       'sections':[],'cases':[],'downloads':[]}
    out.mkdir(parents=True,exist_ok=True)
    fig,axes=plt.subplots(1,len(states),figsize=(4*len(states),3.7),squeeze=False,layout='constrained')
    for ax,(case,state) in zip(axes.flat,states):
        v=state['voltage_peak_V'];d=out/f'{v}V';d.mkdir();key=case.name
        if state['status'] in ['criteria_met','extinguished','measurement_limit_reached','total_cycle_limit_reached']:
            done=json.loads((case/'finalized.json').read_text()) if (case/'finalized.json').exists() else None
            if done!={'checkpoint_cycle':state['checkpoint_cycle'],'status':state['status']}:
                sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'voltage_scan'))
                from analyze_scan import summarize_case
                summarize_case(root,case)
        final=case/'final_output'
        if final.exists():
            for p in final.rglob('*'):
                if p.is_file():
                    q=d/p.relative_to(final).as_posix().replace(key,str(v)+'V')
                    q.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,q)
                    if q.suffix in ['.md','.html']:q.write_text(q.read_text().replace(key,str(v)+'V'))
        for name in ['status.json','history.dat','assessment.json','assessments.jsonl']:
            if (case/name).exists():shutil.copy2(case/name,d/name)
        cp=case/state['latest_block']/'picdata.bin' if state.get('latest_block') else case/'latest_checkpoint.bin'
        if not cp.exists():cp=case/'input_cycle0.bin'
        filename=f'{slug}_{v}V_restart.zip'
        archive(d/filename,[(cp,'picdata.bin')]+[(root/name,name) for name in ['source-eduPIC.cc','config.json','criteria.json','LICENSE']])
        child={**m,'title':f'{v} V · gap{gap:g} mm','status':state['status'],'conditions':{**conditions,'voltage_peak_V':[v]},
               'cases':[],'sections':[],'downloads':[],'report_directory':f'results/{slug}/{v}V'}
        accepted=state.get('completed_measurement_cycles',0) if state['status']=='criteria_met' else 0
        child['measurement_note']=f'저장 RF{state["checkpoint_cycle"]}; 기준 충족 측정 {accepted} RF'
        child['summary']='전자 소멸; 정상 방전의 측정 평균 아님' if state['status']=='extinguished' else ('정한 통계 기준을 충족했습니다.' if state['status']=='criteria_met' else '현재까지 저장된 자료이며 최종 통계 수렴 판정 전입니다.')
        if state.get('measurement_start_cycle') and accepted:
            child['measurement_note']+=f'; RF{state["measurement_start_cycle"]}–{state["checkpoint_cycle"]}'
        patterns={'convergence':['convergence','extinction'],'density':['distributions'],'heating':['heating'],'fields':['fields_density'],
                  'ionization':[],'distributions':[],'walls':['currents_ionenergy'],'power':[]}
        used=set()
        for name,title in STANDARD_SECTIONS:
            images=[]
            for p in sorted(d.glob('*.png')):
                if p not in used and any(term in p.stem for term in patterns[name]):images.append({'path':p.name,'caption':title});used.add(p)
            child['sections'].append({'id':name,'availability':'보존된 원본 진단 참조' if state['status']=='criteria_met' else ('입자 수·소멸 이력' if name=='convergence' else '최종 정상 방전 측정 없음'),'images':images})
        for p in sorted(d.rglob('*')):
            if p.is_file() and p.suffix in ['.zip','.pdf','.csv']:child['downloads'].append({'label':p.stem,'path':p.relative_to(d).as_posix()})
        (d/'report.json').write_text(json.dumps(child,ensure_ascii=False,indent=2)+'\n')
        summaries=list(d.glob('*_summary.json'));summary=json.loads(summaries[0].read_text()) if summaries else {}
        m['cases'].append({'voltage_V':v,'status':state['status'],'total_rf':state['checkpoint_cycle'],'measurement_rf':accepted,
                           'ne_mean_m3':summary.get('mean_density_e') if accepted else None,'path':f'{v}V/README.md'})
        if (case/'history.dat').exists():
            a=np.loadtxt(case/'history.dat',ndmin=2)
            for col,label in [(1,'Electrons'),(2,'Ar+ ions')]:ax.plot(a[:,0],a[:,col],label=label)
        ax.set(title=f'{v} V | {state["status"]}',xlabel='RF cycles',ylabel='Macroparticles');ax.legend(fontsize=8)
    save(fig,out/'progress.png')
    m['sections']=[{'id':'convergence','availability':'저장된 입자 수·상태','images':[{'path':'progress.png','caption':'저장 이력; 실시간 CPU 상태가 아님'}]}]
    filename=slug+'_source.zip';archive(out/filename,[(root/name,name) for name in ['source-eduPIC.cc','config.json','criteria.json','LICENSE','reflected_initial_cycle0.bin']])
    m['downloads'].append({'label':'실행 소스·공통 초기 상태','path':filename})
    (out/'run.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n');return m
