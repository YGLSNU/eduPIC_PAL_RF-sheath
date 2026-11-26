#!/usr/bin/env python3
"""Publish validated independent snapshots; final readback records a completion event."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import fcntl,json,subprocess,sys,time,traceback,urllib.request,hashlib,os
REPO=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(REPO/'scripts/brh_scan'));from common import put,sha
def main(root):
 lock=(root/'publisher.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 cfg=json.loads((root/'config.json').read_text());out=root.parent/'export'/root.name;last=0;signature=None
 put(root/'publisher.json',{'pid':os.getpid(),'interval_seconds':900,'export_path':str(out)})
 while not (root/'STOP_PUBLISH').exists():
  s=json.loads((root/'status.json').read_text());final=s['status'] in ['criteria_met','measurement_limit_reached','total_cycle_limit_reached','extinguished','paused_error'];sig=(s['status'],bool(s.get('measured_RF')))
  try:
   if time.monotonic()-last>=900 or sig!=signature:
    commands=[[sys.executable,str(REPO/'scripts/psr_vi/report.py'),str(root),str(out)],[sys.executable,str(REPO/'scripts/results/verify_reports.py'),'--export',str(out)],[sys.executable,str(REPO/'scripts/results/publish_run.py'),str(out),'--branch',cfg['results_branch'],'--push']]
    for args in commands:
     p=subprocess.run(args,cwd=REPO,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
     print(p.stdout,flush=True)
     if p.returncode:
      if 'denied to' in p.stdout or 'HTTP 403' in p.stdout or 'returned error: 403' in p.stdout:
       put(root/'publication_blocked.json',{'reason':'GitHub push authorization denied; wait for verified recovery before retry','log':p.stdout[-3000:]});return
      raise RuntimeError('Publication stage failed: '+str(args[:2]))
    # Commit-pinned readback avoids branch/CDN cache races.
    ref=subprocess.check_output(['git','ls-remote','origin','refs/heads/'+cfg['results_branch']],cwd=REPO,text=True).split()[0]
    base=f'https://raw.githubusercontent.com/YGLSNU/eduPIC_PAL_RF-sheath/{ref}/results/{root.name}/'
    with urllib.request.urlopen(base+'README.md',timeout=60) as f:remote=f.read().decode()
    m=json.loads((out/'run.json').read_text());assert m['report_updated'] in remote
    archive=f'{root.name}_restart.zip';digest=hashlib.sha256()
    with urllib.request.urlopen(base+archive,timeout=60) as f:
     for b in iter(lambda:f.read(1024*1024),b''):digest.update(b)
    assert digest.hexdigest()==sha(out/archive)
    record={'published_at_Asia_Seoul':datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),'commit':ref,'status':s['status'],'report_readback':True,'restart_download_SHA256':digest.hexdigest(),'export_path':str(out)}
    put(root/'last_publication.json',record);print('Published verified PSR snapshot',record,flush=True);last=time.monotonic();signature=sig
    if final:put(root/'completion_event.json',record);return
   time.sleep(30)
  except Exception:traceback.print_exc();time.sleep(30)
if __name__=='__main__':main(Path(sys.argv[1]).resolve())
