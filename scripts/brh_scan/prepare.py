#!/usr/bin/env python3
"""Prepare isolated, geometry-consistent BRH gap cases from a saved reference."""
from pathlib import Path
import argparse,hashlib,json,math,shutil,subprocess
from datetime import datetime
from zoneinfo import ZoneInfo
import numpy as np
from scipy.linalg import solve_banded

REPO=Path(__file__).resolve().parents[2]
REFERENCE=Path('/workspace/edupic-results/2026-11-20_Ar_20mTorr_100-250-300-400-500V_13.56MHz_40mm_topRF')

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def put(p,m):Path(p).write_text(json.dumps(m,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def read_checkpoint(p):
    a=np.fromfile(p,dtype='<f8');n=int(a[2]);ni=int(a[3+4*n]);assert len(a)==4+4*(n+ni)
    return a[:2].copy(),a[3:3+4*n].reshape(4,n).copy(),a[4+4*n:].reshape(4,ni).copy()

def field(e,i,L,ng,weight,voltage=250.):
    dx=L/(ng-1);charge=1.60217662e-19;epsilon=8.85418781e-12;dens=[]
    for a in [e,i]:
        c=a[0]/dx;p=np.minimum(c.astype(int),ng-2);f=c-p
        n=np.bincount(p,weights=1-f,minlength=ng)+np.bincount(p+1,weights=f,minlength=ng)
        n*=weight/(1e-4*dx);n[[0,-1]]*=2;dens.append(n)
    rho=charge*(dens[1]-dens[0]);ab=np.zeros((3,ng-2));ab[0,1:]=1;ab[1]=-2;ab[2,:-1]=1
    rhs=-rho[1:-1]*dx*dx/epsilon;rhs[-1]-=voltage
    pot=np.zeros(ng);pot[-1]=voltage;pot[1:-1]=solve_banded((1,1),ab,rhs)
    E=np.empty(ng);E[1:-1]=(pot[:-2]-pot[2:])/(2*dx)
    E[0]=(pot[0]-pot[1])/dx-rho[0]*dx/(2*epsilon);E[-1]=(pot[-2]-pot[-1])/dx+rho[-1]*dx/(2*epsilon)
    return E

def seed_case(cp,L,ng,rng,weight=112000.,nt=8000):
    _,e,i=read_checkpoint(cp);oldL=.04;oldgrid=640;freq=13.56e6
    Eold=field(e,i,oldL,oldgrid,112000.)
    # Reconstruct integer-position-time velocities before changing the leapfrog step.
    for a,mass,charge,dt in [(e,9.10938356e-31,-1.60217662e-19,1/freq/4000),(i,6.63352090e-26,1.60217662e-19,20/freq/4000)]:
        a[1]+=charge/mass*np.interp(a[0],np.linspace(0,oldL,oldgrid),Eold)*dt/2
    values=[]
    for a in [e,i]:
        n=int(round(a.shape[1]*L/oldL*112000/weight))
        if n==a.shape[1]:b=a.copy()
        else:
            k=n//a.shape[1];rem=n%a.shape[1]
            ids=np.concatenate([np.tile(np.arange(a.shape[1]),k),rng.choice(a.shape[1],rem,replace=False)])
            rng.shuffle(ids);b=a[:,ids].copy()
        b[0]*=L/oldL
        if L!=oldL:
            b[0]+=rng.uniform(-.2,.2,n)*L/(ng-1)
            b[0]=np.clip(b[0],1e-12,L-1e-12)
            # Separate exact resampling clones; all initialization transients are discarded.
            b[1:]+=rng.normal(0,.002*np.std(b[1:]),b[1:].shape)
        values.append(b)
    en,ion=values;Enew=field(en,ion,L,ng,weight)
    for a,mass,charge,dt in [(en,9.10938356e-31,-1.60217662e-19,1/freq/nt),(ion,6.63352090e-26,1.60217662e-19,20/freq/4000)]:
        a[1]-=charge/mass*np.interp(a[0],np.linspace(0,L,ng),Enew)*dt/2
    return np.concatenate([[0.,0.,en.shape[1]],en.ravel(),[ion.shape[1]],ion.ravel()]).astype('<f8')

def main():
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('--source',type=Path,help='40mm optical-depth source (or published source_control.cc)');p.add_argument('--checkpoint',type=Path,help='Original 40mm 4000-step/RF, 640-grid reference40.bin; not a new BRH checkpoint');args=p.parse_args();root=args.root.resolve();root.mkdir(parents=True,exist_ok=True)
    if (root/'config.json').exists():raise SystemExit('Already prepared; use run_scan.py to resume existing work')
    source_path=args.source or REFERENCE/'source-eduPIC.cc';source=source_path.read_text()
    source=source.replace('const int        N_T            = 4000;', '#ifndef EDUPIC_STEPS_PER_RF\n#define EDUPIC_STEPS_PER_RF 8000\n#endif\nconst int        N_T            = EDUPIC_STEPS_PER_RF;')
    source=source.replace('const int        N_SUB          = 20;', '#ifndef EDUPIC_ION_SUBCYCLING\n#define EDUPIC_ION_SUBCYCLING 40\n#endif\nconst int        N_SUB          = EDUPIC_ION_SUBCYCLING;')
    source=source.replace('const int N_BIN                     = 20;', 'const int N_BIN                     = N_T / 200;')
    (root/'source_control.cc').write_text(source)
    if args.checkpoint:cp=args.checkpoint.resolve()
    else:
        status=json.loads((REFERENCE/'250V/status.json').read_text());cp=REFERENCE/'250V'/status['latest_block']/'picdata.bin'
    shutil.copy2(cp,root/'reference40.bin');shutil.copy2(REPO/'LICENSE',root/'LICENSE')
    settings={'id':'261123_BRH_gap25-120','date':'2026-11-23','started_at_Asia_Seoul':datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),
        'gas':'Ar','pressure_mTorr':20,'temperature_K':350,'frequency_Hz':13.56e6,'voltage_peak_V':250,
        'gaps_mm':[25,30,40,50,60,80,100,120],'weight':112000.,'fictive_area_m2':1e-4,'dx_target_m':6.25e-5,
        'electron_steps_per_RF':8000,'phase_bins':200,'ion_subcycling':40,'max_workers':4,
        'source_reference_SHA256':sha(source_path),'reference_checkpoint_SHA256':sha(cp),
        'reference_checkpoint_path':str(cp),'control_source_SHA256':sha(root/'source_control.cc'),
        'initialization':'40 mm 250 V converged particle distribution resampled to keep common initial physical density and constant macroparticle weight; x stretched, clone jitter; leapfrog velocities synchronized and restaggered. All changed-condition transients excluded.',
        'surface':'absorbing material walls; no SEE or material reflection','electron_MCC':'same residual optical-depth Ar ground-state MCC at all gaps; at most one event per step','Coulomb_binary_collisions':False}
    put(root/'config.json',settings)
    criteria_path=source_path.parent/'criteria.json'
    if not criteria_path.exists():criteria_path=REFERENCE/'criteria.json'
    criteria=json.loads(criteria_path.read_text());criteria['minimum_measurement_cycles']=200
    criteria.update(BRH_fraction_relative_tolerance=.1,BRH_fraction_absolute_tolerance=.005,BRH_phase_return_window_RF=.1,BRH_required_consecutive_round_trips=2,BRH_work_relative_tolerance=.1,BRH_work_absolute_tolerance_eV=.1,BRH_minimum_candidate_returns=100,BRH_minimum_candidate_UIDs=30)
    put(root/'criteria.json',criteria)
    for gap in settings['gaps_mm']:
        d=root/f'{gap}mm';d.mkdir();ng=math.ceil(gap*.001/settings['dx_target_m'])+1
        arr=seed_case(cp,gap*.001,ng,np.random.default_rng(261123000+gap));arr.tofile(d/'input_cycle0.bin')
        flags=['g++','-std=c++11','-O3','-march=native','-ffp-contract=off',f'-DEDUPIC_GAP_M={gap/1000:.9f}',f'-DEDUPIC_GRID_POINTS={ng}',f'-DEDUPIC_WEIGHT={settings["weight"]:.1f}',str(root/'source_control.cc'),'-o',str(d/'solver_warm')]
        subprocess.run(flags,check=True,capture_output=True)
        case={'gap_mm':gap,'grid_points':ng,'weight':settings['weight'],'compile_command':flags,'initial_SHA256':sha(d/'input_cycle0.bin'),'initial_e':int(arr[2]),'status':'queued','phase':'warmup','checkpoint_cycle':0,'measured_RF':0,'elapsed_solver_seconds':0.,'source_SHA256':sha(root/'source_control.cc')}
        put(d/'status.json',case);print('Prepared',gap,'mm, grid',ng,'electrons',int(arr[2]),flush=True)
    print('Prepared all gap cases in',root,flush=True)

if __name__=='__main__':main()
