"""Explicit VI conventions; no fabricated experiment or circuit parameters."""
from pathlib import Path
import json
import numpy as np
import pandas as pd

def load(path,metadata):
    m=json.loads(Path(metadata).read_text()) if not isinstance(metadata,dict) else metadata
    if m.get('template_only'):raise ValueError('Template metadata: fill actual conventions and set template_only=false')
    required=['amplitude_convention','phase_kind','current_polarity','probe_reference_plane','frequency_Hz','calibrated']
    missing=[k for k in required if k not in m]
    if missing:raise ValueError('Missing experiment metadata: '+', '.join(missing))
    if not isinstance(m['frequency_Hz'],(int,float)) or not np.isfinite(m['frequency_Hz']) or m['frequency_Hz']<=0:raise ValueError('Explicit positive frequency_Hz required')
    if m['phase_kind'] not in ['common_time_origin','VI_difference']:raise ValueError('Unknown phase_kind')
    factors={'peak':1.,'RMS':np.sqrt(2),'peak-to-peak':.5}
    factor=factors[m['amplitude_convention']]
    a=pd.read_csv(path,sep='\t' if str(path).endswith('.tsv') else ',').rename(columns=m.get('column_mapping',{}))
    for c in ['harmonic','frequency_Hz','V_amp','I_amp']:
        if c not in a:raise ValueError('Missing '+c)
        a[c]=pd.to_numeric(a[c],errors='raise')
    if not np.isfinite(a[['harmonic','frequency_Hz','V_amp','I_amp']].to_numpy()).all():raise ValueError('Nonfinite experimental values')
    if a.harmonic.duplicated().any() or (a[['V_amp','I_amp']]<0).any().any():raise ValueError('Invalid amplitudes or duplicate harmonics')
    if not np.allclose(a.frequency_Hz,a.harmonic*m['frequency_Hz'],rtol=1e-6):raise ValueError('Noncommensurate frequencies require Hz-domain analysis, not harmonic-axis coercion')
    a['V_peak_V']=factor*a.V_amp;a['I_peak_A']=factor*a.I_amp
    polarity=m['current_polarity']
    if polarity not in [1,-1]:raise ValueError('current_polarity must be +1 or -1')
    if m['phase_kind']=='common_time_origin':
        if not m.get('time_reference'):raise ValueError('Common phasors require a time_reference')
        for c in ['V_phase_deg','I_phase_deg']:
            if c not in a or a[c].isna().any():raise ValueError('Missing common phase '+c)
        delta=a.V_phase_deg-a.I_phase_deg-(180 if polarity==-1 else 0)
    else:
        if 'Delta_phi_VI_deg' not in a or a.Delta_phi_VI_deg.isna().any():raise ValueError('VI difference phases required')
        delta=a.Delta_phi_VI_deg-(180 if polarity==-1 else 0)
    a['Delta_phi_VI_deg']=(delta+180)%360-180
    a['P_W']=.5*a.V_peak_V*a.I_peak_A*np.cos(np.deg2rad(delta))
    z=np.divide(a.V_peak_V,a.I_peak_A,out=np.full(len(a),np.nan),where=a.I_peak_A>m.get('I_noise_floor_A',0))*np.exp(1j*np.deg2rad(delta))
    z=np.asarray(z);a['Z_app_real_ohm']=z.real;a['Z_app_imag_ohm']=z.imag
    a['waveform_reconstructible']=m['phase_kind']=='common_time_origin'
    return a,m

def voltage_input(path,metadata,output):
    a,m=load(path,metadata)
    if m['phase_kind']!='common_time_origin' or m.get('DC_bias_V') is None or not np.isfinite(m['DC_bias_V']):raise ValueError('Measured-voltage mode requires common voltage phases and explicit DC_bias_V')
    if not m['calibrated'] or m['probe_reference_plane']!='electrode':raise ValueError('Measured-voltage drive requires calibrated electrode-plane phasors; no invented de-embedding')
    np.savetxt(output,np.c_[a.harmonic,a.V_peak_V,np.deg2rad(a.V_phase_deg)],fmt='%.17g')
    return {'EDUPIC_PSR_VOLTAGE_FILE':str(Path(output).resolve()),'EDUPIC_PSR_VDC':str(m['DC_bias_V'])}
