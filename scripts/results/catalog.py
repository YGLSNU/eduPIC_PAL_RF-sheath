#!/usr/bin/env python3
"""Render research reports and synchronize catalogs using git, without a GitHub API token."""
from __future__ import annotations
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tempfile
from datetime import date

REPO = 'YGLSNU/eduPIC_PAL_RF-sheath'
WEB = 'https://github.com/' + REPO
CODE_BRANCH = 'simulation/20mTorr-topRF'
STATUS = {'criteria_met':'통계 기준 충족', 'measurement_complete':'측정 완료·통계 기준 별도',
          'extinguished':'전자 소멸', 'incomplete':'미완료', 'diagnostic':'과도구간 진단',
          'running':'계산 중', 'building':'컴파일 중', 'paused_error':'오류로 중단', 'paused_at_checkpoint':'체크포인트 중단',
          'measurement_limit_reached':'측정 상한·기준 미충족', 'total_cycle_limit_reached':'주기 상한·기준 미충족'}
STANDARD_SECTIONS = [('convergence','수렴·입자 수지'), ('density','밀도 공간분포'),
                     ('heating','RF heating'), ('fields','전위·전기장'),
                     ('ionization','평균 에너지·이온화'), ('distributions','에너지 분포'),
                     ('walls','전극 flux·손실'), ('power','전력 전달·손실')]

def git(*args, cwd=None, env=None, check=True, input=None):
    return subprocess.run(['git', *args], cwd=cwd, env=env, input=input,
                          text=True, capture_output=True, check=check).stdout.strip()

def safe_path(value):
    p=PurePosixPath(value)
    if not value or p.is_absolute() or '..' in p.parts or '\\' in value:
        raise ValueError('Unsafe report path: '+value)
    return value

def validate(meta):
    for key in ['id','branch','date','title','status','changed_conditions','conditions','source','sections']:
        if key not in meta: raise ValueError('Missing run metadata: '+key)
    if not re.fullmatch(r'\d{6}_[A-Za-z0-9_.-]+', meta['id']):
        raise ValueError('Run id must be YYMMDD_changedconditions')
    if date.fromisoformat(meta['date']).strftime('%y%m%d')!=meta['id'][:6]:
        raise ValueError('Run id date differs from actual execution date')
    if meta['status'] not in STATUS: raise ValueError('Unknown status: '+meta['status'])
    if not meta['branch'].startswith('results/'): raise ValueError('A run belongs on a results/ branch')
    for c in meta.get('cases',[]): safe_path(c['path'])
    for section in meta['sections']:
        for im in section.get('images',[]):safe_path(im['path'])
    for d in meta.get('downloads',[]):safe_path(d['path'])
    if meta.get('details'):safe_path(meta['details'])
    return meta

def escape(value):return str(value).replace('|','\\|').replace('\n',' ')
def label(status):return STATUS.get(status,status)
def blob(branch,path):return f'{WEB}/blob/{branch}/{path}'
def raw(branch,path):return f'{WEB}/raw/refs/heads/{branch}/{path}'

def file_size(value):
    if value is None:return '—'
    if value<1024:return f'{value} B'
    if value<1048576:return f'{value/1024:.1f} KiB'
    return f'{value/1048576:.2f} MiB'

def condition_rows(c):
    p=c.get('pressure_mTorr'); pressure=f'{p:g} mTorr' if isinstance(p,(int,float)) else str(p)
    if c.get('original_pressure_Pa') is not None:pressure+=f' (원조건 {c["original_pressure_Pa"]:g} Pa)'
    voltage=c.get('voltage_peak_V',[])
    if not isinstance(voltage,list):voltage=[voltage]
    return [('기체 / 압력 / 온도',f'{c.get("gas","Ar")} / {pressure} / {c.get("temperature_K",350)} K'),
            ('인가 파형 / 주파수',f'{c.get("waveform","정현파")} / {c.get("frequency_MHz",13.56):g} MHz'),
            ('전압 / gap',f'{", ".join(str(v) for v in voltage)} V peak / {c.get("gap_mm","별도 표")} mm'),
            ('전극 연결',c.get('electrodes','별도 조건 참조')),
            ('면적 / 형상',c.get('geometry','1D3V 동일 면적 평판, 환산 면적 1 cm²; 실제 지름·측벽 제외')),
            ('표면 / 충돌 모델',c.get('surface_model','흡수 경계, SEE·전자 반사 없음; ground-state Ar MCC')),
            ('격자 / 시간간격 / 입자 가중치',f'{c.get("grid_points","원본 참조")}점 / RF당 {c.get("steps_per_RF",4000)} 전자 step / {c.get("weight","원본 참조")}')]

