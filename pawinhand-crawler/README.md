# 포인핸드 최근 3개월 보호동물 데이터 수집

반려동물 입양 추천 시스템의 데이터 확보를 위한 수집 모듈입니다. [포인핸드 보호동물 목록](https://pawinhand.kr/shelter/animal)의 **최근 3개월 · 모든 지역 · 모든 동물 · 전체 상태** 조회 결과를 수집하고, 공고별 주요 정보와 원본 응답을 JSON으로 저장합니다.

이 디렉터리에는 수집 코드, 실행 방법, **2026-06-26~2026-09-26 기간의 공고 22,374건**가 포함되어 있습니다. 이미 저장된 데이터를 분석하려면 재수집 없이 [데이터 읽기](#데이터-읽기)를 참고하세요.

## 데이터 개요

| 구분 | 값 |
|---|---|
| 수집 실행일 | 2026-09-26 |
| 조회 기간 | **2026-06-26 ~ 2026-09-26 (최근 3개월)** |
| 조회 조건 | 모든 지역 · 모든 동물 · 전체 상태 |
| 전체 건수 | **22,374개 공고** |
| 동물 종류 | 개 13,589건 / 고양이 8,265건 / 기타 520건 |
| 중복 기준 | 공고번호 `notice_id` |
| 실제 등록날짜 범위 | 20260626 ~ 20260926 |
| 데이터 파일 | **23개**, 22개 × 1,000건 + 마지막 374건 |

**한 레코드는 한 개의 공고입니다.** 같은 동물이 다른 공고번호로 재공고될 수 있으므로 22,374마리의 서로 다른 동물이라고 단정하지 않습니다. `animals-0001.json`은 날짜별·지역별 구분이 아니라 공고번호 순으로 정렬한 결과의 첫 1,000건입니다. 파일 번호는 수집일이나 API 페이지 번호가 아닙니다.

전체 상태로 수집했으므로 모두 현재 입양 가능한 동물은 아닙니다. 실제 저장된 상태 분포는 아래와 같습니다. 아래 수치는 2026-09-26 수집 시점의 원본 상태입니다.

| `status_raw` | 건수 |
|---|---:|
| 보호중 | 7,932 |
| 종료(반환) | 2,513 |
| 종료(입양) | 4,118 |
| 종료(자연사) | 5,001 |
| 종료(안락사) | 1,576 |
| 종료(방사) | 442 |
| 종료(기증) | 792 |

추천 후보를 만들 때는 상태를 따로 검토해야 하며, 수집 데이터 자체에서는 종료 공고를 삭제하지 않았습니다.

## 파일 구성

```text
pawinhand-crawler/
├── crawler.py              # 최근 3개월 전체 수집 코드
├── requirements.txt        # 실행에 필요한 라이브러리
├── README.md               # 코드·데이터 설명과 실행 방법
└── data/three_months/
    ├── animals-0001.json   # 1,000개 공고
    ├── ...
    └── animals-0023.json   # 마지막 374개 공고
```

데이터 JSON 23개를 모두 읽으면 공고 22,374건입니다. 파일은 공고번호 순으로 1,000건씩 나눈 하나의 데이터셋이며, 날짜별·지역별로 나눈 파일이 아닙니다. requirements.txt는 실행 환경 설치에 필요합니다.

## 데이터 사전

각 `animals-*.json`의 최상위는 배열 `[...]`이며, 배열 안의 객체 `{...}` 하나가 공고 하나입니다. 다음 표는 각 객체에 저장한 **모든 최상위 필드**입니다.

| 필드 | 의미 / 형식 | 실제 값 예시 또는 설명 |
|---|---|---|
| `notice_id` | 공고번호 문자열, 중복 판단 기준 | `강원-강릉-2026-00178` |
| `source` | 수집 출처 | `pawinhand` |
| `source_url` | 포인핸드 상세 화면 URL | 공고번호를 URL 인코딩해 연결 |
| `collection_scope` | 수집 조건 설명 | 최근 3개월 · 모든 지역 · 모든 동물 · 전체 상태 |
| `period_start` | 조회 시작일, YYYY-MM-DD | `2026-06-26` |
| `period_end` | 조회 종료일, YYYY-MM-DD | `2026-09-26` |
| `collected_at` | 이 레코드를 받은 시각, UTC ISO 8601 | `2026-09-26T08:54:00.230911+00:00` |
| `registration_date` | 사이트의 등록날짜, YYYYMMDD 문자열 | `20260626` |
| `species` | 동물 종류 | 개 / 고양이 / 기타 |
| `breed` | 종류를 포함한 품종 원문 | `[개] 믹스견` |
| `sex_raw` | 성별 원본 코드 | 포함된 데이터에 M / F / Q 존재 |
| `neutered_raw` | 중성화 원본 코드 | 포함된 데이터에 N / U / Y 존재 |
| `age_raw` | 출생연도·나이 표기 원문 | `2017(년생)` — 현재 나이를 계산한 숫자가 아님 |
| `weight_raw` | 단위를 포함한 체중 원문 | `20(Kg)` — 숫자형으로 변환하지 않음 |
| `color` | 털색 원문 | `갈색&검정&흰색` |
| `status_raw` | 처리 상태 원문 | `보호중`, `종료(반환)` 등 |
| `special_mark` | 특이사항 원문 | `내장칩 있음, 보더콜리 믹스` |
| `notice_start` | 공고 시작일, YYYYMMDD | `20260627` |
| `notice_end` | 공고 종료일, YYYYMMDD | `20260707` |
| `found_location` | 발견장소 원문 | `주문진읍 시장3길 4-3` |
| `shelter_name` | 보호센터명 | `강릉시 동물사랑센터` |
| `shelter_address` | 보호센터 주소 | 사이트 기록 그대로 |
| `shelter_tel` | 보호센터 전화번호 문자열 | `033-641-7515` |
| `office_name` | 관할기관 | `강원특별자치도 강릉시` |
| `image_urls` | 사진 주소의 배열 | 주소만 저장, 사진 파일은 미포함 |
| `raw` | 같은 공고의 서버 원본 응답 객체 | 출처 확인·추후 재가공용 |
| `schema_version` | 저장 형식 버전 | 현재 `3` |

`*_raw` 필드는 수집 시 해석·변환하지 않은 원본 값입니다. 성별·중성화 코드도 지금 파일에는 한국어로 변환하지 않고 저장했습니다. 코드 의미를 사용하는 후속 전처리에서는 원본 화면과 대조한 매핑을 별도로 관리하세요.

### 원본 응답 보존

상위 필드는 사용하기 편하도록 이름을 정리한 값이고, `raw`는 **같은 공고의 원본**입니다. 예를 들어 `notice_id`는 `raw.notify_number`, `special_mark`는 `raw.feature`, `status_raw`는 `raw.state`에서 가져왔습니다. 정보가 두 곳에 보인다고 두 마리나 두 공고가 있는 것은 아닙니다.

원본에는 상위에 꺼내지 않은 `city`, `country`, `s_breeds`, `office_tel`, 조회·댓글 관련 숫자, 추가 정보 항목 등도 보존되어 있습니다. `raw.w_date` 등 사이트 내부 필드의 뜻을 구조일·행동 관찰일로 추정하지 않습니다. 바로 분석할 때는 상위 필드를 사용하고, 원본 확인이 필요할 때 `raw`를 봅니다.

### 날짜·누락값·성격 정보 해석

- `period_start/end`는 **조회 기간**, `registration_date`는 **사이트 등록날짜**, `notice_start/end`는 **공고 기간**, `collected_at`은 **수집 시각**입니다. 서로 같은 뜻이 아닙니다.
- UTC 시각에 9시간을 더하면 한국시간입니다. 구조 시각이나 보호소의 실제 행동 관찰 시각으로 쓰지 않습니다.
- `null`은 해당 값이 제공되지 않았다는 뜻입니다. 0, 건강함, 중성화 미완료, 성격 문제 없음 등으로 바꾸지 않습니다.
- `special_mark`에는 성격뿐 아니라 건강·외모·발견 상황·식별 정보가 섞여 있습니다. 성격 태그나 검증된 행동 평가가 아닙니다. 성격 설명이 없으면 미확인으로 다뤄야 합니다.

## 데이터 읽기

이미 수집된 데이터를 읽기 위해 크롤러를 다시 실행할 필요는 없습니다. 이 README가 있는 디렉터리에서 다음 Python 코드를 실행합니다. 추가 라이브러리는 필요하지 않습니다.

```python
import json
from pathlib import Path

folder = Path('data/three_months')
animals = []
for path in sorted(folder.glob('animals-*.json')):
    animals.extend(json.loads(path.read_text(encoding='utf-8')))

print(len(animals))  # 포함된 데이터: 22374
print(animals[0]['notice_id'])
print(animals[0]['special_mark'])
```

## 설치

Python 3.10 이상이 필요합니다. 아래 명령은 이 README가 있는 디렉터리를 기준으로 합니다.

### Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m playwright install chromium
```

### macOS / Linux

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m playwright install chromium
```

설치된 Chrome을 사용하려면 Chromium 설치를 생략하고 수집 명령에 `--channel chrome`을 추가할 수 있습니다. 이후 예시는 Windows 경로이며 macOS/Linux에서는 `.venv/bin/python`으로 바꿉니다.

## 최근 3개월 전체 수집 실행

저장소에 포함된 결과를 보존하도록 새 수집 결과는 별도 디렉터리에 저장합니다.

```powershell
.\.venv\Scripts\python crawler.py collect --output-dir data/new_run
```

`collect` 한 번으로 기간·필터 확인, 전체 페이지 수집, 상세 항목 저장, JSON 내보내기를 수행합니다. 실행 시점의 최근 3개월을 조회하므로 포함된 데이터와 기간·건수가 달라질 수 있습니다.

```powershell
# 중단한 실행 이어받기
.\.venv\Scripts\python crawler.py resume --output-dir data/new_run

# 실패 원인을 해결한 뒤 같은 위치부터 재시도
.\.venv\Scripts\python crawler.py retry --output-dir data/new_run

# 네트워크 요청 없이 저장 상태 확인 및 JSON 내보내기
.\.venv\Scripts\python crawler.py status --output-dir data/new_run
```

`resume`과 `retry`는 동일한 DB와 최초 조회 기간을 사용합니다. 완료한 실행 디렉터리에서 다시 `collect`를 호출하면 기존 결과를 유지합니다. 새 기간을 조회하려면 새로운 디렉터리를 지정합니다. 같은 디렉터리에 여러 프로세스를 동시에 실행하지 않습니다.

| 옵션 | 기본값 | 설명 |
|---|---|---|
| `--output-dir` | `data/three_months` | 결과 및 로컬 DB 디렉터리. 새 수집은 별도 경로 지정 권장 |
| `--channel` | 설치한 Chromium | `chrome` 또는 `msedge` 사용 가능 |
| `--delay` | `1.5` | 요청 간 대기 초. 최소 1초 |
| `--page-size` | `100` | 요청당 레코드 수. 1~100 |
| `--max-pages` | `5000` | 실행당 페이지 안전 상한. 도달 시 불완전 종료 후 재개 가능 |

## 수집 방식과 기간 검증

1. 브라우저에서 보호동물 목록을 열고 검색조건을 설정합니다.
2. 최근 3개월 검색을 체크하고 지역·축종·상태·성별·중성화를 전체로 설정합니다.
3. 실제 날짜 입력값·선택값과 검색 시 발생한 네트워크 요청의 조건을 대조합니다.
4. 시작일과 종료일이 달력상 3개월 간격인지 검사합니다.
5. 웹사이트가 사용하는 공개 JSON 요청을 페이지 단위로 조회하고 모든 행의 등록날짜가 해당 기간 안에 있는지 검사합니다.
6. 다음 위치에서 빈 응답을 두 번 확인하면 전체 페이지 수집을 완료합니다.

데이터 요청 주소는 `https://pawinhand.net/bridge/animals/condition`입니다. 포인핸드 웹사이트의 공개 응답을 사용하며 국가동물보호정보시스템 OpenAPI 호출은 포함하지 않습니다. 별도 API 키는 필요하지 않습니다.

목록 응답에 특이사항·나이·체중·보호센터 등 주요 상세 항목이 포함되어 있어 이를 저장합니다. 개별 상세 화면을 모두 방문하는 방식은 아닙니다. 상세 URL은 공고번호로 생성해 보존합니다. 댓글·태그·지원 혜택 등 상세 전용 정보와 사진 파일은 별도로 수집하지 않습니다.

## 중복 처리와 오류 복구

- 공고번호를 기본키로 사용합니다. 반복된 공고는 최신 응답으로 갱신하며 중복 응답 수를 기록합니다.
- 페이지 데이터와 다음 수집 위치를 하나의 SQLite 트랜잭션으로 저장합니다.
- 실패 페이지를 건너뛰지 않고 중단합니다. 네트워크 오류는 최대 3회 시도하며, 401/403/429는 즉시 중단합니다.
- 오류 원인은 `failures.json`과 `crawler.log`에 기록합니다. 원인 해결 후 `resume` 또는 `retry`로 이어받습니다.
- 동일 공고만 반복되는 페이지는 무한 반복으로 간주해 중단합니다.

## 코드 구성

| 함수 | 역할 |
|---|---|
| `bootstrap()` / `validate_proof()` | 실제 검색조건 적용 및 기간·요청 일치 검증 |
| `fetch()` | 공개 응답 페이지 조회, 요청 간격 및 재시도 |
| `validate_rows()` / `record()` | 등록날짜·필수 필드 검사, 저장 형식 구성 |
| `save_page()` | 중복 처리, 페이지 데이터·재개 위치 저장 |
| `export_data()` | 1,000건 단위 JSON과 목차·진행·실패 기록 생성 |

## 새 수집 실행 시 생성되는 파일

새 수집을 실행하면 지정한 출력 디렉터리에 공고 JSON 외에도 `state.sqlite3`(이어받기 DB), `crawler.log`(로그), `manifest.json`(건수·완료 여부·파일 목록), `filter-proof.json`(기간 확인), `requests.json`(요청 기록), `progress.json`(진행 상태), `failures.json`(오류)이 생성됩니다. 이 파일들은 실행 관리에 사용되며, 저장소에 포함된 기존 데이터는 공고 JSON 23개입니다.

수집 성공 여부는 실행 결과의 `manifest.json`에서 `complete=true`, `collection_complete=true`, `unique_count=exported_count`를 확인하고 `failures.json`이 빈 배열인지 확인합니다. 이어받기에는 동일한 실행 디렉터리의 SQLite가 필요합니다.

## 데이터 해석과 한계

- 수집 완료는 지정 조건의 공개 조회 결과를 마지막 페이지까지 읽었다는 의미입니다. 서버 전체 DB와 대조한 누락 여부를 보증하지 않습니다.

