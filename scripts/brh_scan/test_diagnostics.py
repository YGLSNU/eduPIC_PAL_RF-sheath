"""Numeric/selection regressions complement the real solver validation."""
from pathlib import Path
import csv,json,tempfile,unittest
import numpy as np
from brh_stats import return_stats,assess
from measurement import pool_native
from postprocess import block_hist,compress_block,edges

CRITERIA={'block_cycles':20,'minimum_measurement_cycles':200,'particle_count_window':600,'particle_count_block_span_tolerance':.01,'particle_count_fitted_drift_tolerance':.02,
    'heating_map_relative_tolerance':.05,'mean_quantity_relative_tolerance':.03,'BRH_fraction_absolute_tolerance':.005,'BRH_fraction_relative_tolerance':.1,'BRH_required_consecutive_round_trips':2}

class DiagnosticsTests(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
    def returns(self,d,rows):
        d.mkdir(exist_ok=True)
        with (d/'brh_roundtrips.csv').open('w') as f:
            w=csv.writer(f);w.writerow(['uid','side','near_fundamental','consecutive_returns','W_field_eV']);w.writerows(rows)
    def test_phase_selection_keeps_negative_work_and_excludes_first_return(self):
        blocks=[self.root/str(k) for k in range(2)]
        for d in blocks:self.returns(d,[[1,1,1,2,-4],[2,1,1,2,2],[3,1,1,1,100],[4,0,1,2,100]])
        s=return_stats(blocks,CRITERIA)
        self.assertEqual(s['powered_side_returns'],6);self.assertEqual(s['candidate_returns'],4)
        self.assertEqual(s['candidate_signed_work_eV']['estimate'],-1)
        self.assertAlmostEqual(s['candidate_return_fraction']['estimate'],2/3)
        self.assertFalse(s['passed']) # too few distinct UIDs despite repeated rows
    def test_raw_histogram_lossless_compression_and_nonuniform_bins(self):
        a=np.zeros((20,200,2,271),dtype='<u8');a[9,2,1,0]=9;a[9,2,1,100]=100
        for k in ['E','Ex']:a.tofile(self.root/f'brh_hist_{k}_counts.bin')
        text='uid,side\n1,1\n';(self.root/'brh_roundtrips.csv').write_text(text);compress_block(self.root)
        self.assertTrue(np.array_equal(block_hist(self.root,'E'),a));self.assertFalse((self.root/'brh_hist_E_counts.bin').exists())
        e=edges();self.assertEqual(len(e),271);self.assertTrue(np.all(np.diff(e)>0));self.assertAlmostEqual(e[100]-e[99],.1);self.assertEqual(e[101]-e[100],1);self.assertEqual(e[-1]-e[-2],5)
    def test_pool_density_weights_energy_and_recomputes_pooled_jE(self):
        blocks=[]
        for j,n in enumerate([1.,9.]):
            d=self.root/str(j);d.mkdir();blocks.append(d)
            for k,v in [('pot',0),('efield',1+j),('ne',n),('ni',n),('je',2+j),('ji',1),('ioniz',5),('meanee',10 if j==0 else 20),('meanei',1)]:np.savetxt(d/(k+'_xt.dat'),np.full((17,200),v))
            np.savetxt(d/'density.dat',np.c_[np.linspace(0,.04,17),np.full(17,n),np.full(17,n)])
            for f in ['eepf.dat','ifed.dat','info.txt']:(d/f).write_text('last-block fixture\n')
            (d/'block.json').write_text(json.dumps({'RF_first':j*20+1,'RF_last':(j+1)*20}));(d/'particle_balance.csv').write_text('RF_cycle,x\n'+str(j)+',1\n')
        dest=self.root/'pooled';pool_native(blocks,dest)
        self.assertTrue(np.allclose(np.loadtxt(dest/'meanee_xt.dat'),19))
        self.assertTrue(np.allclose(np.loadtxt(dest/'powere_xt.dat'),2.5*1.5))
        self.assertFalse(np.isclose(2.5*1.5,(2*1+3*2)/2))
    def test_assessment_accepts_non400_grid_and_does_not_require_positive_gain(self):
        blocks=[]
        for j in range(10):
            d=self.root/str(j);blocks.append(d);self.returns(d,[[u,1,1,2,(-1)**u] for u in range(100)])
            for k,v in [('ne',2),('ni',3),('je',2),('ji',1),('efield',4)]:np.savetxt(d/(k+'_xt.dat'),np.full((17,200),v))
        history=np.c_[np.arange(1,601),np.full(600,2000),np.full(600,2100)]
        result=assess(blocks,history,CRITERIA,40)
        self.assertTrue(result['background_passed']);self.assertTrue(result['BRH']['passed']);self.assertTrue(result['passed'])
        self.assertEqual(result['BRH']['candidate_signed_work_eV']['estimate'],0.)

if __name__=='__main__':unittest.main()
