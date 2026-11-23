#!/usr/bin/env python3
"""Physical passivity and exact restart continuity of particle diagnostics."""
from pathlib import Path
import argparse,json,os,shutil,subprocess,time
import numpy as np
from common import put,sha

def main():
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);a=p.parse_args();r=a.root.resolve();v=r/'validation'/(sha(r/'brh_diagnostics.hpp')[:8]+'_'+sha(__file__)[:8]);v.mkdir(exist_ok=True,parents=True)
    flags=['g++','-std=c++11','-O3','-march=native','-ffp-contract=off','-DEDUPIC_GAP_M=0.04','-DEDUPIC_GRID_POINTS=641','-DEDUPIC_WEIGHT=112000.0']
    for name in ['control','brh']:
        subprocess.run(flags+[str(r/f'source_{name}.cc'),'-o',str(v/name)],check=True)
    def run(name,solver,cycles,previous=None,measure=True):
        d=v/name;d.mkdir(exist_ok=False)
        shutil.copy2(previous/'picdata.bin' if previous else r/'40mm/input_cycle0.bin',d/'picdata.bin')
        for f in ['brh_state.bin','brh_rng.txt']:
            if previous and (previous/f).exists():shutil.copy2(previous/f,d/f)
        with (d/'run.log').open('w') as out:
            subprocess.run([str(v/solver),str(cycles)]+(['m'] if measure else []),cwd=d,stdout=out,stderr=subprocess.STDOUT,check=True,env={**os.environ,'EDUPIC_DIAGNOSTIC_SEED':'26112340','EDUPIC_BRH_MEASUREMENT_START_S':'0'})
        return d
    c=run('control1','control',1);b=run('brh1','brh',1)
    same={f:sha(c/f)==sha(b/f) for f in ['picdata.bin','conv.dat','particle_balance.csv','ne_xt.dat','ni_xt.dat','ioniz_xt.dat','powere_xt.dat'] if (c/f).exists() and (b/f).exists()}
    assert same.get('picdata.bin') and same.get('ne_xt.dat') and all(same.values()),same
    whole=run('whole4','brh',4);one=run('split2','brh',2);two=run('split4','brh',2,previous=one)
    restart={f:sha(whole/f)==sha(two/f) for f in ['picdata.bin','brh_rng.txt']}
    assert all(restart.values()),restart
    interval_events={}
    for f in ['brh_roundtrips.csv','brh_encounters.csv']:
        lines=(one/f).read_text().splitlines()+(two/f).read_text().splitlines()[1:]
        interval_events[f]=(whole/f).read_text().splitlines()==lines
    for f in ['brh_hist_E_counts.bin','brh_hist_Ex_counts.bin']:
        interval_events[f]=bool(np.array_equal(np.fromfile(whole/f,dtype='<u8'),np.fromfile(one/f,dtype='<u8')+np.fromfile(two/f,dtype='<u8')))
    assert all(interval_events.values()),interval_events
    # State contains native C++ struct padding; compare restart by its physical
    # continuation and RNG, not incidental padding bytes.
    w5=run('whole5','brh',1,previous=whole);s5=run('split5','brh',1,previous=two)
    continuation={f:sha(w5/f)==sha(s5/f) for f in ['picdata.bin','brh_roundtrips.csv','brh_encounters.csv','brh_hist_E_counts.bin','brh_work_sum_eV.bin']}
    assert all(continuation.values()),continuation
    ledger=json.loads((w5/'brh_meta.json').read_text())['maximum_return_energy_ledger_residual_eV']
    assert ledger<1e-8,ledger
    result={'passed':True,'passive_one_RF_byte_identity':same,'four_RF_split_restart_byte_identity':restart,'internal_boundary_events_and_raw_histograms':interval_events,'fifth_RF_continuation_byte_identity':continuation,'maximum_return_energy_ledger_residual_eV':ledger,'source_SHA256':sha(r/'source_brh.cc'),'header_SHA256':sha(r/'brh_diagnostics.hpp'),'compiler_flags':flags,'note':'Passivity and restart tests at 40 mm. This does not establish physical BRH, gap/seed convergence, or grid independence.'}
    put(r/'diagnostics_validated.json',result);print(json.dumps(result,indent=2),flush=True)

if __name__=='__main__':main()
