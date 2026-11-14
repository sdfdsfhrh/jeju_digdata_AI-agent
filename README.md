# 닿는제주

제주 여행지를 휠체어·유아차·보행약자의 조건으로 찾아보고, 화장실·주차·경사 정보를 **원본 근거와 함께** 확인하는 프로그램입니다. 제주데이터허브가 핵심·필수 데이터이며, 한국관광공사 무장애 여행 정보는 보조 출처입니다. 시설 조건·순위·이용 판단은 Python 규칙으로 계산하고, 선택적으로 LLM이 문장 해석과 설명을 맡습니다.

> 제출용 초안 · 2026-11-07. 현재 통합 221곳, 상세 판정 대상 122곳, 색인만 99곳. ‘가능’은 원문에 이용 가능한 일부 구간 근거가 있다는 뜻이며 전체 코스의 안전 보장이 아닙니다. 기능 추가는 종료하고 검증·문서 보완만 진행합니다.

데이터 출처: 제주특별자치도·제주데이터허브, 한국관광공사, 기상청(공공누리 제1유형)

## 설치

Windows 10/11, Python 3.10 이상(개발 PC Python 3.13), Chrome/Edge를 권장합니다. GPU·한글 프로그램은 필요하지 않습니다. 압축 파일은 먼저 풀고, `cli.py`, `build_db.py`, `app.py`가 있는 폴더에서 PowerShell을 엽니다.

```powershell
python --version
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

이후 명령의 `python`은 위 가상환경 Python을 사용합니다. 활성화하려면 `.venv\Scripts\Activate.ps1`을 실행합니다. 실행정책으로 활성화가 막히면 정책 변경 없이 `.venv\Scripts\python.exe cli.py --check`처럼 전체 경로로 실행할 수 있습니다.

## .env 설정

```powershell
Copy-Item .env.example .env
notepad .env
```

처음 만들 때만 복사합니다. 기존 `.env`가 있으면 덮어쓰지 마세요. 모두 빈 키로 두어도 DB 기반 규칙 판정이 동작합니다.

| 변수 | 의미 |
|---|---|
| `LLM_PROVIDER` | `none` / `openai` / `gemini` / `claude` |
| `LLM_API_KEY` | 선택한 제공자의 API 키. 코드·문서·캡처에 넣지 않음 |
| `LLM_MODEL` | 비우면 제공자별 기본 모델 사용 |
| `LLM_TIMEOUT` | 기본 20초 |
| `LLM_DAILY_LIMIT` | 공란 또는 0은 제한 없음. 양수일 때만 일일 호출 제한 |
| `LLM_USD_KRW` | 추정비용 환산용 가정 환율, 기본 1400. 실시간 환율 아님 |
| `KMA_SERVICE_KEY` | 공공데이터포털 단기·중기예보 일반 인증키(Decoding) |
| `KTO_SERVICE_KEY` | 관광공사 무장애 API 인증키(Decoding), 수집할 때 사용 |
| `DB_PATH`, `EXTRA_DIR` | 공란이면 기본 DB·보조자료 경로 사용 |

API 키는 프로젝트의 `.env`에서 읽습니다. `python setup_keys.py --key LLM_API_KEY`처럼 숨김 입력으로 저장할 수 있습니다. 키를 수정한 뒤 CLI를 새로 실행하고 Streamlit 서버를 재시작하세요. 월 비용 상한·차단 기능은 없으며 호출 수·토큰 추정 비용만 참고 표시합니다. 자세한 발급·비용은 [키 안내](docs/API_KEY_GUIDE.md)를 보세요.

## 데이터 준비·DB 점검

제주데이터허브 2019~20 원본의 현장 사진 524장은 판정에 쓰지 않고(개수만 기록), 용량과 개인정보 노출 가능성 때문에 제출물에서 제외했습니다. 원본은 제주데이터허브에서 받을 수 있습니다.

기획서는 별도 제출

제출본에는 허브 공개 원본(`data/raw`), 관광공사 저장 CSV·주차장 CSV(`data/extra`), 전처리 표(`output/csv`), catalog 없는 DB(`output/jeju_bf.sqlite`)가 들어 있어 설치 후 바로 실행할 수 있습니다. catalog.xlsx와 그 파생 자료, 실제 .env와 캐시는 포함하지 않습니다.

DB를 다시 만들 때만 다음 명령을 실행합니다.

```powershell
python build_db.py --no-catalog
```

공개 페이지를 확인한 출처 메타데이터는 `docs/data_sources.csv`에 사용자가 직접 기입합니다. 현재는 실제 사용한 허브 자료 5종의 행이 있으며 사용자 확인 메타데이터를 보존하고, 빈 값은 추정하지 않습니다. catalog 목록에서 복사하지 마세요. 원본 행에 있는 기준일은 그대로 유지합니다. DB가 이미 있으면 재빌드할 필요가 없습니다.

`python cli.py --check`는 키가 있으면 외부 API를 실제 호출합니다. 키가 없으면 규칙 판정으로 실행합니다. 제출 ZIP을 다시 만들려면 `python make_submission.py`를 실행합니다. 데이터별 처리 방식·출처·이용조건은 [데이터 명세](docs/DATA_SPEC.md)를 확인하세요.

## 실행

```powershell
python cli.py "한림공원 휠체어로 갈 수 있어?"
python cli.py "내일 오후 휠체어로 화장실 있는 해안 산책로" --no-llm
python launch_app.py
```

`run_app.bat` 더블클릭도 가능합니다(가상환경을 활성화한 터미널에서 실행하면 해당 Python 사용). 기본 주소는 **http://localhost:18766**입니다. 사용 중이면 오류 안내가 나오며 `python launch_app.py --port 18767`로 바꿀 수 있습니다. 서버를 끝낼 때 터미널에서 Ctrl+C를 누릅니다. `--no-llm`은 LLM만 끄므로 기상청 키가 있으면 날씨는 계속 조회합니다.

## 폰 접속

PC와 폰을 같은 Wi-Fi에 연결합니다. PC에서 `ipconfig`로 현재 연결의 IPv4 주소를 확인하고, 폰 브라우저에 `http://<PC IPv4>:18766`을 입력합니다. 포트를 바꿨다면 같은 포트를 씁니다. Windows 방화벽이 묻는다면 신뢰하는 사설 네트워크에서만 해당 앱 접속을 허용합니다. 외부 인터넷 공개·로그인 기능은 제공하지 않습니다. 센터 보안망에서는 내부망 접근 허용 여부를 담당자에게 확인하세요.

