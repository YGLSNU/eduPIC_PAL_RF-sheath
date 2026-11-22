"""Validate and export the new five-cycle measurement, with explicit provenance."""
from pathlib import Path
import base64
import hashlib
import html
import json
import os
import re
import shutil
import zipfile

ROOT = Path(__file__).resolve().parent
KEY = ROOT.name
UPLOAD = Path('/workspace/edupic-results-upload')
OUT = UPLOAD/'results'/KEY
OUT.mkdir(parents=True, exist_ok=True)
CSV = OUT/'csv'
CSV.mkdir(exist_ok=True)
os.environ['MPLCONFIGDIR'] = str(ROOT/'.mpl-cache')
os.environ['XDG_CACHE_HOME'] = str(ROOT/'.cache')
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

meta = json.loads((ROOT/'run-metadata.json').read_text())
assert meta['status'] == 'measurement_complete'
assert meta['output_checkpoint']['cycle'] == 1705
info = (ROOT/'info.txt').read_text()
assert 'VIOLATED' not in info
assert re.search(r'cycles in this run\s*=\s*5\b',info)
names = ['pot','efield','ne','ni','je','ji','powere','poweri','meanee','meanei','ioniz']
arrays = {}
for name,shape in {'conv':(1705,3),'density':(400,3),'eepf':(2000,2),'ifed':(200,3),
                   **{n+'_xt':(400,200) for n in names}}.items():
    a = np.loadtxt(ROOT/(name+'.dat'))
    assert a.shape == shape and np.isfinite(a).all(),name
    arrays[name] = a
conv,density,eepf,ifed = [arrays[n] for n in ['conv','density','eepf','ifed']]
assert np.array_equal(conv[:,0],np.arange(1,1706))
assert np.all(conv[:,1:] > 0)
assert np.all(density[:,1:] >= 0)
x = np.linspace(0,.025,400)
# The original density.dat prints coordinates to five decimal places in metres.
assert np.allclose(density[:,0],x,rtol=0,atol=5.1e-6)
assert np.allclose(arrays['ne_xt'].mean(axis=1),density[:,1],rtol=2e-6,atol=1)
assert np.allclose(arrays['ni_xt'].mean(axis=1),density[:,2],rtol=2e-6,atol=1)
eepf_norm = float(np.sum(eepf[:,1]*np.sqrt(eepf[:,0]))*.05)
ifed_norm = ifed[:,1:].sum(axis=0)
assert abs(eepf_norm-1) < 1e-5
assert np.all(abs(ifed_norm-1) < 2e-4)
phase_samples = (np.arange(200)[:,None]*20+np.arange(1,21)[None,:])/4000
expected_voltage = 250*np.cos(2*np.pi*phase_samples).mean(axis=1)
voltage_error = float(np.max(abs(arrays['pot_xt'][0]-expected_voltage)))
assert voltage_error < .02 and np.max(abs(arrays['pot_xt'][-1])) < 1e-9
for particle in ['e','i']:
    assert np.allclose(arrays['power'+particle+'_xt'],arrays['j'+particle+'_xt']*arrays['efield_xt'],rtol=2e-6,atol=.001)
cfl = float(re.search(r'Max e- energy for CFL condition\s*=\s*([\d.eE+-]+)',info)[1])
tail = eepf[eepf[:,0]>=cfl]
tail_max = float(tail[:,1].max())
mean_ion_energy = (ifed[:,:1]*ifed[:,1:]).sum(axis=0)
power_e = float(arrays['powere_xt'].mean())
power_i = float(arrays['poweri_xt'].mean())
stability_patterns = [
    ('plasma_frequency_times_DT_E',r'Plasma frequency @ center \* DT_E\s*=\s*([\d.eE+-]+)',.2),
    ('DX_over_Debye_length',r'DX / Debye length @ center\s*=\s*([\d.eE+-]+)',1.),
    ('max_electron_collision_frequency_times_DT_E',r'Max\. electron coll\. frequency \* DT_E\s*=\s*([\d.eE+-]+)',.05),
    ('max_ion_collision_frequency_times_DT_I',r'Max\. ion coll\. frequency \* DT_I\s*=\s*([\d.eE+-]+)',.05)]
