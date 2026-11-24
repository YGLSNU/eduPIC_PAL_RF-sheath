#!/usr/bin/env python3
"""One-RF native passivity and storage roundtrip at an added gap; not science data."""
from pathlib import Path
import argparse,json,os,shutil,subprocess
from datetime import datetime
from zoneinfo import ZoneInfo
from common import put,sha
from measurement import validate_block
from postprocess import compress_block

def main():
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('--gap',type=int,default=35);a=p.parse_args()
    r=a.root.resolve();case=r/f'{a.gap}mm';state=json.loads((case/'status.json').read_text());v=r/'validation_new_gap'/f'{a.gap}mm'
    v.mkdir(parents=True,exist_ok=False)
    flags=['g++','-std=c++11','-O3','-march=native','-ffp-contract=off',f'-DEDUPIC_GAP_M={a.gap/1000:.9f}',f'-DEDUPIC_GRID_POINTS={state["grid_points"]}','-DEDUPIC_WEIGHT=112000.0']
    subprocess.run(flags+[str(r/'source_brh.cc'),'-o',str(v/'solver_brh')],check=True)
    env={**os.environ,'EDUPIC_DIAGNOSTIC_SEED':str(261123000+a.gap*100000+1),'EDUPIC_BRH_MEASUREMENT_START_S':'0'}
    for name,binary in [('control',case/'solver_warm'),('diagnostic',v/'solver_brh')]:
        d=v/name;d.mkdir();shutil.copy2(case/'input_cycle0.bin',d/'picdata.bin')
        with (d/'run.log').open('w') as log:subprocess.run([str(binary),'1','m'],cwd=d,stdout=log,stderr=subprocess.STDOUT,env=env,check=True)
    names=['picdata.bin','conv.dat','particle_balance.csv','ne_xt.dat','ni_xt.dat','ioniz_xt.dat','powere_xt.dat']
    same={n:sha(v/'control'/n)==sha(v/'diagnostic'/n) for n in names};assert all(same.values()),same
    before=validate_block(v/'diagnostic',state['grid_points'],1,a.gap)
    compress_block(v/'diagnostic',native=True)
    after=validate_block(v/'diagnostic',state['grid_points'],1,a.gap);assert before==after
    result={'passed':True,'run_id':r.name,'gap_mm':a.gap,'RF_cycles':1,'source_SHA256':sha(r/'source_brh.cc'),'header_SHA256':sha(r/'brh_diagnostics.hpp'),
            'native_byte_identity':same,'numeric_validation_before_and_after_lossless_storage':after,'compiler_flags':flags,
            'checked_at_Asia_Seoul':datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),
            'scope':'Separate one-RF validation only; excluded from physical gap statistics. Original 40mm exact split-restart tests remain applicable to unchanged source.'}
    put(r/'new_gap_validation.json',result);print(json.dumps(result,indent=2),flush=True)

if __name__=='__main__':main()
