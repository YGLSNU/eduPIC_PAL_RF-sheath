"""Block-level exploratory uncertainty; trajectories within a block are correlated."""
from pathlib import Path
import csv,json
import numpy as np
from scipy.stats import t as student_t
from common import stationarity

FIELDS=['ne','ni','je','ji','efield']
def read_table(path):
    path=Path(path)
    if not path.exists() and Path(str(path)+'.gz').exists():path=Path(str(path)+'.gz')
    if not path.exists():return np.empty(0)
    # Every numeric identifier here is far below 2**53.
    a=np.genfromtxt(path,delimiter=',',names=True)
    return np.atleast_1d(a)

def half_width(pseudo):
    a=np.asarray(pseudo);n=len(a)
    if n<2:return np.full(a.shape[1:],np.inf)
    dev=a-a.mean(axis=0);denom=np.sum(dev*dev);rhos=[]
    if denom>0:
        for lag in range(1,min(4,n//2)+1):
            rho=float(np.sum(dev[:-lag]*dev[lag:])/denom)
            if rho<=0:break
            rhos.append(rho)
    return student_t.ppf(.975,n-1)*a.std(axis=0,ddof=1)/np.sqrt(n)*np.sqrt(1+2*sum(rhos))

def ratio_indicator(numerators,denominators):
    x=np.asarray(numerators,dtype=float);d=np.asarray(denominators,dtype=float);n=len(x)
    if n<2 or d.sum()<=0 or np.any(d.sum()-d<=0):return {'estimate':None,'half_width':None,'first_last_change':None,'passed_data':False}
    estimate=x.sum()/d.sum();leave=(x.sum()-x)/(d.sum()-d);pseudo=n*estimate-(n-1)*leave
    half=float(half_width(pseudo));h=n//2
    first=x[:h].sum()/max(d[:h].sum(),1e-300);last=x[-h:].sum()/max(d[-h:].sum(),1e-300)
    result={'estimate':float(estimate),'half_width':half,'first_last_change':float(abs(last-first)),'passed_data':True}
    if n//2>=5:
        used=n-n%2;paired=ratio_indicator(x[:used].reshape(-1,2).sum(1),d[:used].reshape(-1,2).sum(1))
        if paired['half_width'] is not None:result['half_width']=max(half,paired['half_width'])
    return result

def return_stats(blocks,criteria):
    rows=[];all_uid=set();candidate_uid=set()
    for p in blocks:
        a=read_table(p/'brh_roundtrips.csv')
        if not len(a):rows.append([0,0,0]);continue
        a=a[a['side']==1];candidate=(a['near_fundamental']>0)&(a['consecutive_returns']>=criteria['BRH_required_consecutive_round_trips'])
        all_uid.update(a['uid'].astype(int).tolist());candidate_uid.update(a['uid'][candidate].astype(int).tolist())
        rows.append([len(a),int(candidate.sum()),float(a['W_field_eV'][candidate].sum())])
    rows=np.array(rows);total=float(rows[:,0].sum());nc=int(rows[:,1].sum())
    fraction=ratio_indicator(rows[:,1],rows[:,0]);work=ratio_indicator(rows[:,2],rows[:,1]);nf=len(all_uid);ncf=len(candidate_uid)
    # A zero sample variance is not proof of zero rare events. A conservative
    # rule-of-three term uses distinct parent UIDs instead of raw timesteps.
    if fraction['half_width'] is not None:fraction['half_width']=max(fraction['half_width'],3/max(nf,1))
    frac_tol=max(criteria['BRH_fraction_absolute_tolerance'],criteria['BRH_fraction_relative_tolerance']*abs(fraction['estimate'] or 0))
    work_tol=max(criteria.get('BRH_work_absolute_tolerance_eV',.1),criteria.get('BRH_work_relative_tolerance',.1)*abs(work['estimate'] or 0))
    frac_ok=fraction['passed_data'] and total>=1000 and nf>=100 and max(fraction['half_width'],fraction['first_last_change'])<=frac_tol
    work_ok=work['passed_data'] and nc>=criteria.get('BRH_minimum_candidate_returns',100) and ncf>=criteria.get('BRH_minimum_candidate_UIDs',30) and max(work['half_width'],work['first_last_change'])<=work_tol
    return {'powered_side_returns':int(total),'candidate_returns':nc,'distinct_return_UIDs':nf,'distinct_candidate_UIDs':ncf,
        'candidate_return_fraction':fraction,'candidate_signed_work_eV':work,'fraction_tolerance':frac_tol,'work_tolerance_eV':work_tol,
        'fraction_passed':bool(frac_ok),'work_passed':bool(work_ok),'passed':bool(frac_ok and work_ok),
        'note':'Fractions are among detected complete powered-side round trips, not a density fraction. Block/40-RF estimates include dependence heuristically; rare-tail/model/grid error is separate.'}

def assess(blocks,history,criteria,gap_mm):
    n=len(blocks);base={'passed':False,'measurement_cycles':n*criteria['block_cycles'],'completed_blocks':n,'particle_count_stationarity':stationarity(history,criteria)}
    if n<2:return {**base,'reason':'insufficient_blocks','background_passed':False,'BRH':return_stats(blocks,criteria)}
    stacks={k:np.stack([np.loadtxt(p/(k+'_xt.dat')) for p in blocks]) for k in FIELDS}
    ng=stacks['ne'].shape[1];L=gap_mm/1000;X=np.linspace(0,L,ng)
    def coarse(a):
        ny=min(40,a.shape[0]);return np.stack([q.mean(axis=0) for q in np.array_split(a,ny,axis=0)]).reshape(ny,40,5).mean(axis=2)
    def obs(a):
        out={}
        for s in ['e','i']:
            profile=a['n'+s].mean(axis=1);power=a['j'+s]*a['efield']
            out['mean_density_'+s]=np.trapezoid(profile,X)/L;out['density_profile_'+s]=profile
            out['mean_power_'+s]=power.mean();out['heating_map_'+s]=coarse(power)
        return out
    mean=obs({k:v.mean(axis=0) for k,v in stacks.items()})
    def indicators(stack):
        count=len(stack['ne']);m=obs({k:v.mean(axis=0) for k,v in stack.items()})
        leave=[obs({k:(v.sum(axis=0)-v[j])/(count-1) for k,v in stack.items()}) for j in range(count)]
        return {k:half_width(count*np.asarray(m[k])-(count-1)*np.stack([q[k] for q in leave])) for k in m}
    widths=indicators(stacks)
    if n//2>=5:
        used=n-n%2;paired={k:v[:used].reshape(used//2,2,*v.shape[1:]).mean(axis=1) for k,v in stacks.items()}
        longer=indicators(paired);widths={k:np.maximum(v,longer[k]) for k,v in widths.items()}
    h=n//2;first=obs({k:v[:h].mean(axis=0) for k,v in stacks.items()});last=obs({k:v[-h:].mean(axis=0) for k,v in stacks.items()});result={}
    for k,value in mean.items():
        scale=max(np.linalg.norm(np.asarray(value).ravel()),1e-300);unc=float(np.linalg.norm(np.asarray(widths[k]).ravel())/scale);drift=float(np.linalg.norm(np.asarray(last[k]-first[k]).ravel())/scale)
        tol=criteria['heating_map_relative_tolerance'] if k.startswith('heating') else criteria['mean_quantity_relative_tolerance']
        result[k]={'relative_uncertainty_indicator':unc,'first_last_half_relative_change':drift,'tolerance':tol,'passed':bool(unc<=tol and drift<=tol)}
        if np.ndim(value)==0:result[k].update(estimate=float(value),half_width=float(widths[k]))
    ready=n*criteria['block_cycles']>=criteria['minimum_measurement_cycles'];background=ready and base['particle_count_stationarity']['passed'] and all(v['passed'] for v in result.values())
    brh=return_stats(blocks,criteria)
    return {**base,'ready':ready,'background_passed':bool(background),'BRH':brh,'passed':bool(background and brh['passed']),'indicators':result,'reason':'criteria_satisfied' if background and brh['passed'] else 'continue_sampling',
        'note':'Exploratory block uncertainty and first/last-half drift. No certified total-error or sequential confidence guarantee; EEDF tails and discretization need separate checks.'}