def render_report(m):
    validate(m);c=m['conditions'];s=m['source']
    lines=[f'# {m["id"]} · {m["title"]}', '',
           f'[전체 실행 목록]({WEB}) · [이 조건군]({WEB}/tree/{m["branch"]})'+
           (f' · [실행 비교]({blob(m["branch"],"results/"+m["id"]+"/README.md")})' if m.get('report_directory') else ''), '',
           f'**{label(m["status"])}** · 실행일 {m["date"]} (한국 시각) · 변경 조건: **{m["changed_conditions"]}**'+
           (f' · 보고서 갱신 {m["report_updated"]}' if m.get('report_updated') else ''), '',
           m.get('summary',''), '', '## 실행 조건', '', '| 항목 | 값 |', '|---|---|']
    lines += [f'| {a} | {escape(b)} |' for a,b in condition_rows(c)]
    lines += [f'| 코드 | {escape(s.get("description","C/eduPIC.cc 계열, C++11 컴파일"))} |',
              f'| 소스 이력 | {escape(s.get("revision","보관된 소스와 manifest 참조"))} |',
              f'| 초기·재시작 상태 | {escape(s.get("initialization","기록 참조"))} |',
              f'| 측정 구간 | {escape(m.get("measurement_note","측정 없음"))} |', '',
              '상태와 그래프는 마지막 저장 자료이며 실시간 CPU 실행 화면은 아닙니다.', '']
    if m.get('setup_image'):lines += [f'![전극 연결]({m["setup_image"]})','']
    if m.get('metrics'):
        lines += ['## 핵심 수치','','| 물리량 | 값 |','|---|---|']
        lines += [f'| {escape(a)} | {escape(b)} |' for a,b in m['metrics']]
        lines.append('')
    if m.get('cases'):
        lines += ['## 조건별 결과','','| V peak | 상태 | 종료 RF | 측정 RF | 평균 전자 밀도 m⁻³ | 보고서 |',
                  '|---:|---|---:|---:|---:|---|']
        for case in m['cases']:
            n=case.get('ne_mean_m3'); n=f'{n:.3e}' if n is not None else '—'
            lines.append(f'| {case["voltage_V"]} | {label(case["status"])} | {case.get("total_rf","—")} | {case.get("measurement_rf",0)} | {n} | [그림·다운로드]({case["path"]}) |')
        lines.append('')
    lines += ['## 자료 범위','','| 진단 | 제공 상태 | 저장·해석 범위 |','|---|---|---|']
    by_id={x['id']:x for x in m['sections']}
    for key,title in STANDARD_SECTIONS:
        sec=by_id.get(key,{})
        state={'available':'자료 있음','partial':'부분 자료','unavailable':'자료 없음'}.get(sec.get('data_status'),'그래프 제공' if sec.get('images') else '상세 설명 참조')
        scope=sec.get('reason') if sec.get('data_status')=='unavailable' else sec.get('availability','저장 자료 없음')
        lines.append(f'| {title} | {state} | {escape(scope)} |')
    lines.append('')
    for sec in m['sections']:
        body=sec.get('text','').strip()
        if sec.get('data_status')=='unavailable':body='**자료 없음:** '+sec['reason']
        if not body and not sec.get('images') and not sec.get('table'):
            body=sec.get('availability') or '저장 자료 없음'
            if m.get('cases'):
                body+='\n\n전압별 상세 보고서: '+' · '.join(f'[{case["voltage_V"]} V]({case["path"]})' for case in m['cases'])
        lines += [f'## {sec.get("title",dict(STANDARD_SECTIONS).get(sec["id"],sec["id"]))}', '',body,'']
        for im in sec.get('images',[]):
            lines += [f'![{im.get("caption",sec["id"])}]({im["path"]})','',im.get('caption',''),'']
        if sec.get('table'):lines += [sec['table'],'']
    lines += ['## 읽는 기준', '',
              '- 위상 그림의 가로축은 RF 위상 t/T, 세로축은 위치 x입니다. 전극 방향은 위 조건표를 따릅니다. 위상 0은 cos 인가 전압의 양의 최댓값입니다.',
              '- Heating은 위상 평균 j × 위상 평균 E입니다. 양수는 전기장에서 입자로, 음수는 반대 방향의 전달입니다. 순간 jE의 평균·온도 상승률과 구분합니다.',
              '- 통계 중단 기준은 전체 물리·격자 오차나 모든 픽셀의 오차를 보증하지 않습니다. 소멸·미완료·짧은 진단을 정상 방전 측정과 구분합니다.',
              '- 전력 표시는 W/m² 또는 W/m³입니다. 실제 전극 면적·회로 없이 발생기 총 W와 동일시하지 않습니다.', '']
    lines += ['## 파일과 재시작', '', '| 자료 | 다운로드 | 크기 |','|---|---|---:|']
    base=m.get('report_directory',f'results/{m["id"]}')
    for d in m.get('downloads',[]):
        path=d['path'];url=raw(m['branch'],base+'/'+path) if path.endswith(('.zip','.pdf','.npz')) else path
        size=file_size(d.get('bytes'))
        lines.append(f'| {escape(d["label"])} | [{Path(path).name}]({url}) | {size} |')
    lines += ['', '[전체 파일 목록·SHA256](files.json)', '']
    if m.get('details'):lines += [f'[기존 상세 기록]({m["details"]})','']
    return '\n'.join(lines).rstrip()+'\n'

