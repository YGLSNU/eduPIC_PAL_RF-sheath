"""Peak phasors with explicit absolute time origins and DC normalization."""
import numpy as np

def phasors(t,x,f0,hmax,fit=False):
    t=np.asarray(t);x=np.asarray(x);dt=np.median(np.diff(t))
    if len(t)<3 or not np.all(np.diff(t)>0):raise ValueError('Increasing timestamps required')
    if hmax*f0>=.5/dt or 1/(dt*hmax*f0)<20:raise ValueError('Highest harmonic needs >=20 samples/cycle and below Nyquist')
    uniform=np.allclose(np.diff(t),dt,rtol=1e-6,atol=dt*1e-5)
    cycles=len(t)*dt*f0;coherent=uniform and abs(cycles-round(cycles))<1e-5
    if coherent and not fit:
        z=np.fft.rfft(x,axis=-1)/len(t);n=np.arange(hmax+1);bins=n*int(round(cycles))
        result=2*z[...,bins]*np.exp(-2j*np.pi*n*f0*t[0]);result[...,0]=z[...,0]
        return result
    if not fit:raise ValueError('Noncoherent sampling: explicitly request sine/cosine fit')
    a=np.column_stack([np.ones(len(t))]+[q for n in range(1,hmax+1) for q in (np.cos(2*np.pi*n*f0*t),np.sin(2*np.pi*n*f0*t))])
    c=np.linalg.lstsq(a,x,rcond=None)[0];return np.r_[c[0],c[1::2]-1j*c[2::2]]

def circular_error(a,b):return (np.asarray(a)-np.asarray(b)+180)%360-180

def phase_fields(a,hmax,phase_first=None):
    """phase bin k is sampled at (k+1)/N, not at the left edge k/N."""
    n=np.arange(hmax+1);z=2*np.fft.rfft(a,axis=-1)[...,:hmax+1]/a.shape[-1]
    first=1/a.shape[-1] if phase_first is None else phase_first
    z*=np.exp(-2j*np.pi*n*first);z[...,0]*=.5
    return z

def contributions(j,e):
    p=.5*np.real(j*np.conj(e));p[...,0]*=2;return p
