"""Summarize completed blocks without changing any original eduPIC outputs."""
from pathlib import Path
import argparse
import base64
import html
import json
import os
import re
import shutil
import zipfile
import numpy as np
os.environ.setdefault('MPLCONFIGDIR', '/workspace/edupic-results/.mpl-cache')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from scipy.stats import t as student_t
from adaptive_common import ROOT, KEY, X, XT, SOURCE_SHA, sha, save_json, checkpoint, complete_blocks, read_arrays, assess

LABELS = {
    'pot': ('Potential','V',1,'RdBu_r'),
    'efield': ('Electric field','kV m$^{-1}$',1e3,'RdBu_r'),
    'ne': ('Electron density','10$^{15}$ m$^{-3}$',1e15,'viridis'),
    'ni': ('Ion density','10$^{15}$ m$^{-3}$',1e15,'viridis'),
    'je': ('Electron current density','A m$^{-2}$',1,'RdBu_r'),
    'ji': ('Ion current density','A m$^{-2}$',1,'RdBu_r'),
    'powere': ('Electron power transfer: binned j_e E','kW m$^{-3}$',1e3,'RdBu_r'),
    'poweri': ('Ion power transfer: binned j_i E','kW m$^{-3}$',1e3,'RdBu_r'),
    'meanee': ('Mean electron energy','eV',1,'viridis'),
    'meanei': ('Mean ion energy','eV',1,'viridis'),
    'ioniz': ('Ionization rate','10$^{21}$ m$^{-3}$ s$^{-1}$',1e21,'viridis')}
KOREAN = {
    'mean_density_e':'공간평균 전자 밀도','mean_density_i':'공간평균 이온 밀도',
    'center_density_e':'중앙 10% 전자 밀도','center_density_i':'중앙 10% 이온 밀도',
    'mean_power_e':'평균 전자 전력밀도','mean_power_i':'평균 이온 전력밀도',
    'density_profile_e':'전자 밀도 공간분포','density_profile_i':'이온 밀도 공간분포',
    'heating_map_e':'전자 heating 맵','heating_map_i':'이온 heating 맵'}

def pooled_arrays(arrays):
    """Linear quantities and particle-weighted energies can be reconstructed from exported grids."""
    stacks = {name:np.array([a[name] for a in arrays]) for name in XT}
    pooled = {name:v.mean(axis=0) for name,v in stacks.items()}
    differences = {}
    for s in ['e','i']:
        pooled['power'+s+'_mean_of_blocks'] = pooled['power'+s].copy()
        pooled['power'+s] = pooled['j'+s]*pooled['efield']
        num = (stacks['meane'+s]*stacks['n'+s]).sum(axis=0)
        den = stacks['n'+s].sum(axis=0)
        pooled['meane'+s] = np.divide(num,den,out=np.zeros_like(num),where=den>0)
        differences[s] = dict(pooled_binned_jE_grid_mean_W_m3=float(pooled['power'+s].mean()),
                              mean_of_block_jE_grid_mean_W_m3=float(pooled['power'+s+'_mean_of_blocks'].mean()),
                              relative_global_difference=float(abs(pooled['power'+s+'_mean_of_blocks'].mean()-pooled['power'+s].mean())/abs(pooled['power'+s].mean())))
    pooled['density'] = np.column_stack([X,pooled['ne'].mean(axis=1),pooled['ni'].mean(axis=1)])
    # Raw energy-histogram sample counts are not exported by the unchanged code.
    # Clearly distinguish these equal-duration block PDF averages from pooled event histograms.
    pooled['eepf_equal_block_mean'] = np.mean([a['eepf'] for a in arrays],axis=0)
    pooled['ifed_equal_block_mean'] = np.mean([a['ifed'] for a in arrays],axis=0)
    return pooled, stacks, differences

