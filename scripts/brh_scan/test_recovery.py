"""Recovery must preserve RF weighting and never invent cumulative uncertainty."""
from pathlib import Path
import json,tempfile,unittest
from unittest.mock import patch
import numpy as np
from common import put,block_cycles
from measurement import pool_native
from recovery import assess_available

class RecoveryTests(unittest.TestCase):
    def test_duration_weighted_native_moments(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);blocks=[]
            for i,(count,n,energy,j,field) in enumerate([(700,2.,3.,4.,5.),(20,8.,9.,10.,11.)]):
                p=root/str(i);p.mkdir();blocks.append(p)
                put(p/'block.json',{'RF_first':1 if i==0 else 701,'RF_last':count if i==0 else 720})
                for key,value in [('pot',1),('efield',field),('ne',n),('ni',n),('je',j),('ji',j),('ioniz',1),('meanee',energy),('meanei',energy)]:
                    np.savetxt(p/(key+'_xt.dat'),np.full((2,2),value))
                np.savetxt(p/'density.dat',np.array([[0,n,n],[1,n,n]]))
                for name in ['eepf.dat','ifed.dat','info.txt']:(p/name).write_text(str(i))
                (p/'particle_balance.csv').write_text('RF_cycle,value\n'+f'{i},1\n')
            dest=root/'pooled';pool_native(blocks,dest)
            n=(700*2+20*8)/720
            self.assertTrue(np.allclose(np.loadtxt(dest/'ne_xt.dat'),n))
            self.assertTrue(np.allclose(np.loadtxt(dest/'meanee_xt.dat'),(700*2*3+20*8*9)/(720*n)))
            self.assertTrue(np.allclose(np.loadtxt(dest/'powere_xt.dat'),((700*4+20*10)/720)*((700*5+20*11)/720)))
            self.assertEqual((dest/'eepf.dat').read_text(),'1')
            self.assertEqual(sum(block_cycles(p) for p in blocks),720)

    def test_no_fabricated_full_window_uncertainty(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);old=root/'old';old.mkdir();new=root/'new';new.mkdir()
            put(old/'recovery_aggregate.json',{});put(old/'block.json',{'RF_first':1,'RF_last':700});put(new/'block.json',{'RF_first':701,'RF_last':720})
            segment={'passed':True,'background_passed':True,'indicators':{}}
            ratio={'estimate':0.,'half_width':.001,'first_last_change':0.,'passed_data':True}
            desc={'candidate_return_fraction':ratio.copy(),'candidate_signed_work_eV':ratio.copy()}
            with patch('recovery.assess',return_value=segment) as call,patch('recovery.return_stats',return_value=desc):
                result=assess_available([old,new],[],{},75)
                self.assertEqual(call.call_args.args[0],[new])
            self.assertEqual(result['measurement_cycles'],720)
            self.assertFalse(result['passed'])
            self.assertIsNone(result['BRH']['candidate_return_fraction']['half_width'])
            self.assertTrue(result['post_resume_segment_assessment']['passed'])

if __name__=='__main__':unittest.main()
