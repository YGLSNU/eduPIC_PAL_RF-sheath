"""Bounded ZIP delivery, including lossless byte parts for large payload files."""
from pathlib import Path
import hashlib,json,zipfile

def info(name,stored=False):
    z=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0));z.compress_type=zipfile.ZIP_STORED if stored else zipfile.ZIP_DEFLATED;z.external_attr=0o100644<<16;return z

REASSEMBLE='''"""Extract every ZIP into one directory, then run this script there."""
from pathlib import Path
import hashlib,json,shutil
root=Path(__file__).resolve().parent
manifest=json.loads((root/'payload_manifest.json').read_text())
for name,m in manifest['files'].items():
    if Path(name).name!=name:raise SystemExit('Invalid payload name')
    parts=[root/p['path'] for p in m['parts']]
    if any(not p.exists() for p in parts):raise SystemExit('Extract all ZIP parts first: '+name)
    destination=root/name
    if not (len(parts)==1 and parts[0]==destination):
        temp=destination.with_name(destination.name+'.joining')
        with temp.open('wb') as out:
            for part in parts:
                with part.open('rb') as src:shutil.copyfileobj(src,out)
        temp.replace(destination)
    h=hashlib.sha256()
    with destination.open('rb') as src:
        for chunk in iter(lambda:src.read(1024*1024),b''):h.update(chunk)
    if h.hexdigest()!=m['sha256'] or destination.stat().st_size!=m['bytes']:raise SystemExit('Checksum mismatch: '+name)
    print('Verified',name)
print('All payload files restored. CSV.gz and NPZ files are ready to read.')
'''

def package(payloads,target,stem,limit=48*1024*1024):
    """Bound uncompressed payload per archive; no scientific records are dropped."""
    target=Path(target);manifest={'schema_version':1,'files':{}};pieces=[]
    for source,name in payloads:
        source=Path(source);assert Path(name).name==name
        size=source.stat().st_size;h=hashlib.sha256()
        with source.open('rb') as f:
            for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
        count=max(1,(size+limit-1)//limit);parts=[]
        for j in range(count):
            member=name if count==1 else name+f'.part{j+1:04d}';length=min(limit,max(0,size-j*limit))
            pieces.append((source,member,j*limit,length,count==1));parts.append({'path':member,'bytes':length})
        manifest['files'][name]={'bytes':size,'sha256':h.hexdigest(),'parts':parts}
    groups=[];current=[];used=0
    for piece in pieces:
        if current and used+piece[3]>limit:groups.append(current);current=[];used=0
        current.append(piece);used+=piece[3]
    if current:groups.append(current)
    archives=[target/(stem+('' if len(groups)==1 else f'_p{j+1:02d}')+'.zip') for j in range(len(groups))]
    manifest['archives']=[p.name for p in archives]
    note=('BRH raw diagnostic payloads. RF range and sampling definitions: summary.json.\n'
          'Download ALL '+str(len(archives))+' ZIP(s) and extract them into the same directory.\n'
          'Files with .partNNNN are lossless byte parts; run: python reassemble_brh.py\n'
          'The script verifies every original payload SHA256. CSV.gz and NPZ remain compressed data files.\n'
          'Trajectory illustration covers only the first five RF of the first measurement block.\n'
          'Round-trip/encounter events, probes, energy histograms and field work cover the recorded measurement epoch.\n')
    # Superseded export packages are reproducible derivatives. Already-pushed
    # Git history and every raw solver block remain intact.
    for old in target.glob(stem+'*.zip'):old.unlink()
    for path,group in zip(archives,groups):
        with zipfile.ZipFile(path,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=3) as z:
            z.writestr(info('ARCHIVE_README.txt'),note);z.writestr(info('payload_manifest.json'),json.dumps(manifest,indent=2)+'\n');z.writestr(info('reassemble_brh.py'),REASSEMBLE)
            for source,member,offset,length,whole in group:
                with source.open('rb') as src,z.open(info(member,source.suffix in ['.gz','.npz']),'w') as dst:
                    src.seek(offset);remaining=length
                    while remaining:
                        b=src.read(min(1024*1024,remaining));assert b;dst.write(b);remaining-=len(b)
        assert path.stat().st_size<95*1024*1024,'Package exceeded GitHub upload budget'
    return archives