stability = {}
for name,pattern,limit in stability_patterns:
    value = float(re.search(pattern,info)[1])
    assert value < limit
    stability[name] = {'reported_value':value,'limit':limit,'passed':True}
validation = {
    'status':'FIVE_CYCLE_MEASUREMENT_VALIDATED', 'measurement_cycles':[1701,1705],
    'source_sha256':meta['source_sha256'], 'source_unchanged':True,
    'all_arrays_finite_and_expected_shape':True,
    'built_in_stability_conditions':stability,
    'phase_map_shape':[400,200], 'RF_period_ns':1e9/13.56e6,
    'phase_bin_width_ns':1e9/13.56e6/200,
    'physical_measurement_duration_ns':5e9/13.56e6,
    'wall_seconds':meta['wall_seconds'],
    'phase_maps_are_folded_over_five_cycles':True,
    'per_cycle_phase_maps_available':False,
    'center_ne_m-3':float(density[200,1]), 'center_ni_m-3':float(density[200,2]),
    'mean_ion_energy_powered_ground_eV':mean_ion_energy.tolist(),
    'electron_grid_phase_mean_power_W_m-3':power_e,
    'ion_grid_phase_mean_power_W_m-3':power_i,
    'eepf_normalization':eepf_norm,'ifed_normalizations':ifed_norm.tolist(),
    'max_powered_boundary_voltage_error_V':voltage_error,
    'mean_xt_density_matches_density_dat':True,
    'phase_bin_jE_matches_exported_power':True,
    'cfl_energy_eV':cfl, 'center_eepf_max_above_cfl_eV-3/2':tail_max,
    'center_eepf_tail_check_passed':tail_max <= 1e-6,
    'spatial_csv_coordinates':'Reconstructed from L/(N_G-1); original density.dat rounds x to 5 decimal places.',
    'statistical_limit':'Five cycles only; not a replacement for a long measurement or a proof of convergence of all observables.'}
(ROOT/'validation.json').write_text(json.dumps(validation,indent=2)+'\n')

for name,head in [('conv','rf_cycle,electron_superparticles,ion_superparticles'),
                  ('density','position_m,electron_density_m-3,ion_density_m-3'),
                  ('eepf','energy_eV,eepf_eV-3_per_2'),
                  ('ifed','energy_eV,powered_IFEDF_eV-1,grounded_IFEDF_eV-1')]:
    a = arrays[name].copy()
    if name == 'density': a[:,0] = x
    np.savetxt(CSV/(KEY+'_'+name+'.csv'),a,delimiter=',',header=head,comments='',fmt='%.9e')
for name in names:
    np.savetxt(CSV/(KEY+'_'+name+'_xt.csv'),np.column_stack([x,arrays[name+'_xt']]),
               delimiter=',',header='position_m,'+','.join(f'phase_bin_{i:03d}' for i in range(200)),comments='',fmt='%.9e')
np.savetxt(CSV/(KEY+'_phase_coordinates.csv'),np.column_stack([np.arange(200),np.arange(200)/200,
            (np.arange(200)+1)/200,(np.arange(200)*20+10.5)/4000]),delimiter=',',
            header='phase_bin,start_t_over_T,end_t_over_T,sample_mean_t_over_T',comments='',fmt='%.9e')

