#!/usr/bin/env python3
"""Complete a voltage-scan overview from saved phase maps and exported diagnostics."""
from pathlib import Path
from io import BytesIO
import argparse
import json
import zipfile
import numpy as np
from plot_phase import plt,save

COLORS=['#4477aa','#ee9933','#aa3377','#228833','#bb4455']

def load_case(directory):
    meta=json.loads((directory/'report.json').read_text())
    diagnostics=json.loads((directory/'data/diagnostics.json').read_text())
    if meta['status']!='criteria_met':raise ValueError('Comparison requires accepted stationary measurements')
    direct=directory/'data/phase_maps.npz'
    if direct.exists():raw=direct.read_bytes()
    else:
        archives=list(directory.glob('*_core.zip'))
        if len(archives)!=1:raise ValueError('Need one core ZIP or data/phase_maps.npz in '+str(directory))
        with zipfile.ZipFile(archives[0]) as z:raw=z.read('measurement_average/phase_maps.npz')
    with np.load(BytesIO(raw),allow_pickle=False) as f:arrays={k:f[k] for k in f.files}
    x=arrays['x_m'];phase=arrays['rf_phase_cycles'];shape=(len(x),len(phase))
    for key in ['pot','efield','ne','ni','meanee','ioniz']:
        assert arrays[key].shape==shape and np.isfinite(arrays[key]).all(),key
    assert np.isclose(x[-1]*1000,meta['conditions']['gap_mm'])
    profiles=np.loadtxt(directory/'data/profiles.csv',delimiter=',',skiprows=1)
    assert np.allclose(profiles[:,0],x)
    assert np.allclose(profiles[:,1],arrays['ne'].mean(axis=1),rtol=2e-8)
    mean_ne=float(np.trapezoid(arrays['ne'].mean(axis=1),x)/(x[-1]-x[0]))
    assert np.isclose(mean_ne,diagnostics['ne_mean_m3'],rtol=2e-8)
    eepf=np.loadtxt(directory/'data/eepf_last_block.csv',delimiter=',',skiprows=1)
    ifed=np.loadtxt(directory/'data/ifed_last_block.csv',delimiter=',',skiprows=1)
    de=np.median(np.diff(eepf[:,0]));di=np.median(np.diff(ifed[:,0]))
    assert abs(np.sum(eepf[:,1]*np.sqrt(eepf[:,0]))*de-1)<2e-5
    assert np.allclose(ifed[:,1:].sum(axis=0)*di,1,atol=.00051)
    return {'meta':meta,'d':diagnostics,'a':arrays,'eepf':eepf,'ifed':ifed,'directory':directory}

def map_comparison(cases,keys,titles,units,path):
    fig,axes=plt.subplots(len(keys),len(cases),figsize=(3.2*len(cases),3.1*len(keys)),squeeze=False,layout='constrained')
    for row,key in enumerate(keys):
        low=min(float(c['a'][key].min()) for c in cases);high=max(float(c['a'][key].max()) for c in cases)
        kw={'cmap':'viridis','vmin':max(0,low),'vmax':high}
        if key in ['pot','efield']:
            limit=max(abs(low),abs(high));kw={'cmap':'RdBu_r','vmin':-limit,'vmax':limit}
        for col,c in enumerate(cases):
            a=c['a'];ax=axes[row,col]
            im=ax.pcolormesh(a['rf_phase_cycles'],a['x_m']*1000,a[key],shading='nearest',rasterized=True,**kw)
            ax.set(title=f'{c["d"]["voltage_V"]} V | {titles[row]}',xlabel='RF phase t/T',ylabel='Position (mm)',xlim=(0,1),ylim=(0,40))
        fig.colorbar(im,ax=list(axes[row]),label=units[row])
    fig.suptitle('Ar 20 mTorr | 40 mm | Common color range within each row | Accepted RF windows listed in the report')
    save(fig,path)

def power_figure(cases,path):
    vs=[c['d']['voltage_V'] for c in cases]
    fig,axes=plt.subplots(1,2,figsize=(11,3.8),layout='constrained')
    if len(cases)==1:
        c=cases[0];p=c['d']['power_W_m2']
        axes[0].bar(['Electrons','Ar+ ions','Total'],[p['e_field_work_J'],p['i_field_work_J'],p['e_field_work_J']+p['i_field_work_J']])
        axes[1].bar(['Electron wall KE','Ion wall KE','Excitation + ionization'],[p['e_wall_energy_J'],p['i_wall_energy_J'],p['excitation_ionization_threshold_J']])
        for ax,title in zip(axes,['Field-to-particle work','Measured losses: not full energy closure']):
            ax.set(ylabel='Power / one face area (W m$^{-2}$)',title=title);ax.grid(axis='y',alpha=.2);ax.tick_params(axis='x',labelsize=9)
        fig.suptitle(f'{vs[0]} V | Whole accepted RF {c["d"]["measurement_first_rf"]}-{c["d"]["measurement_last_rf"]}')
        save(fig,path);return
    for key,label in [('e_field_work_J','Electron field work'),('i_field_work_J','Ion field work')]:
        axes[0].plot(vs,[c['d']['power_W_m2'][key] for c in cases],'o-',label=label)
    axes[0].plot(vs,[c['d']['power_W_m2']['e_field_work_J']+c['d']['power_W_m2']['i_field_work_J'] for c in cases],'k--',label='Total field work')
    for key,label in [('e_wall_energy_J','Electron wall kinetic'),('i_wall_energy_J','Ion wall kinetic'),('excitation_ionization_threshold_J','Excitation + ionization threshold')]:
        axes[1].plot(vs,[c['d']['power_W_m2'][key] for c in cases],'o-',label=label)
    for ax,title in zip(axes,['Field-to-particle work','Measured losses: not full energy closure']):
        ax.set(xlabel='Voltage peak (V)',ylabel='Power / one face area (W m$^{-2}$)',title=title);ax.legend(fontsize=8);ax.grid(alpha=.2)
    fig.suptitle('Whole accepted measurement | Both-wall kinetic loss uses one-face reference area')
    save(fig,path)