## 자주 나는 오류

| 증상 | 확인·해결 |
|---|---|
| `python` 또는 모듈을 찾지 못함 | Python 설치·현재 폴더·가상환경 확인, 같은 Python으로 `-m pip install` |
| DB 없음 | 제출 DB 압축 해제 확인, 필요하면 `python build_db.py --no-catalog` |
| 공개 출처표 미입력 | 그대로 실행 가능. 원본에 없는 번호·기준일은 미확인 |
| `PermissionError` | 결과 CSV를 연 Excel·DB 도구를 닫고 재실행 |
| zip 자료가 읽히지 않음 | 압축 내부 탐색만 하지 말고 실제 폴더로 풀기 |
| 파일 연결 검토·부분성공 | `output/review/` 확인. 양식·장소명·범례에 없는 값은 자동 보완하지 않음 |
| 포트 사용 중 | 기존 앱 확인 또는 `python launch_app.py --port 18767` |
| API 오류·지연 | 키 신청/승인·한도·네트워크/DLP 확인. 규칙 대체·날씨 미확인 안내 확인 |
| 키를 바꿨는데 그대로 | .env 저장 여부와 서버 재시작 확인 |
| 지도 배경이 안 보임 | 브이월드 키/실제 등록 URL·외부 연결 확인. 브이월드→기존 CARTO light→OSM 순으로 자동 대체, 모두 차단되면 목록·근거 표로 확인(API_KEY_GUIDE/LIMITS 참조) |
| 폰 연결 안 됨 | Wi-Fi·PC IPv4·실제 포트·사설망 방화벽 확인 |

## 문서·검증

- [사용자 매뉴얼](docs/USER_MANUAL.md)
- [API 키·추정 비용](docs/API_KEY_GUIDE.md)
- [데이터 활용 명세](docs/DATA_SPEC.md)
- [오류·제약사항](docs/LIMITS.md)

회귀 검증: PowerShell에서 `Get-ChildItem validate*.py | ForEach-Object { python $_.Name; if ($LASTEXITCODE -ne 0) { throw "검증 실패: $($_.Name)" } }`. 검증에는 로컬 원본·DB가 필요하며, 모의 API 검사와 실제 호출 검사는 구분합니다. 민감정보·원본이 포함될 수 있는 로컬 검증 산출물은 공개하지 않습니다.

화면은 Streamlit1.66.1 이상이 필요합니다(개발 PC에서1.66.1 검증). 검색창의 Enter/파란 화살표로 실행하며 누구와·언제 칩을 고르면 문장보다 우선합니다. 자세한 화면 안내는 USER_MANUAL의 지도 앱 화면 절 참조. 제출본의 `.streamlit/config.toml`도 함께 유지하세요.

## 데이터 이용조건

| 데이터 | 이용조건 | 지키는 방법 |
|---|---|---|
| 제주데이터허브 5종 | 상세 페이지에 별도 표시 없음 → 공공데이터의 제공 및 이용 활성화에 관한 법률·시행령에 따름(대회 Q&A 답변) | 화면·문서에 출처 표시, 전처리·적재 방식 명시 |
| 기상청 단기·중기예보 | 공공누리 제1유형(출처표시) | 날씨 옆과 화면 하단에 출처 표시 |
| 관광공사 무장애 여행 정보 | 이용허락범위 제한 없음 | 출처 표시 |
| 전국주차장정보표준데이터 | 이용허락범위 제한 없음 | 출처 표시 |
| 브이월드 지도·검색 | 브이월드 오픈API 이용약관 | 지도에 © 국토교통부 브이월드 표시 |

대회 제공 데이터 목록(catalog.xlsx)은 제3자 배포 제한 자료이므로, 그 내용이 들어간 파일과 DB는 제출물에서 모두 제외했습니다.

## AI 활용 범위

| 단계 | 사용한 AI | 활용 범위 |
|---|---|---|
| 서비스 실행 | OpenAI gpt-6-luna (교체: gemini-3.5-flash-lite, claude-haiku-5-5) | 질문 해석, 결과 설명 문장. 판정·순위 계산에는 쓰지 않음 |
| 기획·설계 | 참가자 · Anthropic Claude 보조 | 참가자가 주제·데이터 구조·화면 설계, Claude는 문서·기획서 초안 보조 |
| 구현·검증 | OpenAI Codex | 코드 작성·수정, 검증 스크립트 실행 |
| 검토·결정 | 참가자 | 데이터·이용조건 확인, 판단 규칙 결정, 화면 캡처 및 결과 검토 |

## 외부 API

국토교통부 브이월드(WMTS 배경지도, 장소 검색) / 한국관광공사(KorWithService2, KorService2) /
기상청(단기예보, 중기 육상예보·기온예보) / LLM 선택(OpenAI, Google Gemini, Anthropic) / 배경지도 대체(CARTO, OpenStreetMap)
