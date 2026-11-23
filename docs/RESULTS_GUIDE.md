# 결과 목록·보고서·업로드 기준

저장소 첫 화면 `main/README.md`가 전체 실행 기록의 고정 북마크입니다. 결과 브랜치 첫 화면은 해당 공통 조건의 실행 기록입니다. 실행 링크를 누르면 조건·그림·다운로드가 있는 보고서로 들어갑니다.

## 브랜치

| 브랜치 | 역할 / 공통 조건 |
|---|---|
| main | 전체 결과 입구와 eduPIC 원본 코드 |
| results/75mTorr | 원본 10 Pa = 75.006168 mTorr, Ar350K,13.56MHz,250Vpeak,25mm,하부 RF/상부 접지 |
| results/20mTorr-topRF | Ar20mTorr,350K,13.56MHz,상부 RF/하부 접지. gap·전압은 실행별 기록 |
| simulation/20mTorr-topRF | 상부 RF·압력/전압 지정과 독립 실행·저장·중단을 위한 코드 작업. 기존 voltage scan 브랜치 |

조건군을 새로 만들 때에는 날짜가 없는 `results/조건군` 브랜치에 `results/family.json`을 추가합니다. 목록 갱신기는 이 파일이 있는 결과 브랜치를 자동으로 발견합니다. `main`에 대용량 결과를 중복 복사할 필요는 없습니다.

## 짧은 이름

- 실행 폴더: `YYMMDD_바꾼조건`. 날짜는 한국 시각의 실제 실행 시작일이며 보고서 정리일이 아닙니다.
- 예: `261119_gap25_V100-300`, `261120_gap40_V100-500`, `261118_measure120`.
- 파일명에서 조건군의 공통 가스·주파수·압력·전극 연결은 생략합니다. 전체 값은 보고서와 run.json에 남깁니다.
- 전압별 하위 폴더는 `100V/`, `250V/`처럼 간단히 씁니다. 내려받을 ZIP은 `261120_gap40_100V_core.zip`처럼 단독으로도 구분되게 합니다.
- 같은 날 같은 조건을 다시 실행하면 `_r2` 등으로 구분하고 seed·초기 상태를 기록합니다.
- `README.md`, `figures/heating.png`, `data/profiles.csv` 같은 역할 이름은 짧게 유지합니다.

## 보고서에 항상 포함할 내용

1. 조건: 기체·압력mTorr·온도·파형·주파수·전압peak/RMS·gap·전극 방향·면적 처리·표면/충돌 모델.
2. 이력: C/Cpp/Rust 계열, 정확한 소스 commit/SHA256, 초기화 또는 재시작 상태, 격자·시간간격·입자 가중치.
3. 판정: 실제 종료 이유, 총 RF, 평균 RF 구간, 중단 지표. 기준 충족·소멸·미완료·과도구간 진단을 구분.
4. 가능한 핵심 그림: 수렴/입자 수지, 평균 밀도, RF heating, 전위/전기장, 평균 에너지/이온화, EEPF/IEDF, 전극 flux/손실, 측정된 전력 채널.
5. 데이터가 없으면 표에 사유를 기록합니다. 빈 입자 상태를 정상 방전의 0밀도 측정으로 제시하지 않습니다.
6. 그림마다 평균 구간·단위·전극 방향을 표시합니다. 위상0은 cos 전압의 양의 최댓값입니다. 전압 간 비교 그림은 종별 공통 색상 범위, 상세 그림은 각 조건의 범위를 사용하고 차이를 설명합니다.
7. EEPF/IEDF 정규화 방식, heating의 정의, 전력의 기준 면적을 기록합니다. 정확한 가중치가 없으면 정규화 히스토그램의 단순 평균을 전체 사건 PDF라고 부르지 않습니다.
8. 요약·CSV·원시 자료·체크포인트·사용 소스를 직접 다운로드로 연결하고 현재 파일 크기·SHA256을 제공합니다.

각 진단에는 `data_status`를 `available`(자료 있음), `partial`(부분 자료), `unavailable`(미측정·미보존) 중 하나로 기록합니다. 자료가 있으면 해당 항목 아래에 그림이나 실제 상세 링크가 있어야 합니다. `unavailable`에는 `reason`으로 측정하지 못한 이유를 적습니다. “다른 곳에 있음”이라는 문장만으로 누락 검사를 통과시키지 않습니다. 등록 도구와 자동 목록 갱신은 8개 진단의 이 조건을 검사한 뒤 게시합니다.