def record(m):
    return {k:m[k] for k in ['id','branch','date','title','status','changed_conditions','conditions','cases','summary'] if k in m}

def render_catalog(records,branch):
    all_records=sorted(records,key=lambda m:(m['date'],m['id']),reverse=True)
    visible=[m for m in all_records if m['branch']==branch] if branch.startswith('results/') else all_records
    lines=['# eduPIC 연구 결과 · 실행 목록','',
           '**이 페이지를 북마크하면 실행일·변경 조건으로 결과와 다운로드를 찾을 수 있습니다.**','',
           f'[전체 목록]({WEB}) · [75 mTorr 기본 조건]({WEB}/tree/results/75mTorr) · [20 mTorr 상부 RF]({WEB}/tree/results/20mTorr-topRF) · [실행 코드]({WEB}/tree/{CODE_BRANCH})','']
    if branch=='results/75mTorr':
        lines += ['공통 조건: Ar **75.006 mTorr (원본 10 Pa)**, 350 K, 13.56 MHz, 250 V peak, gap 25 mm. **하부 x=0 RF / 상부 x=L 접지**. 이 조건들은 실행 이름에서 생략합니다.','']
    elif branch=='results/20mTorr-topRF':
        lines += ['공통 조건: Ar **20 mTorr**, 350 K, 13.56 MHz, **상부 RF / 하부 접지**. gap·전압 등 변경한 조건은 각 실행 이름에 표시합니다. 압력 대조 진단은 개별 보고서의 실제 압력을 따릅니다.','']
    elif branch==CODE_BRANCH:
        lines += ['이 브랜치는 **시뮬레이션을 실행·관리하는 코드 작업 브랜치**입니다. 이전 이름의 voltage scan은 전압을 바꿔 독립 계산한다는 뜻입니다.', '',
                  '`C/eduPIC.cc` 계열을 C++11로 컴파일하며, `scripts/voltage_scan/`이 조건별 실행·체크포인트·통계 중단을 관리합니다. 현재 이 브랜치의 solver는 25 mm 설정입니다. 40 mm 실행에 사용한 소스는 해당 결과의 source ZIP에 있습니다.', '',
                  '[컴파일·전압별 실행 설명](scripts/voltage_scan/README.md) · [결과 등록 방법](docs/RESULTS_GUIDE.md)', '']
    else:
        lines += ['`main`은 원본 코드와 전체 결과의 입구, `simulation/*`은 실행 코드, `results/*`은 공통 조건별 결과 보관입니다. GitHub는 저장·열람 장소이며 계산은 클라우드 실행 환경에서 수행합니다.','']
    lines += ['## 실행 기록','','| 실행일 KST | 실행 / 바꾼 조건 | 주요 조건 | 상태 | 결과 |','|---|---|---|---|---|']
    for m in visible:
        c=m['conditions'];p=c.get('pressure_mTorr');p=f'{p:g}' if isinstance(p,(float,int)) else str(p)
        v=c.get('voltage_peak_V',[]);v=v if isinstance(v,list) else [v]
        conditions=f'{p} mTorr · {c.get("gap_mm","—")} mm · {"/".join(str(x) for x in v)} V peak'
        lines.append(f'| {m["date"]} | **{m["id"]}**<br>{escape(m["changed_conditions"])} | {conditions} | {label(m["status"])} | [보고서·그림·파일]({blob(m["branch"],"results/"+m["id"]+"/README.md")}) |')
    if not visible:lines += ['| — | 등록된 실행 없음 | — | — | — |']
    lines += ['', '각 보고서 첫 화면에서 조건표·평균 구간·종료 이유를 확인할 수 있습니다. 소멸·미완료는 정상 방전의 통계 수렴과 다르게 표시합니다.','',
              '## 이후 결과 추가','','새 실행은 `results/YYMMDD_바꾼조건/run.json`과 그래프·자료를 함께 등록합니다. 등록 도구가 보고서와 목록을 갱신하며, GitHub Actions도 결과 push 뒤 전체 목록을 동기화합니다.', '',
              '[파일 이름·보고서·업로드 기준](docs/RESULTS_GUIDE.md) · [전체 결과 점검 기록](docs/RESULT_AUDIT.md) · [브랜치·이름 변경 이력](docs/MIGRATION.md) · [eduPIC 원본 소개·논문·라이선스](docs/UPSTREAM.md)', '']
    return '\n'.join(lines)

