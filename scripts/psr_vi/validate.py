#!/usr/bin/env python3
"""Executed numerical tests on isolated copies; not production plasma results."""
from pathlib import Path
import os,json,subprocess,shutil,hashlib,sys
import numpy as np
from spectral import phasors
from analyze import csv,put
REPO=Path(__file__).resolve().parents[2]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def seed(path,n=128,weight=56000,temperature_eV=3):
    rng=np.random.default_rng(26112660);x=rng.uniform(1e-10,.015-1e-10,n)
    e=np.vstack([x,rng.normal(0,np.sqrt(temperature_eV*1.60217662e-19/9.10938356e-31),(3,n))]);i=np.vstack([x.copy(),rng.normal(0,np.sqrt(1.38064852e-23*350/6.63352090e-26),(3,n))])
    np.r_[0.,0.,float(n),e.ravel(),float(n),i.ravel()].astype('<f8').tofile(path)
def build(path,ng=65,nt=1000,sub=1,diagnostics=1,weight=56000):
    flags=['g++','-std=c++11','-O3','-march=native','-ffp-contract=off',f'-DEDUPIC_GRID_POINTS={ng}',f'-DEDUPIC_STEPS_PER_RF={nt}',f'-DEDUPIC_ION_SUBCYCLING={sub}','-DEDUPIC_GAP_M=0.015','-DEDUPIC_VOLTAGE_V=150',f'-DEDUPIC_WEIGHT={weight}',f'-DEDUPIC_PSR_DIAGNOSTICS={diagnostics}',str(REPO/'C/eduPIC_psr_vi.cc'),'-o',str(path)]
    subprocess.run(flags,check=True,capture_output=True);return flags
def execute(binary,d,count,src):
    d.mkdir(parents=True,exist_ok=False)
    if Path(src).is_dir():
        for name in ['picdata.bin','psr_rng.txt','psr_state.bin']:
            if (src/name).exists():shutil.copy2(src/name,d/name)
    else:shutil.copy2(src,d/'picdata.bin')
    with (d/'run.log').open('w') as f:subprocess.run([str(binary),str(count),'m'],cwd=d,env={**os.environ,'EDUPIC_DIAGNOSTIC_SEED':'26112660'},stdout=f,stderr=subprocess.STDOUT,check=True)
    return d
def validate_fields(d):
    m=json.loads((d/'psr_metadata.json').read_text());a=csv(d/'terminal_timeseries.csv')
    scale=max(abs(a.J_RF_Am2).max(),1.)
    for k in ['current_uniform_max_abs_Am2','ramo_max_abs_Am2','boundary_max_abs_Am2']:assert m[k]/scale<1e-7,(k,m[k],scale)
    assert m['kick_power_max_abs_Wm2']<1e-6*max(1.,abs(a.Pe_Wm2).max())
    assert np.allclose(a.Pe_Wm2,a.Pe_positive_Wm2+a.Pe_negative_Wm2,atol=1e-6)
    assert np.all(a.Pe_positive_Wm2>=0) and np.all(a.Pe_negative_Wm2<=0)
    balance=csv(d/'particle_balance.csv')
    assert np.array_equal(balance.end_e.to_numpy(),(balance.start_e+balance.ionizations-balance.e_loss_lower-balance.e_loss_upper).to_numpy())
    assert np.array_equal(balance.end_i.to_numpy(),(balance.start_i+balance.ionizations-balance.i_loss_lower-balance.i_loss_upper).to_numpy())
    dt=1/(m['frequency_Hz']*m['steps_per_RF'])
    for col,native in [('Pe_Wm2','e_field_work_J'),('Pi_Wm2','i_field_work_J')]:assert np.isclose(a[col].sum()*dt*m['A_sim_m2'],balance[native].sum(),rtol=1e-9,atol=1e-16)
    return {k:m[k] for k in ['current_uniform_max_abs_Am2','ramo_max_abs_Am2','boundary_max_abs_Am2','kick_power_max_abs_Wm2','full_energy_residual_Jm2']}
def main(root):
    root.mkdir(parents=True,exist_ok=False);source=root/'seed.bin';seed(source);empty=root/'vacuum.bin';np.array([0.,0.,0.,0.],dtype='<f8').tofile(empty)
    binary=root/'solver';flags=build(binary);off=root/'off';build(off,diagnostics=0)
    full=execute(binary,root/'full2',2,source);one=execute(binary,root/'split1',1,source);split=execute(binary,root/'split2',1,one);disabled=execute(off,root/'disabled2',2,source)
    identity={n:sha(full/n)==sha(split/n) for n in ['picdata.bin','psr_rng.txt','psr_state.bin']};assert all(identity.values()),identity
    passive={n:sha(full/n)==sha(disabled/n) for n in ['picdata.bin','psr_rng.txt','conv.dat','particle_balance.csv']};assert all(passive.values()),passive
    numerical=validate_fields(full);vac=execute(binary,root/'vacuum',1,empty);validate_fields(vac)
    a=csv(vac/'terminal_timeseries.csv');v=phasors(a.t_terminal_s,a.V_gap_V.to_numpy(),60e6,10)[1];j=phasors(a.t_terminal_s,a.J_RF_Am2.to_numpy(),60e6,10)[1]
    expected=8.85418781e-12/.015*2*np.pi*60e6*150
    assert abs(abs(j)/expected-1)<2e-5
    assert abs(np.degrees(np.angle(j/v))-90)<1e-6
    assert abs(np.mean(a.V_gap_V*a.J_RF_Am2))<1e-6
    # N_SUB=40 is deliberately not accepted for primary high-frequency inference.
    old=root/'sub40_solver';build(old,sub=40);s40=execute(old,root/'sub40',2,source);m40=json.loads((s40/'psr_metadata.json').read_text())
    result={'passed':True,'source_SHA256':sha(REPO/'C/eduPIC_psr_vi.cc'),'diagnostic_header_SHA256':sha(REPO/'C/psr_vi_diagnostics.hpp'),'compiler_command':flags,'passive_byte_identity':passive,'split_restart_byte_identity':identity,'plasma_2RF_numerical_checks':numerical,'vacuum':{'current_peak_Am2':float(abs(j)),'expected_peak_Am2':expected,'phase_lead_deg':float(np.degrees(np.angle(j/v))),'mean_VJ_Wm2':float(np.mean(a.V_gap_V*a.J_RF_Am2))},'subcycling40_ramo_error_Am2':m40['ramo_max_abs_Am2'],'production_subcycling':1,'scope':'Synthetic spectral tests + vacuum + low-density 128-particle 2RF plasma copies. Not stationary production plasma, not full grid/particle/seed convergence.'}
    put(root/'validation.json',result);print(json.dumps(result,indent=2))
if __name__=='__main__':main(Path(sys.argv[1]).resolve())
