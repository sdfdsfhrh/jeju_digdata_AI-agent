# 닿는제주: 휠체어·유아차 여행 접근성 검증 AI Agent

휠체어·유아차로 제주 여행을 준비할 때 화장실·주차·경사 정보를 조사 원문과 함께 확인할 수 있습니다. 전체 221곳 중 상세 자료가 있는 122곳을 판정합니다.

[빠른 실행](#심사위원-빠른-실행-windows) · [키 입력](#메모장으로-키-넣기) · [자주 나는 오류](#자주-나는-오류) · [결과 설명자료](docs/RESULT_REPORT.md)

공개 데모는 규칙 모드로 실행됩니다. LLM을 활용한 질문 해석과 결과 설명은 평가용 키가 설정된 제출 ZIP에서 확인할 수 있습니다. [닿는제주 공개 데모](https://datneun-jeju.streamlit.app/)

## 심사위원 빠른 실행 (Windows)

Python 3.10 이상이 설치된 PC에서 실행하세요. 처음 패키지를 설치할 때는 인터넷 연결이 필요합니다.

1. 제출 ZIP을 압축 해제합니다. 파일 탐색기에서 `requirements.txt`와 `launch_app.py`가 보이는 폴더를 열고 위쪽 주소창의 경로를 복사합니다.
2. **Windows 키 + R**을 누르고 `cmd`를 입력한 뒤 Enter를 누릅니다.
3. 검은 창에서 아래 명령을 한 줄씩 실행합니다. 첫 줄의 따옴표 안에는 1번에서 복사한 경로를 넣으세요. 두 번째 줄의 설치가 끝나면 세 번째 줄을 실행합니다.

   ```cmd
   cd /d "압축을 푼 폴더의 실제 경로"
   python -m pip install -r requirements.txt
   python launch_app.py
   ```

4. 브라우저에 **닿는제주**가 열리면 실행 완료입니다. 자동으로 열리지 않으면 검은 창에 표시된 주소를 브라우저 주소창에 붙여넣으세요.

**평가용 키**는 `.env.eval`에 들어 있으면 자동으로 사용합니다. 키가 비어 있으면 규칙 모드로 실행합니다. 평가가 끝나면 키를 폐기합니다. [평가용 키 변경](#a-openai-키-평가용llm)

기상청·관광공사·브이월드 키는 ZIP에서 제외합니다. 제출 DB로 판정·추천이 가능하며, 날씨는 미확인으로 표시됩니다. 온라인이면 CARTO 또는 OpenStreetMap 배경을 사용합니다. 외부 위치 조회 결과는 키 설정에 따라 달라질 수 있습니다. [데이터 API 설정](docs/API_KEY_GUIDE.md)

## 메모장으로 키 넣기

### A. OpenAI 키 (평가용·LLM)
1. 압축을 푼 폴더에서 주소창에 cmd 를 입력하고 Enter → 검은 창(터미널)이 열립니다.
2. 아래를 입력하고 Enter:

   ```cmd
   notepad .env.eval
   ```

   "파일이 없습니다. 새로 만들까요?"가 나오면 [예]를 누르고 아래 세 줄을 그대로 적습니다.

   ```dotenv
   LLM_PROVIDER=openai
   OPENAI_API_KEY=
   LLM_DAILY_LIMIT=2000
   ```

3. OPENAI_API_KEY= 바로 뒤에 커서를 두고 Ctrl+V로 키를 붙여 넣습니다.
   띄어쓰기·따옴표 없이 붙여야 합니다. 예) OPENAI_API_KEY=sk-proj-xxxx
4. Ctrl+S로 저장하고 메모장을 닫습니다.
5. python launch_app.py 로 실행 → 화면에 "LLM 사용 중"이 보이면 성공입니다.
   "규칙 모드"로 보이면 3번에서 앞뒤 공백이나 줄바꿈이 들어갔는지 확인하세요.

### B. 데이터 API 키 (센터 담당자용: 기상청·관광공사·브이월드)
1. 같은 방법으로 notepad .env 를 엽니다. 없으면 .env.example 내용을 복사해 새로 만듭니다.
2. 각 항목 = 뒤에 발급받은 키를 Ctrl+V로 붙여 넣습니다.
3. Ctrl+S로 저장하고 닫은 뒤 앱을 다시 실행합니다.
   (키 발급 방법은 이 문서의 발급 절차 참고. python setup_keys.py 로 입력해도 됩니다.)

### 주의
- 메모장이 파일 이름을 ".env.eval.txt"로 바꾸지 않도록, 반드시 터미널에서 notepad .env.eval 로 여세요.
- 키를 화면 캡처·메일·채팅에 붙이지 마세요.

## 추가 설정

가상환경과 일반 실행용 키 설정은 [API 키 안내서](docs/API_KEY_GUIDE.md)와 [사용자 매뉴얼](docs/USER_MANUAL.md)을 참고하세요.

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

`run_app.bat` 더블클릭도 가능합니다(가상환경을 활성화한 터미널에서 실행하면 해당 Python 사용). 기본 주소는 **http://localhost:18766**입니다. 사용 중이면 오류 안내가 나오며 `python launch_app.py --port 18767`로 바꿀 수 있습니다. 서버를 끝낼 때 터미널에서 Ctrl+C를 누릅니다.

## 폰 접속

PC와 폰을 같은 Wi-Fi에 연결합니다. PC에서 `ipconfig`로 현재 연결의 IPv4 주소를 확인하고, 폰 브라우저에 `http://<PC IPv4>:18766`을 입력합니다. 포트를 바꿨다면 같은 포트를 씁니다. Windows 방화벽이 묻는다면 신뢰하는 사설 네트워크에서만 해당 앱 접속을 허용합니다. 외부 인터넷 공개·로그인 기능은 제공하지 않습니다. 센터 보안망에서는 내부망 접근 허용 여부를 담당자에게 확인하세요.

## Windows 환경 실행 안내

### 1. Python 및 라이브러리 설치

프로젝트 폴더에서 아래 명령으로 필요한 라이브러리를 설치합니다. 지원 Python 버전은 위의 빠른 실행 안내를 참고하세요.

```cmd
python -m pip install -r requirements.txt
```

### 2. 프로젝트 실행

같은 폴더에서 아래 명령으로 앱을 실행할 수 있습니다.

```cmd
python -m streamlit run app.py
```

### 3. Windows 보안 정책 관련 오류

일부 Windows 11 환경에서는 Smart App Control(스마트 앱 컨트롤)이나 애플리케이션 제어 정책이 pandas, pyarrow 등의 `.pyd` 파일을 차단할 수 있습니다. 이때 아래와 같은 오류가 표시될 수 있습니다.

```text
ImportError: DLL load failed while importing base:
애플리케이션 제어 정책에서 이 파일을 차단했습니다.
```

1. Python과 필요한 라이브러리가 정상적으로 설치됐는지 확인합니다.
2. **Windows 보안 → 앱 및 브라우저 컨트롤 → 스마트 앱 컨트롤 설정**에서 현재 상태를 확인합니다.
3. Windows 이벤트 뷰어의 `Microsoft-Windows-CodeIntegrity/Operational` 로그에서 이벤트 ID `3077`을 확인합니다.
4. 차단이 확인되면 Windows 업데이트 상태와 패키지의 설치 출처·디지털 서명, 조직의 보안 정책을 확인합니다.
5. 관리되는 PC에서는 관리자에게 실행 허용 방법을 문의합니다.

Smart App Control을 끄면 보호 수준이 낮아질 수 있고 다시 켜는 데 제약이 생길 수 있습니다. 기본 실행 절차에는 보안 설정 변경이 필요하지 않습니다. 위 오류는 Windows가 라이브러리 실행을 제한할 때 발생할 수 있습니다.

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

검증은 `python validate_agent.py`로 실행합니다. 대표 질문 검증 결과는 [결과 설명자료](docs/RESULT_REPORT.md)에 있습니다.

데이터 출처는 제주특별자치도·제주데이터허브, 한국관광공사, 기상청(공공누리 제1유형)입니다.

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


## 공개 항목

- 외부 코드: Leaflet(BSD-2-Clause), Tabler Icons(MIT), deck.gl(MIT), MapLibre GL JS(BSD-3-Clause)의 배포 파일을 포함합니다. 출처와 라이선스는 [데이터 활용 명세](docs/DATA_SPEC.md)에 있습니다.
- [프롬프트 전문](docs/PROMPTS.md)과 [결과 설명자료](docs/RESULT_REPORT.md)
