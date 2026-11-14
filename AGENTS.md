# AGENTS.md — 작업 규칙 (Codex용)

전체 배경·결정·현황은 `HANDOFF.md`를 먼저 읽을 것.

## 프로젝트
- 제주데이터허브 무장애 여행 데이터 → 통합 DB(`build_db.py`, `src/`) → 배리어프리 여정 검증 Agent(`agent/`, `app.py`)
- 데이콘 대회 제출용. 마감 2026-11-20 10:00. 운영진이 Windows 센터 PC(i7-8700, GTX 1060, RAM 32GB, Chrome/Edge, 1920×1080)에서 직접 실행함.

## 절대 규칙
1. API 키·인증정보를 코드·문서·로그에 넣지 않는다. 모두 `.env`(예시는 `.env.example`)로 분리한다.
2. 원본에 없는 값을 만들지 않는다. 모르면 '미확인'으로 두고 사유를 남긴다.
3. 상태값은 `있음 / 없음 / 조건부 / 미확인` 4종만 쓴다. '-'·공란은 '미확인'이며 절대 '없음'이 아니다.
4. 모든 판정·수치에는 원본 근거(파일명 + source_locator + 원문)를 붙인다.
5. 판단·필터·순위는 코드 규칙으로 한다. LLM은 문장 → 조건 정리와 결과 설명문만 맡고, 실패하면(None) 규칙 기반으로 대신한다. LLM 없이도 모든 기능이 동작해야 한다.
6. 외부 호출(LLM, 기상청)은 실패해도 앱이 멈추지 않게 예외 처리하고, 화면에 '미확인'과 사유를 보여 준다.
7. 허브 공개 원본·전처리 CSV·catalog 없는 적재 DB는 제출 가능(대회 Q&A, 2026-11). catalog.xlsx와 그 내용이 포함된 DB·파생 파일, .env·캐시는 제출/GitHub에서 제외한다. 제출 빌드는 --no-catalog를 사용하고 docs/data_sources.csv는 공개 페이지를 확인한 사용자가 채운다.
8. 결과에 개인정보가 나오면 가명처리한다.

## 실행
```
pip install -r requirements.txt
python build_db.py --no-catalog               # 제출 가능한 DB 다시 만들기 (output/jeju_bf.sqlite)
python cli.py "질문"                           # Agent 터미널 테스트 (구현 예정)
streamlit run app.py                           # 화면 (구현 예정)
```

## 코드 스타일
- Python 3.10+ (사용자 PC는 3.13, Windows). 경로는 `os.path`로 OS 독립적으로.
- 의존성은 최소로(pandas, openpyxl, requests, streamlit). 새 패키지를 넣으면 `requirements.txt`와 HANDOFF.md §9 사용 기록에 추가.
- 사용자에게 보이는 문구·주석은 한국어.
- 사용자는 대학생 2학년(Python 기초). 실행 안내는 Windows 기준으로 단계별로 쉽게.

## 작업 후 확인
- `python build_db.py`가 그대로 돌아가는지(기존 파이프라인을 깨지 않았는지)
- LLM 키 없음 상태에서 Agent가 끝까지 동작하는지
- 바뀐 내용을 HANDOFF.md 해당 절(현황·사용 기록)에 반영
