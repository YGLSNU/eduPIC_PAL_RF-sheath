"""Package preserved eduPIC results for GitHub; does not run the simulation."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import base64
import hashlib
import html
import io
import json
import os
import re
import shutil
import struct
import zipfile

BASE = Path('/workspace/edupic-results')
RUN = BASE/'default-20261117'
PREVIEW = BASE/'preview-cycle-325'
REPO = Path('/workspace/eduPIC_PAL_RF-sheath')
UPLOAD = Path('/workspace/edupic-results-upload')
KEY = '2026-11-17_Ar_10Pa_250V_13.56MHz_25mm'
PREFIX = KEY+'_incomplete'
OUT = UPLOAD/'results'/KEY
OUT.mkdir(parents=True, exist_ok=True)
os.environ['MPLCONFIGDIR'] = str(BASE/'.mpl-cache')
os.environ['XDG_CACHE_HOME'] = str(BASE/'.cache')
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

state = json.loads((RUN/'progress.json').read_text())
before = json.loads((RUN/'convergence-before-measurement.json').read_text())
provenance = json.loads((RUN/'provenance.json').read_text())
checkpoint = (RUN/'picdata.bin').read_bytes()
sim_time, cycle, ne_float = struct.unpack_from('<ddd', checkpoint)
ne = int(ne_float)
electron = np.frombuffer(checkpoint, dtype='<f8', count=4*ne, offset=24).reshape(4, ne)
offset = 24+32*ne
ni = int(struct.unpack_from('<d', checkpoint, offset)[0])
ion = np.frombuffer(checkpoint, dtype='<f8', count=4*ni, offset=offset+8).reshape(4, ni)
assert cycle == 1700 and len(checkpoint) == 32+32*(ne+ni)
assert abs(sim_time-cycle/13.56e6) < 1e-10
assert np.isfinite(electron).all() and np.isfinite(ion).all()
assert (RUN/'source-eduPIC.cc').read_bytes() == (REPO/'C/eduPIC.cc').read_bytes()
complete, trailing = (RUN/'conv.dat').read_bytes().rsplit(b'\n', 1)
conv = np.loadtxt(io.StringIO(complete.decode()))
assert conv.shape[1] == 3
assert np.array_equal(conv[:, 0], np.arange(1, len(conv)+1))
assert np.array_equal(conv[1699, 1:], [ne, ni])
assert np.all(conv[:, 1:] > 0)
log = (RUN/'logs/measurement-01701-02700.log').read_text()
records = re.findall(r'c =\s*(\d+)\s+t =\s*(\d+)\s+#e =\s*(\d+)\s+#i =\s*(\d+)', log)
last_cycle, last_step, last_ne, last_ni = map(int, records[-1])
assert last_cycle == state['active_cycle'] and last_step == state['step']
completed_measurement = last_cycle-1701
assert completed_measurement == 774
assert not (RUN/'density.dat').exists() and not (RUN/'info.txt').exists()
active = []
for proc in Path('/proc').iterdir():
    if not proc.name.isdigit():
        continue
    try:
        args = (proc/'cmdline').read_bytes().split(b'\0')
        names = [Path(a.decode(errors='replace')).name for a in args if a]
        if any(n in ['edupic-native', 'run_reference.py', 'finish_when_ready.py'] for n in names):
            active.append(proc.name)
    except (PermissionError, FileNotFoundError, ProcessLookupError):
        pass
assert not active, active

# Same spatial deposition as the original code, applied to one saved state.
x = np.linspace(0, .025, 400)
dx, weight, area = .025/399, 70000., 1e-4
def density_snapshot(positions):
    assert np.all((positions >= 0) & (positions < .025))
    g = positions/dx
    p = g.astype(int)
    f = g-p
    density = np.bincount(p, weights=1-f, minlength=400)
    density += np.bincount(p+1, weights=f, minlength=400)
    density *= weight/(area*dx)
    density[[0,-1]] *= 2
    recovered = float(np.trapezoid(density, x)*area/weight)
    assert np.isclose(recovered, len(positions), rtol=1e-12)
    return density, recovered
ed, check_ne = density_snapshot(electron[0])
idensity, check_ni = density_snapshot(ion[0])
counts_name = PREFIX+'_particle_counts.csv'
density_name = PREFIX+'_snapshot1700_density.csv'
np.savetxt(OUT/counts_name, conv, delimiter=',', fmt='%d',
           header='RF_cycle,electron_superparticles,ion_superparticles', comments='')
np.savetxt(OUT/density_name, np.column_stack([x, ed, idensity]), delimiter=',',
           header='position_m,electron_density_m-3,ion_density_m-3', comments='')
plt.rcParams.update({'font.size':10, 'axes.spines.top':False, 'axes.spines.right':False})
fig, axes = plt.subplots(1,2,figsize=(12.6,4.9),layout='constrained')
for j,label in enumerate(['Electrons','Ar+ ions']):
    axes[0].plot(conv[:,0],conv[:,j+1],lw=1.2,label=label)
axes[0].axvline(1700,color='#41725b',ls='--',lw=1,label='Saved checkpoint')
axes[0].axvspan(1700,last_cycle,color='#b57920',alpha=.08,label='Interrupted measurement')
axes[0].set(xlabel='RF cycle',ylabel='Number of superparticles',title='Saved particle-count history')
axes[0].ticklabel_format(axis='y',style='sci',scilimits=(0,0))
axes[0].legend(fontsize=8)
axes[1].plot(x*1000,ed,label='Electrons',lw=1)
axes[1].plot(x*1000,idensity,label='Ar+ ions',lw=1)
axes[1].set(xlabel='Position x (mm)',ylabel='Instantaneous density (m$^{-3}$)',
            title='Checkpoint at cycle 1700: single snapshot')
axes[1].legend(fontsize=8)
for ax in axes:
    ax.grid(alpha=.18)
fig.suptitle('INCOMPLETE RUN | Ar 10 Pa, 250 V, 13.56 MHz, 25 mm\n'
             'Particle-count stationarity passed; 1000-cycle averaged diagnostics are unavailable',fontsize=12)
for ext in ['png','pdf']:
    fig.savefig(OUT/(PREFIX+'_overview.'+ext),dpi=160)
plt.close(fig)
for ext in ['png','pdf']:
    shutil.copyfile(RUN/'plots'/('stationarity_before_measurement.'+ext),
                    OUT/(PREFIX+'_stationarity1700.'+ext))

now = datetime.now(ZoneInfo('Asia/Seoul')).isoformat(timespec='seconds')
last_time = datetime.fromisoformat(state['updated_utc']).astimezone(ZoneInfo('Asia/Seoul'))
audit = {
    'dataset_id':KEY, 'filename_date_basis':'Simulation start date in Asia/Seoul',
    'prepared_at_Asia_Seoul':now,
    'status':'INCOMPLETE_NO_ACTIVE_PROCESS_IN_CURRENT_ENVIRONMENT',
    'source_repository':provenance['repository'], 'source_commit':provenance['commit'],
    'source_implementation':'C/eduPIC.cc', 'source_unchanged':True,
    'source_sha256':hashlib.sha256((RUN/'source-eduPIC.cc').read_bytes()).hexdigest(),
    'parameters':provenance['parameters'],
    'measurement_requested_cycles':1000,
    'measurement_completed_full_cycles_per_log':completed_measurement,
    'last_logged_cycle_and_step':[last_cycle,last_step],
    'last_log_time_Asia_Seoul':last_time.isoformat(),
    'last_logged_electron_ion_counts':[last_ne,last_ni],
    'restart_checkpoint_cycle':int(cycle),
    'restart_checkpoint_electron_ion_counts':[ne,ni],
    'restart_checkpoint_sha256':hashlib.sha256(checkpoint).hexdigest(),
    'checkpoint_structure_valid':True,
    'saved_complete_convergence_rows':len(conv),
    'trailing_incomplete_conv_bytes_preserved':trailing.decode(),
    'particle_stationarity_before_measurement':before,
    'density_snapshot_is_time_averaged':False,
    'density_snapshot_integrated_superparticle_counts':[check_ne,check_ni],
    'main_run_final_measurement_outputs_available':False,
    'included_early_preview_cycles':[326,330],
    'early_preview_is_converged':False,
    'estimated_restart_measurement_hours':1000*state['average_seconds_per_cycle']/3600,
}
(OUT/(PREFIX+'_manifest.json')).write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n')
span = np.array(before['relative_block_span'])*100
drift = np.array(before['relative_fitted_drift'])*100
report = f'''# eduPIC 결과 기록 — 미완료

**이 자료는 최종 1,000주기 측정 결과가 아닙니다. 현재 환경에서 계산은 실행 중이 아닙니다.**

파일명의 날짜는 한국 시각 기준 실행 시작일(2026-11-17)입니다. 결과 정리 시각은 {now}입니다.
원본 C/eduPIC.cc를 수정 없이 실행했습니다. 소스 커밋: {provenance['commit']}.

## 조건과 실행 상태

| 항목 | 값 또는 상태 |
|---|---|
| 가스·압력·온도 | Ar, 10 Pa, 350 K |
| 구동 전압·주파수 | 전압 진폭 250 V, 13.56 MHz |
| 전극 간격 | 25 mm |
| 공간 격자·시간 간격 | 400점, RF주기당 4,000단계 |
| 슈퍼입자 가중치 | 70,000 |
| 입자 수 수렴 확인 | 1,700주기에서 통과 |
| 구간 평균 입자 수 차이 | 전자 {span[0]:.3f}%, 이온 {span[1]:.3f}% (기준 1% 미만) |
| 최근 600주기 선형 추세 변화 | 전자 {drift[0]:.3f}%, 이온 {drift[1]:.3f}% (기준 2% 미만) |
| 장시간 측정 | 1,000주기 중 774주기까지 진행한 로그가 있으나 최종 진단 파일 없음 |
| 마지막 로그 | {last_time.strftime('%Y-%m-%d %H:%M:%S')} 한국 시각, 누적 2,475주기 시작 |
| 저장된 재시작 상태 | 1,700주기, 전자 {ne:,}개·이온 {ni:,}개 슈퍼입자 |

수렴은 최근 600주기를 세 개의 200주기 구간으로 나누어 평균과 추세를 비교한 입자 수 안정성 판정입니다.
모든 물리량의 수렴이나 수치 정확도가 검증됐다는 뜻은 아닙니다.

## 확인 가능한 결과

- overview 그림의 왼쪽은 디스크에 남은 1–{len(conv):,}주기의 입자 수 기록입니다.
- 오른쪽은 1,700주기 체크포인트에서 재구성한 **순간 밀도**입니다. 1,000주기 시간평균 밀도가 아닙니다.
- 순간 밀도는 원본의 400점 격자, 선형 입자 보간, 경계점 보정을 적용했습니다. 공간 적분한 입자 수가 체크포인트와 일치함을 확인했습니다.
- x=0은 전원 전극, x=25 mm는 접지 전극입니다. 이 한 시점에서 중앙부 전자·이온 밀도는 비슷하고 접지 전극 부근에서 전자 밀도가 감소합니다.
- particle_counts.csv는 입자 수 기록, snapshot1700_density.csv는 위치(m)·전자 밀도(m⁻³)·이온 밀도(m⁻³)이며 Excel에서 열 수 있습니다.
- full ZIP의 early_preview/는 326–330주기를 별도로 측정한 수렴 전 5주기 예비 결과입니다. 최종 결과로 사용할 수 없습니다.

## 기록을 해석할 때 주의할 점

원본 코드는 요청된 측정 실행 전체가 끝난 뒤 입자 데이터와 진단 파일을 저장합니다.
환경 교체 후 현재 확인되는 것은 보존된 파일이며, 실행 중이던 프로세스와 측정 누적값은 이어지지 않았습니다.
main_run/progress.json의 measurement는 마지막으로 기록된 과거 상태입니다.
원본 conv.dat에는 출력 버퍼 때문에 2,406주기까지의 완전한 행과 불완전한 다음 행만 남아 있습니다.
CSV에는 완전한 행만 변환했으며 원본 파일은 full ZIP에 그대로 보관했습니다.
주 실행의 info.txt, density.dat, eepf.dat, ifed.dat, XT 분포 및 최종 안정성 검증 결과는 없습니다.
저장소의 ReferenceCase_RawData는 저자 제공 예제이므로 이번 계산 자료에 섞지 않았습니다.

## 복구 기준

1,700주기 체크포인트에서 측정 1,000주기를 다시 실행할 수 있습니다.
이전 측정의 누적값이 저장되지 않아 남은 226주기만 실행해 기존 측정을 복원할 수는 없습니다.
이전 속도 기준 측정 예상 시간은 약 {audit['estimated_restart_measurement_hours']:.2f}시간입니다.
재실행 시 별도 폴더에 picdata.bin과 원본 소스를 복사하고, conv.dat는 1–1,700주기만 복사한 뒤 실행해야 합니다.
원본 난수 상태는 체크포인트에 저장되지 않아 재시작 이후의 개별 입자 궤적은 이전 실행과 다릅니다.
이번 패키징에서는 시뮬레이션을 재실행하지 않았습니다.

## 출처

원본 eduPIC: Z. Donko et al., Plasma Sources Science and Technology 30, 095017 (2021), GPLv3.
full ZIP에는 원본 소스, 라이선스, 매뉴얼과 로그를 포함했습니다.
'''
report_name = PREFIX+'_report.md'
(OUT/report_name).write_text(report)
png_name = PREFIX+'_overview.png'
encoded = base64.b64encode((OUT/png_name).read_bytes()).decode()
web = ('<!doctype html><html lang="ko"><meta charset="utf-8">'
       '<meta name="viewport" content="width=device-width,initial-scale=1">'
       '<title>eduPIC 2026-11-17 — 미완료 결과 기록</title><style>'
       'body{max-width:1150px;margin:32px auto;padding:18px;font:16px/1.7 sans-serif;color:#203342}'
       'img{width:100%}.notice{padding:18px;background:#fff3db;border-left:5px solid #a96b11}'
       'pre{white-space:pre-wrap;overflow-wrap:anywhere;font:15px/1.7 sans-serif}</style>'
       '<h1>eduPIC — 남아 있는 결과 기록</h1><p class="notice">'
       '<strong>미완료 실행입니다.</strong> 1,700주기 입자 수 수렴은 확인됐지만 장시간 측정의 최종 분포는 저장되지 않았습니다. '
       '아래 오른쪽 그림은 1,700주기의 순간 밀도입니다.</p>'
       f'<img alt="입자 수 변화와 순간 밀도" src="data:image/png;base64,{encoded}">'
       '<pre>'+html.escape(report)+'</pre></html>')
(OUT/(PREFIX+'_report.html')).write_text(web)
shutil.copyfile(Path(__file__), OUT/(PREFIX+'_postprocess.py'))

summary_names = sorted(p.name for p in OUT.iterdir() if p.is_file() and p.suffix != '.zip' and p.name != 'README.md' and p.suffix != '.sha256')
summary_zip = OUT/(PREFIX+'_summary.zip')
full_zip = OUT/(PREFIX+'_full.zip')
for archive in [summary_zip,full_zip]:
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for name in summary_names:
            z.write(OUT/name, KEY+'/'+name)
        if archive == full_zip:
            for p in sorted(RUN.iterdir()):
                if p.is_file() and p.suffix in ['.dat','.json','.jsonl','.cc','.md','.bin','.log','.py']:
                    z.write(p,KEY+'/main_run/'+p.name)
            for p in sorted((RUN/'logs').glob('*.log')):
                z.write(p,KEY+'/main_run/logs/'+p.name)
            z.writestr(KEY+'/main_run/README.md',
                       '# Historical run records\n\nThis run is incomplete and is not running. '
                       'progress.json is a historical record. picdata.bin contains cycle 1700. '
                       'conv.dat has complete rows through cycle 2406 and a truncated trailing line. '
                       'Keep these originals unchanged; use a separate folder for any restart.\n')
            for p in sorted(PREVIEW.iterdir()):
                if p.is_file() and p.suffix in ['.dat','.csv','.png','.pdf','.json','.txt','.log']:
                    z.write(p,KEY+'/early_preview/'+p.name)
            z.writestr(KEY+'/early_preview/README.md',
                       '# 수렴 전 예비 데이터\n\n326–330주기, 별도의 5주기 측정입니다. 정상상태 최종 결과가 아닙니다.\n')
            z.write(REPO/'LICENSE',KEY+'/LICENSE')
            z.write(REPO/'C/eduPIC_manual.pdf',KEY+'/eduPIC_manual.pdf')
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        assert len(z.namelist()) == len(set(z.namelist()))
        assert z.read(KEY+'/'+density_name) == (OUT/density_name).read_bytes()
        if archive == full_zip:
            assert z.read(KEY+'/main_run/picdata.bin') == checkpoint

checksums = {p.name:hashlib.sha256(p.read_bytes()).hexdigest()
             for p in sorted(OUT.iterdir()) if p.is_file() and p.suffix != '.sha256' and p.name != 'README.md'}
(OUT/(PREFIX+'_checksums.sha256')).write_text(''.join(f'{sha}  {name}\n' for name,sha in checksums.items()))
download_base = 'https://github.com/YGLSNU/eduPIC_PAL_RF-sheath/raw/refs/heads/results/2026-11-17-default-incomplete/results/'+KEY+'/'
readme = f'''# {KEY}

**미완료 실행 자료입니다.** 원본 C 버전의 기본 조건으로 1,700주기 입자 수 수렴을 확인했지만,
1,000주기 측정은 완료되지 않았습니다. 마지막 로그는 774주기 측정 후 누적 2,475주기 시작입니다.
보존된 재시작 데이터는 1,700주기 상태입니다. 현재 시뮬레이션은 실행 중이 아닙니다.

## 다운로드

| 자료 | 링크 | 크기 |
|---|---|---|
| 요약 ZIP: 보고서, 그림, CSV | [요약 ZIP 다운로드]({download_base}{summary_zip.name}) | {summary_zip.stat().st_size/1e6:.2f} MB |
| 전체 ZIP: 요약 + 원본 로그, 재시작 데이터, 소스, 예비 결과, 매뉴얼 | [전체 ZIP 다운로드]({download_base}{full_zip.name}) | {full_zip.stat().st_size/1e6:.2f} MB |

직접 다운로드가 열리지 않으면 아래 파일 페이지에서 Download raw(다운로드 아이콘)를 선택하세요.

- [요약 ZIP 파일 페이지]({summary_zip.name})
- [전체 ZIP 파일 페이지]({full_zip.name})
- [보고서 바로 읽기]({report_name})
- [순간 밀도 CSV]({density_name}) / [입자 수 CSV]({counts_name})

![입자 수 기록과 1,700주기 순간 밀도]({png_name})

오른쪽 그림은 **단일 시점의 밀도이며 시간평균 결과가 아닙니다.**
ZIP을 풀고 이름이 report.html로 끝나는 파일을 브라우저에서 열면 그림과 설명을 함께 볼 수 있습니다.
CSV는 Excel에서 열 수 있습니다. 자세한 상태와 복구 기준은 보고서에 있습니다.

## 이름과 조건

파일명 형식: 날짜_가스_압력_전압진폭_주파수_전극간격_상태_자료종류.확장자

- 날짜 2026-11-17은 한국 시각 기준 실제 실행 시작일입니다.
- Ar, 10 Pa, 250 V(진폭), 13.56 MHz, 25 mm. 그 외 기본 조건: 350 K, 격자 400점, RF주기당 4,000단계.
- incomplete는 미완료 자료를 뜻합니다. summary는 요약, full은 전체 보관용입니다.
- early_preview/는 수렴 전 326–330주기의 별도 예비 측정이며 최종 데이터가 아닙니다.
- 자료 정리 시각: {now}. 원본 소스 버전: {provenance['commit']}.
- ZIP 내부 원본 파일명은 원래 실행 기록과의 대응을 위해 유지했습니다.
- 파일 무결성은 이름이 checksums.sha256로 끝나는 파일로 확인할 수 있습니다.
'''
(OUT/'README.md').write_text(readme)
index = UPLOAD/'results/README.md'
index.write_text(f'''# eduPIC 실행 결과

실행일과 핵심 물리 조건으로 결과를 구분합니다. 각 폴더의 README에서 보고서와 다운로드 링크를 확인하세요.

| 실행일 (한국 시각) | 조건 | 상태 | 자료 |
|---|---|---|---|
| 2026-11-17 | Ar 10 Pa, 전압 진폭 250 V, 13.56 MHz, 전극 간격 25 mm | 미완료: 수렴 1,700주기 확인, 최종 측정 분포 없음 | [결과 폴더]({KEY}/) |

파일명 날짜는 결과를 정리하거나 업로드한 날짜가 아니라 실제 실행 시작일입니다.
''')
for p in OUT.iterdir():
    if p.is_file(): p.chmod(0o644)
print(json.dumps({'output':str(OUT),'files':len(list(OUT.iterdir())),
                 'summary_bytes':summary_zip.stat().st_size,'full_bytes':full_zip.stat().st_size,
                 'source_sha256':audit['source_sha256'],'checkpoint_sha256':audit['restart_checkpoint_sha256']},indent=2))
