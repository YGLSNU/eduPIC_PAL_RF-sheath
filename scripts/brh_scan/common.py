from pathlib import Path
import hashlib,json,struct
import numpy as np

def load_array(path, **kwargs):
    """Read unchanged numeric text from plain or losslessly compressed storage."""
    path=Path(path)
    if not path.exists() and Path(str(path)+'.gz').exists():path=Path(str(path)+'.gz')
    return np.loadtxt(path,**kwargs)

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def put(p,m):
    p=Path(p);tmp=p.with_suffix(p.suffix+'.tmp');tmp.write_text(json.dumps(m,ensure_ascii=False,indent=2,allow_nan=False)+'\n');tmp.replace(p)
def checkpoint(p):
    b=Path(p).read_bytes();t,rf,n=struct.unpack_from('<ddd',b);n=int(n);ni=int(struct.unpack_from('<d',b,24+32*n)[0])
    assert len(b)==32+32*(n+ni) and np.isfinite(np.frombuffer(b,dtype='<f8')).all()
    return {'cycle':int(rf),'time_seconds':t,'electrons':n,'ions':ni,'sha256':hashlib.sha256(b).hexdigest()}
def stationarity(history,criteria):
    a=np.array(history,dtype=float);window=criteria['particle_count_window']
    if len(a)<window:return {'passed':False,'available_RF':len(a),'required_RF':window}
    a=a[-window:];result={}
    for key,col in [('e',1),('i',2)]:
        y=a[:,col];mean=y.mean()
        if mean<=0:return {'passed':False,'reason':'empty population'}
        block=y.reshape(3,-1).mean(axis=1);span=(block.max()-block.min())/mean
        slope=np.polyfit(np.arange(len(y)),y,1)[0];drift=abs(slope)*(len(y)-1)/mean
        result[key]={'block_mean_span':float(span),'fitted_drift':float(drift),'passed':bool(span<criteria['particle_count_block_span_tolerance'] and drift<criteria['particle_count_fitted_drift_tolerance'])}
    result['passed']=all(v['passed'] for v in result.values());return result

