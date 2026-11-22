# eduPIC 연구 결과 · 실행 목록

**이 페이지를 북마크하면 실행일·변경 조건으로 결과와 다운로드를 찾을 수 있습니다.**

[전체 목록](https://github.com/YGLSNU/eduPIC_PAL_RF-sheath) · [75 mTorr 기본 조건](https://github.com/YGLSNU/eduPIC_PAL_RF-sheath/tree/results/75mTorr) · [20 mTorr 상부 RF](https://github.com/YGLSNU/eduPIC_PAL_RF-sheath/tree/results/20mTorr-topRF) · [실행 코드](https://github.com/YGLSNU/eduPIC_PAL_RF-sheath/tree/simulation/20mTorr-topRF)

공통 조건: Ar **20 mTorr**, 350 K, 13.56 MHz, **상부 RF / 하부 접지**. gap·전압 등 변경한 조건은 각 실행 이름에 표시합니다. 압력 대조 진단은 개별 보고서의 실제 압력을 따릅니다.

## 실행 기록

| 실행일 KST | 실행 / 바꾼 조건 | 주요 조건 | 상태 | 결과 |
|---|---|---|---|---|
| 2026-11-20 | **261120_loss-check**<br>벽 손실 진단 · 20↔75.006 mTorr 대조 | 20 mTorr · 25 mm · 100/250/300 V peak | 과도구간 진단 | [보고서·그림·파일](https://github.com/YGLSNU/eduPIC_PAL_RF-sheath/blob/results/20mTorr-topRF/results/261120_loss-check/README.md) |
| 2026-11-20 | **261120_gap40_V100-500**<br>gap40 mm · 100/250/300/400/500 V | 20 mTorr · 40 mm · 100/250/300/400/500 V peak | 통계 기준 충족 | [보고서·그림·파일](https://github.com/YGLSNU/eduPIC_PAL_RF-sheath/blob/results/20mTorr-topRF/results/261120_gap40_V100-500/README.md) |
| 2026-11-19 | **261119_gap25_V100-300**<br>gap25 mm · 100/250/300 V | 20 mTorr · 25 mm · 100/250/300 V peak | 전자 소멸 | [보고서·그림·파일](https://github.com/YGLSNU/eduPIC_PAL_RF-sheath/blob/results/20mTorr-topRF/results/261119_gap25_V100-300/README.md) |

각 보고서 첫 화면에서 조건표·평균 구간·종료 이유를 확인할 수 있습니다. 소멸·미완료는 정상 방전의 통계 수렴과 다르게 표시합니다.

## 이후 결과 추가

새 실행은 `results/YYMMDD_바꾼조건/run.json`과 그래프·자료를 함께 등록합니다. 등록 도구가 보고서와 목록을 갱신하며, GitHub Actions도 결과 push 뒤 전체 목록을 동기화합니다.

[파일 이름·보고서·업로드 기준](../docs/RESULTS_GUIDE.md) · [전체 결과 점검 기록](../docs/RESULT_AUDIT.md) · [브랜치·이름 변경 이력](../docs/MIGRATION.md) · [eduPIC 원본 소개·논문·라이선스](../docs/UPSTREAM.md)
