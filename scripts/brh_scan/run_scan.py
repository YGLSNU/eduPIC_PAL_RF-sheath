#!/usr/bin/env python3
"""Recoverable BRH scan. Raw simulation runs locally; publication is separate."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime
from zoneinfo import ZoneInfo
import argparse,csv,fcntl,json,os,shutil,subprocess,time,traceback
import numpy as np
from common import checkpoint,put,sha,stationarity

def now():return datetime.now(ZoneInfo('Asia/Seoul')).isoformat()
def run_case(root,gap):
    d=root/f'{gap}mm';cfg=json.loads((root/'config.json').read_text());criteria=json.loads((root/'criteria.json').read_text())
    lock=(d/'controller.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    state=json.loads((d/'status.json').read_text())
    if state['status'] in ['criteria_met','extinguished','measurement_limit_reached','total_cycle_limit_reached']:return state
    def update(**kw):state.update(kw,updated_at_Asia_Seoul=now());put(d/'status.json',state)
    try:
        previous=Path(state.get('checkpoint_path',str(d/'input_cycle0.bin')));cp=checkpoint(previous)
        history=np.loadtxt(d/'history.dat',ndmin=2).tolist() if (d/'history.dat').exists() else []
        update(status='running',phase=state.get('phase','warmup'),started_at_Asia_Seoul=state.get('started_at_Asia_Seoul',now()),controller_pid=os.getpid())
        while state['phase']=='warmup':
            if (root/'STOP_AFTER_BLOCK').exists() or (d/'STOP_AFTER_BLOCK').exists():update(status='paused_at_checkpoint');return state
            if cp['electrons']==0:update(status='extinguished',first_zero_electron_RF=cp['cycle'],reason='No electrons remain. Steady-discharge EEDF/BRH diagnostics are undefined.');return state
            if cp['cycle']>=criteria['maximum_total_cycles']:update(status='total_cycle_limit_reached');return state
            stable=stationarity(history,criteria)
            if stable['passed']:
                update(phase='measurement',stationarity=stable,measurement_start_RF=cp['cycle']+1);break
            # One diagnostic RF every 100 RF; otherwise amortize startup over up to 49 RF.
            diagnostic=cp['cycle']%100==99;count=1 if diagnostic else min(49,99-cp['cycle']%100)
            start=cp['cycle']+1;end=cp['cycle']+count;work=d/'warmup'/f'RF{start:06d}-{end:06d}'
            if work.exists():work.rename(work.with_name(work.name+'.interrupted.'+str(time.time_ns())))
            work.mkdir(parents=True);shutil.copy2(previous,work/'picdata.bin')
            seed=261123000+gap*100000+start
            update(active_RF=[start,end],stationarity=stable)
            begin=time.monotonic()
            with (work/'run.log').open('w') as log:
                proc=subprocess.Popen(['stdbuf','-oL',str(d/'solver_warm'),str(count)]+(['m'] if diagnostic else []),cwd=work,stdout=log,stderr=subprocess.STDOUT,env={**os.environ,'EDUPIC_DIAGNOSTIC_SEED':str(seed)},start_new_session=True)
                update(solver_pid=proc.pid);ret=proc.wait()
            elapsed=time.monotonic()-begin
            if ret:raise RuntimeError(f'Solver exit {ret}; complete previous checkpoint preserved')
            out=checkpoint(work/'picdata.bin');conv=np.loadtxt(work/'conv.dat',ndmin=2)
            actual=out['cycle']-cp['cycle'];assert len(conv)==actual and actual<=count
            assert actual==count or out['electrons']==0
            record={'stage':'warmup','RF_first':start,'RF_last':out['cycle'],'requested_RF':count,'diagnostic':diagnostic,'seed':seed,'input':cp,'output':out,'wall_seconds':elapsed,'source_SHA256':cfg['control_source_SHA256']}
            put(work/'block.json',record);history.extend(conv.tolist())
            tmp=d/'history.dat.tmp';np.savetxt(tmp,history,fmt='%d');tmp.replace(d/'history.dat')
            previous=work/'picdata.bin';cp=out
            update(checkpoint_cycle=cp['cycle'],checkpoint_path=str(previous),electrons=cp['electrons'],ions=cp['ions'],elapsed_solver_seconds=state.get('elapsed_solver_seconds',0)+elapsed,
                   last_block_seconds=elapsed,last_RF_seconds=elapsed/max(actual,1),last_diagnostic_path=str(work) if diagnostic and out['electrons']>0 else state.get('last_diagnostic_path'))
            print(now(),gap,'mm warmup RF',cp['cycle'],'Ne',cp['electrons'],'s/RF',round(elapsed/max(actual,1),2),flush=True)
        while not (root/'diagnostics_validated.json').exists():
            update(status='running',phase='waiting_for_diagnostics');time.sleep(15)
            if (root/'STOP_AFTER_BLOCK').exists():update(status='paused_at_checkpoint');return state
        update(phase='measurement')
        from measurement import measure_case
        return measure_case(root,d,state,previous,history)
    except Exception as exc:
        update(status='paused_error',error=str(exc));(d/'error.log').write_text(traceback.format_exc());print('ERROR',gap,exc,flush=True);return state

def main():
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('--gaps',type=int,nargs='*');a=p.parse_args();root=a.root.resolve()
    lock=(root/'controller.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    (root/'controller_finished.json').unlink(missing_ok=True)
    cfg=json.loads((root/'config.json').read_text());gaps=a.gaps or [40,60,100,120,30,50,80,25]
    put(root/'controller.json',{'pid':os.getpid(),'started_at_Asia_Seoul':now(),'gaps_mm':gaps,'max_workers':cfg['max_workers']})
    with ThreadPoolExecutor(max_workers=cfg['max_workers']) as pool:
        futures=[pool.submit(run_case,root,g) for g in gaps]
        for future in as_completed(futures):future.result()
    put(root/'controller_finished.json',{'finished_at_Asia_Seoul':now()})

if __name__=='__main__':main()