def complete(directory):
    directory=Path(directory);meta=json.loads((directory/'run.json').read_text())
    cases=[load_case(directory/Path(c['path']).parent) for c in sorted(meta['cases'],key=lambda c:c['voltage_V'])]
    if any(c['meta']['conditions'].get('gap_mm')!=40 or c['meta']['conditions'].get('pressure_mTorr')!=20 for c in cases):
        raise ValueError('This saved diagnostic comparison is for the 20 mTorr, 40 mm scan')
    map_comparison(cases,['pot','efield'],['Potential','Electric field'],['Potential (V)','Electric field (V m$^{-1}$)'],directory/'fields_compare.png')
    map_comparison(cases,['meanee','ioniz'],['Mean electron energy','Ionization'],['Mean energy (eV)','Ionization (m$^{-3}$ s$^{-1}$)'],directory/'ionization_compare.png')
    fig,axes=plt.subplots(1,2,figsize=(10,3.7),layout='constrained')
    for c,color in zip(cases,COLORS):
        for ax,key in zip(axes,['ne','ni']):ax.plot(c['a']['x_m']*1000,c['a'][key].mean(axis=1),color=color,label=f'{c["d"]["voltage_V"]} V')
    for ax,title in zip(axes,['Electron density','Ion density']):
        ax.set(xlabel='Position (mm)',ylabel='Density (m$^{-3}$)',title=title,xlim=(0,40));ax.legend(fontsize=8);ax.grid(alpha=.2)
    fig.suptitle('Whole accepted measurement | Lower x=0 grounded, upper x=40 mm powered');save(fig,directory/'density_compare.png')
    fig,axes=plt.subplots(1,3,figsize=(13,3.8),layout='constrained')
    xmax=0
    for c,color in zip(cases,COLORS):
        label=f'{c["d"]["voltage_V"]} V';e=c['eepf'];i=c['ifed']
        axes[0].semilogy(e[:,0],np.where(e[:,1]>0,e[:,1],np.nan),color=color,label=label)
        axes[1].plot(i[:,0],i[:,1],color=color,label=label);axes[2].plot(i[:,0],i[:,2],color=color,label=label)
        keep=np.max(i[:,1:],axis=1)>0
        if keep.any():xmax=max(xmax,float(i[keep,0].max()))
    axes[0].set(xlabel='Energy (eV)',ylabel='EEPF (eV$^{-3/2}$)',title='Central 10% EEPF',xlim=(0,100))
    for ax,title in zip(axes[1:],['Upper powered IEDF','Lower grounded IEDF']):ax.set(xlabel='Energy (eV)',ylabel='Normalized IEDF (eV$^{-1}$)',title=title,xlim=(0,1.08*xmax))
    for ax in axes:ax.legend(fontsize=8);ax.grid(alpha=.2)
    fig.suptitle('Energy PDFs use each case\'s last 20 RF block; not the full accepted measurement')
    save(fig,directory/'distributions_compare.png')
    fig,axes=plt.subplots(1,3,figsize=(12,3.8),layout='constrained');vs=[c['d']['voltage_V'] for c in cases]
    for ax,species in zip(axes[:2],['e','i']):
        for side,label in [('upper','Upper RF'),('lower','Lower ground')]:ax.plot(vs,[c['d']['wall_flux_m2_s'][species+'_loss_'+side] for c in cases],'o-',label=label)
        ax.set(xlabel='Voltage peak (V)',ylabel='Flux (m$^{-2}$ s$^{-1}$)',title=('Electron' if species=='e' else 'Ion')+' wall flux')
    for side,label in [('upper','Upper RF'),('lower','Lower ground')]:axes[2].plot(vs,[c['d']['mean_ion_energy_last_block_eV'][side] for c in cases],'o-',label=label)
    axes[2].set(xlabel='Voltage peak (V)',ylabel='Mean ion impact energy (eV)',title='Last 20 RF diagnostic block')
    for ax in axes:ax.legend(fontsize=8);ax.grid(alpha=.2)
    fig.suptitle('Wall flux: full accepted measurement | Ion impact energy: last 20 RF block')
    save(fig,directory/'walls_compare.png');power_figure(cases,directory/'power_compare.png')
    sections={s['id']:s for s in meta['sections']}
    descriptions={
      'density':('density_compare.png','전압별 전자·이온 밀도 공간분포. 각 조건의 전체 측정 구간 평균입니다.'),
      'fields':('fields_compare.png','위: 전위, 아래: 전기장. 행마다 공통 색상 범위, 각 조건의 전체 측정 구간 평균입니다.'),
      'ionization':('ionization_compare.png','위: 평균 전자 에너지, 아래: 이온화율. 행마다 공통 색상 범위입니다.'),
      'distributions':('distributions_compare.png','중앙 EEPF와 상·하부 전극 IEDF. 각 전압의 마지막20RF 진단만 사용했습니다.'),
      'walls':('walls_compare.png','전자·이온 flux는 전체 측정 구간, 평균 이온 입사 에너지는 마지막20RF입니다.'),
      'power':('power_compare.png','입자 field-work와 측정된 에너지 손실 채널. 완전한 에너지 폐합이나 발생기 총 W를 뜻하지 않습니다.')}
    windows=[]
    for c in cases:
        d=c['d'];windows.append(f'| {d["voltage_V"]} | {d["measurement_first_rf"]}–{d["measurement_last_rf"]} | {d["distribution_first_rf"]}–{d["distribution_last_rf"]} |')
    table='| V peak | 밀도·장·heating·flux 평균 RF | EEPF·IEDF 진단 RF |\n|---:|---|---|\n'+'\n'.join(windows)
    for key,(path,caption) in descriptions.items():
        sec=sections[key];sec['images']=[{'path':path,'caption':caption}]
        sec['availability']='전압별 전체 측정 구간 비교' if key not in ['distributions'] else '전압별 마지막20RF 분포'
        sec['text']='각 그림은 '+'·'.join(str(v) for v in vs)+' V를 비교합니다. 전압별 상세 그림·CSV는 위 조건별 결과 표에서 열 수 있습니다.'
    sections['distributions']['table']=table
    meta['measurement_note']='/'.join(str(v) for v in vs)+'V에서 각각'+'/'.join(str(c['d']['measurement_rf']) for c in cases)+'RF 평균. EEPF·IEDF는 각 마지막20RF.'
    (directory/'run.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n')
    # Give every previously indirect case section an actual plot in its own place.
    for c in cases:
        d=c['directory'];m=c['meta'];a=c['a'];interval=f'RF{c["d"]["measurement_first_rf"]}–{c["d"]["measurement_last_rf"]}'
        fig,ax=plt.subplots(figsize=(6,3.8),layout='constrained')
        for k,label in [('ne','Electrons'),('ni','Ar+ ions')]:ax.plot(a['x_m']*1000,a[k].mean(axis=1),label=label)
        ax.set(xlabel='Position (mm)',ylabel='Density (m$^{-3}$)',title=f'{c["d"]["voltage_V"]} V | {interval}');ax.legend();ax.grid(alpha=.2);save(fig,d/'figures/density.png')
        fig,axes=plt.subplots(1,2,figsize=(9,3.8),layout='constrained')
        for ax,key,title,unit in zip(axes,['meanee','ioniz'],['Mean electron energy','Ionization rate'],['eV','m$^{-3}$ s$^{-1}$']):
            im=ax.pcolormesh(a['rf_phase_cycles'],a['x_m']*1000,a[key],shading='nearest',rasterized=True)
            ax.set(title=title,xlabel='RF phase t/T',ylabel='Position (mm)',xlim=(0,1),ylim=(0,40));fig.colorbar(im,ax=ax,label=unit)
        fig.suptitle(f'{c["d"]["voltage_V"]} V | {interval}');save(fig,d/'figures/ionization.png')
        power_figure([c],d/'figures/power.png')
        children={s['id']:s for s in m['sections']}
        for key,path,caption in [('density','figures/density.png','전체 측정 구간의 평균 전자·이온 밀도'),('ionization','figures/ionization.png','전체 측정 구간의 평균 전자 에너지·이온화율'),('power','figures/power.png','전체 측정 구간의 측정된 전력 채널')]:
            children[key]['images']=[{'path':path,'caption':caption}];children[key]['text']=''
        children['power']['text']='field-work는 이산 입자 속도 갱신의 일이며, 벽 항은 운동에너지 유출입니다. 미계측 기체 전달·저장 항이 있어 완전한 전력 폐합이나 전체 벽 열부하를 뜻하지 않습니다.'
        (d/'report.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n')
    return {'voltages':vs,'new_overview_figures':[v[0] for v in descriptions.values()],'all_diagnostics_checked':True}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path)
    print(json.dumps(complete(p.parse_args().directory),ensure_ascii=False,indent=2))
