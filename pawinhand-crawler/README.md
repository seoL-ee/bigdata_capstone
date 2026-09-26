#포인핸드 보호동물 데이터 수집

반려동물 입양 추천 시스템에 사용할 **최근 3개월 보호동물 공고**를 수집합니다. 모든 지역·동물·처리 상태를 조회하며, 공고번호 기준으로 중복을 처리합니다.

## 수집 데이터

| 항목 | 내용 |
|---|---|
| 수집일 | 2026-09-26 |
| 조회 기간 | **2026-06-26 ~ 2026-09-26** |
| 규모 | **22,374개 공고**, JSON 23개 |
| 동물 종류 | 개 13,589건 · 고양이 8,265건 · 기타 520건 |
| 저장 위치 | `data/three_months/animals-*.json` |

각 파일은 공고번호 순으로 1,000건씩 나누었으며, 마지막 파일은 374건입니다. 날짜별·지역별 파일이 아니므로 **23개 파일을 함께 읽습니다.**

한 레코드는 동물 한 마리가 아닌 **공고 하나**입니다. 재공고와 입양·반환 등 종료된 공고도 포함되므로 추천에 사용할 때는 상태를 확인해야 합니다.

## 파일 구성

```text
pawinhand-crawler/
├── crawler.py          # 수집·중복 처리·오류 복구
├── requirements.txt    # 실행 라이브러리
├── README.md
└── data/three_months/
    ├── animals-0001.json
    ├── ...
    └── animals-0023.json
```

## 설치 및 실행

Python 3.10 이상이 필요합니다. 터미널에서 `pawinhand-crawler` 폴더로 이동한 뒤 실행합니다.

**Windows PowerShell**

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m playwright install chromium
.\.venv\Scripts\python crawler.py collect --output-dir data/new_run
```

<details>
<summary>macOS / Linux 설치 및 실행</summary>

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m playwright install --with-deps chromium
.venv/bin/python crawler.py collect --output-dir data/new_run
```

</details>

실행 시점의 **최근 3개월 전체 조회 결과**를 수집합니다. 저장소에 포함된 데이터를 보존하기 위해 새 결과는 `data/new_run`에 저장합니다.

완료된 폴더에서 다시 실행하면 재수집하지 않습니다. 새로운 시점의 데이터를 수집하려면 `--output-dir`에 다른 폴더를 지정하세요.

### 중단·실패 시

```powershell
# 중단한 위치부터 이어받기
.\.venv\Scripts\python crawler.py resume --output-dir data/new_run

# 실패 원인을 해결한 뒤 재시도
.\.venv\Scripts\python crawler.py retry --output-dir data/new_run

# 저장 상태 확인 및 JSON 내보내기 (네트워크 요청 없음)
.\.venv\Scripts\python crawler.py status --output-dir data/new_run
```

`resume`과 `retry`는 기존 폴더의 `state.sqlite3`와 최초 조회 기간을 사용합니다. 같은 폴더에서 여러 수집을 동시에 실행하지 마세요.

## 데이터 읽기

기존 데이터를 분석할 때는 재수집이나 추가 라이브러리 설치가 필요하지 않습니다. `pawinhand-crawler` 폴더에서 다음 Python 코드를 실행합니다.

```python
import json
from pathlib import Path

animals = []
for path in sorted(Path('data/three_months').glob('animals-*.json')):
    animals.extend(json.loads(path.read_text(encoding='utf-8')))

print(len(animals))  # 22374
print(animals[0]['notice_id'])
print(animals[0]['special_mark'])
```

주요 항목은 공고번호(`notice_id`), 품종(`breed`), 상태(`status_raw`), 특이사항(`special_mark`), 보호센터(`shelter_name`), 사진 주소(`image_urls`)입니다.

<details>
<summary>전체 데이터 항목 보기</summary>

각 JSON 파일은 배열이며, 객체 하나가 공고 하나입니다.