def export_csv(out, pooled, history):
    csv = out/'csv'; csv.mkdir(exist_ok=True)
    raw = out/'aggregate_dat'; raw.mkdir(exist_ok=True)
    for name in XT+['powere_mean_of_blocks','poweri_mean_of_blocks']:
        a = pooled[name]
        np.savetxt(raw/(KEY+'_'+name+'_xt.dat'),a,fmt='%.9e')
        np.savetxt(csv/(KEY+'_'+name+'_xt.csv'),np.column_stack([X,a]),delimiter=',',comments='',fmt='%.9e',
                   header='position_m,'+','.join(f'phase_bin_{i:03d}' for i in range(200)))
    tabular = [('density',pooled['density'],'position_m,electron_density_m-3,ion_density_m-3'),
               ('eepf_equal_block_mean',pooled['eepf_equal_block_mean'],'energy_eV,equal_block_mean_EEPF_eV-3_per_2'),
               ('ifed_equal_block_mean',pooled['ifed_equal_block_mean'],'energy_eV,equal_block_mean_IFEDF_powered_eV-1,equal_block_mean_IFEDF_grounded_eV-1'),
               ('particle_counts',history,'RF_cycle,electron_superparticles,ion_superparticles')]
    for name,a,header in tabular:
        np.savetxt(csv/(KEY+'_'+name+'.csv'),a,delimiter=',',header=header,comments='',fmt='%.9e')
        np.savetxt(raw/(KEY+'_'+name+'.dat'),a,fmt='%.9e')
    np.savetxt(csv/(KEY+'_phase_coordinates.csv'),np.column_stack([np.arange(200),np.arange(200)/200,
                (np.arange(200)+1)/200,(np.arange(200)*20+10.5)/4000]),delimiter=',',comments='',
                header='phase_bin,start_t_over_T,end_t_over_T,sample_mean_t_over_T',fmt='%.9e')