def load_local(root):
    return [validate(json.loads(p.read_text())) for p in sorted((root/'results').glob('*/run.json'))]

def refresh_files(directory,meta):
    entries={}
    for p in sorted(directory.rglob('*')):
        if p.is_file() and p.name!='files.json':
            data=p.read_bytes()
            entries[p.relative_to(directory).as_posix()]={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),
                'git_blob':hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()}
    for d in meta.get('downloads',[]):
        if d['path'] not in entries:raise FileNotFoundError(directory/d['path'])
        d.update(entries[d['path']])
    (directory/'files.json').write_text(json.dumps(entries,indent=2,ensure_ascii=False)+'\n')

def render_local(root, branch=None, records=None):
    branch=branch or git('branch','--show-current',cwd=root)
    local=load_local(root)
    for m in local:
        directory=root/'results'/m['id']
        for path in sorted(directory.glob('*/report.json')):
            child=validate(json.loads(path.read_text()));refresh_files(path.parent,child)
            path.write_text(json.dumps(child,ensure_ascii=False,indent=2)+'\n')
            (path.parent/'README.md').write_text(render_report(child))
            refresh_files(path.parent,child)
        refresh_files(directory,m)
        (directory/'run.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n')
        (directory/'README.md').write_text(render_report(m))
        # README is included in the final checksum list, after rendering.
        refresh_files(directory,m)
    records=records if records is not None else local
    (root/'README.md').write_text(render_catalog(records,branch))
    (root/'results').mkdir(exist_ok=True)
    (root/'results/README.md').write_text(render_catalog(records,branch).replace('(docs/','(../docs/').replace('(scripts/','(../scripts/'))
    (root/'results/catalog.json').write_text(json.dumps([record(m) for m in records],ensure_ascii=False,indent=2)+'\n')

def show_json(root,ref,path):
    p=subprocess.run(['git','show',ref+':'+path],cwd=root,text=True,capture_output=True)
    return json.loads(p.stdout) if p.returncode==0 else None

def refs_and_records(root,remote):
    git('fetch','--filter=blob:none','--no-tags',remote,
        f'+refs/heads/main:refs/remotes/{remote}/main',
        f'+refs/heads/results/*:refs/remotes/{remote}/results/*',
        f'+refs/heads/simulation/*:refs/remotes/{remote}/simulation/*',cwd=root)
    refs=git('for-each-ref','--format=%(refname)',f'refs/remotes/{remote}/results/',cwd=root).splitlines()
    records=[];managed=[]
    for ref in refs:
        if show_json(root,ref,'results/family.json') is None:continue
        managed.append(ref.removeprefix(f'refs/remotes/{remote}/'))
        for p in git('ls-tree','-r','--name-only',ref,'results',cwd=root).splitlines():
            if re.fullmatch(r'results/[^/]+/run.json',p):
                m=validate(show_json(root,ref,p))
                if m['branch']!=managed[-1] or p!='results/'+m['id']+'/run.json':
                    raise ValueError('Run metadata differs from its branch/folder: '+p)
                records.append(m)
    ids=[(m['branch'],m['id']) for m in records]
    if len(ids)!=len(set(ids)):raise ValueError('Duplicate run ids')
    return managed,sorted(records,key=lambda m:(m['date'],m['id']))

@contextmanager
def temp_index(root,base):
    with tempfile.TemporaryDirectory(prefix='edupic-catalog-') as tmp:
        env={**os.environ,'GIT_INDEX_FILE':str(Path(tmp)/'index')}
        git('read-tree',base,cwd=root,env=env)
        yield env

