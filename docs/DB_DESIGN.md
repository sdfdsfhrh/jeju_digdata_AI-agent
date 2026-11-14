# DB 구조 설계

## 1. 전체 흐름
```
data/raw/*.hwp, *.csv
   │  ① 판별·파싱 (hwp_reader / extract_hwp / prep_csv)      → source_file, extraction_failure
   │  ② 장소명 결정 (내용 > 파일명 > 매니페스트 > 내용·좌표 연결)
   │  ③ 장소 그룹화 → 색인(498) 매칭 (integrate)               → place, place_source_link, review_queue
   │  ④ 세부 테이블 적재                                         → accessibility_item, facility_detail,
   │                                                               measurement, course_point, nearby_facility,
   │                                                               target_recommendation, conflict
   │  ⑤ [옵션] 관광공사 분리 보관·비교                            → kto_place, kto_accessibility, kto_hub_comparison
   └  ⑥ 품질 검증                                               → quality_report.md/json
```

## 2. 테이블 관계
```
source_file 1 ─── N place_source_link N ─── 1 place
source_file 1 ─── N accessibility_item / facility_detail / measurement / course_point
                     / nearby_facility / target_recommendation / extraction_failure
place       1 ─── N (위 세부 테이블 전부), review_queue, conflict
place       1 ─── N kto_hub_comparison (옵션)
```
모든 세부 행은 `place_id`(어느 장소) + `source_file_id`(어느 파일) + `source_locator`(파일 안 어디)를 가진다.

## 3. 테이블 설명
| 테이블 | 요청 항목 | 설명 |
|---|---|---|
| source_file | 데이터 출처, 기준일 | 파일명, SHA-256, 판별 종류, 허브 데이터 번호, 기준일과 그 출처(원본 데이터기준일자/카탈로그 수집기간), 처리 성공 여부 |
| place | 관광지 기본정보 | 장소 고유 ID(이름 기반 해시, 재실행해도 동일), 이름, 주소, 대표 좌표와 좌표 출처, 묶음, 상세파일 유무, 개요, 이동약자 안내, 코스 |
| place_source_link | 원본 연결, 원본 ID 보존 | 장소가 어떤 파일·어떤 행에서 왔는지, 연결 방법, 이름 유사도, 거리, 연결 상태(자동연결/검토필요/신규장소) |
| accessibility_item | 장애인 주차장·화장실·휠체어 접근성·경사로·보조기기, 검증 상태 | 항목별 상태(4종) + 판정 사유 + 원본 값 + 근거 문장 + 적용 대상(장소 자체/대체시설) + 검증 상태 |
| facility_detail | 장애인 주차장·화장실 상세 | 2021 상세표(구분/항목/내용/단위)를 행 그대로 보존 |
| measurement | 경사로(수치) | 경사각·경사로 길이·턱 높이·출입문 폭 등 수치. 원본 문장 보존, 안전 판정 없음 |
| course_point | 관광지 내부 코스 | 지점 순서·좌표·설명, 전체/추천 코스 포함 여부(예/아니오/미확인) |
| nearby_facility | 주변 편의시설 | 주변 음식점·카페·숙박·관광지, 휠체어 진입·장애인 화장실(●=있음, 공란=미확인) |
| target_recommendation | 휠체어 이용자별 추천 | 원본 '●' 표시를 그대로 보존 |
| extraction_failure | 추출 실패 기록 | 파일·항목·사유 |
| review_queue | 검증 상태 | 사람이 확인할 목록 |
| conflict | 출처 충돌 | 서로 다른 값을 모두 보존 (예: 요약표 8면 vs 상세표 11대) |
| status_rule | 표준화 규칙 | 상태 4종의 정의를 DB 안에 함께 보관 |
| kto_* | 관광공사 보강(옵션) | 기본 판정과 분리. data_status='참고용' |

## 4. 표준화 규칙
- 상태 4종: 있음 / 없음 / 조건부 / 미확인
- **'정보 없음'(미확인)과 '시설 없음'(없음)을 구분한다.** 원본이 '없음·미설치'라고 쓴 경우만 '없음'.
- '-', 공란, 그림 아이콘, 추출 실패 → '미확인'
- 2021 요약표 장애인 화장실이 '-'인데 같은 문서 개요에 "장애인 화장실이 없"이 명시된 경우만 '없음'으로 올리고, 판정 사유에 근거를 남긴다.
- 주변정보의 공란은 '없음'인지 '조사 안 함'인지 원본에서 구분할 수 없으므로 '미확인'.
- 수치는 원본 값과 단위를 보존. 범위 표현(3~4°)은 하한 값 + 종류에 '범위 3~4' 표기.

## 5. 장소 매칭 규칙
| 결과 | 조건 |
|---|---|
| 자동연결 | 이름 일치(앞 '제주' 차이 허용) + (1km 이내 또는 주소 일치) / 이름 유사도 ≥0.85 + 300m 이내 + 이름 속 숫자 동일 |
| 검토필요 | 이름 부분 유사(≥0.6) + 근접 / 이름 다르지만 150m 이내 / 이름 같지만 비교할 위치 없음 / 자동연결 후보가 2개 이상 |
| 연결 안 함 | 그 외 |

검토필요는 자동으로 합치지 않고 `review_queue`에 후보와 근거(유사도·거리)를 남긴다.

## 6. 품질 검증 항목
| 항목 | 계산 방법 | 미실행 조건 |
|---|---|---|
| 전체 장소 수 | place 행 수 (상세파일 유무별) | — |
| 중복 의심 | 이름 동일(숫자 동일) 또는 50m 이내 좌표 쌍 | — |
| 추출 실패 파일 수 | source_file.parse_status='실패' | — |
| 항목별 결측률 | 상세파일 장소 중 상태 '미확인' 비율 | 상세파일 장소 0곳 |
| 장소 매칭 성공률 | 2019~2020 상세파일 장소 중 색인 자동연결 비율 | 해당 장소 0곳 |
| 출처 내 충돌 | conflict(요약표 vs 상세표) | — |
| 출처 간 충돌 | kto_hub_comparison '불일치 가능' 건수 | --with-kto 미사용 |
| 좌표 없는 장소 | place.lat 공란 | — |
| 기준일 누락 | place / source_file base_date 공란 | — |
