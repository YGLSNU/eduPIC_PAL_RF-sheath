#!/usr/bin/env python3
"""Plot saved phase diagnostics; this module never runs or changes the PIC solver."""
from pathlib import Path
import csv
import json
import os
import re
import numpy as np
os.environ.setdefault('MPLCONFIGDIR','/tmp/edupic-report-matplotlib')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

def save(fig,path):
    fig.savefig(path,dpi=150,bbox_inches='tight',pad_inches=.1)
    plt.close(fig)

def setup_diagram(path,gap,voltage,upper_powered=True):
    fig,ax=plt.subplots(figsize=(7,1.8),layout='constrained')
    ax.hlines([0,1],0,2,colors=['#777' if upper_powered else '#c33','#c33' if upper_powered else '#777'],lw=5)
    ax.annotate('',xy=(1.7,.98),xytext=(1.7,.02),arrowprops=dict(arrowstyle='<->'))
    ax.text(1.76,.5,f'{gap:g} mm',va='center')
    ax.text(.03,1.12,f'Upper x=L: {voltage:g} V peak, cos(RF)' if upper_powered else 'Upper x=L: grounded')
    ax.text(.03,-.25,'Lower x=0: grounded' if upper_powered else f'Lower x=0: {voltage:g} V peak, cos(RF)')
    ax.set(xlim=(-.1,2.8),ylim=(-.35,1.4));ax.axis('off');save(fig,path)

def phase_maps(arrays,keys,path,title,gap):
    x=np.linspace(0,gap,arrays['ne'].shape[0]);phase=(np.arange(arrays['ne'].shape[1])+.5)/arrays['ne'].shape[1]
    fig,axes=plt.subplots(2,2,figsize=(10,7),layout='constrained')
    units={'ne':'m$^{-3}$','ni':'m$^{-3}$','pot':'V','efield':'V m$^{-1}$',
           'powere':'W m$^{-3}$','poweri':'W m$^{-3}$','meanee':'eV','meanei':'eV','ioniz':'m$^{-3}$ s$^{-1}$'}
    titles={'ne':'Electron density','ni':'Ion density','pot':'Potential','efield':'Electric field',
            'powere':'Electron phase-mean heating','poweri':'Ion phase-mean heating',
            'meanee':'Mean electron energy','meanei':'Mean ion energy','ioniz':'Ionization rate'}
    for ax,k in zip(axes.flat,keys):
        a=arrays[k];kw={}
        if k in ['efield','powere','poweri']:
            limit=float(np.max(np.abs(a)));kw=dict(cmap='RdBu_r',vmin=-limit,vmax=limit)
        im=ax.pcolormesh(phase,x,a,shading='nearest',**kw)
        ax.set(title=titles[k],xlabel='RF phase t/T',ylabel='Position (mm)',xlim=(0,1),ylim=(0,gap))
        fig.colorbar(im,ax=ax,label=units[k])
    fig.suptitle(title);save(fig,path)

def write_csv(path,header,rows):
    with path.open('w') as f:
        w=csv.writer(f,lineterminator='\n');w.writerow(header);w.writerows(rows)

