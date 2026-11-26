"""Pool raw diagnostic counts and signed particle work with explicit censoring."""
from pathlib import Path
import csv,gzip,json,shutil,time,hashlib
import numpy as np
from common import put,block_cycles,diagnostic_metadata
from brh_stats import read_table,return_stats

def edges():return np.r_[np.arange(101)/10,np.arange(11,101),np.arange(105,501,5)]

def block_hist(path,energy):
    f=path/f'brh_hist_{energy}_counts.bin'
    if f.exists():return np.fromfile(f,dtype='<u8').reshape(20,200,2,271)
    if (path/'recovery_aggregate.json').exists():
        with np.load(path/'histogram_counts.npz') as z:return z[energy+'_counts']
    with np.load(path/'brh_hist_counts.npz') as z:return z[energy]

def compress_block(path,native=False):
    """Lossless storage conversion after native/BRH validation, never physics."""
    if (path/'brh_hist_E_counts.bin').exists():
        np.savez_compressed(path/'brh_hist_counts.npz',E=block_hist(path,'E'),Ex=block_hist(path,'Ex'))
        for key in ['E','Ex']:(path/f'brh_hist_{key}_counts.bin').unlink()
    for f in path.glob('brh_*.csv'):
        with f.open('rb') as src,gzip.open(str(f)+'.gz','wb',compresslevel=3) as dst:shutil.copyfileobj(src,dst)
        f.unlink()
    if native:
        manifest={}
        for f in list(path.glob('*_xt.dat'))+[path/'density.dat']:
            if not f.exists():continue
            data=f.read_bytes();dst=path/(f.name+'.gz');tmp=path/(f.name+'.gz.tmp')
            tmp.write_bytes(gzip.compress(data,compresslevel=3,mtime=0))
            assert gzip.decompress(tmp.read_bytes())==data
            manifest[f.name]={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'stored_as':dst.name}
            tmp.replace(dst);f.unlink()
        if manifest:put(path/'native_compression.json',manifest)

