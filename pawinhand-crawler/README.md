# 포인핸드 보호동물 데이터 수집

반려동물 입양 추천 시스템을 위한 수집 모듈입니다. **2026-09-30 기준 최근 3개월(2026-06-30~2026-09-30), 모든 지역·모든 동물·전체 상태**의 목록을 조회하고, 각 공고의 상세 페이지에서 기본 정보와 제공되는 성향·건강정보를 수집했습니다.

## 제공 데이터

| 항목 | 내용 |
|---|---|
| 목록 수집일 | 2026-09-30 |
| 상세 조회일 | 2026-10-01 |
| 조회 기간 | 등록날짜 기준 **2026-06-30~2026-09-30**, 양 끝 포함 |
| 전체 공고 / 상세 조회 성공 | **22,511건 / 22,511건** |
| 추가 성향·건강정보 제공 | **843건** |
| 추가 정보 미제공 | **21,668건** |
| 최종 실패 / 미처리 | **0건 / 0건** |
| 저장 위치 | `data/three_months/animals-0001.json` ~ `animals-0023.json` |

각 파일은 UTF-8 JSON 배열입니다. 앞의 22개 파일은 각각 1,000건, 마지막 파일은 511건으로, **23개 파일을 함께 읽어야 전체 데이터**가 됩니다. 공고번호(`notice_id`)는 중복 없이 저장되어 있습니다. 추가 정보가 있는 843건 모두가 성향·건강의 모든 항목을 채운 것은 아닙니다.

공고 상태 등은 상세 조회 시점의 값입니다. 입양 완료·안락사 등의 종료 상태도 포함하므로 추천 대상 선정 시 `status_raw`를 확인해야 합니다. 이 데이터는 자동 갱신되는 실시간 자료가 아닙니다.

## 파일 구성

```text
pawinhand-crawler/
├── crawler.py
├── requirements.txt
├── README.md
└── data/three_months/
    ├── animals-0001.json
    ├── ...
    └── animals-0023.json
```

## 데이터 읽기

재수집 없이 제공 데이터를 읽으려면 이 폴더에서 실행합니다.

```python
import json
from pathlib import Path

animals = []
for path in sorted(Path("data/three_months").glob("animals-*.json")):
    animals.extend(json.loads(path.read_text(encoding="utf-8")))

print(len(animals))  # 22511
with_extra = [a for a in animals if a["detail_status"] == "present"]
```

## 설치 및 수집 실행

