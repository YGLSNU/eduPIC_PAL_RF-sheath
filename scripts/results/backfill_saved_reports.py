#!/usr/bin/env python3
"""Restore missing report figures from saved eduPIC exports, without running PIC."""
from pathlib import Path
from io import BytesIO
import argparse,csv,json,re,zipfile
import numpy as np
from catalog import STANDARD_SECTIONS
from plot_phase import plt,save,write_csv

COLORS=['#4477aa','#ee9933','#aa3377','#228833','#bb4455']
KEYS=['pot','efield','ne','ni','je','ji','powere','poweri','meanee','meanei','ioniz']

def read(p):return json.loads(p.read_text())
def put(p,m):p.write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n')
def one(d,pattern):
    paths=sorted(d.glob(pattern))
    if len(paths)!=1:raise ValueError((d,pattern,paths))
    return paths[0]
def attach(m,key,path,caption,text=None):
    sec=next((s for s in m['sections'] if s['id']==key),None)
    if sec is None:sec={'id':key};m['sections'].append(sec)
    previous=[im for im in sec.get('images',[]) if im['path']!=path]
    sec['images']=[{'path':path,'caption':caption},*previous];sec['data_status']='available'
    if text is not None:sec['text']=text
    sec.setdefault('availability',caption)

def density_plot(a,path,title):
    fig,ax=plt.subplots(figsize=(7,3.8),layout='constrained')
    for col,label in [(1,'Electrons'),(2,'Ar+ ions')]:ax.plot(a[:,0]*1000,a[:,col],label=label)
    ax.set(xlabel='Position (mm)',ylabel='Density (m$^{-3}$)',title=title);ax.legend();ax.grid(alpha=.2);save(fig,path)

def energy_ionization(x,a,path,title):
    fig,axes=plt.subplots(1,2,figsize=(10,3.8),layout='constrained')
    phase=(np.arange(a['meanee'].shape[1])*20+10.5)/4000
    for ax,key,label,unit in zip(axes,['meanee','ioniz'],['Mean electron energy','Ionization rate'],['eV','m$^{-3}$ s$^{-1}$']):
        im=ax.pcolormesh(phase,x*1000,a[key],shading='nearest',rasterized=True)
        ax.set(xlabel='RF phase t/T',ylabel='Position (mm)',title=label,xlim=(0,1));fig.colorbar(im,ax=ax,label=unit)
    fig.suptitle(title);save(fig,path)

def flux_figure(flux,path,title,lower_powered=False):
    fig,ax=plt.subplots(figsize=(8,3.8),layout='constrained')
    labels=['e lower','e upper','i lower','i upper']
    ax.bar(labels,[flux[k] for k in ['e_lower','e_upper','i_lower','i_upper']],color=['#4477aa','#88aacc','#ee9933','#f4bc70'])
    ax.set(ylabel='Wall flux (m$^{-2}$ s$^{-1}$)',title=title)
    ax.set_xlabel('Lower powered / upper grounded' if lower_powered else 'Lower grounded / upper powered')
    ax.grid(axis='y',alpha=.2);save(fig,path)

def parse_info(text):
    out={}
    for species,name in [('e','Electron'),('i','Ion')]:
        for electrode in ['powered','grounded']:
            pattern=rf'{name} flux at {electrode} electrode\s*=\s*([\d.eE+\-]+)'
            match=re.search(pattern,text)
            if not match:raise ValueError('Missing native flux: '+pattern)
            out[species+'_'+electrode]=float(match[1])
    out['cycles']=int(re.search(r'cycles in this run\s*=\s*(\d+)',text)[1])
    for species,name in [('e','Electron'),('i','Ion')]:
        out[species+'_power_W_m3']=float(re.search(rf'{name} power density \(average\)\s*=\s*([\d.eE+\-]+)',text)[1])
    return out