def process_blocks(case,blocks,assessment):
    last_RF=json.loads((blocks[-1]/'block.json').read_text())['RF_last']
    dest=case/f'brh_pooled_RF{last_RF:06d}';dest.mkdir(exist_ok=True);histE=np.zeros((20,200,2,271),dtype=np.uint64);histEx=histE.copy();work=None;metadata=[]
    for p in blocks:
        m=diagnostic_metadata(p);metadata.append(m)
        histE+=block_hist(p,'E');histEx+=block_hist(p,'Ex')
        a=np.load(p/'work_sum_eV.npy') if (p/'recovery_aggregate.json').exists() else np.fromfile(p/'brh_work_sum_eV.bin',dtype='<f8').reshape(m['grid_points'],200)
        work=a.copy() if work is None else work+a
    np.savez_compressed(dest/'histogram_counts.npz',E_counts=histE,Ex_counts=histEx,energy_edges_eV=edges(),overflow_lower_eV=500.,x_fraction_edges=np.linspace(0,1,21),phase_edges=np.linspace(0,1,201))
    np.save(dest/'work_sum_eV.npy',work)
    for name in ['brh_roundtrips','brh_encounters','brh_trajectories','brh_probes','brh_wall_e']:
        with gzip.open(dest/(name+'.csv.gz'),'wt') as out:
            # Illustrative trajectories use the first measured five RF only;
            # full event/probe/history diagnostics still pool every block.
            selected=blocks[:1] if name=='brh_trajectories' else blocks
            for j,p in enumerate(selected):
                original=p/(name+'.csv');src=original.open() if original.exists() else gzip.open(str(original)+'.gz','rt')
                with src:
                    header=src.readline()
                    if j==0:out.write(header)
                    shutil.copyfileobj(src,out)
    returns=[]
    for p in blocks:
        a=read_table(p/'brh_roundtrips.csv')
        if len(a):returns.append(a)
    a=np.concatenate(returns) if returns else np.empty(0);upper=a[a['side']==1] if len(a) else a
    candidate=(upper['near_fundamental']>0)&(upper['consecutive_returns']>=2) if len(upper) else np.empty(0,dtype=bool)
    duration=sum(m['measurement_end_s']-m['measurement_start_s'] for m in metadata)
    sums={k:sum(m[k] for m in metadata) for k in ['all_fieldwork_eV','sample_fieldwork_eV','all_kicks','sample_kicks','hist_total_samples','hist_E_overflow_samples']}
    summary={'measurement_blocks':[str(p) for p in blocks],'pooled_data_path':str(dest),'first_RF':json.loads((blocks[0]/'block.json').read_text())['RF_first'],'last_RF':last_RF,'measured_RF':sum(block_cycles(p) for p in blocks),'duration_s':duration,
        'background_and_BRH_assessment':assessment,**sums,'max_energy_ledger_error_eV':max(m['maximum_return_energy_ledger_residual_eV'] for m in metadata),
        'powered_side_returns':len(upper),'distinct_return_UIDs':len(np.unique(upper['uid'])) if len(upper) else 0,'candidate_returns':int(candidate.sum()),'distinct_candidate_UIDs':len(np.unique(upper['uid'][candidate])) if candidate.any() else 0,
        'candidate_return_fraction':float(candidate.mean()) if len(upper) else None,'candidate_mean_signed_work_eV':float(upper['W_field_eV'][candidate].mean()) if candidate.any() else None,
        'candidate_mean_parent_collision_dK_eV':float(upper['dK_collision_parent_eV'][candidate].mean()) if candidate.any() else None,'candidate_mean_net_dK_eV':float(upper['dK_staggered_eV'][candidate].mean()) if candidate.any() else None,
        'all_return_mean_signed_work_eV':float(upper['W_field_eV'].mean()) if len(upper) else None,'candidate_signed_fieldwork_sum_eV':float(upper['W_field_eV'][candidate].sum()) if candidate.any() else 0.,
        'sample_inclusion_probability':1/16,'selection':'Both sheaths; same-side outward reference crossings, upper side only for primary statistics. abs(tau_RF-1)<=0.10 for >=2 consecutive returns, regardless of energy sign.',
        'scope':'Complete observed intervals only, censored at beginning/end of global measurement epoch; intervals crossing internal 20-RF boundaries retained. Collision-induced reversals alone do not qualify. This is a detected-return event fraction, not a whole-plasma BRH density fraction.',
        'verdict':'탐색 진단. 반복 위상와 signed work를 gap 간 비교하고 격자·seed·정의 민감도를 확인하기 전 BRH 확정으로 해석하지 않습니다.'}
    summary['candidate_fieldwork_power_per_area_Wm2_estimate']=16*summary['candidate_signed_fieldwork_sum_eV']*112000*1.60217662e-19/(1e-4*duration)
    put(case/'measurement_summary.json',summary);put(dest/'summary.json',summary)
    if len(upper):np.save(dest/'upper_returns.npy',upper)
    return summary

def prune_derived(case):
    """Keep raw blocks; discard reproducible old aggregate directories only."""
    for pattern in ['brh_pooled_RF*','pooled_epoch*_RF*']:
        dirs=sorted([p for p in case.glob(pattern) if p.is_dir()],key=lambda p:p.stat().st_mtime)
        for p in dirs[:-3]:
            if time.time()-p.stat().st_mtime>3600:shutil.rmtree(p)

