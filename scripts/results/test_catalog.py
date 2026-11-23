"""Meaningful offline coverage for multi-branch publishing; no real GitHub writes."""
from pathlib import Path
import copy
import hashlib
import json
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from catalog import git,validate,render_report,sync
from publish_run import publish
import publish_run
from catalog import commit_files

HERE=Path(__file__).parent

class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/'repo';self.root.mkdir()
        self.remote=Path(self.tmp.name)/'remote.git'
        git('init','--bare',str(self.remote),cwd=self.root)
        git('init','-b','main',cwd=self.root)
        git('config','user.name','Offline test',cwd=self.root);git('config','user.email','test@example.invalid',cwd=self.root)
        (self.root/'C').mkdir();(self.root/'C/eduPIC.cc').write_text('original solver fixture\n')
        (self.root/'README.md').write_text('original introduction\n')
        git('add','.',cwd=self.root);git('commit','-m','initial',cwd=self.root)
        git('remote','add','origin',str(self.remote),cwd=self.root);git('push','origin','main',cwd=self.root)
        git('switch','-c','results/20mTorr-topRF',cwd=self.root)
        self.meta=json.loads((HERE/'run.example.json').read_text());self.meta['title']='Offline fixture'
        d=self.root/'results'/self.meta['id'];d.mkdir(parents=True)
        (self.root/'results/family.json').write_text('{"branch":"results/20mTorr-topRF"}')
        (d/'run.json').write_text(json.dumps(self.meta));(d/'README.md').write_text('stale')
        (d/'raw.bin').write_bytes(b'preserved result fixture')
        git('add','.',cwd=self.root);git('commit','-m','result',cwd=self.root)
        git('push','origin','HEAD',cwd=self.root)
        self.original=git('rev-parse','HEAD:results/'+self.meta['id']+'/raw.bin',cwd=self.root)

    def test_sync_updates_main_and_condition_and_preserves_data(self):
        changes=sync(self.root,push=True)
        self.assertEqual(set(changes),{'main','results/20mTorr-topRF'})
        git('fetch','origin',cwd=self.root)
        page=git('show','refs/remotes/origin/main:README.md',cwd=self.root)
        self.assertIn(self.meta['id'],page)
        report=git('show','refs/remotes/origin/results/20mTorr-topRF:results/'+self.meta['id']+'/README.md',cwd=self.root)
        self.assertIn('미완료',report);self.assertIn('상부 RF / 하부 접지',report)
        self.assertEqual(git('show','refs/remotes/origin/main:C/eduPIC.cc',cwd=self.root),'original solver fixture')
        self.assertEqual(git('rev-parse','refs/remotes/origin/results/20mTorr-topRF:results/'+self.meta['id']+'/raw.bin',cwd=self.root),self.original)
        entries=json.loads(git('show','refs/remotes/origin/results/20mTorr-topRF:results/'+self.meta['id']+'/files.json',cwd=self.root))
        readme=git('show','refs/remotes/origin/results/20mTorr-topRF:results/'+self.meta['id']+'/README.md',cwd=self.root)+'\n'
        self.assertEqual(entries['README.md']['sha256'],hashlib.sha256(readme.encode()).hexdigest())
        self.assertEqual(sync(self.root,push=True),{})

    def test_publisher_registers_new_run_and_automatically_updates_main(self):
        export=Path(self.tmp.name)/'export';export.mkdir()
        m=copy.deepcopy(self.meta);m.update(id='261123_gap40_V400',date='2026-11-23',title='Second offline fixture')
        m['downloads']=[{'label':'Raw fixture','path':'fixture.csv'}]
        (export/'run.json').write_text(json.dumps(m));(export/'fixture.csv').write_text('x,y\n0,1\n')
        publish(export,m['branch'],self.root,True)
        git('fetch','origin',cwd=self.root)
        index=json.loads(git('show','refs/remotes/origin/main:results/catalog.json',cwd=self.root))
        self.assertEqual(len(index),2)
        self.assertFalse((export/'README.md').exists())
        files=json.loads(git('show','refs/remotes/origin/results/20mTorr-topRF:results/'+m['id']+'/files.json',cwd=self.root))
        self.assertIn('README.md',files);self.assertIn('fixture.csv',files)

    def test_invalid_dates_and_paths_are_rejected(self):
        m=copy.deepcopy(self.meta);m['date']='2026-11-23'
        with self.assertRaises(ValueError):validate(m)

    def test_overview_sections_without_inline_images_link_to_case_reports(self):
        m=copy.deepcopy(self.meta)
        m['sections']=[{'id':'fields','availability':'전압별 상세 보고서에 저장','images':[],'text':''}]
        m['cases']=[{'voltage_V':100,'status':'incomplete','path':'100V/README.md'},
                    {'voltage_V':300,'status':'incomplete','path':'300V/README.md'}]
        text=render_report(m).split('## 전위·전기장\n',1)[1].split('\n## ',1)[0]
        self.assertIn('전압별 상세 보고서에 저장',text)
        self.assertIn('[100 V](100V/README.md)',text)
        self.assertIn('[300 V](300V/README.md)',text)

    def test_gap_scan_keeps_gap_labels_and_related_report_links(self):
        m=copy.deepcopy(self.meta);m['scan_parameter']='gap_mm'
        m['cases']=[{'gap_mm':40,'status':'running','path':'40mm/README.md'},
                    {'gap_mm':100,'status':'incomplete','path':'100mm/README.md'}]
        m['sections']=[{'id':'fields','availability':'상세 보고서','images':[]}]
        m['related_links']=[{'label':'BRH 진단','url':'METHOD.md'}]
        page=render_report(m)
        self.assertIn('| Gap mm |',page);self.assertIn('[100 mm](100mm/README.md)',page)
        self.assertIn('[BRH 진단](METHOD.md)',page);self.assertNotIn('[100 V]',page)

    def test_upload_survives_a_concurrent_catalog_commit(self):
        export=Path(self.tmp.name)/'export';export.mkdir()
        m=copy.deepcopy(self.meta);m.update(id='261123_gap40_V400',date='2026-11-23')
        (export/'run.json').write_text(json.dumps(m))
        raced=[]
        def racing_git(*args,**kwargs):
            if args[0]=='push' and not raced:
                raced.append(True)
                base=git('rev-parse','refs/remotes/origin/'+m['branch'],cwd=self.root)
                commit=commit_files(self.root,base,{'README.md':'Concurrent index fixture\n'},'Simulate index writer')
                git('push','origin',commit+':refs/heads/'+m['branch'],cwd=self.root)
            return git(*args,**kwargs)
        with patch.object(publish_run,'git',side_effect=racing_git):publish(export,m['branch'],self.root,True)
        index=json.loads(git('show','refs/remotes/origin/main:results/catalog.json',cwd=self.root))
        self.assertEqual(len(index),2);self.assertEqual(raced,[True])
        m=copy.deepcopy(self.meta);m['downloads']=[{'label':'Bad','path':'../../outside'}]
        with self.assertRaises(ValueError):validate(m)
        m=copy.deepcopy(self.meta);m['status']='unknown'
        with self.assertRaises(ValueError):validate(m)

if __name__=='__main__':unittest.main()