def baseline(root):
    for id,start,end in [('261118_measure5',1701,1705),('261118_measure120',1706,1825)]:
        d=root/'results'/id;m=read(d/'run.json');figs=d/'figures';figs.mkdir(exist_ok=True)
        a={};x=None
        for key in KEYS:
            values=np.loadtxt(one(d/'csv','*_'+key+'_xt.csv'),delimiter=',',skiprows=1)
            assert values.shape==(400,201) and np.isfinite(values).all()
            if x is None:x=values[:,0]
            else:assert np.allclose(values[:,0],x)
            a[key]=values[:,1:]
        for s in ['e','i']:assert np.allclose(a['power'+s],a['j'+s]*a['efield'],rtol=4e-6,atol=.003)
        density=np.loadtxt(one(d/'csv','*_density.csv'),delimiter=',',skiprows=1)
        assert np.allclose(density[:,1],a['ne'].mean(axis=1),rtol=3e-6)
        title=f'Ar 75.006 mTorr | 250 V | 25 mm | RF {start}-{end}'
        density_plot(density,figs/'density.png',title+'\nLower RF / upper ground')
        energy_ionization(x,a,figs/'ionization.png',title)
        infos=[];sources=[]
        if id.endswith('measure5'):
            p=one(d,'*_info.txt');infos.append(parse_info(p.read_text()));sources.append(p.name)
        else:
            for p in sorted(d.glob('*_cycle*-*.zip')):
                with zipfile.ZipFile(p) as z:
                    name=next(n for n in z.namelist() if n.endswith('/info.txt'))
                    infos.append(parse_info(z.read(name).decode()));sources.append(p.name+'!'+name)
        count=sum(q['cycles'] for q in infos);assert count==end-start+1
        mean=lambda key:sum(q[key]*q['cycles'] for q in infos)/count
        flux={s+'_'+side:mean(s+'_'+electrode) for s in ['e','i'] for side,electrode in [('lower','powered'),('upper','grounded')]}
        flux_figure(flux,figs/'wall_flux.png',title+'\nWeighted native info.txt flux (rounded exports)',True)
        fig,axes=plt.subplots(1,2,figsize=(11,3.7),layout='constrained')
        means=[]
        for s,label in [('e','Electrons'),('i','Ar+ ions')]:
            p=a['power'+s];axes[0].plot(x*1000,p.mean(axis=1),label=label);means.append(float(p.mean()))
        axes[0].set(xlabel='Position (mm)',ylabel='Phase-mean jE (W m$^{-3}$)',title='Mean power-density profile');axes[0].legend()
        axes[1].bar(['Electron','Ion','Total'],[*means,sum(means)])
        axes[1].set(ylabel='Grid/phase mean jE (W m$^{-3}$)',title='Original phase-mean j x E definition')
        fig.suptitle(title+' | no particle field-work / full energy-closure diagnostic');save(fig,figs/'power.png')
        for s,value in zip(['e','i'],means):assert np.isclose(value,mean(s+'_power_W_m3'),rtol=.001)
        (d/'data').mkdir(exist_ok=True)
        write_csv(d/'data/wall_flux.csv',['channel','flux_m-2_s-1'],flux.items())
        put(d/'data/audit_evidence.json',{'RF_first':start,'RF_last':end,'info_sources':sources,'flux_definition':'Cycle-weighted average of rounded native info.txt exports; lower powered, upper grounded.',
             'mean_phase_jE_W_m3':dict(zip(['electron','ion'],means)),'full_particle_power_balance_recorded':False})
        attach(m,'density','figures/density.png',f'RF{start}–{end} 평균 전자·이온 밀도. x=0 하부 RF, x=25mm 상부 접지입니다.',text='')
        attach(m,'ionization','figures/ionization.png',f'RF{start}–{end}의 평균 전자 에너지·이온화율',text='')
        attach(m,'walls','figures/wall_flux.png','원본 info.txt의 구간별 flux를 측정 RF 길이로 가중 평균했습니다. 출력 반올림 정밀도를 유지합니다.',text='')
        attach(m,'power','figures/power.png','위상 평균 j×E의 공간분포와 원본 정의의 평균 전력밀도입니다. 입자 field-work와 구분합니다.',text='완전한 충돌·벽·저장 에너지 수지는 이 원본 실행에 기록되지 않았습니다.')
        next(s for s in m['sections'] if s['id']=='power')['data_status']='partial'
        m['downloads'] += [q for q in [{'label':'측정 구간 전극 flux CSV','path':'data/wall_flux.csv'},{'label':'후처리 근거·정밀도','path':'data/audit_evidence.json'}] if q['path'] not in {e['path'] for e in m['downloads']}]
        put(d/'run.json',m)
    d=root/'results/261117_initial';m=read(d/'run.json')
    density=np.loadtxt(one(d,'*snapshot1700_density.csv'),delimiter=',',skiprows=1)
    density_plot(density,d/'figures/density.png','RF1700 single saved snapshot | not a time average\nAr 75.006 mTorr | lower RF / upper ground')
    attach(m,'density','figures/density.png','저장된 RF1700 단일 시점의 밀도입니다. 시간평균·최종 정상 방전 측정과 구분합니다.',text='')
    next(s for s in m['sections'] if s['id']=='density')['data_status']='partial';put(d/'run.json',m)