plt.rcParams.update({'font.size':10,'figure.dpi':160,'axes.spines.top':False,'axes.spines.right':False})
titles = {
    'powere':('Electron power transfer j_e E','kW m$^{-3}$',1000,'RdBu_r'),
    'poweri':('Ion power transfer j_i E','kW m$^{-3}$',1000,'RdBu_r'),
    'ioniz':('Ionization rate','10$^{21}$ m$^{-3}$ s$^{-1}$',1e21,'viridis'),
    'meanee':('Mean electron energy','eV',1,'viridis'),
    'pot':('Potential','V',1,'RdBu_r'),
    'efield':('Electric field','kV m$^{-1}$',1000,'RdBu_r'),
    'ne':('Electron density','10$^{15}$ m$^{-3}$',1e15,'viridis'),
    'ni':('Ion density','10$^{15}$ m$^{-3}$',1e15,'viridis'),
    'je':('Electron current density','A m$^{-2}$',1,'RdBu_r'),
    'ji':('Ion current density','A m$^{-2}$',1,'RdBu_r'),
    'meanei':('Mean ion energy','eV',1,'viridis')}
def map_plot(ax,name):
    title,unit,scale,cmap = titles[name]
    a = arrays[name+'_xt']/scale
    kwargs = {}
    if cmap == 'RdBu_r':
        limit = np.max(abs(a)); kwargs.update(vmin=-limit,vmax=limit)
    im = ax.imshow(a,origin='lower',aspect='auto',interpolation='nearest',extent=[0,1,0,25],cmap=cmap,**kwargs)
    ax.set(xlabel='RF phase t/T',ylabel='Position x (mm)',title=title)
    ax.figure.colorbar(im,ax=ax,label=unit,fraction=.046,pad=.03)

headline = 'Original C code | Ar 10 Pa, 250 V, 13.56 MHz, 25 mm\nCycles 1701-1705: short measurement after particle-count stationarity'
figures = []
with PdfPages(OUT/(KEY+'_all_plots.pdf')) as pdf:
    for name,fields,layout in [
        ('heating',['powere','poweri','ioniz','meanee'],(2,2)),
        ('fields_density',['pot','efield','ne','ni'],(2,2)),
        ('currents_ionenergy',['je','ji','meanei'],(1,3))]:
        fig,axes = plt.subplots(*layout,figsize=(12,8.2) if layout==(2,2) else (14,4.7),layout='constrained')
        for ax,field in zip(np.ravel(axes),fields): map_plot(ax,field)
        fig.suptitle(headline,fontsize=12)
        filename = KEY+'_'+name+'.png'
        fig.savefig(OUT/filename)
        pdf.savefig(fig)
        figures.append((name,filename))
        plt.close(fig)
    fig,axes = plt.subplots(1,3,figsize=(14,4.8),layout='constrained')
    axes[0].plot(x*1000,density[:,1],label='Electrons')
    axes[0].plot(x*1000,density[:,2],label='Ar+ ions')
    axes[0].set(xlabel='Position x (mm)',ylabel='Density (m$^{-3}$)',title='Five-cycle averaged density')
    axes[0].legend(fontsize=8)
    good = eepf[:,1]>0
    axes[1].semilogy(eepf[good,0],eepf[good,1])
    axes[1].axvline(cfl,color='#bd4738',ls='--',label=f'CFL: {cfl:.2f} eV')
    axes[1].axhline(1e-6,color='gray',ls=':',lw=.8)
    axes[1].set(xlabel='Energy (eV)',ylabel='EEPF (eV$^{-3/2}$)',title='EEPF in central 10% of the gap',xlim=(0,45))
    axes[1].legend(fontsize=8)
    axes[2].plot(ifed[:,0],ifed[:,1],label='Powered electrode')
    axes[2].plot(ifed[:,0],ifed[:,2],label='Grounded electrode')
    axes[2].set(xlabel='Ion energy (eV)',ylabel='IFEDF (eV$^{-1}$)',title='Ion flux energy distributions')
    axes[2].legend(fontsize=8)
    for ax in axes: ax.grid(alpha=.18)
    fig.suptitle(headline,fontsize=12)
    filename = KEY+'_distributions.png'
    fig.savefig(OUT/filename); pdf.savefig(fig)
    figures.append(('distributions',filename)); plt.close(fig)
    fig,axes = plt.subplots(1,2,figsize=(12,4.7),layout='constrained')
    for ax in axes:
        ax.plot(conv[:,0],conv[:,1],label='Electrons')
        ax.plot(conv[:,0],conv[:,2],label='Ar+ ions')
        ax.axvspan(1700,1705,color='#308269',alpha=.15,label='New five-cycle measurement')
        ax.set(xlabel='RF cycle',ylabel='Number of superparticles')
        ax.grid(alpha=.18); ax.legend(fontsize=8)
    axes[0].set(title='Initialization and approach to steady state')
    axes[1].set(xlim=(1650,1706),title='Zoom near saved state and new measurement')
    recent = conv[conv[:,0]>=1650,1:]
    axes[1].set_ylim(recent.min()*.997,recent.max()*1.003)
    fig.suptitle(headline,fontsize=12)
    filename = KEY+'_convergence.png'
    fig.savefig(OUT/filename); pdf.savefig(fig)
    figures.append(('convergence',filename)); plt.close(fig)