Python 3.10 이상이 필요합니다. `crawler.py`가 있는 폴더에서 실행합니다. 아래는 Windows PowerShell 기준입니다.

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m playwright install chromium
```

**2026-09-30 기준 최근 3개월 전체 목록·상세 수집:**

```powershell
.\.venv\Scripts\python crawler.py collect --as-of 2026-09-30 --workers 3 --output data/run-2026-09-30
```

제공 데이터와 새 수집 결과가 섞이지 않도록 출력 폴더를 따로 지정했습니다. 전체 수집에는 `--limit`을 붙이지 않습니다. 먼저 시험하려면 아래 명령으로 30건을 수집합니다.

```powershell
.\.venv\Scripts\python crawler.py collect --as-of 2026-09-30 --limit 30 --output data/sample-30
```

- `--as-of`는 조회 종료일이며, 시작일은 3개월 전으로 계산합니다. 다른 날짜로 수집할 때는 새 출력 폴더를 사용합니다.
- 중단·실패 후 **같은 명령과 출력 폴더**로 실행하면 결과가 없는 공고만 재시도합니다. 성공한 공고는 다시 조회하지 않습니다.
- `--workers`는 동시 상세 방문 수(1~3, 기본 2), `--timeout 60`은 상세 응답 대기 시간을 늘리는 옵션입니다. 모든 화면 대기 시간에 적용되는 옵션은 아닙니다.
- 설치된 Chrome을 사용하려면 `--channel chrome`을 추가합니다. 이번 전체 수집은 Chrome으로 실행했습니다.
- macOS/Linux에서는 `.venv/bin/python`을 사용합니다. Linux는 브라우저 시스템 라이브러리 설치가 추가로 필요할 수 있습니다.
- 같은 출력 폴더에서 여러 수집 프로세스를 동시에 실행하지 마세요. 완료한 출력 폴더로 재실행해도 기존 성공 데이터의 상태가 갱신되지는 않습니다.

수집 시 JSON 외에 `state.sqlite3`(재개용), `crawler.log`·`failures.json`(오류), `report.json`(완료 여부), `filter-proof.json`(조회 조건)이 생성됩니다. **재개하려면 로컬의 `state.sqlite3`를 보관**해야 합니다. 배포 데이터에는 이 실행 관리 파일들을 포함하지 않았습니다. 전체 완료 기준은 `report.json`의 `complete: true`입니다.

## 데이터 항목

| 항목 | 설명 |
|---|---|
| `schema_version` | 데이터 형식 버전(2) |
| `notice_id`, `source_url` | 공고번호(기본키), 포인핸드 상세 URL |
| `list_position` | 최초 목록 수집 순서, 1부터 시작 |
| `period_start`, `period_end` | 목록 조회 기간 |
| `collected_at` | 해당 상세 정보 수집 시각(UTC) |
| `species`, `breed` | 동물 종류, 품종 |
| `sex_raw`, `neutered_raw` | 성별·중성화 원본 코드 |
| `age_raw`, `weight_raw`, `color` | 나이·체중 원문, 털색 |
| `status_raw` | 보호중·입양 완료 등 원본 처리 상태 |
| `registration_date` | 상세 응답의 등록날짜 (`YYYYMMDD`) |
| `notice_start`, `notice_end` | 공고 시작일·종료일 (`YYYYMMDD`) |
| `found_location`, `office_name` | 발견장소, 관할기관 |
| `shelter_name`, `shelter_address`, `shelter_tel` | 보호센터 이름·주소·전화번호 |
| `special_mark`, `animal_name` | 특이사항, 동물 이름 |
| `image_urls` | 중복 제거한 사진 주소(사진 파일 미포함) |
| `detail_status` | 추가 정보 제공 여부 |
| `personality.gauges` | 건강상태·활동성·사회성·친화도 원본 값 |
| `personality.tags`, `personality.comment` | 성향 태그 전체, 소개글 원문 전체 |
| `health.tests` | 파보·코로나·심장사상충·홍역 검사 원본 값 |
| `health.comment` | 접종·구충·치료 등 건강 기록 원문 전체 |

`detail_status`의 `present`는 추가 값 또는 태그가 제공된 경우, `not_provided`는 관련 응답을 정상 확인했지만 추가 정보가 없는 경우입니다. 수집 진행 중에는 `failed`·`pending`도 생길 수 있으나, **이번 배포 데이터에는 없습니다**.

`null`, 빈 문자열, 빈 배열·객체는 미입력 또는 정보 없음을 나타내며 건강함·검사 음성을 뜻하지 않습니다. 원본의 `aggression` 필드는 화면에서 **친화도**에 대응합니다. 소개글과 건강 기록은 원문을 보존하므로 기본 정보와 다른 시점의 체중 등이 포함될 수 있습니다.

## 수집 흐름과 코드 구성

1. `search`: 사이트 검색창에서 기간·지역·동물·상태를 적용하고 실제 요청 조건과 첫 페이지 표시 순서를 확인합니다.
2. `collect_list`: 목록 페이지를 끝까지 조회하고 공고번호로 중복을 처리합니다. 중복 공고만 나온 페이지도 다음 페이지로 진행합니다.
3. `visit_detail`: 공고별 상세 URL에 접속하여 기본·추가·태그 응답을 수집하고 화면 표시를 확인합니다. 추가 정보가 없으면 다음 공고로 넘어갑니다.
4. `normalize`: 특이사항·성향·건강정보를 공통 항목으로 정리합니다. 동일 내용을 원본 응답과 화면 텍스트 등 여러 형식으로 반복 저장하지 않습니다.
5. `export`: 처리 완료 순서와 무관하게 `list_position` 순서로 최대 1,000건씩 저장합니다.

접속 오류는 정보 없음과 구분해 기록합니다. HTTP 401·403·429 또는 작업자별 연속 3건 실패 시 실행을 중단합니다. 사진·영상 파일과 댓글·입양절차·입양지원 정보는 수집 대상에 포함하지 않습니다.

## 해석 시 유의사항

- 목록은 9월 30일, 상세는 10월 1일에 조회했습니다. 같은 시각의 고정된 서버 스냅샷은 아니며, 재실행 결과도 달라질 수 있습니다.
- `list_position`은 목록 수집 당시 사이트 표시 순서입니다. `registration_date`는 상세 조회 시점의 값이므로, 날짜순 분석이 필요하면 해당 필드로 별도 정렬합니다.
- 최종 데이터의 등록날짜는 모두 지정 기간 안에 있으며, 공고번호 중복·실패·미처리가 없는 것을 확인했습니다. 성향·건강 내용은 게시자의 기록이며 크롤러가 평가한 결과가 아닙니다.