def extinguished(root):
    d=root/'results/261119_gap25_V100-300';m=read(d/'run.json')
    attach(m,'convergence',one(d,'*_progress.png').name,'전자·이온 계산 입자의 시간 이력. 세 전압 모두 소멸하여 통계 수렴으로 판정하지 않았습니다.',text='[300 V 계산 입자 수10배 검증](validation/README.md)도 함께 보관되어 있습니다.')
    attach(m,'density',one(d,'*_comparison_decay.png').name,'입자 수에서 환산한 체적평균 밀도의 감쇠 이력입니다. 정상 방전의 공간분포가 아닙니다.',text='')
    next(s for s in m['sections'] if s['id']=='density')['data_status']='partial';put(d/'run.json',m)
    for child in sorted(d.glob('*/report.json')):
        c=read(child);p=child.parent;a=np.loadtxt(one(p,'*_history.dat'),ndmin=2)
        factor=c['conditions']['weight']/(1e-4*c['conditions']['gap_mm']*.001)
        fig,ax=plt.subplots(figsize=(7,3.8),layout='constrained')
        for col,label in [(1,'Electrons'),(2,'Ar+ ions')]:ax.plot(a[:,0],a[:,col]*factor,label=label)
        ax.set(xlabel='RF cycles since condition change',ylabel='Volume-mean density (m$^{-3}$)',title=f'{c["conditions"]["voltage_peak_V"][0]} V | 20 mTorr | 25 mm\nDecay history, not a stationary spatial profile');ax.legend();ax.grid(alpha=.2)
        (p/'figures').mkdir(exist_ok=True);save(fig,p/'figures/density.png')
        attach(c,'density','figures/density.png','체적평균 밀도의 시간 변화',text='전자 소멸 뒤의 빈 상태는 정상 방전의 측정 평균이 아닙니다.')
        sec=next(s for s in c['sections'] if s['id']=='density');sec['data_status']='partial';sec['images'][0]['caption']='입자 수·입자 가중치·체적으로 환산한 체적평균 밀도의 시간 변화입니다.'
        put(child,c)

def transient_power(rows,summary,meta):
    duration=len(rows)/(meta['conditions']['frequency_MHz']*1e6);area=1e-4;weight=meta['conditions']['weight']
    sums=lambda key:sum(float(r[key]) for r in rows)
    flux={s+'_'+side:sums(s+'_loss_'+side)*weight/(area*duration) for s in ['e','i'] for side in ['lower','upper']}
    power={k:sums(k)/(area*duration) for k in ['e_field_work_J','i_field_work_J','e_wall_energy_J','i_wall_energy_J']}
    power['excitation_ionization_threshold_J']=summary['excitation_ionization_threshold_energy_J']/(area*duration)
    power['electron_stored_kinetic_change_J']=summary['e_kinetic_change_J']/(area*duration)
    assert np.isclose(power['e_field_work_J'],summary['mean_e_field_work_W_m3']*.025,rtol=1e-10)
    assert np.isclose(sums('ionizations'),summary['ionization_pairs'])
    assert np.isclose(sums('e_loss_lower')+sums('e_loss_upper'),summary['e_wall_losses'])
    for r in rows:
        for s in ['e','i']:assert int(r['end_'+s])-int(r['start_'+s])==int(r['ionizations'])-int(r[s+'_loss_lower'])-int(r[s+'_loss_upper'])
    return flux,power

def power_bars(power,path,title):
    fig,axes=plt.subplots(1,2,figsize=(11,3.8),layout='constrained')
    axes[0].bar(['Electrons','Ar+ ions'],[power['e_field_work_J'],power['i_field_work_J']]);axes[0].set(title='Field-to-particle work')
    axes[1].bar(['e wall KE','i wall KE','exc+ion','e storage change'],[power[k] for k in ['e_wall_energy_J','i_wall_energy_J','excitation_ionization_threshold_J','electron_stored_kinetic_change_J']])
    axes[1].set(title='Measured channels; incomplete energy closure')
    for ax in axes:ax.set_ylabel('Power / one face area (W m$^{-2}$)');ax.axhline(0,color='black',lw=.6);ax.tick_params(axis='x',labelsize=8)
    fig.suptitle(title);save(fig,path)

