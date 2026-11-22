"""Regression checks for genuinely missing diagnostics versus unrecorded data."""
from pathlib import Path
import copy,json,unittest
from audit_coverage import audit
from catalog import render_report

class CoverageTests(unittest.TestCase):
    def setUp(self):self.m=json.loads((Path(__file__).parent/'run.example.json').read_text())

    def test_unrecorded_measurements_are_explicit_and_visible(self):
        result=audit(self.m,render_report(self.m))
        self.assertEqual(result['failures'],[])
        self.assertTrue(all(v=='unavailable' for v in result['coverage'].values()))

    def test_unavailable_requires_a_reason(self):
        self.m['sections'][0].pop('reason')
        self.assertTrue(any('explicit reason' in e for e in audit(self.m)['failures']))

    def test_claiming_data_elsewhere_without_a_link_does_not_pass(self):
        sec=self.m['sections'][0];sec.update(data_status='available',text='그림은 다른 곳에 있습니다.')
        self.assertTrue(audit(self.m,render_report(self.m))['failures'])

    def test_file_presence_does_not_hide_missing_inline_placement(self):
        sec=self.m['sections'][0];sec.update(data_status='available',images=[{'path':'figures/saved.png','caption':'Saved graph'}])
        markdown=render_report(self.m).replace('![Saved graph](figures/saved.png)','')
        self.assertTrue(any('not embedded' in e for e in audit(self.m,markdown)['failures']))

    def test_missing_section_is_detected(self):
        self.m['sections'].pop()
        self.assertTrue(any('section absent' in e for e in audit(self.m)['failures']))

if __name__=='__main__':unittest.main()
