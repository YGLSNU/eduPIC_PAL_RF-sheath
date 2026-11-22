#!/usr/bin/env python3
"""Upload one prepared result folder, then update every branch's bookmark page."""
import argparse
import json
from pathlib import Path
import tempfile
import shutil
from catalog import git,validate,render_report,refresh_files,commit_files,sync,safe_path

def publish(export,branch,root,push):
    metadata=validate(json.loads((export/'run.json').read_text()))
    if metadata['branch']!=branch:raise ValueError('Manifest branch differs from destination')
    for f in export.rglob('*'):
        if f.is_symlink():raise ValueError('Result exports cannot contain symlinks')
    # Work on a copy: preserve the simulation's original output and provenance.
    with tempfile.TemporaryDirectory(prefix='edupic-upload-') as tmp:
        dest=Path(tmp)/metadata['id'];shutil.copytree(export,dest)
        for f in dest.rglob('*'):
            if f.is_symlink():raise ValueError('Result exports cannot contain symlinks')
            if f.is_file() and f.stat().st_size>=95*1024*1024:raise ValueError('Split archives below 95 MiB: '+str(f))
        for p in dest.glob('*/report.json'):
            child=validate(json.loads(p.read_text()));refresh_files(p.parent,child)
            p.write_text(json.dumps(child,ensure_ascii=False,indent=2)+'\n')
            (p.parent/'README.md').write_text(render_report(child));refresh_files(p.parent,child)
        refresh_files(dest,metadata)
        (dest/'run.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+'\n')
        (dest/'README.md').write_text(render_report(metadata));refresh_files(dest,metadata)
        git('fetch','--no-tags','origin','refs/heads/'+branch+':refs/remotes/origin/'+branch,cwd=root)
        base='refs/remotes/origin/'+branch
        files={'results/'+metadata['id']+'/'+safe_path(p.relative_to(dest).as_posix()):p.read_bytes()
               for p in dest.rglob('*') if p.is_file()}
        commit=commit_files(root,base,files,'Save '+metadata['id']+' simulation report and data')
        if commit and push:git('push','origin',commit+':refs/heads/'+branch,cwd=root)
        if push:sync(root,push=True)
        return commit

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('export',type=Path);p.add_argument('--branch',required=True);p.add_argument('--push',action='store_true')
    a=p.parse_args();print(publish(a.export.resolve(),a.branch,Path.cwd(),a.push))
