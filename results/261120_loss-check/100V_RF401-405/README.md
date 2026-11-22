# 261120_loss-check · 20.000 mTorr · 100 V · RF401–405 진단

[전체 실행 목록](https://github.com/YGLSNU/eduPIC_PAL_RF-sheath) · [이 조건군](https://github.com/YGLSNU/eduPIC_PAL_RF-sheath/tree/results/20mTorr-topRF) · [실행 비교](https://github.com/YGLSNU/eduPIC_PAL_RF-sheath/blob/results/20mTorr-topRF/results/261120_loss-check/README.md)

**과도구간 진단** · 실행일 2026-11-20 (한국 시각) · 변경 조건: **20.000 mTorr, 100 V, 시작상태 RF400** · 보고서 갱신 2026-11-22

5 RF 과도구간 진단입니다. 이 그림은 정상상태 수렴 결과가 아니며, 원인 분석용 재시작 표본입니다.

## 실행 조건

| 항목 | 값 |
|---|---|
| 기체 / 압력 / 온도 | Ar / 20 mTorr / 350 K |
| 인가 파형 / 주파수 | 정현파 / 13.56 MHz |
| 전압 / gap | 100 V peak / 25 mm |
| 전극 연결 | 상부 x=L RF / 하부 x=0 접지 |
| 면적 / 형상 | 1D3V 동일 면적 평판, 환산 면적 1 cm²; 실제 지름·측벽 제외 |
| 표면 / 충돌 모델 | 흡수 경계, SEE·전자 반사 없음; ground-state Ar MCC |
| 격자 / 시간간격 / 입자 가중치 | 400점 / RF당 4000 전자 step / 70000 |
| 코드 | 상부 RF로 수정한 C/eduPIC.cc 계열, C++11 컴파일 |
| 소스 이력 | 실행별 source ZIP·소스 SHA256 기록 참조 |
| 초기·재시작 상태 | 20mTorr_100V_from400: 전자13785, 이온15627 계산 입자에서 시작 |
| 측정 구간 | RF401–405,5 RF. 압력 대조는 동일 초기 입자 상태를 사용. |

상태와 그래프는 마지막 저장 자료이며 실시간 CPU 실행 화면은 아닙니다.

![전극 연결](figures/setup.png)

## 핵심 수치

| 물리량 | 값 |
|---|---|
| 생성 / 전자 벽 손실 | 88 / 616 = 0.1429 |
| 전자 수 변화 | 13785→13257 (-3.830%) |
| 입자 수지 잔차 | e=0, i=0 |

## 자료 범위

| 진단 | 저장·해석 범위 |
|---|---|
| 수렴·입자 수지 | 5 RF 생성·손실; 정상상태 판정 없음 |
| 밀도 공간분포 | 5 RF 과도구간 평균 |
| RF heating | 5 RF 과도구간의 위상 평균 |
| 전위·전기장 | 5 RF 과도구간의 위상 평균 |
| 평균 에너지·이온화 | 5 RF 과도구간; heating 묶음 그림 |
| 에너지 분포 | 5 RF 정규화 분포 |
| 전극 flux·손실 | 5 RF 입자 흡수 사건 수; particle_balance.csv |
| 전력 전달·손실 | 입자 field-work·벽 운동에너지·운동에너지 변화·추정 충돌 손실; summary.json |

## 수렴·입자 수지

사건 수와 입력/출력 입자 수가 정확히 일치하는지 검사했습니다.

## 밀도 공간분포

아래 분포 그림 첫 패널에 표시합니다.

## RF heating



![TRANSIENT 5 RF | 20.000 mTorr | 100 V | 25 mm | RF 401-405](figures/heating.png)

TRANSIENT 5 RF | 20.000 mTorr | 100 V | 25 mm | RF 401-405

## 전위·전기장



![TRANSIENT 5 RF | 20.000 mTorr | 100 V | 25 mm | RF 401-405](figures/fields.png)

TRANSIENT 5 RF | 20.000 mTorr | 100 V | 25 mm | RF 401-405

## 평균 에너지·이온화



## 에너지 분포



![이온·전자 분포의 표본 길이는 5 RF이며 정상상태 통계가 아닙니다.](figures/distributions.png)

이온·전자 분포의 표본 길이는 5 RF이며 정상상태 통계가 아닙니다.

## 전극 flux·손실



## 전력 전달·손실

저장 운동에너지가 변하는 구간이므로 단순 정상상태 파워 수지를 적용하지 않습니다.

## 읽는 기준

- 위상 그림의 가로축은 RF 위상 t/T, 세로축은 위치 x입니다. 전극 방향은 위 조건표를 따릅니다. 위상 0은 cos 인가 전압의 양의 최댓값입니다.
- Heating은 위상 평균 j × 위상 평균 E입니다. 양수는 전기장에서 입자로, 음수는 반대 방향의 전달입니다. 순간 jE의 평균·온도 상승률과 구분합니다.
- 통계 중단 기준은 전체 물리·격자 오차나 모든 픽셀의 오차를 보증하지 않습니다. 소멸·미완료·짧은 진단을 정상 방전 측정과 구분합니다.
- 전력 표시는 W/m² 또는 W/m³입니다. 실제 전극 면적·회로 없이 발생기 총 W와 동일시하지 않습니다.

## 파일과 재시작

| 자료 | 다운로드 | 크기 |
|---|---|---:|
| eepf | [eepf.csv](data/eepf.csv) | 0.03 MiB |
| ifed | [ifed.csv](data/ifed.csv) | 0.00 MiB |
| info | [info.txt](data/info.txt) | 0.00 MiB |
| particle_balance | [particle_balance.csv](data/particle_balance.csv) | 0.00 MiB |
| profiles | [profiles.csv](data/profiles.csv) | 0.04 MiB |
| summary | [summary.json](data/summary.json) | 0.00 MiB |

[전체 파일 목록·SHA256](files.json)
