# 2026-11-22 결과 페이지 재구성

사용자가 요청한 날짜 없는 조건군 브랜치와 `YYMMDD_바꾼조건` 이름으로 현재 결과를 정리했습니다. 실행일은 유지하고 보고서 갱신일만 별도로 기록합니다.

| 이전 브랜치 | 현재 브랜치 |
|---|---|
| results/2026-11-17-default-incomplete | results/75mTorr |
| results/2026-11-19-20mTorr-top-powered | results/20mTorr-topRF |
| simulation/2026-11-19-20mTorr-top-voltage-scan | simulation/20mTorr-topRF |

| 실행 | 새 폴더 | 조건군 |
|---|---|---|
| 11/17 기본 조건의 초기 실행·미완료 | 261117_initial | 75mTorr |
| 11/18 RF1701–1705 | 261118_measure5 | 75mTorr |
| 11/18 RF1706–1825 | 261118_measure120 | 75mTorr |
| 11/19 gap25mm,100/250/300V | 261119_gap25_V100-300 | 20mTorr-topRF |
| 11/20 gap40mm,100–500V | 261120_gap40_V100-500 | 20mTorr-topRF |
| 11/20 소멸 원인·압력 대조 진단 | 261120_loss-check | 20mTorr-topRF |

브랜치 이름 변경은 Git 참조를 이동하는 방식입니다. 이 작업은 GitHub의 브랜치 rename API가 만드는 자동 URL 리디렉션을 보장하지 않습니다. 현재 북마크는 저장소 main 첫 화면을 사용하세요. 과거 브랜치 스냅샷은 기존 이름의 태그로 보존합니다. 과거의 `raw/refs/heads/이전이름` 다운로드 대신 새 보고서의 다운로드 링크를 사용하세요.

원본 코드 소개·논문·저작권은 [UPSTREAM.md](UPSTREAM.md)에 보존했습니다. 이 재구성은 계산을 다시 실행하거나 기존 solver의 물리 코드를 바꾸지 않습니다. 보관된51개 ZIP의 바이트와 SHA256을 비교해 유지 여부를 확인했습니다. 새 그림은 이미 저장된 진단만 후처리했습니다.

`voltage scan`은 100·250·300V를 따로 컴파일·계산하고 체크포인트·중단을 관리하는 코드 브랜치의 작업명이었습니다. 조건별 결과는 results 브랜치에서 봅니다. 40mm 계산에 사용한 추가 진단 소스는 해당 실행의 source ZIP에 포함되어 있습니다.
