"""Scientific bookkeeping checks for gap summaries, independent of the solver."""
import unittest
import numpy as np
import pandas as pd
from compare import weighted_moments, classify_returns, attach_energy, episode_energy


class ComparisonTests(unittest.TestCase):
    def frame(self):
        # UID 1: five near returns -> four candidate events, one episode.
        # A second episode follows a non-near return. UID 2 starts censored.
        records=[]
        for uid,streaks in [(1,[1,2,3,4,5,0,1,2]),(2,[3,4]),(3,[0,0])]:
            for j,k in enumerate(streaks):
                records.append([uid,j*1e-7,(j+1)*1e-7,int(k>0),k,2.,-3.,-1.])
        return pd.DataFrame(records,columns=['uid','start_t_s','end_t_s','near_fundamental','consecutive_returns','W_field_eV','dK_collision_parent_eV','dK_staggered_eV'])

    def test_distinct_episodes_and_zero_event_denominator(self):
        a,r,u=classify_returns(self.frame())
        self.assertEqual(u.loc[1,'candidate_returns'],5)
        self.assertEqual(u.loc[1,'observed_candidate_episodes'],2)
        self.assertEqual(u.loc[1,'max_observed_near_run'],5)
        self.assertEqual(u.loc[2,'left_censored_candidate_episodes'],1)
        self.assertEqual(u.loc[3,'candidate_returns'],0)
        self.assertEqual(len(u),3)

    def test_gap_in_saved_returns_cannot_form_a_long_episode(self):
        q=self.frame();q.loc[(q.uid==1)&(q.consecutive_returns>=3),'start_t_s']+=1e-9
        _,r,u=classify_returns(q)
        self.assertEqual(u.loc[1,'max_observed_near_run'],2)
        self.assertTrue(r.left_censored.any())

    def test_native_reset_prevents_joining_near_returns(self):
        q=self.frame().iloc[:2].copy();q['consecutive_returns']=1
        _,r,u=classify_returns(q)
        self.assertEqual(u.loc[1,'max_observed_near_run'],1)
        self.assertEqual(u.loc[1,'observed_candidate_episodes'],0)

    def test_energy_ledger_and_cooling_episodes_are_preserved(self):
        a,r,u=classify_returns(self.frame())
        enc=[]
        for uid in [1,2,3]:
            q=a[a.uid==uid]
            for j,t in enumerate(np.r_[q.start_t_s.iloc[0],q.end_t_s]):enc.append([uid,t,20.-j])
        enc=pd.DataFrame(enc,columns=['uid','exit_t_s','exit_K_staggered_eV'])
        a,check=attach_energy(a,enc);nodes=episode_energy(a,r)
        self.assertEqual(check['reconstructed_start_energies'],0)
        self.assertFalse((nodes.uid==2).any()) # initial near returns unobserved
        self.assertTrue((nodes.loc[nodes.return_index>0,'delta_K_eV']<0).all())
        self.assertTrue(np.allclose(nodes.delta_K_eV,nodes.field_work_eV+nodes.collision_dK_eV))
        bad=enc.copy();bad.loc[(bad.uid==1)&(bad.exit_t_s==0),'exit_K_staggered_eV']=99.
        with self.assertRaises(AssertionError):attach_energy(a,bad)

    def test_energy_temperature_is_particle_weighted(self):
        ne=np.array([[1.,9.],[1.,9.]])
        energy=np.array([[10.,20.],[10.,20.]])
        density,te=weighted_moments(ne,energy,np.array([0.,1.]))
        self.assertEqual(density,5.)
        self.assertAlmostEqual(te,2*19/3)
        self.assertNotAlmostEqual(te,2*energy.mean()/3)


if __name__=='__main__':unittest.main()
