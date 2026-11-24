"""Gap comparison and observed-UID statistics from immutable measurement epochs.

No particle pushes, event reselection by energy sign, or lifetime extrapolation.
Caches are derived, and the native solver and its raw blocks remain untouched.
"""
from pathlib import Path
import copy, hashlib, json, shutil, zipfile
import numpy as np
import pandas as pd
from common import put, sha

FREQUENCY = 13.56e6
CHARGE = 1.60217662e-19
AREA = 1e-4
WEIGHT = 112000.
GAPS = [25, 30, 40, 50, 60, 80, 100, 120]


def weighted_moments(ne, energy, x):
    """Integrate particle energy, not an unweighted mean of local mean energies."""
    density = np.trapezoid(ne.mean(axis=1), x) / (x[-1] - x[0])
    mean_energy = np.trapezoid((ne * energy).mean(axis=1), x) / np.trapezoid(ne.mean(axis=1), x)
    return float(density), float(2 * mean_energy / 3)


def classify_returns(a):
    """Count candidate intervals and distinct observed episodes separately.

    A run cannot cross a missing interval, a UID change, or a non-near return.
    Candidate flags retain the solver's history. Episode energy cohorts require
    an observed first near return and >=2 contiguous observed near returns.
    """
    a = a.copy().sort_values(['uid', 'end_t_s']).reset_index(drop=True)
    a['uid'] = a.uid.astype('int64')
    near = a.near_fundamental.astype(bool)
    continuous = (a.uid == a.uid.shift()) & np.isclose(a.start_t_s, a.end_t_s.shift(), rtol=0, atol=1e-14)
    # An intervening unqualified reference-plane excursion resets the native
    # streak even when complete return intervals still touch in time.
    continuous &= a.consecutive_returns == a.consecutive_returns.shift() + 1
    starts = near & ~(continuous & near.shift(fill_value=False))
    a['observed_run'] = starts.cumsum().where(near, 0).astype('int64')
    a['candidate'] = near & (a.consecutive_returns >= 2)
    runs = a.loc[near].groupby('observed_run', sort=False).agg(
        uid=('uid', 'first'), start_t_s=('start_t_s', 'first'), end_t_s=('end_t_s', 'last'),
        observed_returns=('uid', 'size'), first_streak=('consecutive_returns', 'first'),
        candidate_returns=('candidate', 'sum'), max_streak=('consecutive_returns', 'max'))
    runs['left_censored'] = runs.first_streak != 1
    uids = a.groupby('uid').agg(detected_returns=('uid', 'size'),
                              candidate_returns=('candidate', 'sum'), max_streak=('consecutive_returns', 'max'))
    candidates = runs[runs.candidate_returns > 0]
    uids['observed_candidate_episodes'] = candidates.groupby('uid').size().reindex(uids.index, fill_value=0)
    uids['max_observed_near_run'] = runs.groupby('uid').observed_returns.max().reindex(uids.index, fill_value=0)
    uids['left_censored_candidate_episodes'] = candidates.groupby('uid').left_censored.sum().reindex(uids.index, fill_value=0)
    return a, runs, uids.astype('int64')


def attach_energy(a, encounters):
    """Same staggered K at both ends, with an independently checked ledger."""
    lookup = encounters.set_index(['uid', 'exit_t_s']).exit_K_staggered_eV
    assert lookup.index.is_unique, 'Duplicate encounter identity'
    ends = pd.MultiIndex.from_arrays([a.uid, a.end_t_s])
    starts = pd.MultiIndex.from_arrays([a.uid, a.start_t_s])
    end = lookup.reindex(ends).to_numpy()
    start_saved = lookup.reindex(starts).to_numpy()
    assert np.isfinite(end).all(), 'Return endpoint has no saved encounter energy'
    start = end - a.dK_staggered_eV.to_numpy()
    matched = np.isfinite(start_saved)
    discrepancy = float(np.max(np.abs(start[matched] - start_saved[matched]), initial=0))
    assert discrepancy < 1e-7, 'Encounter/return energy mismatch'
    assert np.max(np.abs((a.dK_staggered_eV - a.W_field_eV - a.dK_collision_parent_eV).to_numpy()), initial=0) < 1e-7
    a = a.copy(); a['K_start_eV'] = start; a['K_end_eV'] = end
    return a, {'matched_start_energies': int(matched.sum()), 'reconstructed_start_energies': int((~matched).sum()),
               'maximum_endpoint_discrepancy_eV': discrepancy}


