#!/usr/bin/env python3
"""Check cross-branch Markdown links, metadata, and current file checksums locally."""
from pathlib import Path
from urllib.parse import unquote,urlsplit
import argparse
import hashlib
import json
import re
from catalog import REPO,validate,git
from audit_coverage import audit

def verify(trees,checksums=True):
    failures=[];links=0;hashes=0;reports=0;coverage={'inline':0,'linked':0,'unavailable':0,'missing':0}
    edges={};report_paths=set();starts={str((root/'README.md').resolve()) for root in trees.values()}
    for branch,root in trees.items():
        documents=[root/'README.md',*(root/'docs').glob('*.md'),*(root/'results').rglob('*.md'),*(root/'results').rglob('*.html')]
        for doc in documents:
            text=doc.read_text()
            source=str(doc.resolve());edges.setdefault(source,set())
            targets=re.findall(r'!?\[[^\]]*\]\(([^\s)]+)\)',text)
            targets+=re.findall(r'(?:href|src)=[\"\']([^\"\']+)',text)
            for target in targets:
                path=unquote(target.split('#')[0])
                if not path or path.startswith(('mailto:','data:')):continue
                if path.startswith(('http://','https://')):
                    u=urlsplit(path)
                    if u.netloc!='github.com' or not u.path.startswith('/'+REPO+'/'):continue
                    rest=u.path.removeprefix('/'+REPO+'/')
                    for prefix in ['raw/refs/heads/','blob/','tree/']:
                        if rest.startswith(prefix):rest=rest[len(prefix):];break
                    found=False
                    for ref in sorted(trees,key=len,reverse=True):
                        if rest==ref or rest.startswith(ref+'/'):
                            p=trees[ref]/rest.removeprefix(ref).lstrip('/');found=True;break
                    if not found:
                        if re.match(r'^[0-9a-f]{40}/',rest):
                            ref,oldpath=rest.split('/',1)
                            try:git('cat-file','-e',ref+':'+oldpath,cwd=root)
                            except Exception:failures.append(f'{doc}: missing immutable source link {target}')
                            links+=1;continue
                        failures.append(f'{doc}: unknown current branch link {target}');continue
                else:p=doc.parent/path
                links+=1
                if not p.exists():failures.append(f'{doc}: missing {target} -> {p}')
                else:
                    dest=p/'README.md' if p.is_dir() and (p/'README.md').exists() else p
                    edges[source].add(str(dest.resolve()))
        for metadata in [*(root/'results').glob('*/run.json'),*(root/'results').glob('*/*/report.json')]:
            m=validate(json.loads(metadata.read_text()));reports+=1
            report_paths.add(str((metadata.parent/'README.md').resolve()))
            result=audit(m,(metadata.parent/'README.md').read_text())
            failures.extend(str(metadata)+': '+s for s in result['failures'])
            for kind in result['coverage'].values():coverage[kind]+=1
            if m['branch']!=branch:failures.append(f'{metadata}: branch mismatch')
            for s in m['sections']:
                for im in s.get('images',[]):
                    if not (metadata.parent/im['path']).exists():failures.append(f'{metadata}: missing image '+im['path'])
        if checksums:
            for manifest in (root/'results').rglob('files.json'):
                for name,entry in json.loads(manifest.read_text()).items():
                    p=manifest.parent/name;hashes+=1
                    if not p.exists() or p.stat().st_size!=entry['bytes'] or hashlib.sha256(p.read_bytes()).hexdigest()!=entry['sha256']:
                        failures.append(f'{manifest}: stale checksum {name}')
    reachable=set(starts);pending=list(starts)
    while pending:
        for target in edges.get(pending.pop(),[]):
            if target not in reachable:reachable.add(target);pending.append(target)
    for path in sorted(report_paths-reachable):failures.append('Report is not reachable from any bookmark page: '+path)
    return {'reports':reports,'reachable_reports':len(report_paths&reachable),'diagnostic_coverage':coverage,'links':links,'hashes':hashes,'failures':failures}

def verify_export(root):
    """Validate a standalone run before publishing; external branches stay remote."""
    failures=[];reports=0;hashes=0;links=0
    for metadata in [root/'run.json',*root.glob('*/report.json')]:
        m=validate(json.loads(metadata.read_text()));reports+=1
        text=(metadata.parent/'README.md').read_text()
        failures.extend(str(metadata)+': '+s for s in audit(m,text)['failures'])
        for target in re.findall(r'!?\[[^\]]*\]\(([^\s)]+)\)',text):
            path=unquote(target.split('#')[0])
            if not path or urlsplit(path).scheme:continue
            links+=1
            if not (metadata.parent/path).exists():failures.append(str(metadata)+': missing '+path)
        for d in m.get('downloads',[]):
            if not (metadata.parent/d['path']).is_file():failures.append(str(metadata)+': missing download '+d['path'])
    for manifest in root.rglob('files.json'):
        for name,entry in json.loads(manifest.read_text()).items():
            p=manifest.parent/name;hashes+=1
            if not p.is_file() or p.stat().st_size!=entry['bytes'] or hashlib.sha256(p.read_bytes()).hexdigest()!=entry['sha256']:
                failures.append(str(manifest)+': stale checksum '+name)
    return {'reports':reports,'links':links,'hashes':hashes,'scope':'Standalone export; local report links, diagnostic coverage, downloads and SHA256. Cross-branch URLs remain external.','failures':failures}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--tree',action='append');p.add_argument('--export',type=Path);p.add_argument('--skip-checksums',action='store_true')
    a=p.parse_args()
    if a.export:r=verify_export(a.export.resolve())
    elif a.tree:r=verify({b:Path(d) for b,d in (x.split('=',1) for x in a.tree)},not a.skip_checksums)
    else:p.error('Provide --tree or --export')
    print(json.dumps(r,ensure_ascii=False,indent=2));raise SystemExit(bool(r['failures']))
