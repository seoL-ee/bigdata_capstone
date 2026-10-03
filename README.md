# Big Data Capstone

보호동물의 기본정보, 행동·생활 특성, 사용자·가구의 양육 조건을 함께 고려하는
**보호동물 장기 생활 적합성 추천 시스템**을 개발하는 캡스톤 프로젝트입니다.

단순 선호 기반 추천이 아니라, 정보의 결측과 불확실성을 구분하고
추천 근거와 추가로 확인해야 할 정보를 함께 제공하는 것을 목표로 합니다.

## Repository Structure

```text
bigdata_capstone/
├─ src/
│  ├─ pawinhand/               # PawInHand 수집·정제
│  ├─ rescuegroups/            # RescueGroups 수집·정제
│  ├─ national_api/            # 국가동물보호정보 API
│  ├─ extraction/              # 텍스트 → 행동/생활 feature 추출
│  ├─ profile/                 # User / Animal Profile, Evidence
│  ├─ recommendation/          # filtering, CBF, ranking
│  └─ evaluation/              # extraction / recommendation 평가
├─ data/
│  ├─ pawinhand/
│  ├─ rescuegroups/
│  └─ national_api/
├─ results/
├─ docs/
├─ tests/
├─ requirements.txt
└─ .env.example
```

외부 데이터는 source별로 `raw/`와 `processed/`를 분리해 관리합니다.
API Key, `.env`, RescueGroups raw/processed 데이터는 Git에 포함하지 않습니다.

## Setup

Windows PowerShell 기준:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

필요한 API Key는 개인 `.env`에 설정합니다.

## Data Reproduction

RescueGroups 데이터는 저장소에서 원본을 공유하지 않고,
각 팀원이 자신의 API Key로 동일한 수집·전처리 코드를 실행하여 생성합니다.

> 아래 환경 설정과 재현 명령은 PR #7의 `requirements.txt`, `.env.example`,
> `.gitignore`, `src/rescuegroups/`가 병합된 뒤 사용할 수 있습니다.

```powershell
.\.venv\Scripts\python.exe .\src\rescuegroups\collect.py --species dogs --all
.\.venv\Scripts\python.exe .\src\rescuegroups\collect.py --species cats --all
.\.venv\Scripts\python.exe .\src\rescuegroups\prepare_analysis.py `
  --dogs-snapshot data\rescuegroups\raw\dogs_available_all_<timestamp>.json `
  --cats-snapshot data\rescuegroups\raw\cats_available_all_<timestamp>.json
```

API가 live dataset이므로 발표·실험에 사용한 기준 데이터는 snapshot metadata로 별도 기록합니다.

## Docs

- [시스템 설계](docs/시스템_설계.md)
- [구현 로드맵](docs/구현_로드맵.md)
- [데이터 수집 및 재현 가이드](docs/데이터_수집_및_재현_가이드.md)