def episode_energy(a, runs):
    """Observed episode prefixes, explicitly subject to survival selection at k."""
    nodes = []
    eligible = runs[(runs.observed_returns >= 2) & ~runs.left_censored]
    groups = a.groupby('observed_run')
    for run, r in eligible.iterrows():
        q = groups.get_group(run)
        w = np.r_[0., q.W_field_eV.cumsum().to_numpy()]
        c = np.r_[0., q.dK_collision_parent_eV.cumsum().to_numpy()]
        k = np.r_[q.K_start_eV.iloc[0], q.K_end_eV.to_numpy()]
        assert np.allclose(k-k[0], w+c, atol=1e-7, rtol=0)
        for j in range(len(k)):
            nodes.append([int(r.uid), int(run), j, k[j], k[j]-k[0], w[j], c[j]])
    return pd.DataFrame(nodes, columns=['uid','observed_run','return_index','K_eV','delta_K_eV','field_work_eV','collision_dK_eV'])


def select_trace(a, runs, encounters):
    """Longest observed near run, then lowest UID/time; never select by gain."""
    eligible = runs[(runs.observed_returns >= 2) & ~runs.left_censored]
    if eligible.empty:
        return pd.DataFrame(), pd.DataFrame()
    winner = eligible.sort_values(['observed_returns','uid','start_t_s'], ascending=[False,True,True]).iloc[0]
    q = a[a.uid == winner.uid].reset_index(drop=True)
    selected = np.flatnonzero(q.observed_run.to_numpy() == winner.name)
    left, right = int(selected[0]), int(selected[-1])
    for _ in range(4):
        if left > 0 and abs(q.start_t_s.iloc[left]-q.end_t_s.iloc[left-1]) < 1e-14: left -= 1
        if right+1 < len(q) and abs(q.start_t_s.iloc[right+1]-q.end_t_s.iloc[right]) < 1e-14: right += 1
    q = q.iloc[left:right+1].copy()
    t0, t1 = q.start_t_s.iloc[0], q.end_t_s.iloc[-1]
    enc = encounters[(encounters.uid == winner.uid) & (encounters.exit_t_s >= t0) & (encounters.exit_t_s <= t1)].copy()
    records = [[int(winner.uid), t0, 0., q.K_start_eV.iloc[0], 0., 0., 0., 0., np.nan, 0, 0]]
    w = c = sw = 0.
    for r in q.itertuples():
        w += r.W_field_eV; c += r.dK_collision_parent_eV
        inside = enc[(enc.entry_t_s >= r.start_t_s) & (enc.exit_t_s <= r.end_t_s)]
        sw += inside.W_field_eV.sum()
        records.append([r.uid,r.end_t_s,(r.end_t_s-t0)*FREQUENCY,r.K_end_eV,w,c,w+c,sw,r.tau_RF,int(r.candidate),int(r.consecutive_returns)])
    trace = pd.DataFrame(records, columns=['uid','t_s','time_RF','K_eV','cumulative_field_work_eV','cumulative_collision_dK_eV',
                                          'delta_K_eV','cumulative_detected_sheath_work_eV','tau_RF','candidate','consecutive_returns'])
    assert np.allclose(trace.K_eV-trace.K_eV.iloc[0], trace.delta_K_eV, atol=1e-7, rtol=0)
    enc['time_RF'] = (enc.exit_t_s-t0)*FREQUENCY
    return trace, enc


