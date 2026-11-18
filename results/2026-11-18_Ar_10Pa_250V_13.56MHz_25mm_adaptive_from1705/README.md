# 2026-11-18: 통계 기준에 따른 추가 측정

원본 C/eduPIC.cc, Ar 10 Pa, 350 K, 전압 진폭 250 V, 13.56 MHz, 전극 간격 25 mm.
1,705주기 체크포인트에서 재개했으며, 원본 시뮬레이션 소스와 물리 조건은 바꾸지 않았습니다.

**마지막 업로드 상태: 통계 기준 만족·계산 종료 / 저장 완료 1,825주기 / 새 측정 120주기.**
이는 업로드 당시 상태입니다. 브라우저 화면은 실시간 CPU 실행 상태를 나타내지 않습니다.

[최종 보고서·그림](FINAL_REPORT.md)

## 중단 기준

20주기씩 저장하고 최소 100주기부터 검사합니다. 다음을 두 번 연속 만족하면 자동 종료합니다.

- 전자·이온 평균/중심 밀도와 평균 전력: 블록 통계의 예상 불확실성 지표 및 전후반 변화 각각 3% 이내.
- 전자·이온 밀도 공간분포: 같은 지표를 분포 전체 L2 norm으로 정규화해 3% 이내.
- 전자·이온 heating 맵: 공간 40 × 위상 40으로 평균한 맵 전체의 L2 기준 5% 이내.
- 최근 600주기 입자 수: 200주기씩 세 평균의 범위 1% 미만, 선형 변화량 2% 미만.

Student-t 배수의 블록 표준오차에 양의 시간상관 보정을 사용합니다. 200주기 이상이면 40주기 단위 재집계도 비교합니다.
이는 대략적인 결과 취합용 중단 규칙이며 정확한 참값 대비 오차, 모든 픽셀의 5% 오차, 엄밀한 순차적 95% 신뢰수준을 보장하지 않습니다.
원본 400 × 200 맵은 모두 보관합니다. 최대 1,000주기 추가 측정 시 재평가를 위해 멈추며, 기준 미달 상태를 수렴으로 표기하지 않습니다.

## 구간별 원본과 재시작 파일

| 새 측정 RF주기 | 크기 | 다운로드 |
|---|---|---|
| 1706–1725 | 10.24 MB | [원본 결과·체크포인트 ZIP](https://github.com/YGLSNU/eduPIC_PAL_RF-sheath/raw/refs/heads/results/2026-11-17-default-incomplete/results/2026-11-18_Ar_10Pa_250V_13.56MHz_25mm_adaptive_from1705/2026-11-18_Ar_10Pa_250V_13.56MHz_25mm_adaptive_from1705_cycle1706-1725.zip) |
| 1726–1745 | 10.24 MB | [원본 결과·체크포인트 ZIP](https://github.com/YGLSNU/eduPIC_PAL_RF-sheath/raw/refs/heads/results/2026-11-17-default-incomplete/results/2026-11-18_Ar_10Pa_250V_13.56MHz_25mm_adaptive_from1705/2026-11-18_Ar_10Pa_250V_13.56MHz_25mm_adaptive_from1705_cycle1726-1745.zip) |
| 1746–1765 | 10.24 MB | [원본 결과·체크포인트 ZIP](https://github.com/YGLSNU/eduPIC_PAL_RF-sheath/raw/refs/heads/results/2026-11-17-default-incomplete/results/2026-11-18_Ar_10Pa_250V_13.56MHz_25mm_adaptive_from1705/2026-11-18_Ar_10Pa_250V_13.56MHz_25mm_adaptive_from1705_cycle1746-1765.zip) |
| 1766–1785 | 10.24 MB | [원본 결과·체크포인트 ZIP](https://github.com/YGLSNU/eduPIC_PAL_RF-sheath/raw/refs/heads/results/2026-11-17-default-incomplete/results/2026-11-18_Ar_10Pa_250V_13.56MHz_25mm_adaptive_from1705/2026-11-18_Ar_10Pa_250V_13.56MHz_25mm_adaptive_from1705_cycle1766-1785.zip) |
| 1786–1805 | 10.25 MB | [원본 결과·체크포인트 ZIP](https://github.com/YGLSNU/eduPIC_PAL_RF-sheath/raw/refs/heads/results/2026-11-17-default-incomplete/results/2026-11-18_Ar_10Pa_250V_13.56MHz_25mm_adaptive_from1705/2026-11-18_Ar_10Pa_250V_13.56MHz_25mm_adaptive_from1705_cycle1786-1805.zip) |
| 1806–1825 | 10.25 MB | [원본 결과·체크포인트 ZIP](https://github.com/YGLSNU/eduPIC_PAL_RF-sheath/raw/refs/heads/results/2026-11-17-default-incomplete/results/2026-11-18_Ar_10Pa_250V_13.56MHz_25mm_adaptive_from1705/2026-11-18_Ar_10Pa_250V_13.56MHz_25mm_adaptive_from1705_cycle1806-1825.zip) |

각 ZIP에는 해당 구간의 15개 DAT, info.txt, 로그, 검사 기록 및 마지막 picdata.bin이 있습니다.
현재 마지막 재시작 상태는 1825주기입니다.

- [시작 1,705주기 체크포인트·원본 소스](https://github.com/YGLSNU/eduPIC_PAL_RF-sheath/raw/refs/heads/results/2026-11-17-default-incomplete/results/2026-11-18_Ar_10Pa_250V_13.56MHz_25mm_adaptive_from1705/2026-11-18_Ar_10Pa_250V_13.56MHz_25mm_adaptive_from1705_input_cycle1705_restart.zip)
- [재시작 방법](2026-11-18_Ar_10Pa_250V_13.56MHz_25mm_adaptive_from1705_RESUME.md)
- [중단 기준 설정](2026-11-18_Ar_10Pa_250V_13.56MHz_25mm_adaptive_from1705_criteria.json)
- [검사 수치](2026-11-18_Ar_10Pa_250V_13.56MHz_25mm_adaptive_from1705_assessment.json)
- [파일 목록·체크섬](2026-11-18_Ar_10Pa_250V_13.56MHz_25mm_adaptive_from1705_manifest.json)

강제 종료 시 마지막으로 완전히 저장된 구간까지만 재개할 수 있습니다. 원본 코드는 난수 상태를 저장하지 않습니다.
중간 재시작으로 개별 궤적은 달라질 수 있으나 같은 조건의 통계적 연속 계산은 가능합니다.
원본 진단 누적값은 재시작 때 초기화되므로 이전 결과를 보관하고 후처리로 결합해야 합니다.
