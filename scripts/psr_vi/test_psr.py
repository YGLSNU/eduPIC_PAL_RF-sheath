import tempfile,json,unittest
from pathlib import Path
import numpy as np
from spectral import phasors,phase_fields,contributions,circular_error
from experiment import load,voltage_input

class SpectralTests(unittest.TestCase):
 def test_absolute_time_peak_rms_dc_and_power(self):
  f=60e6;t=.137/f+np.arange(4000)/(f*1000)
  v=3+2*np.cos(2*np.pi*f*t+.3)+.7*np.cos(6*np.pi*f*t-.8)
  j=4+5*np.cos(2*np.pi*f*t-.2)+.4*np.cos(6*np.pi*f*t+.6)
  a=phasors(t,v,f,10);b=phasors(t,j,f,10)
  self.assertTrue(np.allclose(a[[0,1,3]],[3,2*np.exp(.3j),.7*np.exp(-.8j)],atol=1e-10))
  self.assertAlmostEqual(contributions(a,b).sum(),np.mean(v*j),places=10)
  self.assertAlmostEqual(np.linalg.norm(a[2:])/abs(a[1]),.35)
  self.assertAlmostEqual(circular_error(179,-179),-2)
 def test_phase_fold_timestamp(self):
  t=(np.arange(1000)+1)/1000;a=2*np.cos(2*np.pi*3*t+.6)
  self.assertAlmostEqual(abs(phase_fields(a,10)[3]-2*np.exp(.6j)),0,places=11)
 def test_noncoherent_fit_and_sampling_gate(self):
  t=np.arange(2100)/(60e6*1000);x=2+np.cos(2*np.pi*60e6*t+.4)
  with self.assertRaises(ValueError):phasors(t,x,60e6,5)
  self.assertTrue(np.allclose(phasors(t,x,60e6,5,fit=True)[[0,1]],[2,np.exp(.4j)]))
  with self.assertRaises(ValueError):phasors(t,x,60e6,100)
 def test_relative_phase_cannot_drive_waveform(self):
  with tempfile.TemporaryDirectory() as td:
   p=Path(td)/'VI.csv';p.write_text('harmonic,frequency_Hz,V_amp,I_amp,Delta_phi_VI_deg\n1,60000000,100,2,60\n')
   m={'amplitude_convention':'RMS','phase_kind':'VI_difference','current_polarity':1,'probe_reference_plane':'electrode','calibrated':True,'frequency_Hz':60e6}
   a,_=load(p,m);self.assertAlmostEqual(a.P_W.iloc[0],100)
   self.assertFalse(a.waveform_reconstructible.iloc[0])
   with self.assertRaises(ValueError):voltage_input(p,m,Path(td)/'voltage.dat')
if __name__=='__main__':unittest.main()