def export_diagnostics(case,target,summary_path=None,archive_prefix='261123'):
    # Imported lazily so background numeric analysis does not initialize plotting.
    import os
    os.environ.setdefault('MPLCONFIGDIR','/tmp/edupic-matplotlib')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.colors import LogNorm
    from export import image_section,im,save
    summary_path=Path(summary_path) if summary_path else case/'measurement_summary.json'
    s=json.loads(summary_path.read_text());d=Path(s['pooled_data_path']);figs=target/'figures';figs.mkdir(exist_ok=True)
    note=f'RF {s["first_RF"]}–{s["last_RF"]} ({s["measured_RF"]} RF); exploratory diagnostics'
    a=np.load(d/'upper_returns.npy') if (d/'upper_returns.npy').exists() else np.empty(0);candidate=(a['near_fundamental']>0)&(a['consecutive_returns']>=2) if len(a) else np.empty(0,dtype=bool)
    fig,axs=plt.subplots(2,2,figsize=(11,8))
    if len(a):
        axs[0,0].hist(a['tau_RF'],bins=np.linspace(0,6,121),histtype='step',label='all detected upper-side returns');axs[0,0].axvspan(.9,1.1,color='tab:orange',alpha=.2);axs[0,0].set(xlabel='Round-trip duration / T_RF',ylabel='Events',yscale='log');axs[0,0].legend(fontsize=7)
        z=axs[0,1].hist2d(a['start_phase'],a['end_phase'],bins=40,norm=LogNorm());fig.colorbar(z[3],ax=axs[0,1],label='Events');axs[0,1].plot([0,1],[0,1],'w--',lw=.7);axs[0,1].set(xlabel='Departure RF phase',ylabel='Return RF phase')
        # All gains, including negative. Bin-mean error bars describe the event
        # population, not a confidence interval of independent trajectories.
        bins=np.linspace(0,4,41);centers=(bins[:-1]+bins[1:])/2;means=[]
        for lo,hi in zip(bins[:-1],bins[1:]):
            q=a['W_field_eV'][(a['tau_RF']>=lo)&(a['tau_RF']<hi)];means.append(q.mean() if len(q)>=5 else np.nan)
        axs[1,0].plot(centers,means,'o-',ms=3,label='all collisions included');axs[1,0].axhline(0,color='k',lw=.7);axs[1,0].axvspan(.9,1.1,color='tab:orange',alpha=.2);axs[1,0].set(xlabel='Round-trip duration / T_RF',ylabel='Mean signed field work (eV / return)');axs[1,0].legend(fontsize=8)
        groups=[('all',np.ones(len(a),dtype=bool)),('phase candidate',candidate),('no MCC',(a['n_elastic']+a['n_excitation']+a['n_ionization'])==0),('inelastic',(a['n_excitation']+a['n_ionization'])>0)]
        xx=np.arange(len(groups));w=[a['W_field_eV'][q].mean() if q.any() else np.nan for _,q in groups];c=[a['dK_collision_parent_eV'][q].mean() if q.any() else np.nan for _,q in groups]
        axs[1,1].bar(xx-.18,w,.36,label='field work');axs[1,1].bar(xx+.18,c,.36,label='parent MCC change');axs[1,1].set_xticks(xx,[lab+'\nN='+str(int(q.sum())) for lab,q in groups],fontsize=7);axs[1,1].set(ylabel='Mean signed energy change (eV)');axs[1,1].axhline(0,color='k',lw=.7);axs[1,1].legend(fontsize=7)
    else:
        for ax in axs.ravel():ax.text(.5,.5,'No complete detected upper-side returns',ha='center',transform=ax.transAxes)
    fig.suptitle(note);fig.tight_layout();save(fig,figs/'brh_returns.png')
    extra=[]
    if len(a):
        fig,axs=plt.subplots(1,2,figsize=(11,4))
        z=axs[0].hist2d(a['turn_start_phase'],a['turn_end_phase'],bins=40,norm=LogNorm());fig.colorbar(z[3],ax=axs[0],label='Events')
        axs[0].plot([0,1],[0,1],'w--',lw=.7);axs[0].set(xlabel='Previous actual field-turn phase',ylabel='Next actual field-turn phase')
        maximum=min(10,max(2,int(a['consecutive_returns'].max())));axs[1].hist(a['consecutive_returns'],bins=np.arange(-.5,maximum+1.5),histtype='step');axs[1].set(xlabel='Consecutive |tau/T - 1| <= 0.10 returns',ylabel='Events',yscale='log');fig.suptitle(note);save(fig,figs/'phase_persistence.png')
        extra.append(im('figures/phase_persistence.png',note+'; 실제 전기장 회전 시각의 위상 재현성과 연속 왕복 횟수. 기준면 재도착 위상과 구분합니다.'))
    # Paths illustrate the deterministic low-rate UID subsample. Longest
    # recorded paths are selected for visibility, without selecting energy gain.
    first=Path(s['measurement_blocks'][0]);paths=read_table(first/'brh_trajectories.csv')
    if len(paths):
        from matplotlib.collections import LineCollection
        ids,numbers=np.unique(paths['uid'],return_counts=True);chosen=ids[np.argsort(numbers)[-12:]]
        t0=diagnostic_metadata(first)['measurement_start_s'];fig,axs=plt.subplots(2,1,figsize=(10,7),sharex=True);collection=None
        for uid in chosen:
            q=paths[paths['uid']==uid];q=q[np.argsort(q['t_s'])]
            if len(q)<2:continue
            t=(q['t_s']-t0)*13.56e6;points=np.c_[t,q['x_m']*1000];segments=np.stack([points[:-1],points[1:]],axis=1)
            collection=LineCollection(segments,cmap='viridis',norm=plt.Normalize(0,40),linewidths=.7);collection.set_array(q['E_staggered_eV'][:-1]);axs[0].add_collection(collection)
            axs[1].plot(t,q['W_cumulative_eV']-q['W_cumulative_eV'][0],lw=.8)
        gap=json.loads((case/'status.json').read_text())['gap_mm'];axs[0].set(ylim=(0,gap),xlim=(0,5),ylabel='x (mm)',title='Illustrative UID subsample; color = staggered E (eV)')
        if collection is not None:fig.colorbar(collection,ax=axs[0],label='E (eV)')
        axs[1].set(xlabel='Time since first measured block / T_RF',ylabel='Signed field work since first sample (eV)');axs[1].axhline(0,color='k',lw=.5);fig.suptitle('First 5 RF of first block; paths selected by recording length, not energy sign');save(fig,figs/'trajectories.png')
        extra.append(im('figures/trajectories.png','첫 측정 블록의 처음5RF, 해시 추출 UID 중 기록이 긴 최대12개 궤적 예시. 집단 전체의 BRH 증거로 단독 사용하지 않습니다.'))
    hist=np.load(d/'histogram_counts.npz');e=hist['energy_edges_eV'];width=np.diff(e);E=(e[:-1]+e[1:])/2;counts=hist['E_counts'];excounts=hist['Ex_counts']
    n=counts.sum(axis=(1,2))[:,:270];pdf=n/np.maximum(n.sum(axis=1,keepdims=True),1)/width
    ee=pdf/np.sqrt(E);fig,axs=plt.subplots(1,2,figsize=(11,4))
    for ix in [0,2,5,9,14,17,19]:
        lab=f'x/L={(ix+.5)/20:.3f}';axs[0].semilogy(E,np.where(ee[ix]>0,ee[ix],np.nan),label=lab)
        q=excounts[ix].sum(axis=(0,1))[:270];q=q/max(q.sum(),1)/width;axs[1].semilogy(E,np.where(q>0,q,np.nan),label=lab)
    axs[0].set(xlabel='Total electron energy E (eV)',ylabel='EEPF (eV$^{-3/2}$)',xlim=(0,60),ylim=(1e-8,50));axs[1].set(xlabel='Axial energy Ex (eV)',ylabel='Axial-energy PDF (eV$^{-1}$)',xlim=(0,40),ylim=(1e-8,50))
    for ax in axs:ax.legend(fontsize=7);ax.grid(alpha=.2)
    fig.suptitle(note+'; raw counts pooled before normalization');save(fig,figs/'eepf_positions.png')
    phase_counts=counts[9:11].sum(axis=(0,2))[:,:270];phase_pdf=phase_counts/np.maximum(phase_counts.sum(axis=1,keepdims=True),1)/width
    fig,ax=plt.subplots(figsize=(8,4));z=ax.pcolormesh(np.linspace(0,1,201),e,np.log10(np.maximum(phase_pdf.T,1e-8)),vmin=-6,vmax=1,cmap='viridis',shading='flat');ax.set(ylim=(0,40),xlabel='RF phase',ylabel='E (eV)',title='Central 10%: log10 EEDF (eV$^{-1}$)');fig.colorbar(z,ax=ax);save(fig,figs/'phase_eedf.png')
    gap=json.loads((case/'status.json').read_text())['gap_mm'];ng=np.load(d/'work_sum_eV.npy').shape[0];dx=gap/1000/(ng-1)
    rawwork=np.load(d/'work_sum_eV.npy');power=rawwork*112000*1.60217662e-19/(1e-4*dx*(s['duration_s']/200));power[[0,-1]]*=2
    fig,ax=plt.subplots(figsize=(8,4));v=np.percentile(np.abs(power),99.5);pic=ax.imshow(power,origin='lower',aspect='auto',extent=[0,1,0,gap],cmap='RdBu_r',vmin=-v,vmax=v);ax.set(xlabel='RF phase',ylabel='x (mm)',title='Instantaneous field-kick work / cell volume (W/m3)');fig.colorbar(pic,ax=ax);save(fig,figs/'instantaneous_work.png')
    # CSVs expose exactly the plotted distributions, with sample counts so
    # downstream aggregation can preserve weights.
    data=target/'data';data.mkdir(exist_ok=True)
    with (data/'position_eepf.csv').open('w') as f:
        w=csv.writer(f);w.writerow(['x_L','E_center_eV','E_width_eV','raw_count','EEPF_eV-1.5','EEDF_eV-1'])
        for ix in range(20):
            for j in range(270):w.writerow([(ix+.5)/20,E[j],width[j],int(n[ix,j]),ee[ix,j],pdf[ix,j]])
    shutil.copy2(summary_path,target/'measurement_summary.json')
    from archive import package
    payload_names={'histogram_counts.npz','summary.json','upper_returns.npy','work_sum_eV.npy','recovery_aggregate.json','block.json'}
    archives=package([(p,p.name) for p in sorted(d.glob('*')) if p.is_file() and (p.name in payload_names or p.name.startswith('brh_'))]+[(summary_path,'measurement_summary.json')],target,f'{archive_prefix}_{target.name}_BRH_data')
    text=f'검출된 상부 기준 왕복 {s["powered_side_returns"]}개, 고유 UID {s["distinct_return_UIDs"]}개. 위상 반복 후보 {s["candidate_returns"]}개(고유 UID {s["distinct_candidate_UIDs"]}개). '
    if s['candidate_return_fraction'] is not None:text+=f'검출 왕복 중 후보 비율 {s["candidate_return_fraction"]*100:.3f}%. '
    if s['candidate_mean_signed_work_eV'] is not None:text+=f'후보의 평균 signed field work {s["candidate_mean_signed_work_eV"]:.4g} eV/왕복. '
    if s.get('candidate_mean_net_dK_eV') is not None:text+=f'충돌을 합친 후보의 순 운동에너지 변화 {s["candidate_mean_net_dK_eV"]:.4g} eV/왕복. '
    text+='전체 전자의 BRH 밀도 분율이 아닙니다. '+s['verdict']
    sections={'bounce':image_section('bounce',[im('figures/brh_returns.png',note+'; 에너지 부호와 독립적으로 정한 반복 위상 후보. 충돌/경계 검출 조건은 METHOD 참조.')]+extra,text),
        'spatial_eepf':image_section('spatial_eepf',[im('figures/eepf_positions.png',note+'; 전체 E와 Ex를 구분합니다. 각 위치에서 E<500eV 사건으로 정규화.'),im('figures/phase_eedf.png',note+'; 중앙10%의 위상별 EEDF.')]),
        'instantaneous_work':image_section('instantaneous_work',[im('figures/instantaneous_work.png',note+'; 순간 kick 에너지의 평균. 표준 heating의 <j>×<E>와 다릅니다.')])}
    sections['bounce']['title']='BRH 왕복·위상·에너지 진단';sections['spatial_eepf']['title']='위치별 EEPF·Ex 및 위상별 EEDF';sections['instantaneous_work']['title']='순간 전기장 일 지도'
    downloads=[{'label':f'BRH 사건·원시 energy counts·probe·일 지도 ({j+1}/{len(archives)}; 분할 시 모두 받기)','path':p.name} for j,p in enumerate(archives)]+[{'label':'BRH 수치·표본 수·해석 범위','path':'measurement_summary.json'},{'label':'위치별 EEPF CSV (raw count 포함)','path':'data/position_eepf.csv'}]
    return sections,downloads,text
