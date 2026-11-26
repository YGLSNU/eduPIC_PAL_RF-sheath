#!/usr/bin/env python3
"""Independent recoverable PSR run; never starts/stops any BRH solver."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import argparse,fcntl,json,os,shutil,subprocess,sys,time,traceback,hashlib,gzip
import numpy as np
from validate import seed,build,validate_fields,sha
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'brh_scan'))
from common import checkpoint,put,stationarity
from analyze import analyze
REPO=Path(__file__).resolve().parents[2]
def now():return datetime.now(ZoneInfo('Asia/Seoul')).isoformat()
def prepare(root,gate):
 root.mkdir(parents=True,exist_ok=False);(root/'source').mkdir()
 validation=json.loads((gate/'validation.json').read_text());assert validation['passed']
 for n in ['eduPIC_psr_vi.cc','psr_vi_diagnostics.hpp']:
  shutil.copy2(REPO/'C'/n,root/'source'/n)
 assert sha(root/'source/eduPIC_psr_vi.cc')==validation['source_SHA256'] and sha(root/'source/psr_vi_diagnostics.hpp')==validation['diagnostic_header_SHA256']
 shutil.copy2(gate/'validation.json',root/'implementation_validated.json');shutil.copy2(REPO/'LICENSE',root/'LICENSE')
 cfg={'id':root.name,'date':now()[:10],'started_at_Asia_Seoul':now(),'gas':'Ar','pressure_mTorr':20,'temperature_K':350,'frequency_Hz':60e6,'gap_mm':15,'voltage_peak_V':150,'A_sim_m2':1e-4,'A_eff_m2':None,'drive_mode':'prescribed_sine','DC_bias_V':0,'self_bias_mode':'fixed','grid_points':481,'steps_per_RF':4000,'ion_subcycling':1,'weight':56000,'harmonic_max':64,'block_cycles':20,'minimum_measurement_cycles':200,'maximum_measurement_cycles':1000,'maximum_total_cycles':20000,'source_SHA256':sha(root/'source/eduPIC_psr_vi.cc'),'header_SHA256':sha(root/'source/psr_vi_diagnostics.hpp'),'source_branch':'simulation/psr-vi','results_branch':'results/20mTorr-60MHz-topRF','initial_density_m3':1e15,'initial_e_temperature_eV':3,'seed':26112660,'initialization':'Fresh preionized spatially paired uniform electron/ion positions, Maxwellian electron3eV/ion350K; not a breakdown threshold test. Changed-condition transients excluded.','surface':'absorbing; no SEE/material reflection','MCC':'same Ar optical-depth electron MCC; isotropic/backscatter Ar+ MCC; no binary Coulomb','experiment_status':'not_provided','external_circuit':'none; ideal imposed voltage','scope_note':'Separate source/execution tree; existing BRH sources and criteria are untouched.'}
 count=round(cfg['initial_density_m3']*cfg['A_sim_m2']*.015/cfg['weight']);seed(root/'input_cycle0.bin',count)
 flags=build(root/'solver',ng=cfg['grid_points'],nt=cfg['steps_per_RF'],sub=1,weight=cfg['weight'])
 # Compile the immutable run copy rather than an editable checkout source.
 flags[-3]=str(root/'source/eduPIC_psr_vi.cc');subprocess.run(flags,check=True,capture_output=True)
 cfg['compile_command']=flags;put(root/'config.json',cfg)
 criteria={'particle_count_window':600,'particle_count_block_span_tolerance':.01,'particle_count_fitted_drift_tolerance':.02}
 put(root/'criteria.json',criteria)
 put(root/'status.json',{'status':'queued','phase':'warmup','completed_RF':0,'measured_RF':0,'checkpoint_path':str(root/'input_cycle0.bin'),'measurement_blocks':[],'started_at_Asia_Seoul':now()})
 print('Prepared independent PSR run',root,'particles/species',count,flush=True)
def compress(d):
 manifest={}
 for p in list(d.glob('*.csv'))+list(d.glob('*_xt.dat'))+[d/'density.dat',d/'phase_fields.bin']:
  if not p.exists():continue
  dst=Path(str(p)+'.gz');temp=Path(str(dst)+'.tmp');h=hashlib.sha256()
  with p.open('rb') as src,gzip.open(temp,'wb',compresslevel=3) as out:
   for b in iter(lambda:src.read(1024*1024),b''):h.update(b);out.write(b)
  verify=hashlib.sha256()
  with gzip.open(temp,'rb') as src:
   for b in iter(lambda:src.read(1024*1024),b''):verify.update(b)
  assert h.digest()==verify.digest();manifest[p.name]={'uncompressed_SHA256':h.hexdigest(),'uncompressed_bytes':p.stat().st_size,'stored_as':dst.name};temp.replace(dst);p.unlink()
 if manifest:put(d/'compression_manifest.json',manifest)
def converged(root,blocks):
 if len(blocks)<10:return {'passed':False,'reason':'minimum200RF_not_reached'}
 import pandas as pd
 spectra=[pd.read_csv(p/'analysis/harmonic_spectra.csv') for p in blocks]
 z=np.array([s.J_real_Am2.to_numpy()+1j*s.J_imag_Am2.to_numpy() for s in spectra]);power=np.array([json.loads((p/'analysis/analysis.json').read_text())['electron_direct_Wm2'] for p in blocks]);mean=z.mean(axis=0)
 width=2.3*np.std(z,axis=0,ddof=1)/np.sqrt(len(z));noise=max(float(np.mean([a.J_noise_floor_Am2.iloc[0] for a in spectra])),1e-6);used=abs(mean)>np.maximum(3*width,noise);used[0]=False
 amp=width/np.maximum(abs(mean),1e-300);phase=np.degrees(np.arcsin(np.minimum(1,amp)))
 h=len(z)//2;drift=abs(z[:h].mean(axis=0)-z[-h:].mean(axis=0))/np.maximum(abs(mean),1e-300)
 pwidth=2.3*power.std(ddof=1)/np.sqrt(len(power));ptol=max(.05*abs(power.mean()),1.)
 power_drift=float(abs(power[:h].mean()-power[-h:].mean()))
 passed=bool(used[1] and np.all(amp[used]<.05) and np.all(phase[used]<5) and np.all(drift[used]<.05) and pwidth<ptol and power_drift<ptol)
 return {'passed':passed,'resolved_orders':np.flatnonzero(used).tolist(),'relative_complex_uncertainty':amp.tolist(),'phase_uncertainty_deg':phase.tolist(),'relative_first_last_drift':drift.tolist(),'electron_power_uncertainty_Wm2':float(pwidth),'electron_power_first_last_drift_Wm2':power_drift,'scope':'Exploratory 20RF block indicators, not certified total error; discretization/seed checks remain separate.'}
def run(root):
 lock=(root/'controller.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 cfg=json.loads((root/'config.json').read_text());criteria=json.loads((root/'criteria.json').read_text());s=json.loads((root/'status.json').read_text())
 assert sha(root/'source/eduPIC_psr_vi.cc')==cfg['source_SHA256'] and sha(root/'source/psr_vi_diagnostics.hpp')==cfg['header_SHA256'],'Immutable native source changed'
 def update(**kw):s.update(kw,updated_at_Asia_Seoul=now());put(root/'status.json',s)
 if s['status'] in ['criteria_met','measurement_limit_reached','total_cycle_limit_reached','extinguished']:return
 put(root/'controller.json',{'pid':os.getpid(),'started_at_Asia_Seoul':now()});update(status='running',controller_pid=os.getpid());hist=np.loadtxt(root/'history.dat',ndmin=2).tolist() if (root/'history.dat').exists() else []
 try:
  while True:
   if (root/'STOP_AFTER_BLOCK').exists():update(status='paused_at_checkpoint');return
   old=checkpoint(s['checkpoint_path'])
   if old['electrons']==0:update(status='extinguished',reason='No electrons; no stationary discharge/harmonics or PSR inference');break
   if old['cycle']>=cfg['maximum_total_cycles']:update(status='total_cycle_limit_reached',reason='Total RF cap reached without the required stationary window');break
   if s['phase']=='warmup':
    stable=stationarity(hist,criteria);update(stationarity=stable)
    if stable['passed']:update(phase='measurement',measurement_start_RF=old['cycle']+1);continue
   if s['phase']=='measurement' and s['measured_RF']>=cfg['maximum_measurement_cycles']:update(status='measurement_limit_reached',reason='Sampling cap reached; stopping indicators not all met. Not a PSR confirmation or full numerical convergence.');break
   count=cfg['block_cycles'] if s['phase']=='measurement' or old['cycle'] else 2
   count=min(count,cfg['maximum_total_cycles']-old['cycle']);first=old['cycle']+1;last=old['cycle']+count
   d=root/s['phase']/f'RF{first:06d}-{last:06d}'
   if d.exists():d.rename(d.with_name(d.name+'.interrupted.'+str(time.time_ns())))
   d.mkdir(parents=True);previous=Path(s['checkpoint_path'])
   shutil.copy2(previous,d/'picdata.bin')
   for n in ['psr_rng.txt','psr_state.bin']:
    if (previous.parent/n).exists():shutil.copy2(previous.parent/n,d/n)
   update(active_RF=[first,last]);begin=time.monotonic()
   with (d/'run.log').open('w') as log:
    args=[str(root/'solver'),str(count)]+(['m'] if s['phase']=='measurement' else [])
    p=subprocess.Popen(args,cwd=d,stdout=log,stderr=subprocess.STDOUT,env={**os.environ,'EDUPIC_DIAGNOSTIC_SEED':str(cfg['seed'])},start_new_session=True)
    update(solver_pid=p.pid);ret=p.wait()
   elapsed=time.monotonic()-begin
   if ret:raise RuntimeError(f'Solver exit {ret}; previous checkpoint retained')
   cp=checkpoint(d/'picdata.bin');conv=np.loadtxt(d/'conv.dat',ndmin=2);assert len(conv)==cp['cycle']-old['cycle']
   record={'phase':s['phase'],'RF_first':first,'RF_last':cp['cycle'],'input':old,'output':cp,'elapsed_seconds':elapsed,'requested_RF':count};put(d/'block.json',record)
   hist.extend(conv.tolist());np.savetxt(root/'history.dat.tmp',hist,fmt='%d');(root/'history.dat.tmp').replace(root/'history.dat');measurement_update={}
   if s['phase']=='measurement' and cp['electrons']:
    numerical=validate_fields(d);put(d/'numerical_validation.json',numerical)
    info=(d/'info.txt').read_text();assert 'VIOLATED' not in info,'Native PIC stability criterion violated; do not interpret this block'
    # Load the recorded analysis revision in a fresh interpreter per block;
    # an hours-long controller must not run stale imported plotting code.
    with (d/'analysis.log').open('w') as log:subprocess.run([sys.executable,str(REPO/'scripts/psr_vi/analyze.py'),str(d),str(d/'analysis'),'--harmonic-max',str(cfg['harmonic_max'])],stdout=log,stderr=subprocess.STDOUT,check=True)
    blocks=[Path(p) for p in s['measurement_blocks']]+[d];assessment=converged(root,blocks);put(d/'assessment.json',assessment)
    measurement_update=dict(measurement_blocks=[str(p) for p in blocks],measured_RF=s['measured_RF']+cp['cycle']-old['cycle'],assessment=assessment,last_analysis=str(d/'analysis'),last_measurement_path=str(d))
   compress(d);update(checkpoint_path=str(d/'picdata.bin'),completed_RF=cp['cycle'],electrons=cp['electrons'],ions=cp['ions'],last_seconds_per_RF=elapsed/max(1,cp['cycle']-old['cycle']),**measurement_update)
   print(now(),s['phase'],'saved RF',cp['cycle'],'Ne',cp['electrons'],'s/RF',round(s['last_seconds_per_RF'],3),flush=True)
   if cp['electrons']==0:update(status='extinguished',reason='Electron extinction; not a stationary discharge');break
   if s['phase']=='measurement' and s['measured_RF']>=cfg['minimum_measurement_cycles'] and s.get('assessment',{}).get('passed'):
    stable=stationarity(hist,criteria)
    if stable['passed']:update(status='criteria_met',reason='Background and resolved-harmonic block indicators met; model/grid/seed uncertainty remains separate.');break
  put(root/'controller_finished.json',{'finished_at_Asia_Seoul':now(),'status':s['status']})
 except Exception as exc:
  update(status='paused_error',error=str(exc));(root/'error.log').write_text(traceback.format_exc());raise
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('--prepare',type=Path,metavar='VALIDATION_DIRECTORY');a=p.parse_args()
 if a.prepare:prepare(a.root.resolve(),a.prepare.resolve())
 else:run(a.root.resolve())
