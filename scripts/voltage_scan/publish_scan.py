#!/usr/bin/env python3
"""Publish saved scan states with short names and update all bookmark catalogs."""
from pathlib import Path
import argparse
import json
import sys
import tempfile
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'results'))
from export_scan import export
from publish_run import publish

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('root',type=Path)
    p.add_argument('--watch',action='store_true')
    p.add_argument('--interval',type=float,default=60)
    p.add_argument('--export-only',type=Path)
    args=p.parse_args();root=args.root.resolve();previous=None
    terminal={'criteria_met','extinguished','measurement_limit_reached','total_cycle_limit_reached','paused_at_checkpoint','paused_error'}
    while True:
        states=[json.loads(q.read_text()) for q in sorted(root.glob('*/status.json'))]
        signature=[(s['voltage_peak_V'],s.get('checkpoint_cycle'),s['status']) for s in states]
        if signature!=previous:
            if args.export_only:
                export(root,args.export_only.resolve());return
            with tempfile.TemporaryDirectory(prefix='edupic-scan-export-') as tmp:
                dest=Path(tmp)/'export';meta=export(root,dest)
                publish(dest,meta['branch'],Path(__file__).resolve().parents[2],True)
            previous=signature
        if not args.watch or (states and all(s['status'] in terminal for s in states)):break
        time.sleep(max(5,args.interval))

if __name__=='__main__':main()