| 필드 | 설명 |
|---|---|
| `notice_id` | 공고번호 · 중복 판단 기준 |
| `source`, `source_url` | 출처 및 상세 화면 주소 |
| `collection_scope` | 조회 조건 |
| `period_start`, `period_end` | 조회 시작·종료일 (`YYYY-MM-DD`) |
| `collected_at` | 수집 시각 (UTC ISO 8601) |
| `registration_date` | 사이트 등록날짜 (`YYYYMMDD`) |
| `species`, `breed` | 동물 종류 및 품종 원문 |
| `sex_raw`, `neutered_raw` | 성별·중성화 원본 코드 |
| `age_raw`, `weight_raw` | 출생연도·나이 표기 및 체중 원문 |
| `color` | 털색 |
| `status_raw` | 보호중·종료(입양) 등 처리 상태 |
| `special_mark` | 특이사항 원문 |
| `notice_start`, `notice_end` | 공고 시작·종료일 (`YYYYMMDD`) |
| `found_location` | 발견장소 |
| `shelter_name`, `shelter_address`, `shelter_tel` | 보호센터 이름·주소·전화번호 |
| `office_name` | 관할기관 |
| `image_urls` | 사진 URL 배열 (사진 파일은 미포함) |
| `raw` | 같은 공고의 전체 원본 응답 |
| `schema_version` | 저장 형식 버전 (`3`) |

`*_raw`는 해석·변환하지 않은 값입니다. `raw`는 별도 공고가 아니라 같은 공고의 원본이며, `null`은 값이 제공되지 않았음을 뜻합니다.

</details>

## 코드 동작

1. Playwright로 [포인핸드 목록](https://pawinhand.kr/shelter/animal)의 최근 3개월·전체 검색조건을 설정합니다.
2. 화면의 날짜·필터와 실제 요청이 일치하는지 검증합니다.
3. 사이트의 공개 JSON 응답을 페이지별로 수집하고 등록날짜를 검사합니다.
4. 공고번호를 기준으로 SQLite에 저장하고, 다음 위치에서 빈 응답을 두 번 확인하면 완료합니다.
5. 공고를 1,000건 단위 JSON 파일로 내보냅니다.

목록 응답에 특이사항·체중·보호센터 등 상세 항목이 포함되어 있어 개별 상세 화면을 모두 방문하지 않습니다. 국가동물보호정보시스템 OpenAPI를 사용하는 코드는 아닙니다.

| 주요 함수 | 역할 |
|---|---|
| `bootstrap`, `validate_proof` | 검색조건 설정 및 기간 검증 |
| `fetch` | 페이지 조회 및 네트워크 오류 재시도 |
| `validate_rows`, `record` | 응답 검사 및 데이터 정리 |
| `save_page` | 공고번호 중복 처리 및 재개 위치 저장 |
| `export_data` | JSON 파일과 실행 기록 생성 |

## 실행 결과와 오류 확인

새로 수집하면 공고 JSON 외에 실행 관리 파일이 생성됩니다. 저장소에 제공된 데이터는 공고 JSON 23개이며, 아래 파일은 새 실행 시 만들어집니다.

| 파일 | 용도 |
|---|---|
| `manifest.json` | 완료 여부·건수·결과 파일 목록 |
| `crawler.log`, `failures.json` | 실행 로그 및 수집 중 오류 |
| `state.sqlite3` | 중단 후 이어받기에 필요한 DB |
| `filter-proof.json`, `requests.json`, `progress.json` | 검색조건·요청·진행 기록 |

성공 여부는 `manifest.json`의 `collection_complete`가 `true`인지 확인합니다. 오류가 나면 로그와 터미널 메시지를 확인한 뒤 재시도하세요. **초기 브라우저 실행·검색조건 설정 단계에서 실패하면 `failures.json`이 생성되지 않을 수 있습니다.**

네트워크 오류는 최대 3회 시도하며, 실패한 페이지를 건너뛰지 않습니다. HTTP 401·403·429 응답은 즉시 중단합니다.

## 데이터 사용 시 참고

- `special_mark`는 성격뿐 아니라 건강·외모·발견 상황이 섞인 원문이며, 검증된 성격 평가가 아닙니다.
- 조회 기간, 사이트 등록날짜, 공고 기간, 수집 시각은 서로 다릅니다.
- 전체 수집은 지정 조건의 공개 조회 결과를 끝까지 읽었다는 의미입니다. 수집 도중 공고가 추가·삭제되면 목록이 바뀔 수 있습니다.
- 사이트 구조·응답이 변경되면 코드 점검이 필요합니다. 데이터 이용 시 원 출처의 이용조건을 확인하세요.
