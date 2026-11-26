#!/usr/bin/env python3
"""Publish complete snapshots every 15 min and on terminal/pilot transitions."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import argparse,fcntl,hashlib,json,os,subprocess,sys,time,traceback,urllib.request
from common import put
from capacity import TERMINAL

REPO=Path(__file__).resolve().parents[2]
def verify_remote(out):
    """Read back the published report and a representative restart download."""
    base='https://raw.githubusercontent.com/YGLSNU/eduPIC_PAL_RF-sheath/refs/heads/results/20mTorr-topRF/results/'+out.name+'/'
    with urllib.request.urlopen(base+'README.md',timeout=60) as response:report=response.read().decode()
    meta=json.loads((out/'run.json').read_text())
    if meta['report_updated'] not in report:raise RuntimeError('Remote report is not the just-published snapshot')
    child=json.loads((out/'75mm/report.json').read_text())
    archive=next(d['path'] for d in child['downloads'] if d['path'].endswith('_restart.zip'))
    expected=hashlib.sha256((out/'75mm'/archive).read_bytes()).hexdigest();digest=hashlib.sha256();size=0
    with urllib.request.urlopen(base+'75mm/'+archive,timeout=60) as response:
        for chunk in iter(lambda:response.read(1024*1024),b''):digest.update(chunk);size+=len(chunk)
    if digest.hexdigest()!=expected:raise RuntimeError('Remote restart download SHA256 mismatch')
    return {'report_readback':True,'restart_download':archive,'bytes':size,'SHA256':expected,'passed':True}

def main():
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('--interval-seconds',type=int,default=900);a=p.parse_args();root=a.root.resolve()
    lock=(root/'publisher.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    out=root.parent/'export'/root.name;last=0;signature=None
    put(root/'publisher.json',{'pid':os.getpid(),'interval_seconds':a.interval_seconds,'export_path':str(out),'started_at_Asia_Seoul':datetime.now(ZoneInfo('Asia/Seoul')).isoformat()})
    def special():
        cfg=json.loads((root/'config.json').read_text())
        paths=[Path(cfg.get('case_sources',{}).get(str(g),{}).get('path',str(root/f'{g}mm')))/'status.json' for g in cfg['gaps_mm']]
        states=[json.loads(p.read_text()) for p in paths]
        final=tuple((m['gap_mm'],m['status']) for m in states if m['status'] in ['criteria_met','extinguished','measurement_limit_reached','total_cycle_limit_reached','paused_error','diagnostic'])
        return final
    while not (root/'STOP_PUBLISH').exists():
        try:
            sig=special();finished=(root/'controller_finished.json').exists()
            cfg=json.loads((root/'config.json').read_text())
            if finished and cfg.get('case_sources'):
                finished=all(json.loads((Path(s['path'])/'status.json').read_text())['status'] in TERMINAL for s in cfg['case_sources'].values())
            if time.monotonic()-last>=a.interval_seconds or sig!=signature or finished:
                # Export reads only completed immutable block paths. The separate
                # uploader uses the existing atomic catalog/update implementation.
                subprocess.run([sys.executable,str(REPO/'scripts/brh_scan/export.py'),str(root),str(out)],cwd=REPO,check=True)
                subprocess.run([sys.executable,str(REPO/'scripts/results/verify_reports.py'),'--export',str(out)],cwd=REPO,check=True)
                subprocess.run([sys.executable,str(REPO/'scripts/results/publish_run.py'),str(out),'--branch','results/20mTorr-topRF','--push'],cwd=REPO,check=True)
                verification=verify_remote(out)
                last=time.monotonic();signature=sig
                put(root/'last_publication.json',{'published_at_Asia_Seoul':datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),'export_path':str(out),'terminal_transitions':[list(x) for x in sig],'remote_verification':verification})
                print('Published complete snapshot',datetime.now().isoformat(),flush=True)
                if finished:return
            time.sleep(30)
        except Exception:
            traceback.print_exc();time.sleep(30)

if __name__=='__main__':main()