def diagnostics(root):
    d=root/'results/261120_loss-check';m=read(d/'run.json');cases=[]
    with zipfile.ZipFile(one(d,'*_all.zip')) as z:
        for q in sorted(d.glob('*/report.json')):
            p=q.parent;c=read(q);summary=read(p/'data/summary.json');rows=list(csv.DictReader((p/'data/particle_balance.csv').open()))
            prefix='2026-11-20_Ar_20mTorr_extinction_diagnosis/controls/'+summary['case']+'/'
            a={key:np.loadtxt(BytesIO(z.read(prefix+key+'_xt.dat'))) for key in KEYS}
            assert all(v.shape==(400,200) and np.isfinite(v).all() for v in a.values())
            for s in ['e','i']:assert np.allclose(a['power'+s],a['j'+s]*a['efield'],rtol=4e-6,atol=.003)
            profiles=np.loadtxt(p/'data/profiles.csv',delimiter=',',skiprows=1);x=profiles[:,0]
            assert np.allclose(profiles[:,1],a['ne'].mean(axis=1),rtol=3e-6)
            f=p/'figures';first,last=summary['first_RF_cycle'],summary['last_RF_cycle']
            title=f'TRANSIENT {len(rows)} RF | {summary["pressure_mTorr"]:.3f} mTorr | {summary["voltage_peak_V"]} V | RF {first}-{last}'
            c['source']['description']='상부 RF C/eduPIC.cc + 입자·에너지 수지 기록 진단; C++11 컴파일'
            c['source']['revision']='진단 소스 SHA256 5acbe3b6b8aa8f73655cbdcfcb95c75f2d490607f070700ac7e67d943b7ec4ef'
            c['measurement_note']=f'RF{first}–{last}, {len(rows)} RF 과도구간 진단; 정상상태 평균이 아닙니다. 동일 초기 상태의 압력 대조는 250 V·RF1–5 두 조건입니다.'
            density_plot(profiles[:,:3],f/'density.png',title)
            energy_ionization(x,a,f/'ionization.png',title)
            fig,axes=plt.subplots(1,2,figsize=(10,3.8),layout='constrained')
            cycle=[first-1]+[int(r['RF_cycle']) for r in rows]
            for s,label in [('e','Electrons'),('i','Ar+ ions')]:axes[0].plot(cycle,[int(rows[0]['start_'+s])]+[int(r['end_'+s]) for r in rows],'o-',label=label)
            axes[0].set(xlabel='RF cycle',ylabel='Macroparticles',title='Saved short transient');axes[0].legend()
            cycle=cycle[1:]
            for values,label in [([int(r['ionizations']) for r in rows],'Ionization pairs'),([int(r['e_loss_lower'])+int(r['e_loss_upper']) for r in rows],'Electron wall loss'),([int(r['i_loss_lower'])+int(r['i_loss_upper']) for r in rows],'Ion wall loss')]:axes[1].plot(cycle,values,'o-',label=label)
            axes[1].set(xlabel='RF cycle',ylabel='Events per RF',title='Exact discrete particle balance');axes[1].legend(fontsize=8)
            fig.suptitle(title);save(fig,f/'particle_balance.png')
            flux,power=transient_power(rows,summary,c)
            flux_figure(flux,f/'wall_flux.png',title);power_bars(power,f/'power.png',title)
            write_csv(p/'data/wall_flux.csv',['channel','flux_m-2_s-1'],flux.items());write_csv(p/'data/power_channels.csv',['channel','W_m-2'],power.items())
            for key,filename,caption in [('convergence','particle_balance','5 RF 입자 수·생성/손실. 정상상태 수렴 판정이 아닙니다.'),('density','density','5 RF 과도구간 평균 밀도 공간분포'),('ionization','ionization','5 RF 과도구간 평균 전자 에너지·이온화율'),('walls','wall_flux','5 RF 흡수 사건 수로 구한 상·하부 전극 flux'),('power','power','5 RF의 field-work·벽 운동에너지·저장 전자 운동에너지 변화')]:
                attach(c,key,'figures/'+filename+'.png',caption,text='')
            next(s for s in c['sections'] if s['id']=='power').update(data_status='partial',text='전자 저장 운동에너지가 변하는 과도구간입니다. 이온·기체·전기장 저장 항을 모두 포함한 완전한 전력 폐합이 아닙니다.')
            for e in [{'label':'5 RF 전극 flux CSV','path':'data/wall_flux.csv'},{'label':'5 RF 측정 전력 채널 CSV','path':'data/power_channels.csv'}]:
                if e['path'] not in {v['path'] for v in c['downloads']}:c['downloads'].append(e)
            put(q,c)
            cases.append({'m':c,'summary':summary,'a':a,'x':x,'directory':p,'flux':flux,'power':power})
    parent_diagnostics(d,m,cases)

