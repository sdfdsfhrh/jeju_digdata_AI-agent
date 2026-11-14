# 제출 데이터 분리 검토 (2026-11-08)

근거: 사용자가 전달한 대회 Q&A 2건. 공개 허브 원본·전처리 CSV·적재 DB는 출처/처리 방식 기재 후 제출 가능. catalog.xlsx 원본 또는 그 내용이 담긴 DB는 ZIP·GitHub에 포함 금지.

## catalog 내용 유입 경로 조사

- build_db.py: load_catalog → catalog_lookup → 번호·이름·수집기간 → 원본 출처 행과 장소 기준일. index 기준일도 목록에서 보완하던 경로가 있음.
- source_file: hub_dataset_no, hub_dataset_name, catalog_period, base_date, base_date_source. 원래 DB에서 번호/이름/기간이 채워진 행은 각각 181개. 번호/기간의 실제 값은 이 보고서에 복제하지 않음.
- place.base_date 및 accessibility_item.base_date 등 통합/최신 출처 선택에서 파생되는 날짜: 새 빌드에서 원본/공개 출처표만 사용.
- output/jeju_bf.sqlite 및 과거 산출 DB, output/csv/source_file.csv·place.csv·accessibility_item.csv와 관련 검토/품질 보고서: 기존 파일은 패키징 제외. 제출용 디렉터리에서 재생성한 산출물만 포함.
- logs/build.log: catalog 경로·빌드 옵션 기록. 과거 로그 전체 제외.
- output/agent_cache.sqlite·LLM 사용량/응답 캐시·output/validation 및 보고서: 날짜/출처 설명이 남을 가능성이 있어 전체 제외. __pycache__ 제외.
- docs/DATA_SPEC.md의 목록 번호/수집기간, README의 번호와 catalog 빌드 안내, docs/LIMITS.md의 catalog 보완 날짜를 제거/수정. 과거 HANDOFF·개발 대조 보고서·캡처는 제출에서 제외. 파일별 검색 목록은 로컬 output/submission_audit/catalog_locations.json(비제출).
- src/integrate.py의 coord_source 및 품질 보고서·anchor.py의 원본 설명에 고정돼 있던 목록 식별 번호도 제거하여 원본 파일 기반 표기로 바꿈. 좌표/판정은 바꾸지 않음.
- 코드의 catalog 읽기 함수/스키마 열 정의는 목록 데이터 자체가 아님. 개발용 --catalog는 유지하되 제출용 --no-catalog와 동시 지정하면 오류. catalog_period는 제출 DB에서 전부 NULL.
- data/manifest.generated.csv는 이름/파일종류/읽기 결과만 담고 catalog 값이 없음. 새 빌드로 다시 생성해 포함. manifest_override.csv는 원본 ID/장소 수동 연결표이며 catalog 메타데이터를 보완하지 않음.

## 공개 출처표

docs/data_sources.csv는 실제 사용한 허브 자료 5종의 데이터명만 제공한다. 사용자가 공개 상세 페이지에서 직접 확인한 데이터번호·데이터명·제공처·기준일·등록일·출처URL·확인일을 기입한다. 기준일이 비면 등록일로 대체하지 않는다. 현재는 번호/날짜를 catalog에서 채우지 않는다.

## 비교 결과

외부 API·LLM을 끄고 같은 시점에 기존 DB와 --no-catalog DB로 한림공원·협재해수욕장·성산일출봉 질문 + validate_agent.QUESTIONS 10개(빈 질문 포함), 총 13개를 비교했다. 전체 결과 목록의 장소명·순서·등급·필수항목 상태/유효상태·전체 시설 상태가 13/13 일치했다. 성산일출봉 자체 상세 데이터는 새로 생기지 않으며 기존의 판정 불가/대안 안내 흐름을 유지한다. 기준일/출처 설명은 달라질 수 있고, 아래는 DB별 실제 변경 컬럼이다. 과거 출처표 값은 보고서에 복제하지 않는다.

| 테이블 | 이전 / 제출 행수 | 변경 컬럼·행수 |
|---|---|---|
| source_file | 183 / 183 | hub_dataset_no: 181행, hub_dataset_name: 181행, catalog_period: 181행, base_date: 78행, base_date_source: 78행 |
| place | 221 / 221 | base_date: 119행, coord_source: 105행(고정 목록 번호 제거) |
| accessibility_item | 2062 / 2062 | 변화 없음 |
| course_point | 6019 / 6019 | 변화 없음 |
| nearby_facility | 819 / 819 | 변화 없음 |
| kto_hub_comparison | 0 / 0 | 변화 없음 |

## 패키징

make_submission.py는 매번 임시 경로에서 --no-catalog로 새 DB를 만들고 빌드 표식·catalog 미사용·기간 NULL·SQLite 무결성을 검사한다. 새 DB를 ZIP 안 output/jeju_bf.sqlite에 배치하므로 받은 즉시 실행 가능하다. 기존 output 전체를 복사하지 않는다. dist/submission_files.txt와 manifest JSON에 전체 경로/크기/SHA-256을 기록하고 ZIP 내부에도 넣는다. .env.example만 포함하고 실제 .env·캐시·catalog·기존 DB·기존 보고서는 제외한다.

검증: 실제 제출 ZIP의 DB로 대표 13질문 재비교, validate_agent.py·validate_named_visit.py·validate_parking.py·validate_submission.py 확인. 날짜 범위를 과거 catalog 값으로 고정하던 named_visit 검증은 실제 DB 출처 범위를 대조하도록 수정했습니다.

## 최신 추천·API 수정 반영

위13질문 비교는 catalog 제외 작업 당시의 DB 간 비교 기록입니다. 이후 사용자 지시로 추천 순위를 변경했습니다. 현재 추천은 필수 조건 미충족을 맨 뒤로 두고 빨강 범주(0/미확인/1~2/3이상), 같은 범주 내 시설 상태, 이용 판단, 주황 수, 거리 순입니다. 시설 상태·등급 계산은 유지합니다. 현재 동작은 USER_MANUAL·LIMITS, API 원인은 API_DIAGNOSTICS_20261108.md, ZIP 재생성 전 용량은 SUBMISSION_SIZE.md를 참고합니다. 원본 파일·이미지는 줄이지 않았습니다.

## 인증정보 사전 검사 (11/9)

최종 ZIP 검사에서 별도 실험 스크립트1개에 인증정보가 발견되어 해당 스크립트를 제출 대상에서 제외했습니다. 사용자 원본 스크립트는 수정하지 않았습니다. make_submission.py는 .env의 실제 키를 출력하지 않고 선택한 파일에 포함됐는지 ZIP 생성 전에 검사하며, 발견하면 파일명만 알리고 생성을 중단합니다. 최종 ZIP도 validate_submission.py로 별도 검사합니다.
