#!/usr/bin/env python3
"""Frequency-matched VI comparisons, circular phase error, explicit area and drive mode."""
from pathlib import Path
import argparse,json
import numpy as np
import pandas as pd
from experiment import load
from spectral import circular_error
def compare(spectrum,experiment,metadata,output,drive_mode='prescribed_sine'):
    e,m=load(experiment,metadata);s=pd.read_csv(spectrum);a=s.merge(e,on='harmonic',suffixes=('_sim','_exp'))
    if not len(a):raise ValueError('No common measured harmonics')
    if not np.allclose(a.frequency_Hz_sim,a.frequency_Hz_exp,rtol=1e-6):raise ValueError('Different physical frequencies cannot be compared by order alone')
    area=m.get('A_eff_m2');a['simulation_I_peak_A']=a.J_peak_Am2*area if area else np.nan
    a['I_absolute_error_A']=a.simulation_I_peak_A-a.I_peak_A
    a['I_relative_error']=a.I_absolute_error_A/np.where(a.I_peak_A>m.get('I_noise_floor_A',1e-9),a.I_peak_A,np.nan)
    a['V_absolute_error_V']=a.V_peak_V_sim-a.V_peak_V_exp
    a['voltage_error_is_prediction']=drive_mode!='measured_voltage'
    if drive_mode=='measured_voltage':a['V_absolute_error_V']=np.nan
    a['phase_circular_error_deg']=circular_error(a.Delta_phi_VI_deg_sim,a.Delta_phi_VI_deg_exp)
    a.loc[~a.VI_phase_valid,'phase_circular_error_deg']=np.nan
    fundamental=e[e.harmonic==1]
    if len(fundamental):a['experimental_I_n_over_I_1']=a.I_peak_A/max(float(fundamental.I_peak_A.iloc[0]),1e-300)
    a['absolute_current_comparison_valid']=bool(area and area>0);a['reference_plane']=m['probe_reference_plane'];a['calibrated']=m['calibrated']
    a.to_csv(output,index=False);return a
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('spectrum');p.add_argument('experiment');p.add_argument('metadata');p.add_argument('output');p.add_argument('--drive-mode',default='prescribed_sine',choices=['prescribed_sine','measured_voltage']);a=p.parse_args();compare(a.spectrum,a.experiment,a.metadata,a.output,a.drive_mode)