for name in ['run-metadata.json','validation.json','info.txt','run.log']:
    shutil.copyfile(ROOT/name,OUT/(KEY+'_'+name))
tail_status = '통과' if validation['center_eepf_tail_check_passed'] else '추가 검토 필요'
report = f'''# 수렴 확인 후 5 RF주기 측정 결과

**이번에는 보존된 1,700주기 상태에서 새로 측정한 1,701–1,705주기의 결과입니다.**
중단 직전 2,470주기대의 마지막 5주기를 복원한 데이터가 아니며, 기존에 계획한 1,000주기 측정 결과도 아닙니다.
이 짧은 5주기 실행은 완료됐습니다. 초기 수렴 데이터는 2026-11-17에 생성됐고 새 측정 실행일은 2026-11-18입니다.

## 실행 정보

- 원본 C/eduPIC.cc 수정 없음. 소스 커밋 {meta['source_commit']}.
- Ar 10 Pa, 350 K, 전압 진폭 250 V, 13.56 MHz, 전극 간격 25 mm.
- 격자 400점, RF주기당 4,000단계, 입자 가중치 70,000.
- 측정 범위: 1,701–1,705 RF주기, 물리 시간 {validation['physical_measurement_duration_ns']:.3f} ns.
- 실제 계산 소요 시간: {meta['wall_seconds']:.1f}초.
- 시작/종료(한국 시각): {meta['started_at_Asia_Seoul']} / {meta['completed_at_Asia_Seoul']}.
- 최종 체크포인트: 1,705주기, 전자 {meta['output_checkpoint']['electrons']:,}개·이온 {meta['output_checkpoint']['ions']:,}개 슈퍼입자.

## 주요 값

| 물리량 | 값 |
|---|---|
| 중심 부근 전자 밀도 | {density[200,1]:.5e} m⁻³ |
| 중심 부근 이온 밀도 | {density[200,2]:.5e} m⁻³ |
| 전자 전력밀도: 코드의 격자·위상 평균 | {power_e/1000:.3f} kW/m³ |
| 이온 전력밀도: 코드의 격자·위상 평균 | {power_i/1000:.3f} kW/m³ |
| 평균 이온 입사 에너지: 전원 / 접지 전극 | {mean_ion_energy[0]:.2f} / {mean_ion_energy[1]:.2f} eV |

5주기의 짧은 측정이므로 전극별 비대칭, 고에너지 꼬리, 세부 구조에는 통계 변동이 남습니다.
입자 수 수렴 기준을 통과한 상태에서 시작했다는 의미이며, 모든 물리량의 수렴을 5주기로 새로 입증한 것은 아닙니다.

## RF 위상–위치 그림을 읽는 방법

가로축은 한 RF주기 내의 위상 t/T, 세로축은 전극 사이 위치 x입니다. x=0은 전원 전극, x=25 mm는 접지 전극입니다.
5개 RF주기를 같은 위상에 겹쳐 집계한 맵으로, 주기별 독립 지도 5장이나 5주기 길이의 연속 시간 기록은 아닙니다.
원본 XT 배열은 공간 400점 × 위상 200구간이며 RF주기는 {validation['RF_period_ns']:.3f} ns, 위상 구간 폭은 {validation['phase_bin_width_ns']:.4f} ns입니다.

- heating 그림: 전자·이온 전력 전달, 이온화율, 평균 전자 에너지.
- fields_density 그림: 전위, 전기장, 전자·이온 밀도.
- currents_ionenergy 그림: 전자·이온 전류밀도, 평균 이온 에너지.
- distributions 그림: 5주기 평균 공간 밀도, 중앙 10% EEPF, 전극 입사 IFEDF.
- convergence 그림: 초기부터의 입자 수 이력과 새 측정 구간.

Heating의 단위는 W/m³이며 그림에서는 kW/m³로 표시했습니다. 양수는 전기장으로부터 입자로, 음수는 입자로부터 전기장으로 향하는 전력 전달을 뜻합니다.
원본 코드는 위상 구간별로 집계한 전류밀도와 전기장을 곱해 jE를 계산합니다. 미세 시간단계의 jE를 먼저 계산해 평균한 값과 완전히 동일하다고 가정하면 안 됩니다.
이는 전자 온도 상승률 또는 Ohmic/sheath heating의 성분별 분해 결과가 아닙니다.

## 전체 출력

| 원본 파일 | 의미 | 단위 |
|---|---|---|
| conv.dat | RF주기별 전자·이온 슈퍼입자 수 | 개수 |
| density.dat | 5주기 평균 공간 밀도 | m⁻³ |
| eepf.dat | 중앙 10% 영역의 EEPF | eV⁻³ᐟ² |
| ifed.dat | 전원·접지 전극 IFEDF | eV⁻¹ |
| pot_xt.dat | 전위 | V |
| efield_xt.dat | 전기장 | V/m |
| ne_xt.dat / ni_xt.dat | 전자·이온 밀도 | m⁻³ |
| je_xt.dat / ji_xt.dat | 전자·이온 전류밀도 | A/m² |
| powere_xt.dat / poweri_xt.dat | 전자·이온 전력 전달 jE | W/m³ |
| meanee_xt.dat / meanei_xt.dat | 평균 전자·이온 에너지 | eV |
| ioniz_xt.dat | 이온화율 | m⁻³s⁻¹ |
| info.txt | 조건, 안정성 기준, 플럭스, 평균 에너지·전력 | 파일 내 표기 |
| input-cycle1700.bin / picdata.bin | 입력 1,700주기 / 출력 1,705주기 재시작 상태 | 바이너리 |

## 검증과 파일 사용

원본 코드의 4개 수치 안정성·정확도 조건을 통과했습니다. 모든 결과 배열의 크기와 유한값,
EEPF/IFEDF 정규화, 전극 전위 경계, XT 평균 밀도와 density.dat의 일치, 출력 전력과 bin별 jE 일치를 확인했습니다.
중심 EEPF의 CFL 꼬리 확인: {tail_status} (기준 에너지 {cfl:.3f} eV). 이는 전체 시공간의 에너지 분포를 대체하는 검사는 아닙니다.
자세한 수치는 validation.json에 있습니다.

summary ZIP에는 보고서·그림·전체 그림 PDF·CSV가 있습니다. full ZIP에는 추가로 원본 DAT, 소스, 입력/출력 체크포인트, 실행 로그, 매뉴얼이 들어 있습니다.
csv/의 XT 파일은 첫 열이 위치이고 나머지 200열이 위상 구간입니다. phase_coordinates.csv에 위상 좌표가 있습니다.
원본 density.dat가 위치를 소수점 5자리까지 출력하므로, CSV에서는 코드의 격자식 L/(N_G-1)로 정확한 좌표를 재구성했습니다.
원본 난수 초기화 방식을 유지했으며 RNG 상태는 체크포인트에 보존되지 않습니다. 재실행 시 입자 궤적은 조금씩 달라집니다.

원본 eduPIC: Z. Donko et al., Plasma Sources Science and Technology 30, 095017 (2021), GPLv3.
'''
report_name = KEY+'_report.md'
(OUT/report_name).write_text(report)
embedded = []
for name,filename in figures:
    encoded = base64.b64encode((OUT/filename).read_bytes()).decode()
    embedded.append(f'<h2>{html.escape(name)}</h2><img alt="{html.escape(name)}" src="data:image/png;base64,{encoded}">')