def analyze_case(state, summary, cache):
    """Compute once per immutable pooled epoch; snapshots can be republished."""
    source = Path(summary['pooled_data_path']); native = Path(state['pooled_native_path'])
    signature = hashlib.sha256((sha(Path(__file__)) + json.dumps(summary, sort_keys=True)).encode()).hexdigest()
    dest = cache / f'{state["gap_mm"]}mm'
    marker = dest/'analysis.json'
    if marker.exists() and json.loads(marker.read_text()).get('signature') == signature:
        return dest, json.loads(marker.read_text())
    dest.mkdir(parents=True, exist_ok=True)
    gap = state['gap_mm']; x = np.linspace(0, gap/1000, state['grid_points'])
    ne = np.loadtxt(native/'ne_xt.dat'); energy = np.loadtxt(native/'meanee_xt.dat')
    mean_ne, te = weighted_moments(ne, energy, x)
    center = (x >= .45*x[-1]-1e-12) & (x <= .55*x[-1]+1e-12)
    center_ne, center_te = weighted_moments(ne[center], energy[center], x[center])
    ion = np.loadtxt(native/'ioniz_xt.dat')
    with np.load(source/'histogram_counts.npz') as z:
        counts = z['E_counts']; edges = z['energy_edges_eV']
        start = int(np.flatnonzero(np.isclose(edges,20))[0])
        central = counts[9:11].sum(axis=(0,1,2))
        hot = float(central[start:].sum()/central.sum())
    balance = pd.read_csv(native/'particle_balance.csv'); duration = summary['duration_s']
    electron_power = balance.e_field_work_J.sum() / (AREA*duration)
    wall_flux = (balance.e_loss_lower+balance.e_loss_upper).sum()*WEIGHT/(AREA*duration)
    r = {'signature': signature, 'gap_mm': gap, 'RF_first': summary['first_RF'], 'RF_last': summary['last_RF'],
         'measured_RF': summary['measured_RF'], 'background_passed': summary['background_and_BRH_assessment'].get('background_passed',False),
         'all_criteria_passed': summary['background_and_BRH_assessment'].get('passed',False),
         'ne_volume_m3': mean_ne, 'ne_central10_m3': center_ne, 'Te_energy_equiv_eV': te, 'Te_central10_energy_equiv_eV': center_te,
         'central_fraction_E_ge20eV': hot, 'electron_field_power_Wm2': float(electron_power),
         'electron_power_eV_per_particle_per_RF': float(electron_power/(mean_ne*gap/1000)/FREQUENCY/CHARGE),
         'mean_ionization_m3s': float(np.trapezoid(ion.mean(axis=1),x)/(x[-1]-x[0])),
         'electron_wall_flux_m2s': float(wall_flux), 'inventory_over_wall_loss_RF': float(mean_ne*gap/1000/wall_flux*FREQUENCY),
         'histogram_energy_overflow_samples': summary['hist_E_overflow_samples']}
    encounters = pd.read_csv(source/'brh_encounters.csv.gz', float_precision='round_trip', dtype={'uid':'int64','parent':'int64','sequence':'int64','side':'int8'})
    for side, label in [(1,'upper'),(0,'lower')]:
        q = encounters[encounters.side == side]
        r[f'{label}_encounters'] = len(q)
        for key,col in [('Eout','exit_K_staggered_eV'),('Exout','exit_Ex_staggered_eV')]:
            for stat,val in [('mean',q[col].mean()),('p10',q[col].quantile(.1)),('median',q[col].median()),('p90',q[col].quantile(.9))]:
                r[f'{label}_{key}_{stat}_eV'] = float(val) if np.isfinite(val) else None
    if (source/'upper_returns.npy').exists():
        raw = pd.DataFrame(np.load(source/'upper_returns.npy'))
    else:
        raw = pd.read_csv(source/'brh_roundtrips.csv.gz',float_precision='round_trip')
        raw = raw[raw.side == 1]
    a, runs, uids = classify_returns(raw)
    a, check = attach_energy(a, encounters); r['validation'] = check
    r.update({'detected_return_UIDs':len(uids), 'detected_returns':len(a), 'candidate_returns':int(a.candidate.sum()),
              'candidate_UIDs':int((uids.candidate_returns>0).sum()), 'observed_candidate_episodes':int((runs.candidate_returns>0).sum()),
              'candidate_events_per_return_UID':float(uids.candidate_returns.mean()) if len(uids) else None,
              'candidate_events_per_candidate_UID':float(uids.loc[uids.candidate_returns>0,'candidate_returns'].mean()) if a.candidate.any() else None,
              'max_candidate_events_per_UID':int(uids.candidate_returns.max()) if len(uids) else 0, 'max_observed_near_run':int(runs.observed_returns.max()) if len(runs) else 0,
              'candidate_event_fraction':float(a.candidate.mean()) if len(a) else None, 'candidate_UID_fraction':float((uids.candidate_returns>0).mean()) if len(uids) else None,
              'candidate_fieldwork_eV':summary['candidate_mean_signed_work_eV'], 'candidate_net_dK_eV':summary['candidate_mean_net_dK_eV'],
              'candidate_collision_dK_eV':summary['candidate_mean_parent_collision_dK_eV'],
              'all_returns_fieldwork_eV':summary['all_return_mean_signed_work_eV']})
    brh = summary['background_and_BRH_assessment']['BRH']
    r['candidate_fraction_uncertainty'] = brh['candidate_return_fraction'].get('half_width')
    r['candidate_work_uncertainty_eV'] = brh['candidate_signed_work_eV'].get('half_width')
    assert r['candidate_returns'] == summary['candidate_returns'] and r['candidate_UIDs'] == summary['distinct_candidate_UIDs']
    uids.reset_index().to_csv(dest/'uid_counts.csv.gz',index=False,compression={'method':'gzip','mtime':0})
    runs.reset_index().to_csv(dest/'observed_runs.csv.gz',index=False,compression={'method':'gzip','mtime':0})
    nodes = episode_energy(a, runs); nodes.to_csv(dest/'episode_energy.csv.gz',index=False,compression={'method':'gzip','mtime':0})
    aggregate = nodes.groupby('return_index').agg(episodes=('uid','size'),distinct_UIDs=('uid','nunique'),
        mean_K_eV=('K_eV','mean'),median_K_eV=('K_eV','median'),mean_delta_K_eV=('delta_K_eV','mean'),
        mean_field_work_eV=('field_work_eV','mean'),mean_collision_dK_eV=('collision_dK_eV','mean'))
    aggregate.to_csv(dest/'episode_statistics.csv')
    trace, enc = select_trace(a, runs, encounters)
    if len(trace):
        trace.to_csv(dest/'selected_trace.csv',index=False);enc.to_csv(dest/'selected_encounters.csv',index=False)
        r['trace_uid'] = int(trace.uid.iloc[0]);r['trace_max_near_run'] = int(trace.consecutive_returns.max())
    else:
        for name in ['selected_trace.csv','selected_encounters.csv']:(dest/name).unlink(missing_ok=True)
    r['validation']['episode_nodes'] = len(nodes)
    r['validation']['ledger_and_candidate_counts_passed'] = True
    put(marker,r)
    return dest,r


