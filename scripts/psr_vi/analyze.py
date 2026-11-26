#!/usr/bin/env python3
"""Per-block coherent VI/local-power/sheath spectra; no PSR declaration by peak alone."""
from pathlib import Path
import argparse,gzip,json,os,hashlib
os.environ.setdefault('MPLCONFIGDIR','/tmp/edupic-psr-mpl')
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from spectral import phasors,phase_fields,contributions

def array_file(path,dtype='<f8'):
    path=Path(path)
    if path.exists():return np.fromfile(path,dtype=dtype)
    with gzip.open(str(path)+'.gz','rb') as f:return np.frombuffer(f.read(),dtype=dtype)
def csv(path):
    path=Path(path);return pd.read_csv(path if path.exists() else str(path)+'.gz')
def put(path,m):Path(path).write_text(json.dumps(m,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def save(fig,path):fig.savefig(path,dpi=140,bbox_inches='tight');plt.close(fig)
def analyze(block,out,hmax=64):
    block=Path(block);out=Path(out);out.mkdir(parents=True,exist_ok=True);figs=out/'figures';figs.mkdir(exist_ok=True)
    meta=json.loads((block/'psr_metadata.json').read_text());f=meta['frequency_Hz'];L=meta['gap_m'];ng=meta['grid_points'];nt=meta['steps_per_RF']
    if nt/hmax<20:raise ValueError('Insufficient samples per highest harmonic')
    a=csv(block/'terminal_timeseries.csv');t=a.t_terminal_s.to_numpy()
    vh=phasors(t,a.V_gap_V.to_numpy(),f,hmax);jh=phasors(t,a.J_RF_Am2.to_numpy(),f,hmax)
    # Prescribed ideal boundary: voltage harmonics beyond fundamental are zero.
    config_path=next((p/'config.json' for p in [block.parent.parent,block.parent] if (p/'config.json').exists()),None)
    mode=json.loads(config_path.read_text()).get('drive_mode','prescribed_sine') if config_path else 'prescribed_sine'
    if mode=='prescribed_sine':vh[2:]=0
    spectrum=np.fft.rfft(a.J_RF_Am2.to_numpy())*2/len(a);stride=int(round(len(a)/nt));used=np.ones(len(spectrum),bool)
    for n in range(hmax+1):used[max(0,n*stride-1):min(len(used),n*stride+2)]=False
    floor=max(1e-8,3*float(np.median(np.abs(spectrum[used]))))
    rows=[];v1=abs(vh[1]);j1=abs(jh[1]);reference=np.angle(vh[1])
    for n in range(hmax+1):
        v,j=vh[n],jh[n];vvalid=n>0 and abs(v)>max(1e-9,1e-8*v1);jvalid=n>0 and abs(j)>floor;valid=vvalid and jvalid
        factor=1 if n==0 else .5;p=factor*np.real(v*np.conj(j));z=v/j if valid else complex(np.nan,np.nan)
        rows.append([n,n*f,abs(v),abs(v)/(1 if n==0 else np.sqrt(2)),v.real,v.imag,np.degrees(np.angle(v)) if vvalid else np.nan,
          abs(j),abs(j)/(1 if n==0 else np.sqrt(2)),j.real,j.imag,np.degrees(np.angle(j)) if jvalid else np.nan,
          np.degrees(np.angle(v*np.conj(j))) if valid else np.nan,abs(j)/j1 if j1>floor else np.nan,abs(v)/v1 if v1>1e-9 else np.nan,
          20*np.log10(max(abs(j)/j1,1e-300)) if j1>floor else np.nan,np.degrees(np.angle(np.exp(1j*(np.angle(v)-n*reference)))) if vvalid and v1>1e-9 else np.nan,
          np.degrees(np.angle(np.exp(1j*(np.angle(j)-n*reference)))) if jvalid and v1>1e-9 else np.nan,p,z.real,z.imag,valid,floor])
    columns=['harmonic','frequency_Hz','V_peak_V','V_RMS_V','V_real_V','V_imag_V','V_phase_deg','J_peak_Am2','J_RMS_Am2','J_real_Am2','J_imag_Am2','J_phase_deg','Delta_phi_VI_deg','J_n_over_J_1','V_n_over_V_1','J_dBc','V_phase_aligned_deg','J_phase_aligned_deg','terminal_P_Wm2','Z_app_real_ohmm2','Z_app_imag_ohmm2','VI_phase_valid','J_noise_floor_Am2']
    spec=pd.DataFrame(rows,columns=columns)
    spec['V_DC_mean_V']=np.where(spec.harmonic==0,vh[0].real,np.nan)
    spec['J_DC_mean_Am2']=np.where(spec.harmonic==0,jh[0].real,np.nan)
    spec['J_phase_valid']=(spec.harmonic>0)&(spec.J_peak_Am2>floor)
    spec['V_phase_valid']=(spec.harmonic>0)&(spec.V_peak_V>max(1e-9,1e-8*v1))
    spec['imposed_voltage_component']=spec.V_phase_valid
    spec['generated_current_component']=(spec.harmonic>0)&(~spec.imposed_voltage_component)&spec.J_phase_valid
    spec.to_csv(out/'harmonic_spectra.csv',index=False)
    raw=array_file(block/'phase_fields.bin').reshape(meta['field_shape']);x=np.linspace(0,L,ng);h=phase_fields(raw[:6],hmax,phase_first=float(a.t_field_s.iloc[0]*f)%1)
    pe=contributions(h[4],h[1]);pi=contributions(h[5],h[1]);pe_int=np.trapezoid(pe,x,axis=0);pi_int=np.trapezoid(pi,x,axis=0)
    direct_e=float(np.trapezoid(raw[6].mean(axis=1),x));positive=float(np.trapezoid(raw[7].mean(axis=1),x));negative=float(np.trapezoid(raw[8].mean(axis=1),x))
    local=np.c_[np.repeat(x,hmax+1),np.tile(np.arange(hmax+1),ng),pe.ravel(),pi.ravel()]
    pd.DataFrame(local,columns=['x_m','harmonic','electron_P_Wm3','ion_P_Wm3']).to_csv(out/'harmonic_power_spatial.csv.gz',index=False,compression={'method':'gzip','mtime':0})
    local_fields=np.c_[np.repeat(x,hmax+1),np.tile(np.arange(hmax+1),ng),h[1].real.ravel(),h[1].imag.ravel(),h[4].real.ravel(),h[4].imag.ravel(),h[5].real.ravel(),h[5].imag.ravel()]
    pd.DataFrame(local_fields,columns=['x_m','harmonic','E_real_Vm','E_imag_Vm','je_energy_real_Am2','je_energy_imag_Am2','ji_energy_real_Am2','ji_energy_imag_Am2']).to_csv(out/'harmonic_fields_spatial.csv.gz',index=False,compression={'method':'gzip','mtime':0})
    power=pd.DataFrame({'harmonic':np.arange(hmax+1),'frequency_Hz':np.arange(hmax+1)*f,'electron_P_Wm2':pe_int,'ion_P_Wm2':pi_int,'terminal_P_Wm2':spec.terminal_P_Wm2})
    power.to_csv(out/'harmonic_power.csv',index=False)
    # Preserve full Hz spectrum, including asynchronous/broadband content.
    hz=np.fft.rfftfreq(len(a),1/(f*nt));full=np.fft.rfft(a.J_RF_Am2.to_numpy())*2/len(a);full[0]*=.5;full[-1]*=.5
    pd.DataFrame({'frequency_Hz':hz,'J_peak_Am2':abs(full)}).to_csv(out/'current_spectrum_Hz.csv.gz',index=False,compression={'method':'gzip','mtime':0})
    s=csv(block/'sheath_timeseries.csv');ok=s.valid.astype(bool).to_numpy();fit_records=[];cs=[]
    region_info={'valid':False,'definition':'Fixed spatial intervals at the block-mean valid integral sheath edges; not a moving-boundary energy budget or attributed PSR heating gain.'}
    if ok.mean()>.9:
        left=float(s.loc[ok,'x_g_m'].mean());right=float(s.loc[ok,'x_p_m'].mean())
        def at(z):
            p=min(ng-2,max(0,int(z/L*(ng-1))));f0=(z-x[p])/(x[p+1]-x[p]);return pe[p]*(1-f0)+pe[p+1]*f0
        def integral(lo,hi):
            inside=(x>lo)&(x<hi);xx=np.r_[lo,x[inside],hi];values=np.vstack([at(lo),pe[inside],at(hi)]);return np.trapezoid(values,xx,axis=0)
        power['electron_ground_region_Wm2']=integral(0,left);power['electron_mean_bulk_region_Wm2']=integral(left,right);power['electron_powered_region_Wm2']=integral(right,L)
        assert np.allclose(power.electron_ground_region_Wm2+power.electron_mean_bulk_region_Wm2+power.electron_powered_region_Wm2,pe_int,atol=1e-6)
        region_info.update(valid=True,mean_x_g_m=left,mean_x_p_m=right,valid_sheath_fraction=float(ok.mean()))
        power.to_csv(out/'harmonic_power.csv',index=False)
    put(out/'power_regions.json',region_info)
    for label,vcol,qcol in [('powered','U_sp_V','Q_sp_Cm2'),('ground','U_sg_V','Q_sg_Cm2')]:
        v=s[vcol].to_numpy()*(-1 if label=='powered' else 1);q=s[qcol].to_numpy();use=ok&np.isfinite(v)&(v>5)
        cap=np.full(len(s),np.nan)
        if use.sum()>20 and np.ptp(v[use])>1:
            scale=float(np.ptp(v[use]));origin=float(np.mean(v[use]));best=None
            for degree in [1,2,3]:
                coef=np.polynomial.polynomial.polyfit((v[use]-origin)/scale,q[use],degree);pred=np.polynomial.polynomial.polyval((v[use]-origin)/scale,coef)
                error=float(np.sqrt(np.mean((pred-q[use])**2))/max(np.ptp(q[use]),1e-300))
                fit_records.append({'side':label,'degree':degree,'relative_RMSE':error,'scale_V':scale,'origin_V':origin,'coefficients_Cm2':coef.tolist(),'single_valued_approximation_only':True})
                if degree==3:best=(coef,error)
            coef,error=best;derivative=np.polynomial.polynomial.polyder(coef)/scale;cap[use]=np.polynomial.polynomial.polyval((v[use]-origin)/scale,derivative)
            if error>.15:cap[:]=np.nan
            cap[(cap<=0)|(~use)]=np.nan
        cs.append(cap)
    ceq=np.divide(cs[0]*cs[1],cs[0]+cs[1],out=np.full(len(s),np.nan),where=np.isfinite(cs[0])&np.isfinite(cs[1])&((cs[0]+cs[1])>0));la=s.L_bulk_times_area_Hm2.to_numpy();fest=np.full(len(s),np.nan)
    valid_lc=np.isfinite(ceq)&(ceq>0)&np.isfinite(la)&(la>0);fest[valid_lc]=1/(2*np.pi*np.sqrt(la[valid_lc]*ceq[valid_lc]))
    fest[(~ok)|(~np.isfinite(fest))|(s.s_g_m.to_numpy()<2*L/(ng-1))|(s.s_p_m.to_numpy()<2*L/(ng-1))]=np.nan
    s['C_sp_Fm2_approx']=cs[0];s['C_sg_Fm2_approx']=cs[1];s['f_PSR_est_Hz_approx']=fest;s.to_csv(out/'sheath_estimates.csv.gz',index=False,compression={'method':'gzip','mtime':0})
    put(out/'sheath_QV_fits.json',{'fits':fit_records,'note':'Scaled static polynomials are approximate; hysteresis is visible in RF-colored trajectories. Fits/capacitances are not a circuit identification or PSR proof.'})
    sh=[]
    for c in ['s_g_m','s_p_m','U_sp_V','U_bulk_V','U_sg_V','Q_sp_Cm2','Q_sg_Cm2']:
        if ok.all():z=phasors(s.t_s.to_numpy(),s[c].to_numpy(),f,hmax)
        else:z=np.full(hmax+1,complex(np.nan,np.nan))
        sh.extend([[c,n,n*f,abs(z[n]),np.degrees(np.angle(z[n]))] for n in range(hmax+1)])
    pd.DataFrame(sh,columns=['quantity','harmonic','frequency_Hz','peak_amplitude_SI','phase_deg']).to_csv(out/'sheath_harmonics.csv',index=False)
    if 'J_e_midgap_energy_Am2' in a:
        jt=phasors(a.t_field_s.to_numpy(),a.J_e_midgap_energy_Am2.to_numpy(),f,hmax);et=phasors(a.t_field_s.to_numpy(),a.E_midgap_Vm.to_numpy(),f,hmax)
        jfloor=max(1e-8,3*float(np.median(abs(np.fft.rfft(a.J_e_midgap_energy_Am2.to_numpy())[used])*2/len(a))))
        efloor=max(1e-8,3*float(np.median(abs(np.fft.rfft(a.E_midgap_Vm.to_numpy())[used])*2/len(a))))
        pd.DataFrame({'harmonic':np.arange(hmax+1),'frequency_Hz':np.arange(hmax+1)*f,'midgap_je_energy_peak_Am2':abs(jt),'midgap_je_phase_deg':np.where(abs(jt)>jfloor,np.degrees(np.angle(jt)),np.nan),'midgap_E_peak_Vm':abs(et),'midgap_E_phase_deg':np.where(abs(et)>efloor,np.degrees(np.angle(et)),np.nan),'J_noise_floor_Am2':jfloor,'E_noise_floor_Vm':efloor}).to_csv(out/'bulk_harmonics.csv',index=False)
    # Figures use full raw currents; band reconstruction is a visualization only.
    keep=np.arange(len(a))>=max(0,len(a)-2*nt);tt=(t[keep]-t[keep][0])*f;tf=(a.t_field_s.to_numpy()[keep]-t[keep][0])*f
    fig,axs=plt.subplots(3,1,figsize=(10,8));axs[0].plot(tt,a.V_gap_V.to_numpy()[keep]);axs[0].set(ylabel='Vgap (V)')
    axs[1].plot(tt,a.J_RF_Am2.to_numpy()[keep],label='RF terminal total');axs[1].plot(tt,(-a.J_e_path_x_Am2-a.J_i_path_x_Am2).to_numpy()[keep],label='spatial-mean conduction');axs[1].plot(tt,a.J_displacement_RF_Am2.to_numpy()[keep],label='vacuum term');axs[1].legend(fontsize=7);axs[1].set(ylabel='J (A/m2)')
    axs[2].plot(tf,a.Pe_Wm2.to_numpy()[keep],label='electron signed kick power');axs[2].axhline(0,color='k',lw=.5);axs[2].set(xlabel='RF cycles (last two); actual timestamps',ylabel='P / area (W/m2)');save(fig,figs/'VI_waveforms.png')
    fig,axs=plt.subplots(2,2,figsize=(11,7));n=spec.harmonic.to_numpy()[1:];axs[0,0].semilogy(n,np.maximum(spec.J_peak_Am2.to_numpy()[1:],1e-12),'o-');axs[0,0].axhline(floor,color='r',ls='--');axs[0,0].set(ylabel='J peak (A/m2)')
    axs[0,1].plot(n,spec.V_peak_V.to_numpy()[1:],'o-');axs[0,1].set(ylabel='V peak (V); prescribed boundary')
    axs[1,0].plot(n,spec.Delta_phi_VI_deg.to_numpy()[1:],'o');axs[1,0].set(ylabel='V-I phase (deg)')
    axs[1,1].plot(n,pe_int[1:],'o-',label='electron, full gap');axs[1,1].plot(n,power.terminal_P_Wm2.to_numpy()[1:],'x',label='terminal')
    if region_info['valid']:axs[1,1].plot(n,power.electron_mean_bulk_region_Wm2.to_numpy()[1:],'s-',label='electron, fixed mean-bulk region')
    axs[1,1].legend(fontsize=7);axs[1,1].axhline(0,color='k',lw=.5);axs[1,1].set(ylabel='Signed harmonic power (W/m2)')
    for ax in axs.ravel():ax.set(xlabel='Harmonic n');ax.grid(alpha=.2)
    save(fig,figs/'harmonics.png')
    fig,axs=plt.subplots(1,2,figsize=(11,4))
    for ax,vcol,qcol,sign in zip(axs,['U_sp_V','U_sg_V'],['Q_sp_Cm2','Q_sg_Cm2'],[-1,1]):
        points=ax.scatter(sign*s[vcol],s[qcol],c=(s.t_s*f)%1,s=1,cmap='twilight',rasterized=True);ax.set(xlabel='Sheath drop magnitude (V)',ylabel='Space charge / area (C/m2)');fig.colorbar(points,ax=ax,label='RF phase')
    save(fig,figs/'sheath_QV.png')
    # No all-time/grid dump: phase-folded high-resolution arrays stay separate.
    fig,axs=plt.subplots(2,1,figsize=(10,7));v=np.percentile(abs(raw[6]),99.5)
    from scipy.signal import resample_poly
    displayed=resample_poly(raw[6],1,max(1,nt//800),axis=1,padtype='wrap')
    im=axs[0].imshow(displayed,origin='lower',extent=[0,1,0,L*1000],aspect='auto',cmap='RdBu_r',vmin=-v,vmax=v);fig.colorbar(im,ax=axs[0],label='Mean instantaneous je E (W/m3); display anti-alias filter')
    sg=s.groupby(np.arange(len(s))%nt)[['x_g_m','x_p_m','U_bulk_V']].mean();phase_axis=(np.arange(nt)+1)/nt
    axs[0].plot(phase_axis,sg.x_g_m*1000,'k',lw=.7);axs[0].plot(phase_axis,sg.x_p_m*1000,'k',lw=.7);axs[0].set(ylabel='x (mm)',xlabel='RF phase')
    axs[1].plot(phase_axis,sg.U_bulk_V);axs[1].set(xlabel='RF phase',ylabel='Bulk voltage (V)');save(fig,figs/'PSR_power.png')
    # A high-frequency band is diagnostic, not an attributed PSR heating gain.
    ft=np.fft.rfft(a.J_RF_Am2.to_numpy());freq=np.fft.rfftfreq(len(a),1/(nt*f));mask=(freq>=2*f)&(freq<=hmax*f);filtered=np.fft.irfft(ft*mask,n=len(a));bulk=s.U_bulk_V.to_numpy()
    fig,axs=plt.subplots(3,1,figsize=(10,8));axs[0].plot(tt,a.J_RF_Am2.to_numpy()[keep],label='raw total J');axs[0].plot(tt,filtered[keep],label='2..64 f0 reconstruction; may ring');axs[0].legend(fontsize=7);axs[0].set(ylabel='J (A/m2)')
    axs[1].plot(tf,bulk[keep],label='bulk voltage');axs[1].set(ylabel='Bulk voltage (V)')
    if 'J_e_midgap_energy_Am2' in a:
        twin=axs[1].twinx();twin.plot(tf,a.J_e_midgap_energy_Am2.to_numpy()[keep],color='tab:orange',alpha=.7);twin.set(ylabel='Midgap electron energy-current (A/m2)')
    axs[2].semilogy(hz/f,np.maximum(abs(full),1e-12));axs[2].set(xlim=(0,hmax),xlabel='Frequency / f0',ylabel='J peak (A/m2)');save(fig,figs/'PSR_synchronized.png')
    result={'analysis_SHA256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'spectral_SHA256':hashlib.sha256(Path(__file__).with_name('spectral.py').read_bytes()).hexdigest(),'block':str(block),'measured_RF':meta['cycles'],'harmonic_max':hmax,'local_phasor_phase_first_from_actual_timestamps':float(a.t_field_s.iloc[0]*f)%1,'V1_phase_reference_valid':bool(v1>1e-9),'THD_J_orders_2_to_max':float(np.linalg.norm(jh[2:])/j1) if j1>floor else None,
      'J_noise_floor_Am2':floor,'electron_direct_Wm2':direct_e,'electron_positive_Wm2':positive,'electron_negative_Wm2':negative,'electron_DC_Wm2':float(pe_int[0]),'electron_resolved_harmonics_Wm2':float(pe_int[1:].sum()),'electron_noncoherent_unresolved_residual_Wm2':float(direct_e-pe_int.sum()),
      'terminal_time_mean_VJ_Wm2':float(np.mean(a.V_gap_V*a.J_RF_Am2)),'terminal_harmonic_sum_Wm2':float(power.terminal_P_Wm2.sum()),'sheath_valid_fraction':float(ok.mean()),'PSR_status':'not_established','PSR_note':'Harmonics alone are not proof. Inspect synchronized bulk current/voltage, sheath motion, signed power, numerical convergence; no PSR-attributed heating increment without a control.',
      'mean_f_PSR_est_Hz_approx':float(np.nanmedian(fest)) if np.isfinite(fest).any() else None,'drive_mode':mode,'A_eff_m2':None,'experiment_status':'not_provided','field_power_note':'Per-block coherent complex product. DC and unresolved/noncoherent remainder are separate. Terminal high-order voltage is fixed zero for ideal sine drive.'}
    put(out/'analysis.json',result);return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('block',type=Path);p.add_argument('output',type=Path);p.add_argument('--harmonic-max',type=int,default=64);a=p.parse_args();print(json.dumps(analyze(a.block,a.output,a.harmonic_max),indent=2))
