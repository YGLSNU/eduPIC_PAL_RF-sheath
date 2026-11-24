"""Reserve capacity for earlier scans without stopping their solver processes."""
from contextlib import contextmanager
from pathlib import Path
import fcntl,json,os,time

TERMINAL={'criteria_met','extinguished','measurement_limit_reached','total_cycle_limit_reached'}
class StopAtCheckpoint(Exception):pass

def legacy_reservations(cfg):
    count=0
    for item in cfg.get('capacity_reservations',[]):
        root=Path(item['root']);controller=root/'controller.json'
        if not controller.exists():continue
        pid=json.loads(controller.read_text())['pid'];proc=Path(f'/proc/{pid}/cmdline')
        if not proc.exists():continue
        command=proc.read_bytes()
        if b'run_scan.py' not in command or str(root).encode() not in command:continue
        for gap in item['gaps_mm']:
            status=json.loads((root/f'{gap}mm/status.json').read_text())['status']
            if status not in TERMINAL and status not in ['paused_error','paused_at_checkpoint']:count+=1
    return count

@contextmanager
def solver_slot(root,update,case=None):
    cfg=json.loads((root/'config.json').read_text())
    if not cfg.get('capacity_reservations'):
        yield;return
    directory=root/'capacity';directory.mkdir(exist_ok=True)
    limit=cfg.get('total_solver_slots',4);held=None;last=0
    while held is None:
        if (root/'STOP_AFTER_BLOCK').exists() or (case is not None and (case/'STOP_AFTER_BLOCK').exists()):raise StopAtCheckpoint()
        reserved=legacy_reservations(cfg)
        for slot in range(min(reserved,limit),limit):
            f=(directory/f'{slot}.lock').open('a')
            try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);held=f;break
            except BlockingIOError:f.close()
        if held is None:
            if time.monotonic()-last>30:
                update(status='queued',execution_state='waiting_for_capacity',capacity_reserved_for_earlier_scan=reserved,solver_pid=None)
                last=time.monotonic()
            time.sleep(2)
    try:
        update(status='running',execution_state='solver',capacity_reserved_for_earlier_scan=reserved)
        yield
    finally:
        fcntl.flock(held,fcntl.LOCK_UN);held.close()
