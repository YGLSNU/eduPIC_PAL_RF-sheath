"""Publishing metadata must not download unchanged scientific archives."""
from pathlib import Path
import hashlib,json,subprocess,tempfile,unittest
from catalog import commit_files,refresh_remote_manifests

class PartialPublishTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.git('init','-q');self.git('config','user.name','Recovery test');self.git('config','user.email','recovery-test@example.invalid')
        self.folder='results/261126_partial/'
        d=self.root/self.folder;d.mkdir(parents=True);data=b'previously published scientific archive'
        self.blob=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
        self.entry={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'git_blob':self.blob}
        (d/'archive.zip').write_bytes(data);(d/'files.json').write_text(json.dumps({'archive.zip':self.entry}))
        self.git('add','.');self.git('commit','-qm','original')
        self.object=self.root/'.git/objects'/self.blob[:2]/self.blob[2:];self.object.unlink()
    def git(self,*args):return subprocess.check_output(['git',*args],cwd=self.root,text=True).strip()
    def test_tree_commit_preserves_missing_base_object(self):
        commit=commit_files(self.root,'HEAD',{'new-report.txt':'Recovered checkpoint report\n'},'publish metadata')
        self.assertEqual(self.git('rev-parse',commit+':'+self.folder+'archive.zip'),self.blob)
        self.assertEqual(self.git('show',commit+':new-report.txt'),'Recovered checkpoint report')
        self.assertFalse(self.object.exists())
    def test_cached_manifest_needs_no_blob_size_fetch(self):
        files={}
        refresh_remote_manifests(self.root,'HEAD',files,[{'id':'261126_partial','branch':'results/test'}],'results/test')
        self.assertEqual(json.loads(files[self.folder+'files.json'])['archive.zip'],self.entry)
        self.assertFalse(self.object.exists())

if __name__=='__main__':unittest.main()
