# eduPIC 연구 결과 · 실행 목록

**이 페이지를 북마크하면 실행일·변경 조건으로 결과와 다운로드를 찾을 수 있습니다.**

[전체 목록](https://github.com/YGLSNU/eduPIC_PAL_RF-sheath) · [75 mTorr 기본 조건](https://github.com/YGLSNU/eduPIC_PAL_RF-sheath/tree/results/75mTorr) · [20 mTorr 상부 RF](https://github.com/YGLSNU/eduPIC_PAL_RF-sheath/tree/results/20mTorr-topRF) · [실행 코드](https://github.com/YGLSNU/eduPIC_PAL_RF-sheath/tree/simulation/20mTorr-topRF)

`main`은 원본 코드와 전체 결과의 입구, `simulation/*`은 실행 코드, `results/*`은 공통 조건별 결과 보관입니다. GitHub는 저장·열람 장소이며 계산은 클라우드 실행 환경에서 수행합니다.

**BRH (bounce resonance heating):** [gap 스캔 진행·결과](https://github.com/YGLSNU/eduPIC_PAL_RF-sheath/blob/results/20mTorr-topRF/results/261124_BRH_gap20-80_step5/README.md) · [진단·실행 설명](https://github.com/YGLSNU/eduPIC_PAL_RF-sheath/blob/simulation/20mTorr-topRF/scripts/brh_scan/README.md)

[Gap별 플라즈마 파라미터·전자별 반복 가열 요약](https://github.com/YGLSNU/eduPIC_PAL_RF-sheath/blob/results/20mTorr-topRF/results/261124_BRH_gap20-80_step5/comparison/README.md)

## 실행 기록

| 실행일 KST | 실행 / 바꾼 조건 | 주요 조건 | 상태 | 결과 |
|---|---|---|---|---|
| 2026-11-26 | **261126_PSR_gap15_f60_V150**<br>PSR/VI · 15 mm · 60 MHz · 150 V peak | 20 mTorr · 15 mm · 150 V peak | 계산 중 | [보고서·그림·파일](https://github.com/YGLSNU/eduPIC_PAL_RF-sheath/blob/results/20mTorr-60MHz-topRF/results/261126_PSR_gap15_f60_V150/README.md) |

각 보고서 첫 화면에서 조건표·평균 구간·종료 이유를 확인할 수 있습니다. 소멸·미완료는 정상 방전의 통계 수렴과 다르게 표시합니다.

## 이후 결과 추가

새 실행은 `results/YYMMDD_바꾼조건/run.json`과 그래프·자료를 함께 등록합니다. 등록 도구가 보고서와 목록을 갱신하며, GitHub Actions도 결과 push 뒤 전체 목록을 동기화합니다.

[파일 이름·보고서·업로드 기준](docs/RESULTS_GUIDE.md) · [전체 결과 점검 기록](docs/RESULT_AUDIT.md) · [브랜치·이름 변경 이력](docs/MIGRATION.md) · [eduPIC 원본 소개·논문·라이선스](docs/UPSTREAM.md)