(OUT/(KEY+'_report.html')).write_text('<!doctype html><html lang="ko"><meta charset="utf-8">'
    '<meta name="viewport" content="width=device-width,initial-scale=1"><title>eduPIC 수렴 후 5주기 측정</title>'
    '<style>body{max-width:1200px;margin:30px auto;padding:20px;font:16px/1.7 sans-serif;color:#203342}'
    'img{width:100%}.note{padding:18px;background:#edf4fa;border-left:4px solid #2467ad}'
    'pre{white-space:pre-wrap;overflow-wrap:anywhere;font:15px/1.7 sans-serif}</style>'
    '<h1>수렴 확인 후 5 RF주기 측정 결과</h1><p class="note">1,700주기 저장 상태에서 새로 측정한 '
    '1,701–1,705주기입니다. 각 맵은 5주기를 같은 RF 위상에 모아 집계한 결과이며 장시간 측정 결과가 아닙니다.</p>'
    +''.join(embedded)+'<h2>상세 설명</h2><pre>'+html.escape(report)+'</pre></html>')
for p in [Path(__file__),ROOT/'run_five_cycles.py']:
    shutil.copyfile(p,OUT/(KEY+'_'+p.name))

summary_names = sorted(str(p.relative_to(OUT)) for p in OUT.rglob('*') if p.is_file()
                       and p.suffix not in ['.zip','.sha256'] and p.name!='README.md')