def parent_diagnostics(d,m,cases):
    labels=[chr(65+i) for i in range(len(cases))]
    table='| 표식 | 압력 mTorr | V peak | 진단 RF | 상세 보고서 |\n|---|---:|---:|---|---|\n'+'\n'.join(f'| {label} | {c["summary"]["pressure_mTorr"]:.3f} | {c["summary"]["voltage_peak_V"]} | {c["summary"]["first_RF_cycle"]}–{c["summary"]["last_RF_cycle"]} | [그림·CSV]({c["directory"].name}/README.md) |' for label,c in zip(labels,cases))
    caution='모두 5 RF 과도구간이며 서로 다른 초기 상태가 섞여 있습니다. 압력만 바꾼 직접 대조는 250 V·RF1–5의 20/75.006 mTorr 두 조건입니다.'
    m['source']['description']='상부 RF C/eduPIC.cc + 입자·에너지 수지 기록 진단; C++11 컴파일'
    m['source']['revision']='진단 소스 SHA256 5acbe3b6b8aa8f73655cbdcfcb95c75f2d490607f070700ac7e67d943b7ec4ef'
    m['source']['initialization']='20/75.006 mTorr의 250 V 대조는 동일 RF0 입력. 나머지는 기존 20 mTorr 조건별 RF200 또는 RF400 체크포인트에서 재시작. 이어지는 5 RF 과도구간을 진단했습니다.'
    for filename,keys,units in [('heating',['powere','poweri'],['W m$^{-3}$','W m$^{-3}$']),('fields',['pot','efield'],['V','V m$^{-1}$']),('ionization',['meanee','ioniz'],['eV','m$^{-3}$ s$^{-1}$'])]:
        fig,axes=plt.subplots(2,len(cases),figsize=(3.2*len(cases),6),layout='constrained')
        phase=(np.arange(200)*20+10.5)/4000
        for row,key in enumerate(keys):
            low=min(float(c['a'][key].min()) for c in cases);high=max(float(c['a'][key].max()) for c in cases)
            options=dict(vmin=max(0,low),vmax=high,cmap='viridis')
            if key in ['powere','poweri','pot','efield']:
                lim=max(abs(low),abs(high));options=dict(vmin=-lim,vmax=lim,cmap='RdBu_r')
            for label,ax,c in zip(labels,axes[row],cases):
                s=c['summary'];im=ax.pcolormesh(phase,c['x']*1000,c['a'][key],shading='nearest',rasterized=True,**options)
                ax.set(title=f'{label}: {s["pressure_mTorr"]:.1f}mT {s["voltage_peak_V"]}V\nRF{s["first_RF_cycle"]}-{s["last_RF_cycle"]} | {key}',xlabel='RF phase',ylabel='x (mm)',xlim=(0,1))
            fig.colorbar(im,ax=list(axes[row]),label=units[row])
        fig.suptitle('SHORT TRANSIENTS: different restart states | Common row color scales | No stationary parameter scan')
        save(fig,d/(filename+'_compare.png'))
    fig,axes=plt.subplots(1,2,figsize=(11,3.8),layout='constrained')
    for label,c,color in zip(labels,cases,COLORS):
        for ax,key in zip(axes,['ne','ni']):ax.plot(c['x']*1000,c['a'][key].mean(axis=1),color=color,label=label)
    for ax,title in zip(axes,['Electron density','Ion density']):ax.set(xlabel='x (mm)',ylabel='5-RF mean density (m$^{-3}$)',title=title);ax.legend();ax.grid(alpha=.2)
    fig.suptitle('5-RF transients from different restart states; see A-E conditions table');save(fig,d/'density_compare.png')
    fig,axes=plt.subplots(1,3,figsize=(12,3.8),layout='constrained')
    for label,c,color in zip(labels,cases,COLORS):
        e=np.loadtxt(c['directory']/'data/eepf.csv',delimiter=',',skiprows=1);i=np.loadtxt(c['directory']/'data/ifed.csv',delimiter=',',skiprows=1)
        assert abs(np.sum(e[:,1]*np.sqrt(e[:,0]))*np.median(np.diff(e[:,0]))-1)<2e-5
        assert np.allclose(i[:,1:].sum(axis=0)*np.median(np.diff(i[:,0])),1,atol=.00051)
        axes[0].semilogy(e[:,0],np.where(e[:,1]>0,e[:,1],np.nan),color=color,label=label)
        axes[1].plot(i[:,0],i[:,1],color=color,label=label);axes[2].plot(i[:,0],i[:,2],color=color,label=label)
    for ax,title,unit in zip(axes,['Central EEPF','Upper RF IEDF','Lower ground IEDF'],['EEPF (eV$^{-3/2}$)','Normalized IEDF (eV$^{-1}$)','Normalized IEDF (eV$^{-1}$)']):ax.set(xlabel='Energy (eV)',ylabel=unit,title=title);ax.legend();ax.grid(alpha=.2)
    axes[0].set_xlim(0,100);fig.suptitle('5-RF transient distributions; different conditions A-E, not stationary averages');save(fig,d/'distributions_compare.png')
    fig,axes=plt.subplots(1,2,figsize=(11,3.8),layout='constrained')
    for s,ax in zip(['e','i'],axes):
        for side,style in [('lower','o-'),('upper','s--')]:ax.plot(labels,[c['flux'][s+'_'+side] for c in cases],style,label=side)
        ax.set(xlabel='Diagnostic condition A-E',ylabel='Wall flux (m$^{-2}$ s$^{-1}$)',title=('Electron' if s=='e' else 'Ion')+' wall flux');ax.legend()
    fig.suptitle('Five-RF absorbed-particle flux; lower grounded / upper RF');save(fig,d/'walls_compare.png')
    fig,axes=plt.subplots(1,2,figsize=(11,3.8),layout='constrained')
    for k,label in [('e_field_work_J','Electron field work'),('i_field_work_J','Ion field work')]:axes[0].plot(labels,[c['power'][k] for c in cases],'o-',label=label)
    for k,label in [('e_wall_energy_J','Electron wall KE'),('i_wall_energy_J','Ion wall KE'),('excitation_ionization_threshold_J','Excitation + ionization'),('electron_stored_kinetic_change_J','Electron storage change')]:axes[1].plot(labels,[c['power'][k] for c in cases],'o-',label=label)
    for ax in axes:ax.set(xlabel='Diagnostic condition A-E',ylabel='W per one-face m$^2$');ax.axhline(0,color='black',lw=.6);ax.legend(fontsize=8)
    fig.suptitle('Transient measured channels and electron storage; incomplete energy closure');save(fig,d/'power_compare.png')
    for key,title in STANDARD_SECTIONS:
        if key=='convergence':continue
        attach(m,key,key+'_compare.png','조건 A–E의 5 RF 과도구간 비교',text=caution)
    sec=next(s for s in m['sections'] if s['id']=='heating');sec['table']=table
    next(s for s in m['sections'] if s['id']=='power').update(data_status='partial',text=caution+' 이온·기체·전기장 저장 항을 모두 포함한 완전한 전력 폐합은 아닙니다.')
    put(d/'run.json',m)

