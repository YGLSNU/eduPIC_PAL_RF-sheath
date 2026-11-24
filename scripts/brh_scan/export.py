#!/usr/bin/env python3
"""Snapshot completed blocks, plot actual data, and export standard reports."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import argparse,copy,csv,json,os,shutil,time,zipfile
os.environ.setdefault('MPLCONFIGDIR','/tmp/edupic-matplotlib')
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from common import put,sha

REPO=Path(__file__).resolve().parents[2]
WEB='https://github.com/YGLSNU/eduPIC_PAL_RF-sheath'
RUN='261123_BRH_gap25-120';BRANCH='results/20mTorr-topRF'
KEYS=['convergence','density','heating','fields','ionization','distributions','walls','power']
def save(fig,path):fig.savefig(path,dpi=135,bbox_inches='tight');plt.close(fig)
def im(path,caption):return {'path':path,'caption':caption}
def unavailable(key,reason):return {'id':key,'data_status':'unavailable','reason':reason,'images':[]}
def image_section(key,images,text=''):return {'id':key,'data_status':'available','availability':'실제 저장된 RF 구간; 아래 그림 설명 참조','text':text,'images':images}
def phaseplot(data,keys,L,path,title,signed=False):
    fig,axs=plt.subplots(1,len(keys),figsize=(5*len(keys),4),squeeze=False)
    for ax,(key,label) in zip(axs[0],keys):
        a=data[key];v=np.nanpercentile(np.abs(a),99.5) if signed else None
        pic=ax.imshow(a,origin='lower',aspect='auto',extent=[0,1,0,L],cmap='RdBu_r' if signed else 'viridis',vmin=-v if signed else None,vmax=v)
        ax.set(xlabel='RF phase t/T',ylabel='x (mm)',title=label);fig.colorbar(pic,ax=ax)
    fig.suptitle(title);save(fig,path)

def core_plots(d,out,L,note):
    """d is an immutable completed native measurement block or pooled directory."""
    figs=out/'figures';figs.mkdir(exist_ok=True);sections={};data={}
    for f in d.glob('*_xt.dat'):
        a=np.loadtxt(f,ndmin=2)
        if np.isfinite(a).all():data[f.stem]=a
    if (d/'density.dat').exists():
        a=np.loadtxt(d/'density.dat');fig,ax=plt.subplots(figsize=(7,4))
        ax.plot(a[:,0]*1000,a[:,1],label='electrons');ax.plot(a[:,0]*1000,a[:,2],label='ions')
        ax.set(xlabel='x (mm); lower GND at 0, upper RF at L',ylabel='Density (m$^{-3}$)',title=note);ax.legend();save(fig,figs/'density.png')
        sections['density']=image_section('density',[im('figures/density.png',note)])
    groups=[('heating',[('powere_xt','Electron <j> <E> (W/m3)'),('poweri_xt','Ion <j> <E> (W/m3)')],True),
            ('fields',[('pot_xt','Potential (V)'),('efield_xt','Electric field (V/m)')],False),
            ('ionization',[('meanee_xt','Mean electron energy (eV)'),('ioniz_xt','Ionization rate (m-3 s-1)')],False)]
    for key,plots,signed in groups:
        if all(k in data for k,_ in plots):
            phaseplot(data,plots,L,figs/f'{key}.png',note,signed)
            sections[key]=image_section(key,[im(f'figures/{key}.png',note)])
    if (d/'eepf.dat').exists() and (d/'ifed.dat').exists():
        dist_note=(d/'distribution_note.txt').read_text() if (d/'distribution_note.txt').exists() else note
        e=np.loadtxt(d/'eepf.dat');i=np.loadtxt(d/'ifed.dat');fig,axs=plt.subplots(1,2,figsize=(10,4))
        axs[0].semilogy(e[:,0],np.where(e[:,1]>0,e[:,1],np.nan));axs[0].set(xlim=(0,60),xlabel='E (eV)',ylabel='EEPF (eV$^{-3/2}$)',title='Central 10% of gap')
        for j,lab in [(1,'upper RF'),(2,'lower GND')]:axs[1].plot(i[:,0],i[:,j],label=lab)
        axs[1].set(xlabel='Ion energy (eV)',ylabel='PDF (eV$^{-1}$)');axs[1].legend();fig.suptitle(dist_note);save(fig,figs/'distributions.png')
        sections['distributions']=image_section('distributions',[im('figures/distributions.png',dist_note+'; 정규화된 서로 다른 블록 EEPF는 임의로 합치지 않습니다.')])
    if (d/'particle_balance.csv').exists():
        rows=list(csv.DictReader((d/'particle_balance.csv').open()))
        if rows:
            rf=np.array([float(r['RF_cycle']) for r in rows]);duration=len(rows)/13.56e6
            keys=['e_loss_lower','e_loss_upper','i_loss_lower','i_loss_upper'];labels=['e lower','e upper','ion lower','ion upper']
            flux=[sum(float(r[k]) for r in rows)*112000/(1e-4*duration) for k in keys]
            fig,ax=plt.subplots(figsize=(7,4));ax.bar(labels,flux);ax.set(ylabel='Flux (m$^{-2}$ s$^{-1}$)',title=note);save(fig,figs/'walls.png')
            sections['walls']=image_section('walls',[im('figures/walls.png',note)])
            keys=['e_field_work_J','i_field_work_J','e_wall_energy_J','i_wall_energy_J']
            power=[sum(float(r[k]) for r in rows)/(1e-4*duration) for k in keys]
            fig,ax=plt.subplots(figsize=(7,4));ax.bar(['e field work','ion field work','e wall loss','ion wall loss'],power);ax.axhline(0,color='k',lw=.7);ax.set(ylabel='Power / area (W/m$^2$)',title=note);save(fig,figs/'power.png')
            sections['power']=image_section('power',[im('figures/power.png',note+'; 이산 field work와 벽 운동에너지 유출. 전체 전력 폐합은 아닙니다.')])
    return sections

def compare_brh(series,out):
    """Only post-background measurement epochs; never mix in the short pilot."""
    rows=[];fig,axs=plt.subplots(1,2,figsize=(11,4))
    for gap,status,s in sorted(series):
        assessment=s['background_and_BRH_assessment'].get('BRH',{});f=s['candidate_return_fraction'];w=s['candidate_mean_signed_work_eV']
        ef=assessment.get('candidate_return_fraction',{}).get('half_width');ew=assessment.get('candidate_signed_work_eV',{}).get('half_width')
        rows.append([gap,status,s['first_RF'],s['last_RF'],s['measured_RF'],s['powered_side_returns'],s['candidate_returns'],s['distinct_candidate_UIDs'],f,ef,w,ew,s.get('candidate_mean_net_dK_eV')])
        if f is not None:axs[0].errorbar(gap,100*f,yerr=100*ef if ef is not None else None,fmt='o',capsize=3,color='tab:blue')
        if w is not None:axs[1].errorbar(gap,w,yerr=ew,fmt='o',capsize=3,color='tab:orange',label='1T phase candidate' if len(axs[1].lines)==0 else None)
        if s['all_return_mean_signed_work_eV'] is not None:axs[1].plot(gap,s['all_return_mean_signed_work_eV'],'x',color='k')
    axs[0].set(xlabel='Gap (mm)',ylabel='1T candidate / detected returns (%)');axs[1].set(xlabel='Gap (mm)',ylabel='Mean signed field work (eV / return)');axs[1].axhline(0,color='k',lw=.7)
    for ax in axs:ax.grid(alpha=.2);ax.set_xlim(20,125)
    fig.suptitle('Available measurement windows; dots without bars lack block uncertainty\nOrange: phase candidates; black crosses: all detected upper-side returns');save(fig,out/'figures/brh_gap_compare.png')
    with (out/'brh_gap_summary.csv').open('w') as f:
        writer=csv.writer(f);writer.writerow(['gap_mm','status','RF_first','RF_last','measured_RF','detected_upper_returns','candidate_returns','candidate_UIDs','candidate_event_fraction','fraction_uncertainty_indicator','candidate_fieldwork_eV','work_uncertainty_eV','candidate_net_dK_eV']);writer.writerows(rows)
    table='| Gap mm | 상태 | 측정 RF | 왕복 / 1T후보 | 후보 UID | 후보 % | 후보 field work eV/왕복 |\n|---:|---|---|---:|---:|---:|---:|\n'
    for r in rows:
        table+=f'| {r[0]} | {r[1]} | {r[2]}–{r[3]} ({r[4]}RF) | {r[5]} / {r[6]} | {r[7]} | '+(f'{100*r[8]:.3f}' if r[8] is not None else '—')+' | '+(f'{r[10]:.4g}' if r[10] is not None else '—')+' |\n'
    images=[im('figures/brh_gap_compare.png','검출 왕복 사건 중 기본1T 후보의 비율과 signed field work. 전체 전자의 BRH 밀도 분율이 아닙니다. 검은×는 전체 검출 왕복의 평균입니다.')]
    if len(series)>=2:
        fig,axs=plt.subplots(1,2,figsize=(11,4))
        for gap,status,s in sorted(series):
            with np.load(Path(s['pooled_data_path'])/'histogram_counts.npz') as z:
                edge=z['energy_edges_eV'];width=np.diff(edge);energy=(edge[:-1]+edge[1:])/2
                for ax,k in zip(axs,['E_counts','Ex_counts']):
                    counts=z[k][9:11].sum(axis=(0,1,2))[:270];pdf=counts/max(counts.sum(),1)/width
                    if k=='E_counts':pdf=pdf/np.sqrt(energy)
                    ax.semilogy(energy,np.where(pdf>0,pdf,np.nan),label=f'{gap} mm, {s["measured_RF"]} RF')
        axs[0].set(xlabel='Total E (eV)',ylabel='Central 10% EEPF (eV$^{-3/2}$)',xlim=(0,60));axs[1].set(xlabel='Axial Ex (eV)',ylabel='Central 10% axial-energy PDF (eV$^{-1}$)',xlim=(0,40))
        for ax in axs:ax.legend(fontsize=7);ax.grid(alpha=.2)
        fig.suptitle('Gap comparison; raw counts pooled within each actual measurement window');save(fig,out/'figures/eepf_gap_compare.png');images.append(im('figures/eepf_gap_compare.png','각gap의 실제 측정 RF를 범례에 표시했습니다. 중앙10%, E<500eV로 정규화한 원시 counts 기반 비교입니다.'))
    return {'id':'BRH_gap_compare','title':'기본1T 반복 후보·EEDF의 gap 비교','data_status':'partial','text':'600RF 배경 안정화 뒤 수집한 측정 구간만 비교하며, 별도20RF pilot은 제외합니다. 단일gap이나 통계 중단 기준 전 자료만으로 BRH를 확정하지 않습니다. error bar는20/40RF 블록 불확실도 지표이며, 막대가 없는 점은 아직 블록 추정이 없습니다.','images':images,'table':table}

def export(root,out):
    out.mkdir(parents=True,exist_ok=True);cfg=json.loads((root/'config.json').read_text());criteria=json.loads((root/'criteria.json').read_text());date=datetime.now(ZoneInfo('Asia/Seoul')).isoformat(timespec='seconds')
    for f in ['config.json','criteria.json','diagnostics_validated.json','measurement_engine_validated.json']:
        if (root/f).exists():shutil.copy2(root/f,out/f)
    conditions={'gas':'Ar','pressure_mTorr':20,'temperature_K':350,'frequency_MHz':13.56,'voltage_peak_V':[250],'gap_mm':cfg['gaps_mm'],
        'steps_per_RF':8000,'grid_points':'401–1921 (dx ≤62.5 µm)','weight':112000,'electrodes':'상부 x=L RF / 하부 x=0 접지',
        'surface_model':'흡수 벽, SEE·물질 반사 없음; ground-state Ar optical-depth MCC (탄성·여기·이온화); binary Coulomb 충돌 없음'}
    source={'description':'40mm 기준 C/eduPIC.cc 계열을 C++11로 컴파일; 8k step/RF, 동일 optical-depth MCC, 수동 BRH 입자 진단',
        'revision':'control SHA256 '+cfg['control_source_SHA256']+'; 진단 소스·헤더 SHA는 검증 기록/ZIP 참조',
        'initialization':'40mm·250V RF2001 저장 입자에서 분포 재표본·x 변환·시간 stagger 변환. gap별 초기 물리 밀도와 가중치 고정. 과도구간은 정상 측정에서 제외.'}
    base={'schema_version':1,'id':cfg['id'],'branch':BRANCH,'date':cfg['date'],'report_updated':date,'conditions':conditions,'source':source,
        'related_links':[{'label':'BRH 진단·판정 기준','url':'../METHOD.md'}]}
    histories={};cases=[];summaryrows=[];child_meta=[];brh_series=[]
    entries=[(g,f'{g}mm',False) for g in cfg['gaps_mm']]
    if (root/'pilot40mm/measurement_summary.json').exists() and json.loads((root/'pilot40mm/status.json').read_text())['status']=='diagnostic':entries.append((40,'pilot40mm',True))
    for gap,folder,is_pilot in entries:
        d=root/folder;target=out/folder;target.mkdir(exist_ok=True);(target/'figures').mkdir(exist_ok=True)
        state=json.loads((d/'status.json').read_text());cpRF=state.get('checkpoint_cycle',0);meas=state.get('measured_RF',0);phase=state['phase']
        status=state['status']
        missing_reason=state.get('data_invalidation_reason') or '해당 RF 진단을 아직 측정하지 않았습니다. 안정화 중 자료는 정상 측정과 구분합니다.'
        put(target/'status.json',state);sections={k:unavailable(k,missing_reason) for k in KEYS}
        history=np.loadtxt(d/'history.dat',ndmin=2) if (d/'history.dat').exists() else np.empty((0,3))
        if not is_pilot:histories[gap]=history
        if len(history):
            np.savetxt(target/'history.csv',history,delimiter=',',header='RF,e_macroparticles,i_macroparticles',comments='',fmt='%d')
            fig,axs=plt.subplots(1,2,figsize=(11,4));axs[0].plot(history[:,0],history[:,1],label='e');axs[0].plot(history[:,0],history[:,2],label='ion');axs[0].legend()
            axs[0].set(xlabel='RF cycles since changed-gap initialization',ylabel='Macroparticle count')
            volume=1e-4*gap/1000;axs[1].plot(history[:,0],history[:,1]*112000/volume,label='e');axs[1].plot(history[:,0],history[:,2]*112000/volume,label='ion')
            axs[1].set(xlabel='RF cycles',ylabel='Volume-mean density (m$^{-3}$)');fig.suptitle(f'{gap} mm; {phase}; completed checkpoint RF {cpRF}');save(fig,target/'figures/convergence.png')
            sections['convergence']=image_section('convergence',[im('figures/convergence.png',f'저장된 이력 RF{int(history[0,0])}–{int(history[-1,0])}. 체적 평균은 입자 수에서 계산한 값이며 공간분포와 다릅니다.')])
        native=state.get('pooled_native_path') or state.get('last_diagnostic_path')
        native_note='아직 phase 측정 없음'
        if native:
            nd=Path(native);block=json.loads((nd/'block.json').read_text()) if (nd/'block.json').exists() else {}
            native_note=state.get('pooled_note') or f'Warmup snapshot RF {block.get("RF_first","?")}–{block.get("RF_last","?")} (transient, not stationary)'
            sections.update(core_plots(nd,target,gap,native_note))
        downloads=[{'label':'저장된 실행 상태·실제 RF·종료 사유','path':'status.json'}]
        if native:
            nd=Path(native);signature=sha(nd/'particle_balance.csv') if (nd/'particle_balance.csv').exists() else str(nd)
            cache=target/'core_manifest.json';old_core=json.loads(cache.read_text()) if cache.exists() else {}
            core_name=f'261123_{folder}_core.zip'
            if old_core.get('signature')!=signature:
                with zipfile.ZipFile(target/core_name,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=3) as z:
                    for f in nd.iterdir():
                        if f.is_file() and (f.name.endswith('_xt.dat') or f.name in ['density.dat','eepf.dat','ifed.dat','info.txt','particle_balance.csv','block.json','validation.json','block_windows.json','distribution_note.txt']):z.write(f,f.name)
                put(cache,{'signature':signature,'measurement_note':native_note})
            downloads.append({'label':'표준 진단 원시 수치·이력: '+native_note,'path':core_name})
        if len(history):downloads.append({'label':'입자 수 이력 CSV','path':'history.csv'})
        # Archive only completed checkpoints. Keep an explicitly dated checkpoint
        # until 500 more RF or a terminal state, avoiding an upload per block.
        archive_meta=target/'restart_manifest.json';old=json.loads(archive_meta.read_text()) if archive_meta.exists() else {}
        final=status in ['criteria_met','extinguished','measurement_limit_reached','total_cycle_limit_reached','paused_error','paused_at_checkpoint']
        cp=Path(state.get('checkpoint_path',d/'input_cycle0.bin'))
        if not old or cpRF-old.get('RF',-10000)>=500 or (cpRF>old.get('RF',-1) and time.time()-old.get('backup_time_unix',0)>=3600) or (final and old.get('checkpoint_SHA256')!=sha(cp)):
            archive=target/f'261123_{folder}_restart.zip'
            with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=3) as z:
                z.write(cp,'picdata.bin')
                for f in ['brh_state.bin','brh_rng.txt']:
                    if (cp.parent/f).exists():z.write(cp.parent/f,f)
                z.writestr('provenance.json',json.dumps({'RF':cpRF,'gap_mm':gap,'source_control_SHA256':cfg['control_source_SHA256'],'checkpoint_SHA256':sha(cp),'companion_state':(cp.parent/'brh_state.bin').exists(),'note':'Without brh companion, RNG and optical-depth draws restart statistically; with companion all are restored. Diagnostic histograms are per measurement block.'},indent=2))
            old={'RF':cpRF,'checkpoint_SHA256':sha(cp),'archive':archive.name,'backup_time_unix':time.time()};put(archive_meta,old)
        downloads += [{'label':f'재시작 입자·동반 상태 (저장 RF {old["RF"]}; 보고서의 최신 RF와 다를 수 있음)','path':old['archive']},{'label':'재시작 파일 provenance','path':'restart_manifest.json'}]
        brhtext=state.get('data_invalidation_reason') or '아직 BRH 왕복 진단 측정 전입니다. 입자 수 안정화나 EEDF만으로 BRH 발생을 판정하지 않습니다.'
        if state.get('measurement_summary_path') or is_pilot:
            from postprocess import export_diagnostics
            brh_sections,brh_downloads,brhtext=export_diagnostics(d,target,state.get('measurement_summary_path'))
            sections.update(brh_sections);downloads+=brh_downloads
            if not is_pilot:brh_series.append((gap,status,json.loads(Path(state['measurement_summary_path']).read_text())))
        sections['bounce']=sections.get('bounce',unavailable('bounce',brhtext));sections['bounce']['title']='BRH 왕복·위상·에너지 진단'
        state_reason=state.get('reason') or state.get('error') or ('실행 대기 중' if state['status']=='queued' else ('배경 입자 수 안정화 중' if phase=='warmup' else '위상·입자 진단 측정 중; 최종 BRH 판정 전'))
        if status=='extinguished':state_reason=f'RF{cpRF}에서 전자 수 0으로 종료. 잔류 이온은 존재할 수 있습니다. 정상 EEDF/BRH를 정의하지 않습니다.'
        m=copy.deepcopy(base);m.update(title=f'BRH · gap {gap} mm · 250 V'+(' · 짧은20RF 예비 진단' if is_pilot else ''),status=status,changed_conditions=f'BRH gap {gap} mm'+(' short pilot' if is_pilot else ''),report_directory=f'results/{RUN}/{folder}',
            summary=state_reason+' '+brhtext,measurement_note=native_note,sections=list(sections.values()),downloads=downloads,
            metrics=[['저장 체크포인트',f'RF {cpRF}'],['예비 진단 누적' if is_pilot else '정상 측정 누적',f'{meas} RF'],['현재 단계',phase],['안정성 확인',json.dumps(state.get('stationarity',{}),ensure_ascii=False)],['진행 상태 갱신',state.get('updated_at_Asia_Seoul','미시작')]])
        if is_pilot:m['source']['initialization']='Main40mm의 중간 체크포인트에서 별도2RF 이력 채움 +20RF 진단. 정한600RF 안정화·200RF 측정 기준 미충족. 초기 상태: '+json.dumps(state['pilot_initial_checkpoint'])
        m['conditions']['gap_mm']=gap;m['conditions']['grid_points']=state['grid_points'];put(target/'report.json',m);child_meta.append((folder,m))
        if not is_pilot:
            cases.append({'gap_mm':gap,'voltage_V':250,'status':status,'total_rf':cpRF,'measurement_rf':meas,'ne_mean_m3':state.get('ne_mean_m3'),'path':f'{gap}mm/README.md'})
            summaryrows.append([gap,250,status,phase,cpRF,meas,state.get('electrons',''),state.get('ions',''),state.get('last_RF_seconds',''),state_reason])
    figs=out/'figures';figs.mkdir(exist_ok=True);fig,axs=plt.subplots(1,2,figsize=(11,4))
    for gap,a in histories.items():
        if len(a):
            axs[0].plot(a[:,0],a[:,1]*112000/(1e-4*gap/1000),label=f'{gap} mm')
            if len(a)>1:axs[1].plot(a[:,0],a[:,1]/max(1,a[0,1]),label=f'{gap} mm')
    axs[0].set(xlabel='RF cycles since gap change',ylabel='Volume-mean electron density (m$^{-3}$)');axs[1].set(xlabel='RF cycles since gap change',ylabel='Electron count / first RF count')
    for ax in axs:ax.legend(fontsize=8);ax.grid(alpha=.25)
    fig.suptitle('Gap scan: completed snapshots only; not a BRH verdict');save(fig,figs/'progress.png')
    with (out/'summary.csv').open('w') as f:
        w=csv.writer(f);w.writerow(['gap_mm','V_peak','status','phase','completed_RF','measured_RF','electrons','ions','last_seconds_per_RF','reason']);w.writerows(summaryrows)
    active=any(c['status'] in ['running','incomplete','queued'] for c in cases)
    status='running' if active else ('criteria_met' if all(c['status']=='criteria_met' for c in cases) else 'measurement_complete')
    if not active:
        for terminal in ['paused_error','paused_at_checkpoint','measurement_limit_reached','total_cycle_limit_reached']:
            if any(c['status']==terminal for c in cases):status=terminal;break
        if all(c['status']=='extinguished' for c in cases):status='extinguished'
    parent=copy.deepcopy(base);parent.update(title='Bounce resonance heating · gap 스캔',status=status,scan_parameter='gap_mm',changed_conditions='BRH · gap25/30/40/50/60/80/100/120 mm',
        summary='250 V에서 gap만 바꾸며 넓은 에너지 분포와 충돌을 포함한 전자 왕복·위상 재현성·signed field work를 비교합니다. 아래는 마지막 완결 블록의 저장 기록입니다. 진행 중인 gap의 결과 및 BRH 여부를 최종값으로 해석하지 않습니다.',
        measurement_note='안정화: 마지막600RF의 3×200RF 평균 변화<1%, fitted drift<2%. 정상 진단: 최소200RF, 20RF블록. 평균량/밀도3%, heating5% 및 BRH 통계 별도. 상한1000RF에서 미충족은 미수렴으로 표시.',
        related_links=[{'label':'BRH 진단·판정·재시작','url':'METHOD.md'},{'label':'실행 코드와 명령','url':WEB+'/blob/simulation/20mTorr-topRF/scripts/brh_scan/README.md'}],cases=cases,
        sections=[image_section('convergence',[im('figures/progress.png','체적 평균 밀도·입자 수의 진행 이력. 안정화 과도구간 포함.')])]+[
            {'id':k,'data_status':'partial','availability':'gap별 상세 보고서의 실제 측정 구간을 따릅니다. 아직 미측정인 조건은 사유를 표시합니다.','images':[]} for k in KEYS if k!='convergence']+
            [{'id':'bounce','title':'BRH 왕복·위상·에너지 진단','text':'왕복 진단의 자료·그림·사건 통계는 조건별 상세 보고서에서 제공합니다.\n\n'+' · '.join(f'[{g} mm]({g}mm/README.md#brh-왕복위상에너지-진단)' for g in cfg['gaps_mm']),'images':[]}],
        downloads=[{'label':'조건별 진행 요약 CSV','path':'summary.csv'},{'label':'공통 설정','path':'config.json'},{'label':'수렴·중단 기준','path':'criteria.json'}])
    if (out/'diagnostics_validated.json').exists():parent['downloads'].append({'label':'수동 진단·재시작 검증','path':'diagnostics_validated.json'})
    if (out/'measurement_engine_validated.json').exists():parent['downloads'].append({'label':'측정 제어·통합·압축·상한 중단 실행 검증','path':'measurement_engine_validated.json'})
    if brh_series:
        parent['sections'].append(compare_brh(brh_series,out));parent['downloads'].append({'label':'gap별 BRH 사건·에너지·불확실도 요약 CSV','path':'brh_gap_summary.csv'})
    from compare import build_comparison
    comparison=build_comparison(root,out,base,cases,brh_series)
    child_meta.append(('comparison',comparison))
    parent['comparison_path']='comparison/README.md'
    parent['related_links'].insert(0,{'label':'Gap별 파라미터·전자별 반복 가열 요약','url':'comparison/README.md'})
    parent['sections'].insert(0,{'id':'comparison_link','title':'Gap별 결과 요약',
        'text':'[전자 밀도·에너지 환산 온도·쉬스 출구 에너지·흡수 전력·이온화율 및 전자 UID별 반복 횟수·에너지 변화](comparison/README.md). 측정이 추가되면 함께 갱신됩니다.','images':[]})
    if any(pilot for _,_,pilot in entries):
        parent['sections'].append({'id':'pilot','title':'40mm 짧은 예비 진단 · 본 스캔과 구분','text':'[20RF 예비 진단의 조건·수치·그림·다운로드](pilot40mm/README.md). 본 gap 스캔의 수렴 결과가 아니며 BRH 확정 자료로 사용하지 않습니다.','images':[im('pilot40mm/figures/brh_returns.png','실제20RF의 왕복·위상·signed energy 진단. 상세 페이지에 위치별 EEPF와 순간 일 지도도 있습니다.')]})
    source_files=[root/f for f in ['source_control.cc','source_brh.cc','brh_diagnostics.hpp','reference40.bin','config.json','criteria.json','diagnostics_validated.json','measurement_engine_validated.json','LICENSE'] if (root/f).exists()]
    script_files=list((REPO/'scripts/brh_scan').glob('*.py'))+list((REPO/'scripts/brh_scan').glob('*.md'))
    sig=''.join(sha(f) for f in source_files+sorted(script_files));cached=out/'source_signature.txt'
    if not cached.exists() or cached.read_text()!=sig:
        with zipfile.ZipFile(out/'261123_BRH_source.zip','w',compression=zipfile.ZIP_DEFLATED) as z:
            for f in source_files:z.write(f,f.name)
            for f in (REPO/'scripts/brh_scan').glob('*.py'):z.write(f,'scripts/brh_scan/'+f.name)
            if (REPO/'scripts/brh_scan/README.md').exists():z.write(REPO/'scripts/brh_scan/README.md','README.md')
        cached.write_text(sig)
    parent['downloads'].append({'label':'실행 소스·진단·설정·원본40mm 기준 입자','path':'261123_BRH_source.zip'})
    if (REPO/'scripts/brh_scan/METHOD.md').exists():shutil.copy2(REPO/'scripts/brh_scan/METHOD.md',out/'METHOD.md')
    put(out/'run.json',parent)
    # Rendering, checksums and coverage audit are shared with existing uploads.
    import sys
    sys.path.insert(0,str(REPO/'scripts/results'))
    from catalog import render_report,refresh_files
    from audit_coverage import audit
    for directory,meta in [(out/folder,m) for folder,m in child_meta]+[(out,parent)]:
        refresh_files(directory,meta);put(directory/('run.json' if directory==out else 'report.json'),meta)
        (directory/'README.md').write_text(render_report(meta));refresh_files(directory,meta)
        assert not audit(meta,(directory/'README.md').read_text())['failures']
    print('Exported snapshot',date,out,flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('export',type=Path);a=p.parse_args();export(a.root.resolve(),a.export.resolve())
