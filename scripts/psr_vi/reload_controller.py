#!/usr/bin/env python3
"""One owned checkpoint update, not a general auto-restart or reconnect service."""
from pathlib import Path
import sys,json,os,subprocess,time,fcntl
root=Path(sys.argv[1]).resolve();token=sys.argv[2]
assert root.name.endswith('PSR_gap15_f60_V150')
lock=(root/'controller_update.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
marker=root/'STOP_AFTER_BLOCK'
while marker.exists() and marker.read_text()==token:
    state=json.loads((root/'status.json').read_text())
    if state['status'] in ['criteria_met','measurement_limit_reached','total_cycle_limit_reached','extinguished','paused_error']:break
    if state['status']=='paused_at_checkpoint':
        pid=state.get('controller_pid');p=Path(f'/proc/{pid}/cmdline')
        if p.exists() and p.read_bytes():time.sleep(1);continue
        marker.unlink()
        with (root/'controller.log').open('a') as f:
            process=subprocess.Popen([sys.executable,'-u',str(Path(__file__).with_name('run.py')),str(root)],stdout=f,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,start_new_session=True)
        (root/'controller.pid').write_text(str(process.pid)+'\n')
        (root/'controller_update_applied.json').write_text(json.dumps({'token':token,'new_pid':process.pid,'checkpoint_RF':state['completed_RF']},indent=2)+'\n')
        break
    time.sleep(5)
