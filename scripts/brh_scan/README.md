# BRH gap 스캔 실행·결과

## 다른 클라우드에서의 체크포인트 복원

2026-11-26 재개는 75 mm RF2500, 80 mm RF2420의 입자·UID·MCC 잔여 optical depth·RNG 동반 상태를 복원합니다. 80 mm의 일시중단만 해제하며 100/120 mm는 재개 대상에서 제외합니다. 기존 실행일과 원자료를 보존하고 `recovery_manifest.json`에 재개 이력을 별도로 남깁니다. `run_scan.py ROOT --gaps 75 80`은 `case_sources`의 원래 실행 폴더도 명시적으로 이어 계산할 수 있습니다.

GitHub의 누적 native 평균과 BRH 원시 사건·counts는 보존됐지만, 이전 개별20RF native 행렬은 백업에 없습니다. 복원 누적 자료를 `recovery_aggregate.json`으로 표시하며 개별20RF 블록처럼 취급하지 않습니다. 전체 평균은 실제RF 길이로 가중하고, 에너지 평균은 밀도로 가중하며, heating은 합산한 `<j> × <E>`로 다시 계산합니다. 에너지 counts와 signed work는 원시 합계를 더합니다. 누적 불확실도·공동 중단 기준을 재구성할 수 없어 `passed`로 표시하지 않으며, 재개 후의20RF/40RF 블록 평가를 `post_resume_segment_assessment`에 별도로 보관합니다. 기존 누적 측정 상한1000RF는 유지합니다.

본 계산 전 현재 체크포인트에서2RF 연속 실행과1RF씩 두 번 재시작한 입자·UID 상태·RNG의 바이트 일치를 확인하고, 누적 native/counts 합산도 복사본으로 검증합니다. 이 검증 구간은 물리 측정에 포함하지 않습니다. 결과 게시기는 `verify_reports.py --export EXPORT`로8개 진단·상대 링크·다운로드·SHA256을 확인한 뒤 기존 등록 도구로 게시하고, 원격 보고서와 대표 재시작ZIP을 다시 내려받아 검사합니다. 계산과 자동 게시 모두 클라우드 환경이 살아 있는 동안 작동합니다.

**BRH = bounce resonance heating: 전자 왕복과 RF의 공명 가열.** 계산은 클라우드 CPU에서 실행하고 GitHub는 코드·저장 기록·결과를 보관합니다. GitHub 페이지를 여는 것만으로 PIC 계산이 시작되지는 않습니다.

