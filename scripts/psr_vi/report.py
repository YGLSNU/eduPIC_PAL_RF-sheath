#!/usr/bin/env python3
"""Separate PSR/harmonics report using the established result schema and audit."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import json,os,sys,shutil,tempfile,zipfile,gzip,csv
os.environ.setdefault('MPLCONFIGDIR','/tmp/edupic-psr-mpl')
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
REPO=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(REPO/'scripts/brh_scan'));sys.path.insert(0,str(REPO/'scripts/results'))
from common import put,sha
from catalog import render_report,refresh_files,validate
from audit_coverage import audit
from packaging_psr import package
from export import core_plots

def now():return datetime.now(ZoneInfo('Asia/Seoul')).isoformat(timespec='seconds')
def image(section,paths,text):return {'id':section,'data_status':'available','text':text,'images':[{'path':p,'caption':text} for p in paths]}
def report(root,out):
 root=Path(root);out=Path(out);out.mkdir(parents=True,exist_ok=True);(out/'figures').mkdir(exist_ok=True);(out/'data').mkdir(exist_ok=True)
 cfg=json.loads((root/'config.json').read_text());s=json.loads((root/'status.json').read_text());downloads=[]
 put(out/'run_metadata.json',{**cfg,'diagnostic_schema':1,'data_scope':'stationary_measurement' if s['measured_RF'] else 'warmup_and_optional_labelled_transient_only','analysis_SHA256':sha(REPO/'scripts/psr_vi/analyze.py'),'phasor_convention':'peak 2/N; DC mean; exp(-i n omega t); actual timestamps','terminal_current_positive':'RF(L) into plasma (-x)'})
 downloads.append({'label':'진단·위상·소스·조건 메타데이터','path':'run_metadata.json'})
 for name in ['config.json','status.json','criteria.json','implementation_validated.json']:
  shutil.copy2(root/name,out/name);downloads.append({'label':name,'path':name})
 for name in ['experiment_template.csv','experiment_metadata.template.json','METHOD.md']:
  if (REPO/'scripts/psr_vi'/name).exists():shutil.copy2(REPO/'scripts/psr_vi'/name,out/name);downloads.append({'label':name,'path':name})
 resolution=root/'resolution_checks'
 if (resolution/'resolution_validation.json').exists():
  for name in ['resolution_validation.json','vacuum_dt_convergence.csv','plasma_sensitivity.csv','validation_reproduction.zip']:
   shutil.copy2(resolution/name,out/'data'/name);downloads.append({'label':'별도 수치 검증(과도구간, 정상 통계 제외) '+name,'path':'data/'+name})
 keys=['convergence','density','heating','fields','ionization','distributions','walls','power']
 reason='아직 배경 안정화/정상 측정 전입니다. 과도구간을 정상 방전·PSR 결과로 해석하지 않습니다.'
 sections={k:{'id':k,'data_status':'unavailable','reason':reason,'images':[]} for k in keys}
 if (root/'history.dat').exists():
  h=np.loadtxt(root/'history.dat',ndmin=2);h=h[h[:,0]<=s['completed_RF']];np.savetxt(out/'data/history.csv',h,delimiter=',',header='RF,e_macroparticles,i_macroparticles',comments='',fmt='%d')
  fig,axs=plt.subplots(1,2,figsize=(11,4));axs[0].plot(h[:,0],h[:,1],label='electrons');axs[0].plot(h[:,0],h[:,2],label='ions');axs[0].legend();axs[0].set(xlabel='RF',ylabel='Macroparticles')
  axs[1].plot(h[:,0],h[:,1]*cfg['weight']/(cfg['A_sim_m2']*cfg['gap_mm']/1000));axs[1].set(xlabel='RF',ylabel='Volume-mean electron density (m-3)');fig.suptitle('Transient + measurement history; not PSR proof');fig.savefig(out/'figures/convergence.png',dpi=140,bbox_inches='tight');plt.close(fig)
  sections['convergence']=image('convergence',['figures/convergence.png'],'실제 저장 RF의 입자 수·체적 평균 밀도. 과도구간을 포함합니다.');downloads.append({'label':'입자 수 이력','path':'data/history.csv'})
  balance_rows=[]
  for stage in ['warmup','measurement']:
   for d in sorted((root/stage).glob('RF*')):
    if not (d/'block.json').exists() or '.interrupted.' in d.name:continue
    if json.loads((d/'block.json').read_text())['RF_last']>s['completed_RF']:continue
    f=d/'particle_balance.csv.gz';f=f if f.exists() else d/'particle_balance.csv'
    if f.exists():
     b=pd.read_csv(f);b['stage']=stage;balance_rows.append(b)
  if balance_rows:
   history=pd.concat(balance_rows,ignore_index=True);history['Pe_Wm2']=history.e_field_work_J*cfg['frequency_Hz']/cfg['A_sim_m2'];history['Pi_Wm2']=history.i_field_work_J*cfg['frequency_Hz']/cfg['A_sim_m2'];history.to_csv(out/'data/RF_particle_power_history.csv',index=False)
   fig,ax=plt.subplots(figsize=(10,4));ax.plot(history.RF_cycle,history.Pe_Wm2,label='electron field work');ax.plot(history.RF_cycle,history.Pi_Wm2,label='ion field work');ax.set(xlabel='RF',ylabel='Field power / area (W/m2)',title='Actual cycle-resolved transient/measurement power');ax.legend();fig.savefig(out/'figures/power_history.png',dpi=140,bbox_inches='tight');plt.close(fig)
   sections['convergence']['images'].append({'path':'figures/power_history.png','caption':'주기별 전자·이온 field-kick 전력. 배경 안정화 입자 수와 함께 확인하며 과도구간은 정상 통계에서 제외합니다.'});downloads.append({'label':'RF별 입자·흡수전력 이력','path':'data/RF_particle_power_history.csv'})
 measured=[Path(p) for p in s.get('measurement_blocks',[])];analysis=[];transient=False
 if not measured and (root/'transient_probe/analysis/analysis.json').exists():measured=[root/'transient_probe'];transient=True
 if measured:
  last=measured[-1];note=f'Last validated native block RF {json.loads((last/"block.json").read_text())["RF_first"]}–{json.loads((last/"block.json").read_text())["RF_last"]}; native energy distributions are this block only'
  with tempfile.TemporaryDirectory(prefix='psr-native-view-') as td:
   td=Path(td)
   for p in last.iterdir():
    if p.name.endswith('_xt.dat.gz') or p.name=='density.dat.gz':
     with gzip.open(p,'rb') as f:(td/p.name[:-3]).write_bytes(f.read())
    elif p.name in ['eepf.dat','ifed.dat','info.txt','density.dat'] or p.name.endswith('_xt.dat'):shutil.copy2(p,td/p.name)
   for name in ['particle_balance.csv']:
    src=last/(name+'.gz')
    if src.exists():
     with gzip.open(src,'rb') as f:(td/name).write_bytes(f.read())
    elif (last/name).exists():shutil.copy2(last/name,td/name)
   sections.update(core_plots(td,out,cfg['gap_mm'],note))
  balance=pd.read_csv(last/('particle_balance.csv.gz' if (last/'particle_balance.csv.gz').exists() else 'particle_balance.csv'));duration=len(balance)/cfg['frequency_Hz']
  for kind,columns,labels in [('walls',['e_loss_lower','e_loss_upper','i_loss_lower','i_loss_upper'],['e GND','e RF','ion GND','ion RF']),('power',['e_field_work_J','i_field_work_J','e_wall_energy_J','i_wall_energy_J'],['e field','ion field','e wall','ion wall'])]:
   values=[balance[k].sum()/(cfg['A_sim_m2']*duration)*(cfg['weight'] if kind=='walls' else 1) for k in columns]
   fig,ax=plt.subplots(figsize=(8,4));ax.bar(labels,values);ax.set(ylabel='Flux (m-2 s-1)' if kind=='walls' else 'Power / area (W/m2)',title=note);fig.savefig(out/'figures'/(kind+'.png'),dpi=140,bbox_inches='tight');plt.close(fig)
  for name in ['VI_waveforms.png','harmonics.png','sheath_QV.png','PSR_power.png','PSR_synchronized.png']:shutil.copy2(last/'analysis/figures'/name,out/'figures'/name)
  sections['heating']=image('heating',['figures/PSR_power.png'],'마지막 검증 블록: 순간 jeE를 먼저 계산한 뒤 위상 평균. 음의 기여를 보존하고 쉬스 경계를 표시합니다.')
  for name in ['harmonic_spectra.csv','harmonic_power.csv','harmonic_power_spatial.csv.gz','harmonic_fields_spatial.csv.gz','sheath_estimates.csv.gz','sheath_harmonics.csv','sheath_QV_fits.json','current_spectrum_Hz.csv.gz','analysis.json','bulk_harmonics.csv','power_regions.json']:
   if not (last/'analysis'/name).exists():continue
   shutil.copy2(last/'analysis'/name,out/'data'/name);downloads.append({'label':'마지막 검증 블록 '+name,'path':'data/'+name})
  spectra=[];powers=[];summaries=[]
  for b in measured:
   rec=json.loads((b/'block.json').read_text());a=pd.read_csv(b/'analysis/harmonic_spectra.csv');a.insert(0,'RF_last',rec['RF_last']);spectra.append(a)
   p=pd.read_csv(b/'analysis/harmonic_power.csv');p.insert(0,'RF_last',rec['RF_last']);powers.append(p);summaries.append(json.loads((b/'analysis/analysis.json').read_text()))
  all_spectra=pd.concat(spectra);all_spectra.to_csv(out/'data/block_harmonic_spectra.csv',index=False)
  all_power=pd.concat(powers);all_power.to_csv(out/'data/block_harmonic_power.csv',index=False)
  # Average products calculated within each block; never multiply averaged phasors.
  aggregations={c:['mean','std','count'] for c in all_power if c.endswith('_Wm2')};aggregations['frequency_Hz']='first'
  aggregation=all_power.groupby('harmonic').agg(aggregations);aggregation.columns=['_'.join(c) for c in aggregation.columns];aggregation.to_csv(out/'data/harmonic_power_block_statistics.csv')
  for name in ['block_harmonic_spectra.csv','block_harmonic_power.csv','harmonic_power_block_statistics.csv']:downloads.append({'label':'블록별 평균·변동 '+name,'path':'data/'+name})
  analysis=[image('VI_harmonics',['figures/VI_waveforms.png','figures/harmonics.png'],'단자 양의 방향은 상부RF→플라즈마. 전류밀도 A/m², peak/RMS와 위상·차수별 전력은 CSV 참조. 이상적인 정현파에서 V(n>1)=0은 경계조건입니다.'),
    image('sheath_nonlinearity',['figures/sheath_QV.png'],'공간 쉬스 전하/면적과 전압강하의 RF위상 궤적. 전극 표면전하와 구분합니다. 적분 경계가 유효하지 않은 시점은 NaN; 정적 다항식은 근사이며 hysteresis를 포함할 수 있습니다.'),
    image('PSR_diagnostics',['figures/PSR_synchronized.png','figures/PSR_power.png'],'원전류와 고주파 재구성, bulk전압, 순간 전자 가열. 고조파 peak·필터 ringing·근사 LC주파수만으로 PSR을 확정하거나 PSR 가열 증가분으로 명명하지 않습니다. 기본 전력그림의 legacy <j><E>와 새 순간 jeE는 구분합니다.')]
  put(out/'data/PSR_summary.json',{'PSR_status':'not_established','data_scope':'transient_only_excluded_from_stationary_statistics' if transient else 'stationary_measurement_blocks','blocks':len(measured),'measured_RF':s['measured_RF'],'mean_electron_net_Wm2':float(np.mean([a['electron_direct_Wm2'] for a in summaries])),'mean_electron_positive_Wm2':float(np.mean([a['electron_positive_Wm2'] for a in summaries])),'mean_electron_negative_Wm2':float(np.mean([a['electron_negative_Wm2'] for a in summaries])),'note':'Blocks preserve signed power and unresolved spectral remainder. Heating gain needs a control/model; stationary grid/seed convergence is not implied by an RF sampling cap.'})
  downloads.append({'label':'PSR·순가열 판단 범위','path':'data/PSR_summary.json'})
  # Native arrays, high-resolution signals and per-block products remain downloadable.
  for b in measured:
   dest=out/'blocks'/b.name;dest.mkdir(parents=True,exist_ok=True)
   signature=sha(b/'block.json')+sha(REPO/'scripts/psr_vi/packaging_psr.py');marker=dest/'archive_signature.txt'
   if not marker.exists() or marker.read_text()!=signature:
    payload=[(p,p.name) for p in b.iterdir() if p.is_file() and p.name not in ['picdata.bin','psr_rng.txt','psr_state.bin','run.log']]
    package(payload,dest,f'{cfg["id"]}_{b.name}');marker.write_text(signature)
   downloads.extend({'label':f'RF block {b.name} 원자료·phase필드·전력(분할 ZIP 모두 받기)','path':str(p.relative_to(out))} for p in sorted(dest.glob('*.zip')))
 # Preserve missing experimental data as a real empty state, not synthetic evidence.
 (out/'data/comparison.csv').write_text('harmonic,frequency_Hz,simulation_J_peak_Am2,experiment_I_peak_A,absolute_error,relative_error,circular_phase_error_deg,status\n')
 put(out/'data/experiment_status.json',{'status':'not_provided','missing':['VI data','peak/RMS convention','phase reference','DC information','effective area','calibrated probe reference plane'],'note':'A_eff absent: no absolute experimental ampere fit. Templates only. No matching network/stray model invented.'})
 analysis.append({'id':'experiment','title':'실험 비교','data_status':'unavailable','reason':'실험 VI 파일·기준면·면적·위상/DC 정보가 제공되지 않았습니다. 빈 비교 CSV와 입력 템플릿을 제공합니다.','images':[]})
 if (resolution/'resolution_validation.json').exists():
  vacuum=pd.read_csv(resolution/'vacuum_dt_convergence.csv');sensitivity=pd.read_csv(resolution/'plasma_sensitivity.csv')
  fig,axs=plt.subplots(1,2,figsize=(12,4))
  for order,a in vacuum.groupby('harmonic'):axs[0].loglog(1/a.nt,a.continuous_relative_error,'o-',label=f'n={order}')
  axs[0].set(xlabel='dt / RF period',ylabel='Vacuum current relative complex error',title='Analytic vacuum: finite-difference transfer');axs[0].legend()
  for name,a in sensitivity.groupby('case'):
   if name!='baseline':axs[1].semilogy(a.harmonic,np.maximum(a.complex_difference_over_baseline_J1,1e-12),label=name)
  axs[1].set(xlabel='Harmonic n',ylabel='Complex difference / baseline J1',title='Common RF22 transient; not steady convergence');axs[1].legend(fontsize=7)
  fig.tight_layout();fig.savefig(out/'figures/resolution_checks.png',dpi=140,bbox_inches='tight');plt.close(fig)
  checks=json.loads((resolution/'resolution_validation.json').read_text());powers=[c['electron_power_net_Wm2'] for c in checks['plasma_cases']]
  text=f'다중 고조파 진공 해석해와 동일한 과도 체크포인트의 dt·격자·입자 수·stride 검증. 오른쪽 차이는 기본파 전류로 정규화한 값이며 약한 고차 자체의 상대오차율이 아닙니다. 짧은 과도 시험의 전자 순전력은 {min(powers):.2f}–{max(powers):.2f} W/m²로 달랐고 확률 충돌 변동을 포함합니다. 정상 수렴이나 PSR 발생을 증명하는 결과가 아닙니다.'
  analysis.append({**image('numerical_sensitivity',['figures/resolution_checks.png'],text),'title':'수치 검증·민감도'})
 downloads.extend([{'label':'실험 비교 CSV(현재 빈 상태)','path':'data/comparison.csv'},{'label':'실험 비교 미확인 입력','path':'data/experiment_status.json'}])
 cp=Path(s['checkpoint_path']);restart=out/f'{cfg["id"]}_restart.zip'
 with zipfile.ZipFile(restart,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=3) as z:
  z.write(cp,'picdata.bin')
  for name in ['psr_rng.txt','psr_state.bin']:
   if (cp.parent/name).exists():z.write(cp.parent/name,name)
  z.writestr('provenance.json',json.dumps({'RF':s['completed_RF'],'source_SHA256':cfg['source_SHA256'],'header_SHA256':cfg['header_SHA256'],'checkpoint_SHA256':sha(cp),'frequency_Hz':cfg['frequency_Hz'],'ng':cfg['grid_points'],'nt':cfg['steps_per_RF'],'subcycling':cfg['ion_subcycling'],'units':'particle checkpoint original eduPIC binary; accompanying PSR RNG/optical-depth + previous endpoint state required for exact continuation'},indent=2))
 downloads.append({'label':f'재시작 입자·난수·전류 상태 RF{s["completed_RF"]}','path':restart.name})
 source=out/f'{cfg["id"]}_source.zip'
 with zipfile.ZipFile(source,'w',compression=zipfile.ZIP_DEFLATED) as z:
  for p in (root/'source').iterdir():z.write(p,'C/'+p.name)
  if (root/'source_versions').exists():
   for p in (root/'source_versions').rglob('*'):
    if p.is_file():z.write(p,'source_versions/'+str(p.relative_to(root/'source_versions')))
  for p in (REPO/'scripts/psr_vi').iterdir():
   if p.is_file():z.write(p,'scripts/psr_vi/'+p.name)
  for folder,names in [('brh_scan',['common.py','archive.py','export.py','prepare.py']),('results',['catalog.py','audit_coverage.py','verify_reports.py','publish_run.py'])]:
   for name in names:z.write(REPO/'scripts'/folder/name,'scripts/'+folder+'/'+name)
  for p in [root/'config.json',root/'criteria.json',root/'implementation_validated.json',root/'LICENSE']:z.write(p,p.name)
 downloads.append({'label':'사용 소스·분석·설정·검증·라이선스','path':source.name})
 status=s['status'] if s['status']!='paused_error' else 'paused_error'
 meta={'schema_version':1,'id':cfg['id'],'branch':cfg['results_branch'],'date':cfg['date'],'report_updated':now(),'title':'PSR·VI harmonics · gap15 mm · 60MHz · 150V','changed_conditions':'PSR/VI · 15 mm · 60 MHz · 150 V peak','status':status,
  'conditions':{'gas':'Ar','pressure_mTorr':20,'temperature_K':350,'frequency_MHz':60,'voltage_peak_V':[150],'gap_mm':15,'grid_points':cfg['grid_points'],'steps_per_RF':cfg['steps_per_RF'],'weight':cfg['weight'],'electrodes':'상부 x=L RF / 하부 x=0 접지','surface_model':'흡수벽, SEE/재료반사 없음; Ar optical-depth electron MCC, Ar+ elastic MCC; binary Coulomb 없음','geometry':'1D3V 동일면적 정전 PIC/MCC; A_sim=1cm², A_eff 미제공; 회로/self-bias/측벽 없음'},
  'source':{'description':'독립 C/eduPIC_psr_vi.cc · 원래 Ar PIC/MCC + 보존 전류/전력/적분 쉬스/고조파 진단; 이온 매step 갱신','revision':'source SHA256 '+cfg['source_SHA256']+'; diagnostic header '+cfg['header_SHA256'],'initialization':cfg['initialization']},
  'summary':f'실제 상태: {s["status"]}; {s.get("reason") or s.get("error") or "배경 안정화/측정 진행 중"}. PSR 발생 또는 가열 peak를 미리 확정하지 않습니다. 13.56MHz BRH 계산과 별도 코드·폴더·결과 브랜치입니다.',
  'measurement_note':f'마지막 완결 RF {s["completed_RF"]}; 정상 측정 {s["measured_RF"]}RF. 안정화는 마지막600RF 입자 수 span<1%, drift<2%; 정상 측정 최소200RF, 상한1000RF. 고조파별 블록 평균·변동과 PIC 검증을 별도 기록.',
  'metrics':[['저장 RF',s['completed_RF']],['측정 RF',s['measured_RF']],['단자 전류 정의','RF→plasma (-x); continuum/path charge deposition + displacement; surface-charge/Ramo cross-check'],['PSR 판정','미확정; peak·LC 추정·선택대역 전력은 단독 증거가 아님'],['실험 비교','데이터 미제공; 전류밀도/정규화만 제공']],
  'sections':list(sections.values())+analysis,'downloads':downloads,'related_links':[{'label':'분석·부호·한계·실행 방법','url':'METHOD.md'},{'label':'독립 실행 코드','url':'https://github.com/YGLSNU/eduPIC_PAL_RF-sheath/tree/simulation/psr-vi/scripts/psr_vi'}]}
 if transient:
  warning='과도구간 2RF 진단(정상 통계 제외): '
  meta['summary']+=' '+warning+'아래 스펙트럼·쉬스·전력은 초기화 후 별도 복사본에서 얻은 예비 진단입니다. 정상상태나 PSR 발생의 증거로 사용하지 않습니다.'
  for section in meta['sections']:
   if section['id'] in ['convergence','numerical_sensitivity']:continue
   if section.get('images'):
    section['text']=warning+section.get('text','')
    for im in section['images']:im['caption']=warning+im.get('caption','')
  for d in meta['downloads']:
   if d['path'].startswith(('data/harmonic','data/sheath','data/block','blocks/','data/current')):d['label']=warning+d['label']
 titles={'VI_harmonics':'VI 고조파','sheath_nonlinearity':'쉬스 비선형성','PSR_diagnostics':'PSR·전자 전력흡수'}
 for section in meta['sections']:
  if section['id'] in titles:section['title']=titles[section['id']]
 validate(meta);refresh_files(out,meta);put(out/'run.json',meta);(out/'README.md').write_text(render_report(meta));refresh_files(out,meta)
 failures=audit(meta,(out/'README.md').read_text())['failures'];assert not failures,failures
 print('Exported PSR snapshot',now(),s['status'],s['completed_RF'],s['measured_RF'],flush=True)
if __name__=='__main__':report(Path(sys.argv[1]),Path(sys.argv[2]))
