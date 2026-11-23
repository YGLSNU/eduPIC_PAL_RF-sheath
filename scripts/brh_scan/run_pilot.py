#!/usr/bin/env python3
"""An explicitly short 40 mm diagnostic, independent of main scan convergence."""
from pathlib import Path
import argparse,json,os,shutil,subprocess,time
import numpy as np
from common import checkpoint,put,sha
from measurement import validate_block,pool_native,now
from postprocess import process_blocks
from brh_stats import assess

def main():
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);a=p.parse_args();root=a.root.resolve();d=root/'pilot40mm';d.mkdir(exist_ok=False)
    src=json.loads((root/'40mm/status.json').read_text());previous=Path(src.get('checkpoint_path',root/'40mm/input_cycle0.bin'));start_cp=checkpoint(previous)
    state={'gap_mm':40,'grid_points':641,'weight':112000,'status':'running','phase':'pilot','checkpoint_cycle':start_cp['cycle'],'measured_RF':0,'checkpoint_path':str(previous),'pilot_initial_checkpoint':start_cp,'started_at_Asia_Seoul':now(),'reason':'Short 20 RF validation pilot; main gap scan convergence criteria have NOT been met.'};put(d/'status.json',state)
    flags=['g++','-std=c++11','-O3','-march=native','-ffp-contract=off','-DEDUPIC_GAP_M=0.04','-DEDUPIC_GRID_POINTS=641','-DEDUPIC_WEIGHT=112000.0',str(root/'source_brh.cc'),'-o',str(d/'solver_brh')];subprocess.run(flags,check=True)
    epoch_time=None;blocks=[];history=[]
    for count,name,measuring in [(2,'history_fill',False),(20,'measurement',True)]:
        old=checkpoint(previous);work=d/name;work.mkdir();shutil.copy2(previous,work/'picdata.bin')
        for f in ['brh_state.bin','brh_rng.txt']:
            if (previous.parent/f).exists():shutil.copy2(previous.parent/f,work/f)
        env={**os.environ,'EDUPIC_DIAGNOSTIC_SEED':'2611234040'}
        if measuring:env['EDUPIC_BRH_MEASUREMENT_START_S']=format(epoch_time,'.17g')
        begin=time.monotonic()
        with (work/'run.log').open('w') as log:
            proc=subprocess.Popen([str(d/'solver_brh'),str(count)]+(['m'] if measuring else []),cwd=work,stdout=log,stderr=subprocess.STDOUT,env=env,start_new_session=True)
            state.update(solver_pid=proc.pid,active_RF=[old['cycle']+1,old['cycle']+count],updated_at_Asia_Seoul=now());put(d/'status.json',state);ret=proc.wait()
        assert ret==0,ret;cp=checkpoint(work/'picdata.bin');previous=work/'picdata.bin';epoch_time=cp['time_seconds'];assert cp['electrons']>0
        history.extend(np.loadtxt(work/'conv.dat',ndmin=2).tolist());put(work/'block.json',{'stage':'short_pilot','RF_first':old['cycle']+1,'RF_last':cp['cycle'],'input':old,'output':cp,'wall_seconds':time.monotonic()-begin,'source_SHA256':sha(root/'source_brh.cc'),'header_SHA256':sha(root/'brh_diagnostics.hpp')})
        state.update(checkpoint_cycle=cp['cycle'],checkpoint_path=str(previous),electrons=cp['electrons'],ions=cp['ions'],updated_at_Asia_Seoul=now());put(d/'status.json',state)
        if measuring:blocks.append(work);validate_block(work,641,20,40)
    assessment=assess(blocks,history,json.loads((root/'criteria.json').read_text()),40);pool_native(blocks,d/'pooled');process_blocks(d,blocks,assessment)
    np.savetxt(d/'history.dat',history,fmt='%d');state.update(status='diagnostic',phase='short_pilot_complete',measured_RF=20,measurement_blocks=[str(p) for p in blocks],pooled_native_path=str(d/'pooled'),pooled_note=f'Short diagnostic RF {start_cp["cycle"]+3}–{cp["cycle"]} (20 RF; not convergence-qualified)',updated_at_Asia_Seoul=now());put(d/'status.json',state)
    print('Pilot complete:',d,flush=True)

if __name__=='__main__':main()
