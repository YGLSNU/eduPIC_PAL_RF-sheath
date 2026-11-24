"""Refinement scheduling, provenance, and non-default gap report checks."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import json,tempfile,threading,time,unittest
import numpy as np
from capacity import solver_slot,StopAtCheckpoint

class RefinementTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)

    def test_reserved_legacy_slots_limit_new_solvers(self):
        (self.root/'config.json').write_text(json.dumps({'capacity_reservations':[{}],'total_solver_slots':4}))
        lock=threading.Lock();counts=[0,0]
        def work():
            with solver_slot(self.root,lambda **kw:None):
                with lock:counts[0]+=1;counts[1]=max(counts)
                time.sleep(.05)
                with lock:counts[0]-=1
        with patch('capacity.legacy_reservations',return_value=3),ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(work) for _ in range(2)]
            for f in futures:f.result()
        self.assertEqual(counts[1],1)

    def test_stop_while_waiting_never_launches_a_solver(self):
        (self.root/'config.json').write_text(json.dumps({'capacity_reservations':[{}],'total_solver_slots':4}))
        (self.root/'STOP_AFTER_BLOCK').touch()
        with patch('capacity.legacy_reservations',return_value=4),self.assertRaises(StopAtCheckpoint):
            with solver_slot(self.root,lambda **kw:None):self.fail('entered solver')

    def test_new_date_new_gap_and_reused_origin_are_rendered(self):
        from export import export
        from test_diagnostics import CRITERIA
        root=self.root/'261124_BRH_gap20-80_step5';root.mkdir();old=self.root/'previous35mm';old.mkdir()
        cfg={'id':root.name,'date':'2026-11-24','gaps_mm':[20,35],'run_gaps_mm':[20],
             'case_sources':{'35':{'path':str(old),'run_id':'261123_BRH_gap25-120','date':'2026-11-23'}},'control_source_SHA256':'fixture'}
        (root/'config.json').write_text(json.dumps(cfg));(root/'criteria.json').write_text(json.dumps(CRITERIA))
        for g,d in [(20,root/'20mm'),(35,old)]:
            d.mkdir(exist_ok=True);np.array([0.,0.,0.,0.],dtype='<f8').tofile(d/'input_cycle0.bin')
            (d/'status.json').write_text(json.dumps({'gap_mm':g,'grid_points':g*16+1,'status':'queued','phase':'warmup','checkpoint_cycle':0,'measured_RF':0}))
        out=self.root/'export';export(root,out)
        parent=json.loads((out/'run.json').read_text());reuse=json.loads((out/'35mm/report.json').read_text())
        self.assertEqual(parent['id'],root.name);self.assertEqual(reuse['date'],'2026-11-23')
        self.assertIn('261124_BRH_source.zip',[d['path'] for d in parent['downloads']])
        self.assertTrue((out/'20mm/261124_20mm_restart.zip').exists())
        self.assertTrue((out/'35mm/261123_35mm_restart.zip').exists())
        comparison=(out/'comparison/README.md').read_text()
        self.assertIn('[20]',comparison);self.assertIn('[35]',comparison);self.assertIn('2개 계획',comparison)

if __name__=='__main__':unittest.main()
