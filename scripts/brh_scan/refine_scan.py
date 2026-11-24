#!/usr/bin/env python3
"""Add missing gaps with identical physics; reference existing cases explicitly."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import argparse,copy,json,math,shutil,subprocess
import numpy as np
from common import put,sha
from prepare import seed_case

def prepare(previous,root,gaps):
    if root.exists():raise ValueError('New refinement folder must not already exist; use run_scan.py to resume')
    old=json.loads((previous/'config.json').read_text());criteria=json.loads((previous/'criteria.json').read_text())
    today=datetime.now(ZoneInfo('Asia/Seoul'));tag=today.strftime('%y%m%d')
    if not root.name.startswith(tag+'_'):raise ValueError('Folder date must be the actual preparation date in Asia/Seoul')
    root.mkdir(parents=True)
    for name in ['source_control.cc','source_brh.cc','brh_diagnostics.hpp','reference40.bin','criteria.json','LICENSE','diagnostics_validated.json','measurement_engine_validated.json']:
        if (previous/name).exists():shutil.copy2(previous/name,root/name)
    gate=json.loads((root/'diagnostics_validated.json').read_text())
    assert gate['passed'] and sha(root/'source_brh.cc')==gate['source_SHA256'] and sha(root/'brh_diagnostics.hpp')==gate['header_SHA256']
    assert sha(root/'source_control.cc')==old['control_source_SHA256']
    reuse={};new=[]
    for g in gaps:
        if g in old['gaps_mm']:
            origin=old.get('case_sources',{}).get(str(g),{})
            reuse[str(g)]=origin or {'path':str(previous/f'{g}mm'),'run_id':old['id'],'date':old['date'],'source_root':str(previous)}
        else:new.append(g)
    cfg=copy.deepcopy(old);cfg.update(id=root.name,date=today.date().isoformat(),started_at_Asia_Seoul=today.isoformat(),
        gaps_mm=gaps,run_gaps_mm=new,case_sources=reuse,max_workers=4,total_solver_slots=4,compress_native_text=True,
        capacity_reservations=[{'root':str(previous),'gaps_mm':old['gaps_mm']}],
        parent_scan={'id':old['id'],'root':str(previous),'criteria_SHA256':sha(previous/'criteria.json')},
        validation_origin={'run_id':old['id'],'note':'Same exact native source/header and compiler flags; original passivity/restart gate retained; new-gap smoke recorded separately.'},
        reference_checkpoint_path=str(root/'reference40.bin'),initial_seed_base=261123000,
        parallelism_note='Four solver slots total, reserving slots for unfinished cases of the earlier scan; expand new concurrency as earlier cases terminate.')
    put(root/'config.json',cfg)
    for gap in new:
        d=root/f'{gap}mm';d.mkdir();ng=math.ceil(gap*.001/cfg['dx_target_m'])+1
        arr=seed_case(root/'reference40.bin',gap*.001,ng,np.random.default_rng(cfg['initial_seed_base']+gap));arr.tofile(d/'input_cycle0.bin')
        flags=['g++','-std=c++11','-O3','-march=native','-ffp-contract=off',f'-DEDUPIC_GAP_M={gap/1000:.9f}',f'-DEDUPIC_GRID_POINTS={ng}',f'-DEDUPIC_WEIGHT={cfg["weight"]:.1f}',str(root/'source_control.cc'),'-o',str(d/'solver_warm')]
        subprocess.run(flags,check=True,capture_output=True)
        put(d/'status.json',{'gap_mm':gap,'grid_points':ng,'weight':cfg['weight'],'compile_command':flags,
            'initial_SHA256':sha(d/'input_cycle0.bin'),'initial_e':int(arr[2]),'status':'queued','phase':'warmup','checkpoint_cycle':0,'measured_RF':0,
            'elapsed_solver_seconds':0.,'source_SHA256':cfg['control_source_SHA256'],'execution_date':cfg['date']})
        print('Prepared new gap',gap,'mm; grid',ng,flush=True)
    assert json.loads((root/'criteria.json').read_text())==criteria
    print('Reused gaps:',list(map(int,reuse)), 'New gaps:',new,flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('previous',type=Path);p.add_argument('root',type=Path)
    p.add_argument('--start',type=int,default=20);p.add_argument('--stop',type=int,default=80);p.add_argument('--step',type=int,default=5)
    a=p.parse_args();assert a.step>0 and a.start>0 and a.stop>=a.start
    prepare(a.previous.resolve(),a.root.resolve(),list(range(a.start,a.stop+1,a.step)))