for mode in ['summary','full']:
    archive = OUT/(KEY+'_'+mode+'.zip')
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for name in summary_names: z.write(OUT/name,KEY+'/'+name)
        if mode=='full':
            for p in sorted(ROOT.iterdir()):
                if p.is_file() and p.suffix in ['.dat','.bin','.cc','.json','.txt','.log','.py']:
                    z.write(p,KEY+'/raw/'+p.name)
            z.write('/workspace/eduPIC_PAL_RF-sheath/LICENSE',KEY+'/LICENSE')
            z.write('/workspace/eduPIC_PAL_RF-sheath/C/eduPIC_manual.pdf',KEY+'/eduPIC_manual.pdf')
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None and len(z.namelist())==len(set(z.namelist()))
        if mode=='full':
            assert z.read(KEY+'/raw/picdata.bin')==(ROOT/'picdata.bin').read_bytes()
            assert z.read(KEY+'/raw/input-cycle1700.bin')==(ROOT/'input-cycle1700.bin').read_bytes()
checksums = [(str(p.relative_to(OUT)),hashlib.sha256(p.read_bytes()).hexdigest())
             for p in sorted(OUT.rglob('*')) if p.is_file() and p.suffix!='.sha256' and p.name!='README.md']
(OUT/(KEY+'_checksums.sha256')).write_text(''.join(f'{digest}  {name}\n' for name,digest in checksums))
url = 'https://github.com/YGLSNU/eduPIC_PAL_RF-sheath/raw/refs/heads/results/2026-11-17-default-incomplete/results/'+KEY+'/'
readme = f'''# 2026-11-18: 수렴 확인 후 5 RF주기 측정

**1,700주기 체크포인트에서 새로 측정한 1,701–1,705주기입니다. 이 5주기 실행은 완료됐습니다.**
중단 직전 2,470주기대의 복원 데이터나 1,000주기 장시간 측정 결과가 아닙니다.
원본 C 코드와 기본 물리 조건을 그대로 사용했습니다. 날짜는 새 측정 실행일(한국 시각)입니다.

| 항목 | 값 |
|---|---|
| 조건 | Ar 10 Pa, 350 K, 전압 진폭 250 V, 13.56 MHz, 전극 간격 25 mm |
| 계산 시간 | {meta['wall_seconds']:.1f}초 |
| 중심 부근 전자 밀도 | {density[200,1]:.4e} m⁻³ |
| 평균 전자 / 이온 전력밀도 | {power_e/1000:.3f} / {power_i/1000:.3f} kW/m³ |
| 원본 코드의 안정성 검사 | 4개 기준 통과 |

## 다운로드와 보고서

- [전체 ZIP 다운로드]({url}{KEY}_full.zip): 원본 DAT, 입력/출력 체크포인트, 소스, 로그까지 포함 ({(OUT/(KEY+'_full.zip')).stat().st_size/1e6:.2f} MB).
- [요약 ZIP 다운로드]({url}{KEY}_summary.zip): 보고서, 그림, PDF, 모든 변환 CSV ({(OUT/(KEY+'_summary.zip')).stat().st_size/1e6:.2f} MB).
- [보고서 읽기]({report_name}) / [전체 그림 PDF]({KEY}_all_plots.pdf) / [CSV 폴더](csv/).
- [전체 ZIP 파일 페이지]({KEY}_full.zip) / [요약 ZIP 파일 페이지]({KEY}_summary.zip): 직접 링크가 열리지 않으면 Download raw를 선택하세요.

## Heating과 이온화

각 맵은 5주기를 같은 RF 위상에 모아 집계한 결과입니다. 가로축 t/T, 세로축 전극 사이 위치입니다.
x=0이 전원 전극, x=25 mm가 접지 전극입니다. 양의 jE는 전기장에서 입자로의 전력 전달을 뜻합니다.
Ohmic/sheath heating의 성분별 분해나 전자 온도 상승률은 아닙니다.

![전자·이온 heating, 이온화율, 평균 전자 에너지]({KEY}_heating.png)

## 전위·전기장·밀도

![전위, 전기장, 전자·이온 밀도]({KEY}_fields_density.png)

## 전류와 이온 에너지

![전류밀도와 평균 이온 에너지]({KEY}_currents_ionenergy.png)

## 시간평균 밀도와 에너지 분포

![밀도, EEPF, IFEDF]({KEY}_distributions.png)

5주기는 짧은 통계 표본이므로 세부 분포와 전극별 차이에는 통계 변동이 남습니다.
자세한 파일별 의미, 검증 결과와 실행 범위는 보고서를 참고하세요.
'''
(OUT/'README.md').write_text(readme)
index = UPLOAD/'results/README.md'
old = index.read_text()
row = f'| 2026-11-18 | Ar 10 Pa, 전압 진폭 250 V, 13.56 MHz, 전극 간격 25 mm | 수렴 확인 후 1,701–1,705주기 측정 완료 (5주기 통계) | [결과 폴더]({KEY}/) |\n'
if row not in old:
    old = old.replace('\n파일명 날짜는', '\n'+row+'\n파일명 날짜는')
    old = old.replace('이번','이번')
    # Keep the new dataset row contiguous with the existing Markdown table.
    old = old.replace('|\n\n| 2026-11-18','|\n| 2026-11-18')
    index.write_text(old)
for p in OUT.rglob('*'):
    if p.is_file(): p.chmod(0o644)
print(json.dumps(validation,indent=2))
print('OUTPUT:',OUT)
for p in OUT.glob('*.zip'): print(p.name,p.stat().st_size)