def normalize_scope(roots):
    for root in roots:
        for p in [*(root/'results').glob('*/run.json'),*(root/'results').glob('*/*/report.json')]:
            m=read(p);sections={s['id']:s for s in m['sections']}
            for key,title in STANDARD_SECTIONS:
                sec=sections.setdefault(key,{'id':key})
                if sec.get('images'):sec.setdefault('data_status','available')
                elif m['status'] in ['incomplete','extinguished']:
                    reason='최종 장시간 측정 분포가 저장되지 않은 미완료 실행입니다.' if m['status']=='incomplete' else '정상 방전 측정에 도달하기 전에 전자가 소멸하여 해당 정상상태 진단을 측정하지 못했습니다.'
                    sec.update(data_status='unavailable',reason=reason,availability='최종 측정 자료 없음',text=reason,images=[])
                else:raise ValueError('Unexplained missing diagnostic: '+str(p)+' '+key)
            m['sections']=[sections[k] for k,_ in STANDARD_SECTIONS]+[s for s in m['sections'] if s['id'] not in dict(STANDARD_SECTIONS)]
            m['coverage_reviewed_on']='2026-11-22';m['report_updated']='2026-11-22';put(p,m)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--baseline',type=Path,required=True);p.add_argument('--top',type=Path,required=True);a=p.parse_args()
    baseline(a.baseline);extinguished(a.top);diagnostics(a.top);normalize_scope([a.baseline,a.top])
    print('Backfilled saved diagnostics and explicitly classified unavailable measurements. No PIC execution.')

if __name__=='__main__':main()