def plot_summary(rows, snapshots, dest):
    import matplotlib.pyplot as plt
    from export import save
    figs = dest/'figures';figs.mkdir(exist_ok=True)
    fig, axs = plt.subplots(2,3,figsize=(14,8));axs=axs.ravel()
    specs = [([('ne_volume_m3','Volume mean'),('ne_central10_m3','Central 10%')],'Electron density (m$^{-3}$)'),
             ([('Te_energy_equiv_eV','Volume'),('Te_central10_energy_equiv_eV','Central 10%')],'Energy-equivalent Te (eV)'),
             ([('upper_Eout_mean_eV','Upper: mean'),('upper_Eout_p90_eV','Upper: P90'),('lower_Eout_mean_eV','Lower: mean')],'Sheath-return exit E (eV)'),
             ([('central_fraction_E_ge20eV','Central E >= 20 eV')],'High-energy particle-time fraction'),
             ([('electron_field_power_Wm2','All-electron field work')],'Electron power / area (W m$^{-2}$)'),
             ([('mean_ionization_m3s','Volume mean')],'Ionization rate (m$^{-3}$ s$^{-1}$)')]
    colors=['tab:blue','tab:orange','tab:green']
    for ax,(series,label) in zip(axs,specs):
        for j,(key,lab) in enumerate(series):
            for i,r in enumerate(rows):
                ax.plot(r['gap_mm'],r[key],marker=['o','s','^'][j],linestyle='none',color=colors[j],
                        markerfacecolor=colors[j] if r['background_passed'] else 'none',label=lab if i==0 else None)
        ax.set(xlabel='Gap (mm)',ylabel=label,xlim=(20,125),xticks=GAPS);ax.grid(alpha=.2);ax.legend(fontsize=8)
    fig.suptitle('Available post-background measurement epochs; RF windows in the table\nFilled: background criteria met | Open: background criteria not met; BRH precision separate')
    fig.tight_layout();save(fig,figs/'gap_parameters.png')
    fig,axs=plt.subplots(2,2,figsize=(12,8))
    for r in rows:
        x=r['gap_mm'];f=r['candidate_event_fraction'];ef=r['candidate_fraction_uncertainty']
        if f is not None:
            err=np.array([[100*min(f,ef)],[100*ef]]) if ef is not None else None
            axs[0,0].errorbar(x,100*f,yerr=err,fmt='o',capsize=3,color='tab:blue',markerfacecolor='tab:blue' if r['background_passed'] else 'none')
        if r['candidate_fieldwork_eV'] is not None:
            axs[0,1].errorbar(x,r['candidate_fieldwork_eV'],yerr=r['candidate_work_uncertainty_eV'],fmt='o',capsize=3,color='tab:orange')
            axs[0,1].plot(x,r['candidate_net_dK_eV'],'s',color='tab:green')
        axs[0,1].plot(x,r['all_returns_fieldwork_eV'],'x',color='k')
        if r['candidate_UID_fraction'] is not None:axs[1,0].plot(x,100*r['candidate_UID_fraction'],'o',color='tab:purple')
        axs[1,1].plot(x,r['max_observed_near_run'],'o',color='tab:blue')
    labels=['1T candidate / detected returns (%)','Signed energy per return (eV)','UIDs with >=1 candidate / return UIDs (%)','Maximum observed consecutive near-1T returns']
    for ax,lab in zip(axs.ravel(),labels):ax.set(xlabel='Gap (mm)',ylabel=lab,xlim=(20,125),xticks=GAPS);ax.grid(alpha=.2)
    axs[0,1].axhline(0,color='k',lw=.6);axs[0,1].set_title('Orange: candidate field work; green: net dK\nBlack: all-return field work',fontsize=10)
    fig.suptitle('Observed-event / UID statistics, not a lifetime or whole-plasma BRH fraction\nBars: exploratory block uncertainty; 1T only; unequal RF windows')
    fig.tight_layout();save(fig,figs/'gap_brh.png')
    fig,axs=plt.subplots(1,2,figsize=(12,4.5))
    for r in rows:
        q=pd.read_csv(dest/'data'/f'{r["gap_mm"]}mm_uid_counts.csv.gz')
        for ax,key in zip(axs,['candidate_returns','observed_candidate_episodes']):
            counts=q[key].value_counts().sort_index();ax.plot(counts.index,counts/len(q)*100,'o-',label=f'{r["gap_mm"]} mm ({r["measured_RF"]} RF)')
    axs[0].set(xlabel='Candidate return intervals per observed UID');axs[1].set(xlabel='Distinct observed candidate episodes per UID')
    for ax in axs:ax.set(ylabel='Fraction of detected-return UIDs (%)',yscale='log');ax.grid(alpha=.2);ax.legend(fontsize=8)
    fig.suptitle('Zero-event UIDs included; observation-window counts, not electron lifetimes');fig.tight_layout();save(fig,figs/'uid_counts.png')
    fig,axs=plt.subplots(1,2,figsize=(12,4.5))
    for r in rows:
        n=pd.read_csv(dest/'data'/f'{r["gap_mm"]}mm_episode_energy.csv.gz')
        if n.empty:continue
        g=n.groupby('return_index');mean=g[['delta_K_eV','field_work_eV','collision_dK_eV']].mean();size=g.size()
        label=f'{r["gap_mm"]} mm, N0={size.iloc[0]}'
        for ax,key in zip(axs,['delta_K_eV','field_work_eV']):
            line=ax.plot(mean.index,mean[key],'o-',label=label)[0]
            for k in mean.index[mean.index>=3]:
                ax.annotate(f'N={size.loc[k]}',(k,mean.loc[k,key]),xytext=(4,6),textcoords='offset points',color=line.get_color(),fontsize=8)
    axs[0].set(ylabel='Mean K(k) - K(0) (eV)');axs[1].set(ylabel='Mean cumulative signed field work (eV)')
    for ax in axs:ax.set(xlabel='Consecutive near-1T return number k');ax.axhline(0,color='k',lw=.6);ax.grid(alpha=.2);ax.legend(fontsize=8)
    fig.suptitle('Observed episodes with >=2 near-1T returns, selected independently of energy\nPopulation shrinks with k (survivor selection); sample counts and collision work in CSV')
    fig.tight_layout();save(fig,figs/'episode_energy.png')
    for r in rows:
        f=dest/'data'/f'{r["gap_mm"]}mm_selected_trace.csv'
        if not f.exists():continue
        q=pd.read_csv(f);enc=pd.read_csv(dest/'data'/f'{r["gap_mm"]}mm_selected_encounters.csv')
        fig,axs=plt.subplots(3,1,figsize=(10,9),sharex=True)
        axs[0].plot(q.time_RF,q.K_eV,'o-',ms=4,label='Upper reference exit K')
        lower=enc[enc.side==0];axs[0].scatter(lower.time_RF,lower.exit_K_staggered_eV,marker='x',color='grey',s=20,label='Lower reference exit K')
        axs[0].set(ylabel='Electron kinetic energy (eV)');axs[0].legend(fontsize=8)
        for key,lab,color in [('cumulative_field_work_eV','All field work','tab:orange'),('cumulative_collision_dK_eV','Parent collision change','tab:blue'),('delta_K_eV','Net kinetic-energy change','k'),('cumulative_detected_sheath_work_eV','Work during detected sheath excursions','tab:green')]:
            axs[1].plot(q.time_RF,q[key],'o-',ms=3,label=lab,color=color)
        axs[1].set(ylabel='Cumulative signed energy (eV)');axs[1].legend(fontsize=8)
        axs[2].plot(q.time_RF,q.tau_RF,'o-',ms=4);axs[2].axhspan(.9,1.1,color='tab:orange',alpha=.2)
        selected=q[q.candidate==1];axs[2].scatter(selected.time_RF,selected.tau_RF,color='red',s=35,label='Candidate interval')
        axs[2].set(ylabel='Return duration / T_RF',xlabel='Time from first plotted reference exit / T_RF');axs[2].legend(fontsize=8)
        for ax in axs:ax.grid(alpha=.2)
        fig.suptitle(f'{r["gap_mm"]} mm | UID {r["trace_uid"]} | longest observed near-1T run: {r["trace_max_near_run"]}\nSelected by persistence, not positive gain; points are saved crossings; lines guide the eye')
        fig.tight_layout();save(fig,figs/f'energy_trace_{r["gap_mm"]}mm.png')


