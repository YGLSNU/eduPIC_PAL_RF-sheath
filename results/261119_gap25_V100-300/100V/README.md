# 261119_gap25_V100-300 · 100 V · gap25 mm 소멸 결과

[전체 실행 목록](https://github.com/YGLSNU/eduPIC_PAL_RF-sheath) · [이 조건군](https://github.com/YGLSNU/eduPIC_PAL_RF-sheath/tree/results/20mTorr-topRF) · [실행 비교](https://github.com/YGLSNU/eduPIC_PAL_RF-sheath/blob/results/20mTorr-topRF/results/261119_gap25_V100-300/README.md)

**전자 소멸** · 실행일 2026-11-19 (한국 시각) · 변경 조건: **gap25 mm · 100 V** · 보고서 갱신 2026-11-22

전자 소멸은 정상 방전의 통계 수렴이 아닙니다. 다른 조건을 이어 계산하려면 소멸 전 입자 상태를 사용합니다.

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
| 초기·재시작 상태 | 기존 수렴 입자 분포를 반전한 공통 상태; 변경 조건의 과도구간은 측정에서 제외 |
| 측정 구간 | 정상 방전 최종 측정 없음 |

상태와 그래프는 마지막 저장 자료이며 실시간 CPU 실행 화면은 아닙니다.

## 핵심 수치

| 물리량 | 값 |
|---|---|
| 전자 소멸 RF | 645 |
| 이온 소멸 RF | 3216 |
| 마지막 저장 RF | 3250 |

## 자료 범위

| 진단 | 제공 상태 | 저장·해석 범위 |
|---|---|---|
| 수렴·입자 수지 | 자료 있음 | 입자 수·소멸 과정 |
| 밀도 공간분포 | 부분 자료 | 최종 빈 상태; 정상 방전 공간분포 없음 |
| RF heating | 자료 없음 | 정상 방전 측정에 도달하기 전에 전자가 소멸하여 해당 정상상태 진단을 측정하지 못했습니다. |
| 전위·전기장 | 자료 없음 | 정상 방전 측정에 도달하기 전에 전자가 소멸하여 해당 정상상태 진단을 측정하지 못했습니다. |
| 평균 에너지·이온화 | 자료 없음 | 정상 방전 측정에 도달하기 전에 전자가 소멸하여 해당 정상상태 진단을 측정하지 못했습니다. |
| 에너지 분포 | 자료 없음 | 정상 방전 측정에 도달하기 전에 전자가 소멸하여 해당 정상상태 진단을 측정하지 못했습니다. |
| 전극 flux·손실 | 자료 없음 | 정상 방전 측정에 도달하기 전에 전자가 소멸하여 해당 정상상태 진단을 측정하지 못했습니다. |
| 전력 전달·손실 | 자료 없음 | 정상 방전 측정에 도달하기 전에 전자가 소멸하여 해당 정상상태 진단을 측정하지 못했습니다. |

## 수렴·입자 수지



![전자·이온 소멸 이력](261119_gap25_100V_extinction.png)

전자·이온 소멸 이력

## 밀도 공간분포

전자 소멸 뒤의 빈 상태는 정상 방전의 측정 평균이 아닙니다.

![입자 수·입자 가중치·체적으로 환산한 체적평균 밀도의 시간 변화입니다.](figures/density.png)

입자 수·입자 가중치·체적으로 환산한 체적평균 밀도의 시간 변화입니다.

## RF heating

**자료 없음:** 정상 방전 측정에 도달하기 전에 전자가 소멸하여 해당 정상상태 진단을 측정하지 못했습니다.

## 전위·전기장

**자료 없음:** 정상 방전 측정에 도달하기 전에 전자가 소멸하여 해당 정상상태 진단을 측정하지 못했습니다.

## 평균 에너지·이온화

**자료 없음:** 정상 방전 측정에 도달하기 전에 전자가 소멸하여 해당 정상상태 진단을 측정하지 못했습니다.

## 에너지 분포

**자료 없음:** 정상 방전 측정에 도달하기 전에 전자가 소멸하여 해당 정상상태 진단을 측정하지 못했습니다.

## 전극 flux·손실

**자료 없음:** 정상 방전 측정에 도달하기 전에 전자가 소멸하여 해당 정상상태 진단을 측정하지 못했습니다.

## 전력 전달·손실

**자료 없음:** 정상 방전 측정에 도달하기 전에 전자가 소멸하여 해당 정상상태 진단을 측정하지 못했습니다.

## 읽는 기준

- 위상 그림의 가로축은 RF 위상 t/T, 세로축은 위치 x입니다. 전극 방향은 위 조건표를 따릅니다. 위상 0은 cos 인가 전압의 양의 최댓값입니다.
- Heating은 위상 평균 j × 위상 평균 E입니다. 양수는 전기장에서 입자로, 음수는 반대 방향의 전달입니다. 순간 jE의 평균·온도 상승률과 구분합니다.
- 통계 중단 기준은 전체 물리·격자 오차나 모든 픽셀의 오차를 보증하지 않습니다. 소멸·미완료·짧은 진단을 정상 방전 측정과 구분합니다.
- 전력 표시는 W/m² 또는 W/m³입니다. 실제 전극 면적·회로 없이 발생기 총 W와 동일시하지 않습니다.

## 파일과 재시작

| 자료 | 다운로드 | 크기 |
|---|---|---:|
| 261119 gap25 100V all plots | [261119_gap25_100V_all_plots.pdf](https://github.com/YGLSNU/eduPIC_PAL_RF-sheath/raw/refs/heads/results/20mTorr-topRF/results/261119_gap25_V100-300/100V/261119_gap25_100V_all_plots.pdf) | 20.5 KiB |
| 261119 gap25 100V before extinction restart | [261119_gap25_100V_before_extinction_restart.zip](https://github.com/YGLSNU/eduPIC_PAL_RF-sheath/raw/refs/heads/results/20mTorr-topRF/results/261119_gap25_V100-300/100V/261119_gap25_100V_before_extinction_restart.zip) | 122.8 KiB |
| 261119 gap25 100V particle counts | [261119_gap25_100V_particle_counts.csv](261119_gap25_100V_particle_counts.csv) | 32.9 KiB |
| 261119 gap25 100V restart | [261119_gap25_100V_restart.zip](https://github.com/YGLSNU/eduPIC_PAL_RF-sheath/raw/refs/heads/results/20mTorr-topRF/results/261119_gap25_V100-300/100V/261119_gap25_100V_restart.zip) | 38.0 KiB |
| 261119 gap25 100V summary | [261119_gap25_100V_summary.zip](https://github.com/YGLSNU/eduPIC_PAL_RF-sheath/raw/refs/heads/results/20mTorr-topRF/results/261119_gap25_V100-300/100V/261119_gap25_100V_summary.zip) | 164.5 KiB |

[전체 파일 목록·SHA256](files.json)

[기존 상세 기록](DETAILS.md)