[전체 결과 점검 기록](RESULT_AUDIT.md)에는 현재 보관된 자료로 채운 항목과 원래 최종 측정이 없는 항목을 구분했습니다.

기존75mTorr 자료는 원본상 하부 RF입니다. 20mTorr 결과의 상부 RF와 방향을 혼동하지 마세요. 기존75mTorr120RF의 equal_block_mean과40mm의 마지막20RF EEPF/IEDF는 서로 다른 통계 정의입니다.

## 새 결과 등록

저장된 데이터에서 그림과 수치를 만든 뒤 아래처럼 내보낼 폴더를 준비합니다. 이 단계는 새로운 PIC 계산을 시작하지 않습니다.

```text
EXPORT/
  run.json                 # 실행 조건·상태·그림·다운로드 목록
  README.md                # 도구가 생성 가능
  figures/heating.png
  data/profiles.csv
  261122_gap40_350V_core.zip
```

`scripts/results/run.example.json`을 복사해 실제 기록으로 채웁니다. 모든 핵심 항목이 아직 측정되지 않은 실행도 status를 정확히 쓰고 등록할 수 있습니다. 하위 전압별 보고서는 `100V/report.json`을 두고 부모 run.json의 cases에서 `100V/README.md`로 연결합니다.

```bash
python scripts/results/publish_run.py /path/to/EXPORT --branch results/20mTorr-topRF --push
```

등록 도구는 원본 폴더의 복사본에서 보고서·크기·SHA256을 만든 후 결과 브랜치에 올립니다. 이어 모든 조건 브랜치와 main의 목록을 갱신합니다. 기존파일을 수동으로 올렸거나 갱신을 다시 실행할 때는 다음을 사용합니다.

```bash
python scripts/results/catalog.py sync --push
```

GitHub Actions의 **Update simulation result catalogs**도 결과 push와 매시간 보조 일정에 따라 같은 갱신을 실행합니다. 수동 실행은 저장소 Actions 탭에서 할 수 있습니다. GitHub Actions가 꺼진 저장소에서도 위 업로드 명령이 직접 목록을 갱신합니다. 두 경로 모두 GitHub API 전용 토큰 없이 저장소 Git 쓰기 권한을 사용합니다.

자동 갱신은 run.json을 읽어 목록과 보고서를 작성합니다. 임의의 ZIP 하나에서 알 수 없는 압력·평균 구간을 추측하지 않으므로 **새 실행에는 run.json이 필요합니다**. 시뮬레이션은 업로드 도구나 Actions에서 자동으로 시작하지 않습니다.

## BRH·gap 스캔 템플릿

[BRH 진행·결과](https://github.com/YGLSNU/eduPIC_PAL_RF-sheath/blob/results/20mTorr-topRF/results/261123_BRH_gap25-120/README.md) · [BRH 진단·실행 설명](https://github.com/YGLSNU/eduPIC_PAL_RF-sheath/blob/simulation/20mTorr-topRF/scripts/brh_scan/README.md)

gap 스캔은 부모 `run.json`에 `scan_parameter: "gap_mm"`를 지정하고 cases에 `gap_mm`를 기록합니다. 하위 폴더는 `40mm/`처럼 짧게 씁니다. 표에는 gap이 표시되고 전압은 조건표에 남습니다. 선택 필드 `related_links: [{"label": "설명", "url": "METHOD.md"}]`로 관련 분석을 연결할 수 있습니다. BRH는 기본8개 진단에 왕복·위상·signed field work·충돌·표본 수 항목을 추가합니다. 진행 중이나 소멸한 조건에서 BRH 발생을 미리 결론내리지 않습니다.

## 재현·파일 무결성

- 현재 경로의 `files.json`이 재구성 후 파일 목록과 SHA256입니다.
- 기존 ZIP은 그대로 보존했고 이름만 줄였습니다. ZIP 내부의 원본 파일명·소스·재시작 상태는 기존 실행과 대응합니다.
- 과거 `*_manifest.json`, `*_checksums.sha256`은 당시 보관 기록이므로 지금 이름의 검증에는 files.json을 사용합니다. 원래 경로와 새 경로의 대응은 `docs/legacy-paths.json`에 있습니다.
- 체크포인트 재시작 시 사용한 소스·gap·입자 가중치를 함께 확인합니다. 원본 체크포인트에는 난수 상태와 이전 진단 누적값이 없습니다.