def build_comparison(root,out,base,cases,series):
    """Return a normal child report so catalog/audit/publication keep working."""
    dest=out/'comparison';dest.mkdir(exist_ok=True);(dest/'data').mkdir(exist_ok=True)
    states={g:json.loads((out/f'{g}mm/status.json').read_text()) for g in GAPS if (out/f'{g}mm/status.json').exists()}
    rows=[];provenance=[]
    for gap,status,summary in sorted(series):
        state=states[gap];cache,r=analyze_case(state,summary,root/'comparison_cache');r=copy.deepcopy(r);r['status']=status;rows.append(r)
        for f in cache.glob('*.csv*'):shutil.copy2(f,dest/'data'/f'{gap}mm_{f.name}')
        provenance.append({'gap_mm':gap,'summary_sha256':sha(Path(state['measurement_summary_path'])),
                           'measurement_summary_path':state['measurement_summary_path'],'native_path':state['pooled_native_path'],
                           'RF_first':summary['first_RF'],'RF_last':summary['last_RF'],'measured_RF':summary['measured_RF'],
                           'measurement_blocks':summary['measurement_blocks'],'validation':r['validation']})
    # Do not retain a prior epoch's derived exports if a case is re-equilibrating.
    active={str(r['gap_mm'])+'mm' for r in rows}
    for f in (dest/'data').glob('*mm_*'):
        if f.name.split('_')[0] not in active:f.unlink()
    if rows:plot_summary(rows,states,dest)
    flat=[{k:v for k,v in r.items() if k not in ['signature','validation']} for r in rows]
    pd.DataFrame(flat).to_csv(dest/'data/gap_parameters.csv',index=False)
    put(dest/'analysis_provenance.json',{'analysis_script_sha256':sha(Path(__file__)),'snapshots':provenance,
        'conditions':base['conditions'],'control_source_SHA256':json.loads((root/'config.json').read_text())['control_source_SHA256']})
    status_rows=[]
    labels={'extinguished':'전자 소멸','measurement_limit_reached':'1000 RF 상한·기준 미충족','criteria_met':'통계 기준 충족','running':'계산 중','queued':'대기'}
    for g,s in states.items():
        match=next((r for r in rows if r['gap_mm']==g),None)
        status_rows.append({'gap_mm':g,'status':s['status'],'checkpoint_RF':s.get('checkpoint_cycle',0),'measured_RF':s.get('measured_RF',0),
                            'RF_first':match['RF_first'] if match else None,'RF_last':match['RF_last'] if match else None,
                            'background_passed':match['background_passed'] if match else None,'all_criteria_passed':match['all_criteria_passed'] if match else None})
    pd.DataFrame(status_rows).to_csv(dest/'data/gap_status.csv',index=False)
    table='| Gap mm | 상태 | 측정 RF 구간 | 배경 기준 | BRH 포함 전체 기준 |\n|---:|---|---|---|---|\n'
    for r in status_rows:
        window=f'{r["RF_first"]}–{r["RF_last"]} ({r["measured_RF"]} RF)' if r['RF_first'] else '측정 전 / 정의 불가'
        flag=lambda v:'—' if v is None else ('충족' if v else '미충족')
        table+=f'| [{r["gap_mm"]}](../{r["gap_mm"]}mm/README.md) | {labels.get(r["status"],r["status"])} | {window} | {flag(r["background_passed"])} | {flag(r["all_criteria_passed"])} |\n'
    count_table='| Gap mm | 검출 왕복 UID | 후보 보유 UID | 후보 왕복 사건 | 후보 episode | 후보 사건/보유 UID 평균 | UID당 최대 사건 | 최대 연속 1T 왕복 |\n|---:|---:|---:|---:|---:|---:|---:|---:|\n'
    for r in rows:
        mean=f'{r["candidate_events_per_candidate_UID"]:.3f}' if r['candidate_events_per_candidate_UID'] is not None else '—'
        count_table+=f'| {r["gap_mm"]} | {r["detected_return_UIDs"]} | {r["candidate_UIDs"]} | {r["candidate_returns"]} | {r["observed_candidate_episodes"]} | {mean} | {r["max_candidate_events_per_UID"]} | {r["max_observed_near_run"]} |\n'
    details=' · '.join(f'[{g} mm](../{g}mm/README.md)' for g in states)
    from export import image_section, im, KEYS
    sections=[{'id':k,'data_status':'partial','text':'조건별 원자료·공간/위상 지도: '+details,'images':[]} for k in KEYS]
    section_map={s['id']:s for s in sections}
    section_map['convergence']['text']=table+'\n배경 기준 충족과 BRH 통계 기준 충족은 별도입니다. 상한 종료를 수렴 완료로 표시하지 않습니다. 소멸·미측정 gap은 비교 그래프에서 0으로 채우지 않습니다.'
    if rows:
        section_map['density'].update(image_section('density',[im('figures/gap_parameters.png','실제 측정 epoch의 평균. 채운 점은 배경 기준 충족, 빈 점은 미충족. Eout P90은 분포의 90백분위수이며 오차막대가 아닙니다.')],
            '전자 밀도는 체적 평균과 중앙10%를 구분합니다. Te_eff=2〈E〉/3는 입자 수로 가중한 에너지 환산 온도(eV)이며, 비맥스웰 분포의 단일 열역학 온도나 drift를 뺀 온도가 아닙니다. '
            'Eout은 유효 쉬스 전기장 반사 후 x/L=0.75(상부),0.25(하부) 기준면에서 벌크 방향으로 나오는 전자의 전체 에너지이며 각 검출 반사 사건을 동일 가중합니다. 단일 beam 에너지나 PROES 궤적 에너지와 동일시하지 않습니다. Ex·중앙값·P10/P90도 CSV에 있습니다. '
            '전력은 순간 이산 field work의 합/시간/면적이며 발생기 총 전력과 다릅니다.'))
        sections += [image_section('brh_compare',[im('figures/gap_brh.png','오차막대는 기존20/40RF 블록의 탐색적 불확실도입니다. 수치/모델 오차와 반복 중단의 신뢰수준을 보증하지 않습니다.')],
            '1T 후보는 에너지 부호와 무관하게 |tau/T−1|≤0.1인 왕복이 연속2회 이상인 경우입니다. 2T/3T 등 다른 공명 차수는 이 지표에 포함되지 않습니다.'),
            image_section('uid_statistics',[im('figures/uid_counts.png','0회인 UID를 포함한 분포. 관측 창이 서로 다르며 전자 수명 전체의 횟수가 아닙니다.')],count_table+'\n후보 사건은 연속 두 번째 왕복부터 집계합니다. 예: 연속5회 왕복은 후보4사건·episode1개입니다. 떨어진 후보 episode가 같은 UID에서 반복될 수 있습니다. '
            '분모는 약1/16 해시 표본 중 완전한 상부 기준 왕복이 검출된 UID입니다. 전체 전자나 벽에 도달한 모든 전자가 아닙니다. 관측 시작/끝·검출 경계로 잘린 사건이 있고, 장수명 전자는 관측 기회가 더 많습니다. 이 수치만으로 “전자당 평생 BRH 횟수”를 정할 수 없습니다.'),
            image_section('episode_energy',[im('figures/episode_energy.png','누적 전기장 일과 실제 순 에너지 변화를 분리합니다. k가 클수록 남는 episode가 적으므로 서로 다른 생존 집단의 평균입니다.')],
            '에너지 증가 사례만 고르지 않았습니다. 처음부터 관측된 연속≥2회 후보 episode를 모았으며 각 k의 UID·episode·원시 에너지 값은 CSV에 있습니다. 순 에너지는 충돌 때문에 감소하거나 포화할 수 있습니다. '
            '이 그림의 각 k는 동일 집단 전체를 끝까지 추적한 평균이 아니며, 긴 episode의 생존 선택을 포함합니다.')]
        examples=[im(f'figures/energy_trace_{r["gap_mm"]}mm.png',f'{r["gap_mm"]} mm, UID {r["trace_uid"]}: 최대 지속 길이→작은 UID 순으로 선택. 모든 전자의 대표값이 아닙니다.') for r in rows if 'trace_uid' in r]
        sections.append(image_section('electron_energy',examples,
            '에너지는 저장된 기준면 출구에서의 실제 반 step 운동에너지입니다. 점을 이은 선은 연속 시간 궤적을 복원한 것이 아닙니다. '
            '주황: 궤도 전체 전기장 일, 파랑: parent 전자 충돌 변화, 검정: 둘의 합=순 운동에너지 변화. 녹색은 검출된 쉬스 접근·반사·출구 구간의 전기장 일로, 주황의 일부입니다. '
            '이온화로 daughter에 넘어간 에너지는 parent 손실에 포함됩니다. 상부 기준 왕복만 누적하여 양쪽 왕복의 중복 가산을 피했습니다.'))
    titles={'brh_compare':'Gap별 BRH 후보 비교','uid_statistics':'전자 UID별 반복 횟수','episode_energy':'반복 횟수에 따른 집단 에너지','electron_energy':'개별 전자의 반복 가열·충돌 이력'}
    for s in sections:
        if s['id'] in titles:s['title']=titles[s['id']]
    archive=dest/'261123_BRH_comparison.zip'
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for f in sorted((dest/'data').iterdir()):
            info=zipfile.ZipInfo('data/'+f.name,date_time=(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;z.writestr(info,f.read_bytes())
        info=zipfile.ZipInfo('analysis_provenance.json',date_time=(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
        z.writestr(info,(dest/'analysis_provenance.json').read_bytes())
    active_run=any(s['status'] in ['running','queued','building'] for s in states.values())
    meta=copy.deepcopy(base);meta.update(title='Gap별 플라즈마 파라미터·전자별 BRH 후보 요약',status='running' if active_run else 'measurement_complete',
        changed_conditions='BRH gap25–120 mm 비교',report_directory=f'results/{base["id"]}/comparison',
        summary='8개 계획 조건의 실제 상태와 확보된 측정만 비교합니다. 실행일은 원 계산 시작일이며 보고서 갱신일과 구분합니다. 모든 gap 완료·BRH 확정을 뜻하지 않습니다.',
        measurement_note='아래 gap별 RF 구간 표. 원래 측정 epoch만 사용; warmup·pilot·폐기된 epoch 제외.',sections=sections,
        related_links=[{'label':'전체 gap 진행·개별 결과','url':'../README.md'},{'label':'진단 정의·수렴 기준','url':'../METHOD.md'}],
        downloads=[{'label':'gap별 파라미터 CSV','path':'data/gap_parameters.csv'},{'label':'계획 gap 전체 상태 CSV','path':'data/gap_status.csv'},
                   {'label':'전자별 횟수·episode 에너지·선택 궤적 CSV 모음','path':archive.name},{'label':'원자료 구간·SHA·에너지 장부 검증','path':'analysis_provenance.json'}])
    for r in rows:
        meta['downloads'].append({'label':f'{r["gap_mm"]} mm 전자 UID별 관측 횟수','path':f'data/{r["gap_mm"]}mm_uid_counts.csv.gz'})
    put(dest/'report.json',meta)
    return meta