[진행·결과 보고서](https://github.com/YGLSNU/eduPIC_PAL_RF-sheath/blob/results/20mTorr-topRF/results/261123_BRH_gap25-120/README.md) · [진단·판정 정의](METHOD.md) · [전체 실행 목록](https://github.com/YGLSNU/eduPIC_PAL_RF-sheath)

## 이번 조건

Ar **20 mTorr**, 350 K, **13.56 MHz, 250 V peak** 정현파. **상부 x=L RF, 하부 x=0 접지.** gap **25/30/40/50/60/80/100/120 mm**. 1D3V 동일 면적 평판, 환산 면적1cm², 측벽·재료 반사·SEE 제외. 탄성·여기·이온화 Ar MCC를 포함하며 binary Coulomb 충돌은 없습니다.

40mm 보관 소스의 optical-depth 충돌 모델을 전 gap에서 사용합니다. dx≤62.5µm, 가중치112000 고정, 초기 입자 수는 체적에 비례합니다. RF당 전자8000step, 이온40step마다 갱신, 위상200bin. `C/eduPIC.cc`와 과거 결과 ZIP은 보존하고 **`C/eduPIC_brh.cc` + `C/brh_diagnostics.hpp`**에서 진단합니다. 계측은 추가 난수를 사용하거나 입자에 힘을 가하지 않습니다.

초기 상태는 기존40mm·250V RF2001 저장 입자입니다. 분포를 gap에 맞춰 재표본하고 x와 leapfrog 시간 stagger를 변환합니다. 조건 변경 직후는 평형이 아니므로 과도구간을 정상 측정에서 제외합니다. 점화 임계값을 찾는 계산과도 구분합니다.

## 실행·이어 계산

현재 실행 폴더는 `/workspace/edupic-brh/261123_BRH_gap25-120`입니다. Python3, NumPy, SciPy, Matplotlib, pandas, g++가 필요합니다. 제어기는 gap4개를 동시에 계산합니다. 초기 검증 중에는 진단용 CPU를 남기기 위해3개로 시작했고, 검증 후 완결 체크포인트에서4개로 늘렸습니다.

```bash
# 최초 준비: 기존 reference 경로는 prepare.py 참조
python scripts/brh_scan/prepare.py /workspace/edupic-brh/261123_BRH_gap25-120
python scripts/brh_scan/instrument.py /workspace/edupic-brh/261123_BRH_gap25-120
python scripts/brh_scan/validate.py /workspace/edupic-brh/261123_BRH_gap25-120
python -u scripts/brh_scan/run_scan.py /workspace/edupic-brh/261123_BRH_gap25-120
```

`prepare.py`는 기존 실행을 덮어쓰지 않습니다. 재개할 때는 마지막 명령을 사용하며 완료 조건을 건너뜁니다. 파일 잠금으로 제어기의 중복 실행을 막습니다. 완결 블록 뒤 멈추려면 실행 폴더에 `STOP_AFTER_BLOCK` 파일을 만들고 재개 전 지웁니다. 강제 종료하면 진행 중인 블록 대신 **마지막 완결 체크포인트**에서 재시작합니다.

다른 컴퓨터에는 기존 절대경로의 reference가 없을 수 있습니다. 결과 페이지의 source ZIP에 `source_control.cc`, **원본40mm·4000step/RF·640격자의** `reference40.bin`과 criteria가 들어 있습니다. 이를 풀고 `prepare.py ROOT --source EXTRACT/source_control.cc --checkpoint EXTRACT/reference40.bin`으로 초기화할 수 있습니다. 새 BRH 체크포인트는 아래의 세 파일 재시작 방식을 사용합니다.

입자만 담은 `picdata.bin`은 통계적인 재시작이 가능합니다. 새 BRH 측정은 **`picdata.bin`, `brh_state.bin`, `brh_rng.txt` 세 파일을 함께** 보관해야 UID·왕복 이력·MCC 잔여 optical depth·난수 상태를 연속 복원합니다. 컴파일 조건과 소스도 같아야 합니다. 블록별 히스토그램은 재시작 상태와 별도입니다.

## 보고서 갱신

### 20–80 mm, 5 mm 간격 추가 스캔

[13개 gap 진행·결과](https://github.com/YGLSNU/eduPIC_PAL_RF-sheath/blob/results/20mTorr-topRF/results/261124_BRH_gap20-80_step5/README.md) · [파라미터·전자별 반복 가열 비교](https://github.com/YGLSNU/eduPIC_PAL_RF-sheath/blob/results/20mTorr-topRF/results/261124_BRH_gap20-80_step5/comparison/README.md)

`261124_BRH_gap20-80_step5`는 기존25·30·40·50·60·80 mm의 실행을 재사용하고20·35·45·55·65·70·75 mm를 추가합니다. 물리 소스·초기 기준 입자·가중치·시간격자·수렴 기준은 같습니다. 재사용은 독립 seed 반복 실행이 아니며 원 실행일과 상한/소멸 상태를 유지합니다.

```bash
python scripts/brh_scan/refine_scan.py /workspace/edupic-brh/261123_BRH_gap25-120 /workspace/edupic-brh/261124_BRH_gap20-80_step5 --start 20 --stop 80 --step 5
python scripts/brh_scan/validate_new_gap.py /workspace/edupic-brh/261124_BRH_gap20-80_step5 --gap 35
python -u scripts/brh_scan/run_scan.py /workspace/edupic-brh/261124_BRH_gap20-80_step5
```

최초 준비는 새 폴더에서만 실행합니다. 재개는 마지막 명령을 사용합니다. `capacity.py`가 이전 미종료 계산의 CPU를 예약하고 전체4개 solver 한도 안에서 새 조건을 투입합니다. 자원을 기다리는 조건은 `execution_state: waiting_for_capacity`로 기록합니다. 이전 조건이 종료되면 새 계산의 동시 실행 수가 늘어납니다.

작은 gap부터 우선 배정하려면 `config.json`의 `admit_in_gap_order`를 `true`로 설정합니다. 미완료 gap을 오름차순으로 배정하며 앞선 gap의 solver가 실제로 시작하거나 해당 작업이 종료된 뒤 다음 gap을 투입합니다. 이미 시작한 조건은 최대4개까지 병렬 계산하므로 큰 gap이 먼저 빈 슬롯을 차지하는 일을 막습니다. 개별 조건의 `STOP_AFTER_BLOCK`은 그 조건만 완결 블록 뒤 일시중단합니다. 중단한 조건은 해당 파일을 지우기 전까지 재개되지 않습니다.

2026-11-24 추가 지시부터는 **80·100·120 mm를 일시중단**하고 **35→45→55→65→70→75 mm** 순서로 미완료 조건을 우선 배정합니다. 현재 계산한 결과와 UID·난수 동반 체크포인트를 보관하며, 80 mm 이상은 별도 재개 지시 전까지 자동 재개하지 않습니다. 실행 폴더의 `config.json`과 결과 페이지가 현재 정책과 상태를 기록합니다.

새 실행의 측정 블록은 큰 수치 텍스트를 `.dat.gz`로 무손실 압축합니다. 압축 해제 byte가 원본과 같음을 검사하고 SHA256을 `native_compression.json`에 남깁니다. `load_array`가 plain/gzip을 모두 읽으며 입자·난수·UID 재시작 파일은 그대로 유지합니다. 저장 공간 관리 때 기존 실행의 종료된 측정 블록에도 같은 검증을 거쳐 적용할 수 있습니다. 현재 그림의 집계 디렉터리와 마지막 과도 진단은 plain 형식을 유지하고 재시작 파일·원시 수치를 보존합니다.

아래 export·publish 명령의 실행 폴더를 새 폴더로 바꾸면13개 조건을 함께 갱신합니다. `config.json`의 `case_sources`는 이전 실행을 읽기 전용으로 참조하고, `run_gaps_mm`만 새 제어기가 계산합니다. 보고서는 실제 실행일과 재사용 출처, 각 측정 RF 구간을 구분합니다.

[Gap별 파라미터·전자별 반복 가열 요약](https://github.com/YGLSNU/eduPIC_PAL_RF-sheath/blob/results/20mTorr-topRF/results/261123_BRH_gap25-120/comparison/README.md)은 `compare.py`가 실제 완결 측정 epoch로 생성합니다. 밀도, 입자 가중 에너지 환산 온도, 쉬스 반사 후 기준면 출구 에너지 분포, 흡수 전력, 이온화율과 UID별 후보 사건·episode를 비교합니다. 온도는 Maxwellian fit이나 drift 제거 온도가 아닙니다. 전자 수명 전체로 횟수를 외삽하지 않으며, 에너지 증가 부호와 무관하게 최대 위상 반복 길이로 예시를 선정합니다. 원자료 출구 에너지와 왕복 에너지 장부를 대조하고 검증 기록·CSV를 함께 제공합니다.

```bash
python scripts/brh_scan/export.py /workspace/edupic-brh/261123_BRH_gap25-120 /workspace/edupic-brh/export/261123_BRH_gap25-120
python scripts/results/publish_run.py /workspace/edupic-brh/export/261123_BRH_gap25-120 --branch results/20mTorr-topRF --push
```

기존 등록 도구가 조건별 보고서·크기·SHA256·최상위 북마크를 갱신합니다. 결과 페이지의 시각은 **마지막 업로드 자료**이며 실시간 CPU 상태는 아닙니다. 클라우드가 종료되면 계산·자동 업로드도 멈추지만 이미 GitHub에 저장한 결과는 남습니다. 제어기/업로더의 동작은 실행 폴더의 PID·로그로 확인합니다.

자동 업로더는 `python -u scripts/brh_scan/watch_publish.py ROOT`로 실행합니다. **15분 간격**, 소멸/기준 충족 등 상태 변화, 최종 종료 때 저장된 블록을 게시합니다. `ROOT/STOP_PUBLISH`로 업로드만 중단할 수 있습니다. `controller.log`, `publisher.log`, `last_publication.json`에 실행·게시 기록을 남깁니다. GitHub Actions는 목록을 동기화하며 클라우드의 PIC 계산을 대신하지 않습니다.

재시작 ZIP은 매500RF 또는1시간 경과, 종료 시 갱신합니다. 표의 최신 체크포인트와 ZIP의 저장 RF가 다를 수 있으므로 다운로드 옆의 **실제 저장 RF**를 확인하세요. 진단 동반 상태는 현재 컴파일러·아키텍처의 binary 형식입니다. 다른 환경에서는 입자만 이용한 통계적 재시작과 새 진단 이력 작성을 선택할 수 있습니다.

큰 BRH 자료는 `_p01.zip`, `_p02.zip`처럼 나눠 각 파일을95MiB보다 작게 유지합니다. 표시된 ZIP을 모두 같은 폴더에 풀고, byte 분할 파일이 있으면 동봉한 `reassemble_brh.py`를 실행합니다. SHA256으로 복원 결과를 검사합니다. 궤적 예시는 첫 측정 블록의 처음5RF만 묶으며, 왕복 사건·probe·에너지 counts는 측정 epoch 전체입니다. 클라우드의 모든 원시 블록은 보존하고, 재생성 가능한 오래된 중간 집계만 정리합니다.

완료 전에는 소멸·안정화·정상 측정·통계 상한을 구분합니다. 최소600RF의 배경 안정화 뒤 최소200RF의 진단을 계획하므로 여러 시간이 걸릴 수 있습니다. BRH 유무는 METHOD의 사건 통계와 추가 검증을 함께 보고 판정합니다.