def export_case(source,out,voltage,config):
    """source is the complete saved per-voltage workspace, out is the report folder."""
    source=Path(source);out=Path(out);figdir=out/'figures';data=out/'data'
    figdir.mkdir(exist_ok=True,parents=True);data.mkdir(exist_ok=True)
    state=json.loads((source/'status.json').read_text());assess=json.loads((source/'assessment.json').read_text())
    assert state['status']=='criteria_met' and assess['passed'] and state['consecutive_passes']>=2
    averaged=source/'measurement_average';diag=source/state['latest_block']
    arrays={k:np.loadtxt(averaged/(k+'_xt.dat')) for k in ['pot','efield','ne','ni','je','ji','powere','poweri','meanee','meanei','ioniz']}
    shape=(config['grid_points'],200)
    assert all(a.shape==shape and np.isfinite(a).all() for a in arrays.values())
    for s in ['e','i']:
        assert np.allclose(arrays['power'+s],arrays['j'+s]*arrays['efield'],rtol=2e-8,atol=1e-7)
    x=np.linspace(0,config['gap_m'],config['grid_points']);gap=config['gap_m']*1000
    ne=np.trapezoid(arrays['ne'].mean(axis=1),x)/config['gap_m']
    assert np.isclose(ne,assess['indicators']['mean_density_e']['estimate'],rtol=1e-9)
    m=json.loads((averaged/'manifest.json').read_text());first,last=m['first_RF_cycle'],m['last_RF_cycle']
    title=f'Ar 20 mTorr | {voltage} V peak | {gap:g} mm | RF {first}-{last}'
    setup_diagram(figdir/'setup.png',gap,voltage)
    phase_maps(arrays,['pot','efield','ne','ni'],figdir/'fields.png',title,gap)
    phase_maps(arrays,['powere','poweri','meanee','ioniz'],figdir/'heating.png',title,gap)
    hist=np.loadtxt(source/'history.dat',ndmin=2)
    balance=list(csv.DictReader((source/'particle_balance.csv').open()))
    rows=[r for r in balance if first<=int(r['RF_cycle'])<=last]
    assert len(rows)==assess['measurement_cycles']
    duration=len(rows)/config['frequency_Hz'];A=config['fictive_area_m2'];weight=config['weight']
    sums=lambda key:sum(float(r[key]) for r in rows)
    rates={k:sums(k)*weight/(A*duration) for k in ['e_loss_lower','e_loss_upper','i_loss_lower','i_loss_upper']}
    channels={k:sums(k)/(A*duration) for k in ['e_field_work_J','i_field_work_J','e_wall_energy_J','i_wall_energy_J']}
    channels['excitation_ionization_threshold_J']=(sums('excitations')*11.5+sums('ionizations')*15.8)*1.60217662e-19*weight/(A*duration)
    fig,axes=plt.subplots(1,3,figsize=(13,3.7),layout='constrained')
    for col,label in [(1,'Electrons'),(2,'Ar+ ions')]:axes[0].plot(hist[:,0],hist[:,col],label=label)
    axes[0].axvspan(first,last,color='#9dc99b',alpha=.4,label='Accepted average')
    axes[0].set(xlabel='RF cycles',ylabel='Macroparticles',title='Particle history');axes[0].legend(fontsize=8)
    bx=[];by=[]
    for start in range(0,len(balance),20):
        b=balance[start:start+20]
        if len(b)<20:continue
        losses=sum(int(r['e_loss_lower'])+int(r['e_loss_upper']) for r in b)
        if losses:bx.append(int(b[-1]['RF_cycle']));by.append(sum(int(r['ionizations']) for r in b)/losses)
    axes[1].plot(bx,by);axes[1].axhline(1,color='black',ls='--');axes[1].axvspan(first,last,color='#9dc99b',alpha=.4)
    axes[1].set(xlabel='RF cycles',ylabel='Births / electron wall losses',title='Disjoint 20-RF balance')
    inds=assess['indicators'];keys=list(inds)
    axes[2].barh(np.arange(len(keys)),[100*inds[k]['relative_uncertainty_indicator'] for k in keys])
    axes[2].plot([100*inds[k]['tolerance'] for k in keys],np.arange(len(keys)),'rx',label='Threshold')
    axes[2].set(yticks=np.arange(len(keys)),yticklabels=keys,xlabel='Uncertainty indicator (%)',title='Accepted sampling indicators');axes[2].tick_params(axis='y',labelsize=7);axes[2].legend(fontsize=8)
    fig.suptitle(title);save(fig,figdir/'convergence.png')
    eepf=np.loadtxt(diag/'eepf.dat');ifed=np.loadtxt(diag/'ifed.dat');block=json.loads((diag/'block.json').read_text())
    dfirst,dlast=block['cycles_inclusive'];de=float(np.median(np.diff(eepf[:,0])));di=float(np.median(np.diff(ifed[:,0])))
    assert abs(np.sum(eepf[:,1]*np.sqrt(eepf[:,0]))*de-1)<2e-5
    assert np.allclose(np.sum(ifed[:,1:],axis=0)*di,1,atol=.00051)
    fig,axes=plt.subplots(1,3,figsize=(12,3.6),layout='constrained')
    for s,label in [('e','Electrons'),('i','Ar+ ions')]:axes[0].plot(x*1000,arrays['n'+s].mean(axis=1),label=label)
    axes[0].set(xlabel='Position (mm)',ylabel='Density (m$^{-3}$)',title=f'Whole accepted RF {first}-{last}');axes[0].legend()
    axes[1].semilogy(eepf[:,0],np.where(eepf[:,1]>0,eepf[:,1],np.nan))
    axes[1].set(xlabel='Electron energy (eV)',ylabel='EEPF (eV$^{-3/2}$)',title=f'Central 10%, RF {dfirst}-{dlast}',xlim=(0,100))
    axes[2].plot(ifed[:,0],ifed[:,1],label='Upper RF');axes[2].plot(ifed[:,0],ifed[:,2],label='Lower ground')
    keep=np.max(ifed[:,1:],axis=1)>0; xmax=float(ifed[keep,0].max())*1.1 if keep.any() else 100
    axes[2].set(xlabel='Ion energy (eV)',ylabel='Normalized IEDF (eV$^{-1}$)',title=f'Last diagnostic RF {dfirst}-{dlast}',xlim=(0,xmax));axes[2].legend()
    for ax in axes:ax.grid(alpha=.2)
    fig.suptitle(f'{voltage} V | Density uses accepted average; energy PDFs use the last diagnostic block')
    save(fig,figdir/'distributions.png')
    phase=(np.arange(200)+.5)/200
    fig,axes=plt.subplots(1,3,figsize=(12,3.6),layout='constrained')
    center=(x>.45*config['gap_m'])&(x<.55*config['gap_m'])
    for key,label in [('je','Electrons'),('ji','Ar+ ions')]:axes[0].plot(phase,arrays[key][center].mean(axis=0),label=label)
    axes[0].set(xlabel='RF phase t/T',ylabel='Conduction current density (A m$^{-2}$)',title='Central 10%: no displacement current');axes[0].legend(fontsize=8)
    axes[1].bar(np.arange(4),list(rates.values()),color=['#4477aa','#88aacc','#ee9933','#f4bc70'])
    axes[1].set(xticks=np.arange(4),xticklabels=['e lower','e upper','i lower','i upper'],ylabel='Wall flux (m$^{-2}$ s$^{-1}$)',title='Whole accepted measurement');axes[1].tick_params(axis='x',labelrotation=25)
    keys=list(channels);axes[2].bar(np.arange(5),list(channels.values()))
    axes[2].set(xticks=np.arange(5),xticklabels=['e field','i field','e wall KE','i wall KE','exc+ion'],ylabel='Power / one face area (W m$^{-2}$)',title='Measured channels; not full closure');axes[2].tick_params(axis='x',labelrotation=35)
    fig.suptitle(title);save(fig,figdir/'walls_power.png')
    write_csv(data/'profiles.csv',['x_m','ne_m-3','ni_m-3','phase_je_E_W_m-3','phase_ji_E_W_m-3','ionization_m-3_s-1'],zip(x,*[arrays[k].mean(axis=1) for k in ['ne','ni','powere','poweri','ioniz']]))
    write_csv(data/'eepf_last_block.csv',['energy_eV','EEPF_eV-3_2'],eepf)
    write_csv(data/'ifed_last_block.csv',['energy_eV','upper_RF_eV-1','lower_ground_eV-1'],ifed)
    write_csv(data/'wall_flux.csv',['channel','flux_m-2_s-1'],rates.items())
    write_csv(data/'power_channels.csv',['channel','W_m-2'],channels.items())
    write_csv(data/'sampling_indicators.csv',['indicator','relative_uncertainty','first_last_half_change','tolerance','passed'],[(k,v['relative_uncertainty_indicator'],v['first_last_half_relative_change'],v['tolerance'],v['passed']) for k,v in inds.items()])
    output={'voltage_V':voltage,'total_rf':state['checkpoint_cycle'],'measurement_rf':len(rows),
            'measurement_first_rf':first,'measurement_last_rf':last,'distribution_first_rf':dfirst,'distribution_last_rf':dlast,
            'ne_mean_m3':ne,'ni_mean_m3':assess['indicators']['mean_density_i']['estimate'],
            'birth_loss_ratio':sums('ionizations')/(sums('e_loss_lower')+sums('e_loss_upper')),
            'wall_flux_m2_s':rates,'power_W_m2':channels,'mean_ion_energy_last_block_eV':{'upper':float(np.sum(ifed[:,0]*ifed[:,1])*di),'lower':float(np.sum(ifed[:,0]*ifed[:,2])*di)},
            'basic_numerical_checks':state['last_numerical_validation'],'source_sha256':config['source_sha256']}
    (data/'diagnostics.json').write_text(json.dumps(output,indent=2)+'\n')
    return output,arrays
