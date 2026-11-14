"""SQLite 스키마와 저장 함수.

설계 원칙
- 모든 값은 원본 파일(source_file)과 원본 위치(source_locator: 표·행·열 / CSV 행 번호 / 문단 번호)로 거슬러 올라갈 수 있다.
- 상태값은 4종(있음/없음/조건부/미확인)만 쓰고, 원본 값(value_raw)과 근거 문장(evidence)을 항상 함께 저장한다.
- 수치(경사각, 턱 높이, 폭 등)는 원본 값 그대로 보존하고 안전/위험을 판정하지 않는다.
"""
from __future__ import annotations

import sqlite3

import pandas as pd

SCHEMA = """
CREATE TABLE IF NOT EXISTS run_info (
    key TEXT PRIMARY KEY, value TEXT
);

-- 원본 파일 (출처 관리의 기준)
CREATE TABLE IF NOT EXISTS source_file (
    source_file_id TEXT PRIMARY KEY,
    file_name TEXT, file_ext TEXT,
    file_kind TEXT,              -- index / general_2021 / nearby_2021 / points_2021 / narrative_2019 / points_2019 / kto_list / kto_detail / unknown
    place_name_declared TEXT,    -- 파일명·내용·매니페스트에서 얻은 장소명
    place_name_source TEXT,      -- filename / content / manifest_override / content_link / geo_link
    hub_dataset_no TEXT, hub_dataset_name TEXT, catalog_period TEXT,
    public_provider TEXT, public_registered_date TEXT, public_source_url TEXT,
    base_date TEXT, base_date_source TEXT,
    sha256 TEXT, size_bytes INTEGER, encoding TEXT, reader TEXT,
    parse_status TEXT,           -- 성공 / 부분성공 / 실패
    parse_message TEXT
);

-- 장소 마스터
CREATE TABLE IF NOT EXISTS place (
    place_id TEXT PRIMARY KEY,
    name TEXT, name_norm TEXT,
    address TEXT, lat REAL, lon REAL, coord_source TEXT,
    bundle TEXT,                 -- 2021 / 2019-2020 / 색인만
    detail_level TEXT,           -- 상세파일있음 / 색인만(상세파일 미수집)
    overview TEXT, mobility_note TEXT,
    recommended_course TEXT, full_course TEXT,
    base_date TEXT
);

-- 장소 ↔ 원본 연결 (원본 ID 보존)
CREATE TABLE IF NOT EXISTS place_source_link (
    link_id TEXT PRIMARY KEY,
    place_id TEXT, source_file_id TEXT, source_locator TEXT,
    raw_name TEXT, raw_address TEXT, raw_lat REAL, raw_lon REAL,
    link_method TEXT, name_sim REAL, dist_m REAL, addr_match INTEGER,
    link_status TEXT             -- 자동연결 / 검토필요 / 신규장소
);

-- 접근성 항목 (요약 판정)
CREATE TABLE IF NOT EXISTS accessibility_item (
    item_id TEXT PRIMARY KEY,
    place_id TEXT, category TEXT, item TEXT,
    status TEXT,                 -- 있음 / 없음 / 조건부 / 미확인
    status_reason TEXT,
    value_num REAL, value_unit TEXT, value_raw TEXT,
    evidence TEXT, applies_to TEXT,   -- 대상 장소 자체 / 대체시설
    source_file_id TEXT, source_locator TEXT,
    extract_method TEXT, verify_status TEXT
);

-- 원본 상세표 행 그대로 (주차장·화장실·주출입구 등)
CREATE TABLE IF NOT EXISTS facility_detail (
    detail_id TEXT PRIMARY KEY,
    place_id TEXT, facility_title TEXT, is_alternative INTEGER,
    grp TEXT, item TEXT, value_raw TEXT, unit TEXT, value_num REAL,
    source_file_id TEXT, source_locator TEXT
);

-- 수치 측정값 (경사각·턱 높이·폭 등) — 원본 보존, 안전 판정 없음
CREATE TABLE IF NOT EXISTS measurement (
    meas_id TEXT PRIMARY KEY,
    place_id TEXT, kind TEXT, value REAL, unit TEXT, raw_text TEXT,
    point_seq TEXT, lat REAL, lon REAL,
    source_file_id TEXT, source_locator TEXT, extract_method TEXT
);

-- 관광지 내부 코스 지점
CREATE TABLE IF NOT EXISTS course_point (
    point_id TEXT PRIMARY KEY,
    place_id TEXT, seq INTEGER, lat REAL, lon REAL,
    label TEXT, description TEXT, detail_raw TEXT,
    in_full_course TEXT, in_recommended_course TEXT,   -- 예 / 아니오 / 미확인
    base_date TEXT, source_file_id TEXT, source_locator TEXT
);

-- 주변 편의시설
CREATE TABLE IF NOT EXISTS nearby_facility (
    facility_id TEXT PRIMARY KEY,
    place_id TEXT, category TEXT, name TEXT, distance_km REAL,
    address TEXT, phone TEXT,
    wheelchair_entry TEXT, wheelchair_entry_raw TEXT,
    accessible_toilet TEXT, accessible_toilet_raw TEXT,
    base_date TEXT, source_file_id TEXT, source_locator TEXT
);

-- 대상별 추천 표시 (원본 '●' 그대로)
CREATE TABLE IF NOT EXISTS target_recommendation (
    rec_id TEXT PRIMARY KEY,
    place_id TEXT, target_group TEXT, target TEXT,
    mark_raw TEXT, marked TEXT,  -- 표시있음 / 표시없음
    note_raw TEXT, source_file_id TEXT, source_locator TEXT
);

-- 추출 실패 기록
CREATE TABLE IF NOT EXISTS extraction_failure (
    fail_id TEXT PRIMARY KEY,
    source_file_id TEXT, item TEXT, reason TEXT, source_locator TEXT
);

-- 사람 검토 대기열
CREATE TABLE IF NOT EXISTS review_queue (
    review_id TEXT PRIMARY KEY,
    review_type TEXT,            -- 장소매칭 / 출처내충돌 / 출처간충돌 / 파일연결 / 추천표시변별력
    place_id TEXT, source_file_id TEXT, detail TEXT, candidates TEXT,
    status TEXT                  -- 미검토
);

-- 출처 간/출처 내 값 충돌 (원본을 모두 보존)
CREATE TABLE IF NOT EXISTS conflict (
    conflict_id TEXT PRIMARY KEY,
    place_id TEXT, topic TEXT,
    value_a TEXT, source_a TEXT, value_b TEXT, source_b TEXT, note TEXT
);

-- 외부 주차장: 장소 전용/장애인 주차 상태와 분리 보관
CREATE TABLE IF NOT EXISTS parking_lot (
 parking_lot_id TEXT PRIMARY KEY, management_no TEXT, name TEXT, division TEXT, type TEXT,
 address TEXT, address_road TEXT, address_jibun TEXT, lat REAL, lon REAL, spaces INTEGER,
 hours_json TEXT, fee_info TEXT, fees_json TEXT, disabled_raw TEXT, disabled_status TEXT,
 base_date TEXT, source_file TEXT, source_locator TEXT, source_label TEXT, raw_json TEXT
);

-- 상태값 규칙 (DB 안에 함께 보관)
CREATE TABLE IF NOT EXISTS status_rule (
    status TEXT PRIMARY KEY, meaning TEXT, examples TEXT
);

-- [옵션] 한국관광공사 데이터 (기본 DB와 분리 보관, Agent 기본 판정에는 사용하지 않음)
CREATE TABLE IF NOT EXISTS kto_place (
    kto_id TEXT PRIMARY KEY, title TEXT, addr TEXT, lat REAL, lon REAL,
    contenttypeid TEXT, modifiedtime TEXT, matched_place_id TEXT,
    match_status TEXT, name_sim REAL, dist_m REAL, data_status TEXT, source_file_id TEXT
);
CREATE TABLE IF NOT EXISTS kto_accessibility (
    kto_id TEXT, field TEXT, value_raw TEXT, source_file_id TEXT
);
CREATE TABLE IF NOT EXISTS kto_hub_comparison (
    place_id TEXT, kto_id TEXT, topic TEXT, hub_status TEXT, hub_raw TEXT,
    kto_raw TEXT, judgement TEXT
);
"""


def connect(path: str) -> sqlite3.Connection:
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    cols = {r[1] for r in con.execute('PRAGMA table_info(accessibility_item)')}
    for name in ('source_label', 'base_date', 'modifiedtime'):
        if name not in cols:
            con.execute(f'ALTER TABLE accessibility_item ADD COLUMN {name} TEXT')
    return con


def write_rows(con: sqlite3.Connection, table: str, rows: list[dict]):
    if not rows:
        return
    cols = [r[1] for r in con.execute(f"PRAGMA table_info({table})")]
    df = pd.DataFrame(rows)
    for c in cols:
        if c not in df.columns:
            df[c] = None
    df = df[cols]
    df.to_sql(table, con, if_exists="append", index=False)


def export_csv(con: sqlite3.Connection, out_dir: str, tables: list[str]):
    import os

    os.makedirs(out_dir, exist_ok=True)
    for t in tables:
        pd.read_sql(f"SELECT * FROM {t}", con).to_csv(
            os.path.join(out_dir, f"{t}.csv"), index=False, encoding="utf-8-sig")