def commit_files(root,base,files,message):
    """Change only supplied files, preserving every original data blob and solver file."""
    with temp_index(root,base) as env:
        changed=False
        for path,content in sorted(files.items()):
            safe_path(path)
            data=content.encode() if isinstance(content,str) else content
            oid=subprocess.run(['git','hash-object','-w','--stdin'],input=data,cwd=root,capture_output=True,check=True).stdout.decode().strip()
            old=git('rev-parse',base+':'+path,cwd=root,check=False)
            if old==oid:continue
            changed=True
            git('update-index','--add','--cacheinfo','100644',oid,path,cwd=root,env=env)
        if not changed:return None
        tree=git('write-tree',cwd=root,env=env)
        return git('commit-tree',tree,'-p',base,cwd=root,input=message+'\n')

def refresh_remote_manifests(root,base,files,records,branch):
    """Reuse hashes for unchanged Git blobs; download only new/changed artifacts."""
    inventory={}
    for line in git('ls-tree','-r','--long',base,'results',cwd=root).splitlines():
        header,path=line.split('\t',1);mode,kind,oid,size=header.split()
        if kind=='blob':inventory[path]=(oid,int(size))
    for m in records:
        if m['branch']!=branch:continue
        prefix='results/'+m['id']+'/'
        directories=[prefix]
        for case in m.get('cases',[]):directories.append(prefix+str(PurePosixPath(case['path']).parent)+'/')
        # Transient diagnostic subreports may be linked from prose instead of cases.
        directories+=sorted({str(PurePosixPath(p).parent)+'/' for p in inventory if p.startswith(prefix) and p.endswith('/report.json')})
        for directory in dict.fromkeys(directories):
            old=show_json(root,base,directory+'files.json') or {}
            entries={}
            paths={p for p in inventory if p.startswith(directory)}|{p for p in files if p.startswith(directory)}
            for path in sorted(paths):
                if PurePosixPath(path).name=='files.json':continue
                relative=path[len(directory):];cached=old.get(relative)
                if path in files:
                    content=files[path];data=content.encode() if isinstance(content,str) else content
                elif cached and cached.get('git_blob')==inventory[path][0] and cached['bytes']==inventory[path][1]:
                    entries[relative]=cached;continue
                else:
                    data=subprocess.run(['git','show',base+':'+path],cwd=root,capture_output=True,check=True).stdout
                entries[relative]={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),
                    'git_blob':hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()}
            files[directory+'files.json']=json.dumps(entries,ensure_ascii=False,indent=2)+'\n'

def sync(root,remote='origin',push=False,_attempt=0):
    from audit_coverage import audit
    managed,records=refs_and_records(root,remote)
    branches=['main',*managed]
    if git('rev-parse','--verify',f'refs/remotes/{remote}/{CODE_BRANCH}',cwd=root,check=False):branches.append(CODE_BRANCH)
    changes={}
    for branch in branches:
        base=f'refs/remotes/{remote}/{branch}'
        files={'README.md':render_catalog(records,branch),
               'results/README.md':render_catalog(records,branch).replace('(docs/','(../docs/').replace('(scripts/','(../scripts/'),
               'results/catalog.json':json.dumps([record(m) for m in records],ensure_ascii=False,indent=2)+'\n'}
        for m in records:
            if m['branch']!=branch:continue
            prefix='results/'+m['id']+'/'
            files[prefix+'README.md']=render_report(m)
            errors=audit(m,files[prefix+'README.md'])['failures']
            if errors:raise ValueError(m['id']+': '+'; '.join(errors))
            for path in git('ls-tree','-r','--name-only',base,prefix,cwd=root).splitlines():
                if path.endswith('/report.json'):
                    child=validate(show_json(root,base,path))
                    if child['id']!=m['id'] or child['branch']!=branch:
                        raise ValueError('Child report differs from its run: '+path)
                    text=render_report(child)
                    errors=audit(child,text)['failures']
                    if errors:raise ValueError(path+': '+'; '.join(errors))
                    files[str(PurePosixPath(path).parent)+'/README.md']=text
        refresh_remote_manifests(root,base,files,records,branch)
        commit=commit_files(root,base,files,'Update simulation result catalogs')
        if commit:changes[branch]=commit
    if push and changes:
        try:
            git('push','--atomic',remote,*[sha+':refs/heads/'+branch for branch,sha in changes.items()],cwd=root)
        except subprocess.CalledProcessError:
            if _attempt>=2:raise
            return sync(root,remote,push,_attempt+1)
    return changes

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    render=sub.add_parser('render');render.add_argument('--root',type=Path,default=Path.cwd());render.add_argument('--branch')
    update=sub.add_parser('sync');update.add_argument('--remote',default='origin');update.add_argument('--push',action='store_true')
    args=parser.parse_args()
    if args.command=='render':render_local(args.root.resolve(),args.branch)
    else:print(json.dumps(sync(Path.cwd(),args.remote,args.push),indent=2))

if __name__=='__main__':main()
