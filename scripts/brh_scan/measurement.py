"""Continuous UID/RNG-preserving diagnostic epochs and bounded sampling."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import csv,json,os,re,shutil,subprocess,time
import numpy as np
from common import checkpoint,put,sha,stationarity
from brh_stats import assess

def now():return datetime.now(ZoneInfo('Asia/Seoul')).isoformat()

def validate_block(path,ng,count,gap):
    info=(path/'info.txt').read_text();assert 'VIOLATED' not in info,'Native stability/accuracy condition failed; refine grid/step before interpretation'
    data={}
    for name in ['pot','efield','ne','ni','je','ji','powere','poweri','meanee','meanei','ioniz']:
        a=np.loadtxt(path/(name+'_xt.dat'));assert a.shape==(ng,200) and np.isfinite(a).all(),name;data[name]=a
    for s in ['e','i']:assert np.allclose(data['power'+s],data['j'+s]*data['efield'],rtol=3e-6,atol=.003)
    meta=json.loads((path/'brh_meta.json').read_text());assert meta['maximum_return_energy_ledger_residual_eV']<1e-8
    assert abs((meta['measurement_end_s']-meta['measurement_start_s'])*13.56e6-count)<1e-5
    wm=np.fromfile(path/'brh_work_sum_eV.bin',dtype='<f8');assert len(wm)==ng*200 and np.isfinite(wm).all()
    assert np.isclose(wm.sum(),meta['all_fieldwork_eV'],rtol=1e-8,atol=1e-6)
    for energy in ['E','Ex']:
        from postprocess import block_hist
        hist=block_hist(path,energy);assert hist.size==20*200*2*271 and hist.sum()==meta['hist_total_samples']
    rows=list(csv.DictReader((path/'particle_balance.csv').open()));assert len(rows)==count
    native=sum(float(r['e_field_work_J']) for r in rows)
    assert np.isclose(native,meta['all_fieldwork_eV']*112000*1.60217662e-19,rtol=1e-8,atol=1e-20)
    checks={}
    for key,pattern,limit in [('omega_pe_dt',r'Plasma frequency @ center \* DT_E\s*=\s*([\d.eE+-]+)',.2),('dx_lambdaD',r'DX / Debye length @ center\s*=\s*([\d.eE+-]+)',1.),('nu_e_dt',r'Max\. electron coll\. frequency \* DT_E\s*=\s*([\d.eE+-]+)',.05),('nu_i_dt',r'Max\. ion coll\. frequency \* DT_I\s*=\s*([\d.eE+-]+)',.05)]:
        value=float(re.search(pattern,info)[1]);assert value<limit,key;checks[key]={'value':value,'limit':limit}
    result={'passed':True,'finite_shapes':True,'histogram_count_conservation':True,'fieldwork_native_consistent':True,'roundtrip_energy_ledger_max_eV':meta['maximum_return_energy_ledger_residual_eV'],'native_stability':checks}
    put(path/'validation.json',result);return result

def pool_native(blocks,dest):
    dest.mkdir(exist_ok=True,parents=True);pool={}
    for key in ['pot','efield','ne','ni','je','ji','ioniz']:
        pool[key]=sum(np.loadtxt(p/(key+'_xt.dat')) for p in blocks)/len(blocks)
    for s in ['e','i']:
        pool['power'+s]=pool['j'+s]*pool['efield'];numerator=sum(np.loadtxt(p/('meane'+s+'_xt.dat'))*np.loadtxt(p/('n'+s+'_xt.dat')) for p in blocks)/len(blocks)
        pool['meane'+s]=np.divide(numerator,pool['n'+s],out=np.zeros_like(numerator),where=pool['n'+s]>0)
    for k,a in pool.items():np.savetxt(dest/(k+'_xt.dat'),a,fmt='%.9e')
    density=sum(np.loadtxt(p/'density.dat') for p in blocks)/len(blocks);np.savetxt(dest/'density.dat',density,fmt='%.9e')
    for name in ['eepf.dat','ifed.dat','info.txt']:shutil.copy2(blocks[-1]/name,dest/name)
    put(dest/'block_windows.json',{'blocks':[json.loads((p/'block.json').read_text()) for p in blocks],'normalization':'phase densities/currents/fields averaged over equal RF blocks; energy moments density-weighted; heating is pooled <j>*<E>; native EEPF/IEDF and info.txt from last block only'})
    last=json.loads((blocks[-1]/'block.json').read_text());(dest/'distribution_note.txt').write_text(f'Last native block RF {last["RF_first"]}–{last["RF_last"]} only (20 RF); pooled EEDF uses raw new histogram counts')
    with (dest/'particle_balance.csv').open('w') as out:
        for j,p in enumerate(blocks):
            lines=(p/'particle_balance.csv').read_text().splitlines();out.write('\n'.join(lines if j==0 else lines[1:])+'\n')

def measure_case(root,d,state,previous,history):
    cfg=json.loads((root/'config.json').read_text());criteria=json.loads((root/'criteria.json').read_text());gap=state['gap_mm'];ng=state['grid_points'];valid=json.loads((root/'diagnostics_validated.json').read_text())
    assert valid['passed'] and valid['source_SHA256']==sha(root/'source_brh.cc') and valid['header_SHA256']==sha(root/'brh_diagnostics.hpp'),'Diagnostic source changed since passivity/restart validation'
    binary=d/'solver_brh';build_meta=d/'build_brh.json';sig=valid['source_SHA256']+valid['header_SHA256']
    flags=['g++','-std=c++11','-O3','-march=native','-ffp-contract=off',f'-DEDUPIC_GAP_M={gap/1000:.9f}',f'-DEDUPIC_GRID_POINTS={ng}','-DEDUPIC_WEIGHT=112000.0',str(root/'source_brh.cc'),'-o',str(binary)]
    if not binary.exists() or not build_meta.exists() or json.loads(build_meta.read_text())['signature']!=sig:
        subprocess.run(flags,check=True,capture_output=True);put(build_meta,{'signature':sig,'command':flags})
    def update(**kw):state.update(kw,updated_at_Asia_Seoul=now());put(d/'status.json',state)
    def execute(count,stage,measuring=False):
        nonlocal previous,history
        old=checkpoint(previous);start=old['cycle']+1;end=old['cycle']+count;work=d/stage/f'RF{start:06d}-{end:06d}'
        if work.exists():work.rename(work.with_name(work.name+'.interrupted.'+str(time.time_ns())))
        work.mkdir(parents=True);shutil.copy2(previous,work/'picdata.bin');use_brh=stage!='rewarmup'
        if use_brh:
            for name in ['brh_state.bin','brh_rng.txt']:
                if (previous.parent/name).exists():shutil.copy2(previous.parent/name,work/name)
        env={**os.environ,'EDUPIC_DIAGNOSTIC_SEED':str(261123000+gap*100000+start)}
        if measuring:env['EDUPIC_BRH_MEASUREMENT_START_S']=format(state['measurement_start_time_s'],'.17g')
        update(active_RF=[start,end],phase='measurement' if measuring else stage)
        begin=time.monotonic()
        with (work/'run.log').open('w') as out:
            proc=subprocess.Popen([str(binary if use_brh else d/'solver_warm'),str(count)]+(['m'] if measuring else []),cwd=work,stdout=out,stderr=subprocess.STDOUT,env=env,start_new_session=True)
            update(solver_pid=proc.pid);ret=proc.wait()
        elapsed=time.monotonic()-begin;assert ret==0,f'Solver returned {ret}'
        cp=checkpoint(work/'picdata.bin');conv=np.loadtxt(work/'conv.dat',ndmin=2);actual=cp['cycle']-old['cycle'];assert len(conv)==actual and (actual==count or cp['electrons']==0)
        record={'stage':stage,'RF_first':start,'RF_last':cp['cycle'],'requested_RF':count,'seed':env['EDUPIC_DIAGNOSTIC_SEED'],'input':old,'output':cp,'wall_seconds':elapsed,'source_SHA256':valid['source_SHA256'] if use_brh else cfg['control_source_SHA256'],'header_SHA256':valid['header_SHA256'] if use_brh else None,'initial_companion':(previous.parent/'brh_state.bin').exists() and use_brh}
        put(work/'block.json',record);history.extend(conv.tolist());tmp=d/'history.dat.tmp';np.savetxt(tmp,history,fmt='%d');tmp.replace(d/'history.dat');previous=work/'picdata.bin'
        update(checkpoint_path=str(previous),checkpoint_cycle=cp['cycle'],electrons=cp['electrons'],ions=cp['ions'],elapsed_solver_seconds=state.get('elapsed_solver_seconds',0)+elapsed,last_block_seconds=elapsed,last_RF_seconds=elapsed/max(1,actual))
        print(now(),gap,'mm',stage,'RF',cp['cycle'],'Ne',cp['electrons'],'s/RF',round(elapsed/max(1,actual),2),flush=True)
        return work,cp
    def stopped():return (root/'STOP_AFTER_BLOCK').exists() or (d/'STOP_AFTER_BLOCK').exists()
    while True:
        epoch=state.get('measurement_epoch',1);stage=f'measurement_epoch{epoch}';blocks=[Path(p) for p in state.get('measurement_blocks',[])]
        # Recover a completed block if the controller stopped after writing its
        # checkpoint but before committing the aggregate status transaction.
        for manifest in sorted((d/stage).glob('RF*/block.json')):
            if '.interrupted.' in str(manifest):continue
            rec=json.loads(manifest.read_text())
            if manifest.parent not in blocks and rec['RF_last']<=checkpoint(previous)['cycle']:
                validate_block(manifest.parent,ng,criteria['block_cycles'],gap);blocks.append(manifest.parent)
        blocks.sort(key=lambda p:json.loads((p/'block.json').read_text())['RF_first'])
        if not state.get('history_filled'):
            if stopped():update(status='paused_at_checkpoint');return state
            if checkpoint(previous)['cycle']+2>criteria['maximum_total_cycles']:update(status='total_cycle_limit_reached',reason='History-fill block would exceed total RF cap');return state
            work,cp=execute(2,'history_fill')
            if cp['electrons']==0:update(status='extinguished',reason='Electrons extinct during BRH history fill');return state
            state.pop('reason',None)
            update(history_filled=True,measurement_start_RF=cp['cycle']+1,measurement_start_time_s=cp['time_seconds'],measured_RF=0,measurement_blocks=[])
        passes=state.get('consecutive_passes',0);reset=False
        while True:
            cp=checkpoint(previous)
            if stopped():update(status='paused_at_checkpoint');return state
            if cp['cycle']+criteria['block_cycles']>criteria['maximum_total_cycles']:update(status='total_cycle_limit_reached',reason='Next complete diagnostic block would exceed total RF cap');return state
            if len(blocks)*criteria['block_cycles']>=criteria['maximum_measurement_cycles']:update(status='measurement_limit_reached',reason='Measurement cap reached; background/BRH criteria not all satisfied. Retain checkpoint for extension.');return state
            work,cp=execute(criteria['block_cycles'],stage,True)
            if cp['electrons']==0:update(status='extinguished',reason='Electrons extinct during diagnostic measurement');return state
            validate_block(work,ng,criteria['block_cycles'],gap);blocks.append(work)
            assessment=assess(blocks,history,criteria,gap);put(d/'assessment.json',assessment);put(work/'assessment.json',assessment)
            pooled=d/f'pooled_epoch{epoch}_RF{cp["cycle"]:06d}';pool_native(blocks,pooled)
            # Aggregate BRH/EEDF raw counts, not normalized block distributions.
            from postprocess import process_blocks,compress_block
            brh_summary=process_blocks(d,blocks,assessment);compress_block(work)
            passes=passes+1 if assessment['passed'] else 0
            update(status='running',phase='measurement',measured_RF=len(blocks)*criteria['block_cycles'],measurement_blocks=[str(p) for p in blocks],assessment=assessment,consecutive_passes=passes,pooled_native_path=str(pooled),measurement_summary_path=str(Path(brh_summary['pooled_data_path'])/'summary.json'),data_invalidation_reason=None,pooled_note=f'Measurement RF {state["measurement_start_RF"]}–{cp["cycle"]} ({len(blocks)*criteria["block_cycles"]} RF)',ne_mean_m3=assessment.get('indicators',{}).get('mean_density_e',{}).get('estimate'))
            if passes>=criteria['required_consecutive_passes']:update(status='criteria_met',reason='Background and exploratory BRH fraction/signed-work stopping criteria passed twice. Grid/seed/diagnostic sensitivity checks remain separate.');return state
            # Strong secular profile drift invalidates this measurement epoch.
            drift=max([v['first_last_half_relative_change'] for k,v in assessment.get('indicators',{}).items() if k.startswith('density_profile')]+[0])
            if assessment.get('ready') and drift>criteria['density_profile_relative_tolerance']:
                update(measurement_epoch=epoch+1,history_filled=False,measurement_blocks=[],measured_RF=0,consecutive_passes=0,phase='rewarmup',pooled_native_path=None,measurement_summary_path=None,last_diagnostic_path=None,pooled_note=None,ne_mean_m3=None,
                       data_invalidation_reason='밀도 분포의 장기 변화로 이전 측정 epoch를 제외했습니다. 다시 안정화한 뒤 새 측정 구간을 수집합니다. 원자료는 보존됩니다.',
                       discarded_epoch={'epoch':epoch,'reason':'density-profile secular drift','relative_change':drift,'RF_last':cp['cycle']});reset=True;break
        if reset:
            # Refresh the stationary background, then start a new UID/measurement
            # epoch. Earlier diagnostic blocks remain archived and are excluded.
            while not stationarity(history,criteria)['passed']:
                if stopped():update(status='paused_at_checkpoint');return state
                if checkpoint(previous)['cycle']>=criteria['maximum_total_cycles']:update(status='total_cycle_limit_reached');return state
                work,cp=execute(min(20,criteria['maximum_total_cycles']-checkpoint(previous)['cycle']),'rewarmup')
                if cp['electrons']==0:update(status='extinguished',reason='Extinction during background re-equilibration');return state
            # Discard old companion deliberately: independent new cohort epoch.
            seed=d/f'epoch{epoch+1}_initial';seed.mkdir(exist_ok=True);shutil.copy2(previous,seed/'picdata.bin');previous=seed/'picdata.bin';update(checkpoint_path=str(previous))