def draw_maps(out, pooled, ncycles, last, state, blocks, arrays, history, assessments, final_assess):
    plt.rcParams.update({'font.size':10,'figure.dpi':155,'axes.spines.top':False,'axes.spines.right':False})
    figures=[]
    title = f'Ar 10 Pa | 250 V peak | 13.56 MHz | 25 mm | Original C source\nRF cycles 1706-{last}: {ncycles} measured cycles, {len(blocks)} consecutive blocks'
    def plot(ax,name):
        label,unit,scale,cmap=LABELS[name]
        a=pooled[name]/scale
        extra={}
        if cmap=='RdBu_r':
            lim=float(abs(a).max()); extra=dict(vmin=-lim,vmax=lim)
        im=ax.imshow(a,origin='lower',aspect='auto',extent=[0,1,0,25],interpolation='nearest',cmap=cmap,**extra)
        ax.set(xlabel='RF phase t/T',ylabel='Position x (mm)',title=label)
        ax.figure.colorbar(im,ax=ax,label=unit,fraction=.047,pad=.03)
    def finish(fig,name,pdf):
        fig.suptitle(title,fontsize=12)
        file=KEY+'_'+name+'.png';fig.savefig(out/file);pdf.savefig(fig);plt.close(fig)
        figures.append((name,file))
    with PdfPages(out/(KEY+'_all_plots.pdf')) as pdf:
        for group,names,layout in [
            ('heating',['powere','poweri','ioniz','meanee'],(2,2)),
            ('fields_density',['pot','efield','ne','ni'],(2,2)),
            ('currents_ionenergy',['je','ji','meanei'],(1,3))]:
            fig,axs=plt.subplots(*layout,figsize=(12,8.2) if layout==(2,2) else (14,4.8),layout='constrained')
            for ax,name in zip(np.ravel(axs),names):plot(ax,name)
            finish(fig,group,pdf)
        fig,axs=plt.subplots(1,3,figsize=(14,4.8),layout='constrained')
        for i,label,c in [(1,'Electrons','#2764ad'),(2,'Ar+ ions','#cb6c2b')]:
            axs[0].plot(X*1000,pooled['density'][:,i]/1e15,label=label,color=c)
        axs[0].set(xlabel='Position (mm)',ylabel='Density (10$^{15}$ m$^{-3}$)',title='Time-averaged density')
        axs[0].legend()
        eepf=pooled['eepf_equal_block_mean'];mask=eepf[:,1]>0
        axs[1].semilogy(eepf[mask,0],eepf[mask,1],label='Equal-block mean PDF')
        axs[1].axvline(32.834,color='#b2453b',ls='--',label='CFL energy')
        axs[1].set(xlabel='Energy (eV)',ylabel='EEPF (eV$^{-3/2}$)',xlim=(0,45),title='Central 10% EEPF')
        axs[1].legend(fontsize=8)
        ifed=pooled['ifed_equal_block_mean']
        axs[2].plot(ifed[:,0],ifed[:,1],label='Powered')
        axs[2].plot(ifed[:,0],ifed[:,2],label='Grounded')
        axs[2].set(xlabel='Ion energy (eV)',ylabel='IFEDF (eV$^{-1}$)',title='Equal-block mean ion flux energy PDF')
        axs[2].legend()
        for ax in axs:ax.grid(alpha=.2)
        finish(fig,'distributions',pdf)
        fig,axs=plt.subplots(2,2,figsize=(12,8),layout='constrained')
        for ax in axs[0]:
            ax.plot(history[:,0],history[:,1],label='Electrons')
            ax.plot(history[:,0],history[:,2],label='Ar+ ions')
            ax.axvspan(1705,last,color='#29806c',alpha=.13)
            ax.set(xlabel='RF cycle',ylabel='Superparticles');ax.legend(fontsize=8);ax.grid(alpha=.2)
        axs[0,0].set(title='Full connected trajectory')
        axs[0,1].set(xlim=(1650,last+5),title='Saved state and new measurement')
        subset=history[history[:,0]>=1650,1:]
        axs[0,1].set_ylim(float(subset.min())*.998,float(subset.max())*1.002)
        mid=np.array([np.mean(json.loads((p/'block.json').read_text())['cycles_inclusive']) for p in blocks])
        for s,label in [('e','Electrons'),('i','Ar+ ions')]:
            block_power=np.array([a['power'+s].mean() for a in arrays])/1e3
            axs[1,0].plot(mid,block_power,'o-',label=label)
        axs[1,0].set(xlabel='Block midpoint (RF cycle)',ylabel='Mean jE (kW m$^{-3}$)',title='20-cycle block powers (not pooled jE)')
        axs[1,0].legend();axs[1,0].grid(alpha=.2)
        history_stats=[q for q in assessments if 'indicators' in q]
        for prefix,label in [('mean_power_e','Electron power'),('heating_map_e','Electron heating map'),('heating_map_i','Ion heating map')]:
            axs[1,1].plot([q['measurement_cycles'] for q in history_stats],
                          [q['indicators'][prefix]['relative_uncertainty_indicator']*100 for q in history_stats],
                          'o-',label=label)
        axs[1,1].axhline(3,color='gray',ls='--',lw=.8,label='3% scalar target')
        axs[1,1].axhline(5,color='gray',ls=':',lw=.8,label='5% map target')
        axs[1,1].set(xlabel='Additional measured cycles',ylabel='Uncertainty indicator (%)',title='Approximate statistical indicators')
        axs[1,1].legend(fontsize=7);axs[1,1].grid(alpha=.2)
        finish(fig,'convergence',pdf)
        if 'indicators' in final_assess:
            keys=list(final_assess['indicators'])
            fig,ax=plt.subplots(figsize=(11,5.5),layout='constrained')
            xx=np.arange(len(keys));w=.37
            ax.bar(xx-w/2,[final_assess['indicators'][k]['relative_uncertainty_indicator']*100 for k in keys],w,label='Uncertainty indicator')
            ax.bar(xx+w/2,[final_assess['indicators'][k]['first_last_half_relative_change']*100 for k in keys],w,label='First/last-half change')
            for j,k in enumerate(keys):
                lim=100*final_assess['indicators'][k]['tolerance'];ax.plot([j-.46,j+.46],[lim,lim],color='black',lw=1.6)
            ax.set_xticks(xx,[k.replace('_','\n') for k in keys],fontsize=8)
            ax.set(ylabel='Relative indicator (%)',title='Black marks: stopping targets; not certified total error')
            ax.legend();ax.grid(axis='y',alpha=.2)
            finish(fig,'stopping_criteria',pdf)
    return figures

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--preview',action='store_true');args=parser.parse_args()
    state=json.loads((ROOT/'status.json').read_text())
    if not args.preview:
        assert state['status'] in ['criteria_met','measurement_limit_reached','paused_at_checkpoint'], state
    blocks=complete_blocks();assert blocks
    out=ROOT/('preview_output' if args.preview else 'final_output');out.mkdir(exist_ok=True)
    arrays=[read_arrays(p) for p in blocks]
    pooled,stacks,difference=pooled_arrays(arrays)
    history=np.concatenate([np.loadtxt(ROOT/'history_through1705.dat')]+[a['conv'] for a in arrays])
    last=checkpoint(blocks[-1]/'picdata.bin')['cycle'];ncycles=len(blocks)*20
    assert np.array_equal(history[:,0],np.arange(1,last+1))
    assert sha(ROOT/'source-eduPIC.cc')==SOURCE_SHA
    report_assess=assess()
    if not args.preview:
        assert report_assess==json.loads((ROOT/'assessment.json').read_text())
        if state['status']=='criteria_met':
            assert report_assess['passed'] and state['consecutive_passes']>=2
    history_assess=[json.loads(line) for line in (ROOT/'assessments.jsonl').read_text().splitlines()]
    export_csv(out,pooled,history)
    figures=draw_maps(out,pooled,ncycles,last,state,blocks,arrays,history,history_assess,report_assess)
    block_meta=[json.loads((p/'block.json').read_text()) for p in blocks]
    validations=[json.loads((p/'validation.json').read_text()) for p in blocks]
    eepf=pooled['eepf_equal_block_mean'];ifed=pooled['ifed_equal_block_mean']
    energy=(ifed[:,:1]*ifed[:,1:]).sum(axis=0)
    phase=np.arange(200)*20/4000+10.5/4000
    verror=float(np.max(abs(pooled['pot'][0]-250*np.cos(2*np.pi*phase)*np.sinc(20/4000))))
    assert verror<.002
    assert np.max(abs(pooled['pot'][-1]))<1e-8
    for s,col in [('e',1),('i',2)]:
        density_mean=np.mean([a['density'][:,col] for a in arrays],axis=0)
        assert np.allclose(density_mean,pooled['density'][:,col],rtol=2e-6)
        assert np.allclose(pooled['power'+s],pooled['j'+s]*pooled['efield'])
    validation=dict(status=state['status'], source_unchanged=True, source_sha256=SOURCE_SHA,
                    all_blocks_validated=True, blocks=len(blocks), cycles_inclusive=[1706,last],
                    measurement_cycles=ncycles, phase_grid_shape=[400,200], criterion_map_shape=[40,40],
                    each_block_stability_passed=all(all(q['passed'] for q in v['stability'].values()) for v in validations),
                    phase_mean_density_consistent=True, pooled_power_definition_consistent=True,
                    max_boundary_voltage_error_V=verror,
                    eepf_equal_block_mean_normalization=float(np.sum(eepf[:,1]*np.sqrt(eepf[:,0]))*.05),
                    ifed_equal_block_mean_normalizations=ifed[:,1:].sum(axis=0).tolist(),
                    center_eepf_max_above_cfl=float(eepf[eepf[:,0]>=32.834,1].max()),
                    center_eepf_tail_threshold=1e-6,
                    mean_ion_energy_equal_block_mean_powered_grounded_eV=energy.tolist(),
                    center_grid_index200_density_m3=pooled['density'][200,1:].tolist(),
                    power_aggregation_comparison=difference,
                    initial_checkpoint=checkpoint(ROOT/'input-cycle1705.bin'),final_checkpoint=checkpoint(blocks[-1]/'picdata.bin'),
                    wall_solver_seconds=sum(b['wall_seconds'] for b in block_meta),
                    started_at_Asia_Seoul=block_meta[0]['started_at_Asia_Seoul'],
                    completed_at_Asia_Seoul=block_meta[-1]['completed_at_Asia_Seoul'],
                    aggregation_notes=dict(linear='Equal-duration block averages.',
                        mean_energy='Density-weighted per phase-space cell, reconstructing the original CIC sample weighting up to DAT rounding.',
                        power='Product of pooled phase-binned j and E, matching original code accumulator convention up to DAT rounding.',
                        energy_PDFs='Equal-duration average of individually normalized EEPF/IFEDF. Raw histogram counts are unavailable, so these are not claimed to be exact pooled-particle/impact histograms.'))
    save_json(out/(KEY+'_validation.json'),validation)
    save_json(out/(KEY+'_assessment.json'),report_assess)
    scalarrows=[];criterionrows=[]
    for k,q in report_assess.get('indicators',{}).items():
        criterionrows.append(f"| {KOREAN[k]} | {100*q['relative_uncertainty_indicator']:.3f}% | {100*q['first_last_half_relative_change']:.3f}% | {100*q['tolerance']:.0f}% | {'통과' if q['passed'] else '미달'} |")
        if 'estimate' in q:
            unit='W/m³' if 'power' in k else 'm⁻³'
            scalarrows.append(f"| {KOREAN[k]} | {q['estimate']:.6g} {unit} | ±{100*q['relative_uncertainty_indicator']:.3f}% |")
    criterion_table='\n'.join(criterionrows);scalar_table='\n'.join(scalarrows)
    stage='기준 만족 후 자동 종료' if state['status']=='criteria_met' else ('측정 중간 집계' if args.preview else '저장 후 중단: '+state['status'])
    report=f'''# eduPIC 추가 측정: {stage}

**1,705주기 체크포인트에서 시작해 1,706–{last:,}주기, 총 {ncycles}주기를 새로 측정했습니다.**
20주기씩 {len(blocks)}개의 연속 구간을 따로 저장했습니다. 이전 5주기 결과는 이번 통계에 합치지 않았습니다.
원본 `C/eduPIC.cc`와 기본 조건은 그대로입니다. 계산 관리·통계·그림 작성만 별도 Python 스크립트로 수행했습니다.

| 실행 정보 | 값 |
|---|---|
| 상태 | {stage} |
| 조건 | Ar 10 Pa, 350 K, 전압 진폭 250 V, 13.56 MHz, 전극 간격 25 mm |
| 수치 설정 | 공간 400점, RF주기당 전자 4,000단계, 이온 subcycle 20, 입자 가중치 70,000 |
| 실제 solver 시간 합계 | {validation['wall_solver_seconds']/60:.2f}분 |
| 시작 / 종료 (한국 시각) | {validation['started_at_Asia_Seoul']} / {validation['completed_at_Asia_Seoul']} |
| 저장 상태 | {last:,}주기, 전자 {validation['final_checkpoint']['electrons']:,}개·이온 {validation['final_checkpoint']['ions']:,}개 슈퍼입자 |
| 원본 소스 커밋 | 32050728c961a317d6d6acd6bc86d026da403326 |
| 원본 소스 SHA256 | {SOURCE_SHA} |

## 주요 수치

| 물리량 | 평균 | 예상 통계 불확실성 지표 |
|---|---|---|
{scalar_table}

밀도의 공간평균은 격자 끝점에 사다리꼴 가중치를 사용했고, 중앙 밀도는 전극 간격 중앙 10%의 평균입니다.
평균 전력은 원본 코드와 같은 공간 격자·위상의 산술평균입니다. 두 평균의 공간 가중치는 서로 다르므로 정의를 확인하세요.
전원·접지 전극의 평균 이온 입사 에너지는 정규화 IFEDF의 블록 평균 기준 {energy[0]:.3f} / {energy[1]:.3f} eV입니다.
이온 에너지 분포의 꼬리나 두 전극의 차이는 이번 종료 기준에 포함되지 않았습니다.

## 자동 중단 판정

최소 100주기부터 20주기마다 판정하고 두 번 연속 통과하면 멈춥니다. 마지막 판정의 수치는 다음과 같습니다.

| 대상 | 통계 불확실성 지표 | 전후반 변화 | 각 기준 | 결과 |
|---|---|---|---|---|
{criterion_table}

최근 600주기의 전자·이온 입자 수에도 200주기씩 세 구간 평균의 범위 1% 미만, 선형 변화량 2% 미만을 요구했습니다.
최종 수치는 `{KEY}_assessment.json`에 있습니다. 원본 코드의 네 가지 수치 안정성 조건도 각 구간에서 검사했습니다.

통계 지표는 블록 delete-one jackknife 표준오차에 Student-t(97.5 percentile) 배수와 양의 시간상관 보정을 적용했습니다.
이는 제한된 연속 표본에 대한 **예상 변동 지표**입니다. 반복적인 자동 판정으로 엄밀한 95% 순차적 신뢰수준을 보장하지 않습니다.
전후반 변화는 같은 개수의 첫·마지막 블록을 비교하며 블록 수가 홀수이면 가운데 블록을 제외합니다.
200주기 이상이면 40주기 재집계의 지표도 계산해 더 큰 쪽을 사용합니다. 현재 40주기 재집계 가능 여부: {report_assess.get('longer_block_check_available',False)}.

Heating 기준은 원본 400 × 200 맵을 **공간 40 × RF위상 40**으로 평균한 후, 지표의 L2 norm을 평균 맵의 L2 norm으로 나눕니다.
공간 약 0.63 mm, 위상 0.025 RF주기(약 1.84 ns) 규모의 주요 구조를 비교합니다.
모든 픽셀, 특히 값이 0에 가까운 곳의 상대오차가 5% 이내라는 뜻이 아닙니다. 원본 해상도 맵과 CSV도 함께 보관했습니다.
격자·시간간격 오차와 모델 오차는 별도의 수렴 연구가 필요하며 이번 통계 지표에 포함되지 않습니다.

## 맵과 데이터 합산 방법

가로축은 RF 위상 t/T, 세로축은 전극 사이 위치 x입니다. x=0이 전원 전극, x=25 mm가 접지 전극입니다.
모든 측정 주기를 같은 위상에 모은 평균 맵이며, 개별 RF주기별 영화나 연속 시간 신호는 아닙니다.
양의 jE는 전기장→입자, 음의 jE는 입자→전기장 전력 전달입니다. Ohmic/sheath heating의 성분별 분해나 온도 상승률이 아닙니다.

- 전위, 전기장, 밀도, 전류, 이온화율: 같은 길이 블록의 산술평균.
- 평균 전자·이온 에너지: 각 위치·위상에서 밀도 가중 평균. 단순 에너지 산술평균이 아닙니다.
- 주 heating 맵: 합산한 위상 평균 전류와 전기장의 곱. 원본 코드의 누적·정규화 관례에 맞춥니다.
- 추가 `powere_mean_of_blocks` / `poweri_mean_of_blocks`: 블록마다 계산된 jE의 평균. 주 heating 맵과 구분해 제공합니다.
- EEPF와 IFEDF: `equal_block_mean` 파일은 구간별 정규화 분포의 산술평균입니다. 원본 코드는 히스토그램의 표본 수를 내보내지 않아 전체 입자·충돌 사건을 엄밀히 한데 모은 PDF와 같다고 주장하지 않습니다. 구간별 원본 PDF도 모두 제공합니다.

합산 jE와 블록별 jE 평균의 전체 전력 차이는 전자 {100*difference['e']['relative_global_difference']:.4f}%, 이온 {100*difference['i']['relative_global_difference']:.4f}%입니다.
텍스트 DAT의 출력 반올림 오차가 남습니다. 밀도 CSV의 좌표는 원본 소스의 격자식으로 정확하게 재구성했습니다.

## 결과와 재시작

`summary.zip`은 보고서·PNG·PDF·전체 변환 CSV 및 합산 DAT입니다.
각 `cycle시작-끝.zip`에는 원본 15개 DAT, info.txt, 로그, 검증 결과와 그 구간 끝의 `picdata.bin`이 있습니다.
`restart_cycle{last}.zip`은 마지막 입자 상태와 원본 소스·설정·재시작 설명을 묶은 파일입니다.

새 폴더에서 체크포인트와 같은 소스를 사용해 다음처럼 실행하면 **추가 20주기**를 계산합니다.

```bash
g++ -std=c++11 -O3 -march=native source-eduPIC.cc -o edupic
./edupic 20 m > run.log 2>&1
```

`0`은 초기화 명령이므로 재개에 사용하지 마세요. 체크포인트는 반드시 소스와 조건을 함께 보관하세요.
난수 상태와 진단 누적값은 체크포인트에 없습니다. 재시작 후 궤적은 연속 실행과 달라질 수 있으며 이전 측정은 별도 합산해야 합니다.
관심 조건만 나중에 골라 추가 측정할 수 있습니다. 조건을 바꾼다면 새로운 조건에서 다시 수렴을 확인하세요.

원본 eduPIC: Z. Donko et al., Plasma Sources Science and Technology 30, 095017 (2021), GPLv3.
'''
    (out/(KEY+'_report.md')).write_text(report)
    embedded=[]
    for name,file in figures:
        embedded.append('<h2>'+html.escape(name)+'</h2><img src="data:image/png;base64,'+base64.b64encode((out/file).read_bytes()).decode()+'">')
    (out/(KEY+'_report.html')).write_text('<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>eduPIC 추가 측정 결과</title><style>body{max-width:1200px;margin:30px auto;padding:20px;font:16px/1.7 sans-serif;color:#203342}img{width:100%}pre{white-space:pre-wrap;font:15px/1.7 sans-serif}</style>'
        '<h1>eduPIC: '+html.escape(stage)+'</h1>'+''.join(embedded)+'<pre>'+html.escape(report)+'</pre></html>')
    for name in ['criteria.json','provenance.json','status.json','assessments.jsonl','RESUME.md','adaptive_common.py','run_adaptive.py','publish_checkpoint.py','analyze_adaptive.py','finalize_results.py']:
        shutil.copyfile(ROOT/name,out/(KEY+'_'+name))
    save_json(out/(KEY+'_block_inventory.json'),block_meta)
    for mode in ['summary','restart_cycle'+str(last)]:
        path=out/(KEY+'_'+mode+'.zip')
        with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
            if mode=='summary':
                for p in sorted(out.rglob('*')):
                    if p.is_file() and p.suffix not in ['.zip','.sha256']:
                        z.write(p,KEY+'/'+str(p.relative_to(out)))
            else:
                z.write(blocks[-1]/'picdata.bin',KEY+'/picdata.bin')
                for name in ['source-eduPIC.cc','LICENSE','RESUME.md','provenance.json','criteria.json']:
                    z.write(ROOT/name,KEY+'/'+name)
                z.write(out/(KEY+'_validation.json'),KEY+'/validation.json')
                z.write(out/(KEY+'_assessment.json'),KEY+'/assessment.json')
                z.write(out/'csv'/(KEY+'_particle_counts.csv'),KEY+'/particle_counts.csv')
        with zipfile.ZipFile(path) as z:
            assert z.testzip() is None
            assert len(z.namelist())==len(set(z.namelist()))
            if mode.startswith('restart'):
                assert z.read(KEY+'/picdata.bin')==(blocks[-1]/'picdata.bin').read_bytes()
        assert path.stat().st_size<95_000_000
    checksums=''.join(f'{sha(p)}  {p.relative_to(out)}\n' for p in sorted(out.rglob('*')) if p.is_file() and p.suffix!='.sha256')
    (out/(KEY+'_checksums.sha256')).write_text(checksums)
    print(json.dumps(validation,ensure_ascii=False,indent=2))
    print('REPORT_DIRECTORY',out)

if __name__=='__main__':main()
