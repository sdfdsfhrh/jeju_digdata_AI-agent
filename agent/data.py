"""데이터 접근: 통합 DB(output/jeju_bf.sqlite)와 위치 보조 CSV를 읽는다.

Agent의 도구(tools.py)는 여기 함수만 통해 데이터를 본다. SQL은 이 파일에만 둔다.
모든 행에는 원본 파일명(file_name)과 원본 위치(source_locator)가 함께 따라온다.
"""
from __future__ import annotations

import functools
import os
import re
import sqlite3

import pandas as pd

from . import config


class DataError(Exception):
    """사용자에게 그대로 보여 줄 수 있는 데이터 오류."""


@functools.lru_cache(maxsize=1)
def _con_path() -> str:
    path = config.DB_PATH
    if not os.path.exists(path):
        raise DataError(
            f"통합 DB 파일이 없습니다: {path}\n"
            "먼저 `python build_db.py --no-catalog`를 실행해 DB를 만드세요.")
    return path


def _q(sql: str, params=()) -> list[dict]:
    con = sqlite3.connect(_con_path())
    con.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in con.execute(sql, params)]
    finally:
        con.close()


# ---------------------------------------------------------------------------
# 장소
# ---------------------------------------------------------------------------
@functools.lru_cache(maxsize=1)
def detailed_places() -> tuple:
    """상세 파일(일반정보 HWP 등)이 있는 장소만. 색인만 있는 곳은 판정 근거가 없어 추천 대상에서 뺀다."""
    rows = _q("""SELECT * FROM place WHERE detail_level = '상세파일있음' ORDER BY name""")
    return tuple(rows)


def place_counts() -> dict:
    rows = _q("SELECT detail_level, COUNT(*) n FROM place GROUP BY detail_level")
    return {r["detail_level"]: r["n"] for r in rows}


def all_places() -> list[dict]:
    return _q("SELECT * FROM place ORDER BY name")


def place_evidence(place_id):
    return _q("""SELECT s.file_name, l.source_locator FROM place_source_link l
                 JOIN source_file s USING(source_file_id) WHERE l.place_id = ?""", (place_id,))




def source_date_ranges():
    hub=_q("""SELECT MIN(base_date) lo,MAX(base_date) hi FROM source_file
              WHERE file_kind NOT LIKE 'kto_%' AND file_kind!='index'""")[0]
    kto=_q("""SELECT MIN(base_date) lo,MAX(base_date) hi FROM accessibility_item
              WHERE item_id LIKE 'KTO-%'""")[0]
    return dict(hub=hub,kto=kto)


def db_base_dates() -> tuple[str | None, str | None]:
    r = _q("SELECT MIN(base_date) a, MAX(base_date) b FROM place WHERE detail_level='상세파일있음'")
    return (r[0]["a"], r[0]["b"]) if r else (None, None)


def items(place_id: str) -> list[dict]:
    return _q("""SELECT a.*, s.file_name,
                 CASE WHEN a.item_id LIKE 'KTO-%' THEN a.base_date ELSE COALESCE(a.base_date,s.base_date) END AS display_base_date,
                 COALESCE(a.source_label, '제주데이터허브(필수)') AS origin FROM accessibility_item a
                 LEFT JOIN source_file s USING(source_file_id)
                 WHERE a.place_id = ? ORDER BY a.item,
                 COALESCE(a.modifiedtime, CASE WHEN a.item_id NOT LIKE 'KTO-%' THEN REPLACE(s.base_date,'-','') END, '') DESC,
                 CASE WHEN a.item_id LIKE 'KTO-%' THEN 1 ELSE 0 END""", (place_id,))


def source_counts():
    rows = _q("""SELECT CASE WHEN s.file_kind LIKE 'kto_%' THEN '한국관광공사(보조)' ELSE '제주데이터허브(필수)' END origin,
                 COUNT(DISTINCT l.place_id) n FROM place_source_link l JOIN source_file s USING(source_file_id) GROUP BY origin""")
    return {r['origin']:r['n'] for r in rows}


def measures(place_id: str) -> list[dict]:
    return _q("""SELECT m.*, s.file_name FROM measurement m
                 LEFT JOIN source_file s USING(source_file_id)
                 WHERE m.place_id = ?""", (place_id,))


def points(place_id: str) -> list[dict]:
    return _q("""SELECT c.*, s.file_name FROM course_point c
                 LEFT JOIN source_file s USING(source_file_id)
                 WHERE c.place_id = ? ORDER BY c.seq""", (place_id,))


def nearby(place_id: str) -> list[dict]:
    return _q("""SELECT n.*, s.file_name FROM nearby_facility n
                 LEFT JOIN source_file s USING(source_file_id)
                 WHERE n.place_id = ? ORDER BY n.distance_km""", (place_id,))


def conflicts(place_id: str) -> list[dict]:
    return _q("SELECT * FROM conflict WHERE place_id = ?", (place_id,))


def source_files(place_id: str) -> list[dict]:
    return _q("""SELECT DISTINCT s.file_name, s.file_kind, s.base_date, s.hub_dataset_no, s.hub_dataset_name
                 FROM place_source_link l JOIN source_file s USING(source_file_id)
                 WHERE l.place_id = ? AND s.file_kind != 'index'""", (place_id,))


# ---------------------------------------------------------------------------
# 지역(읍·면·동) — 장소 지역 필터와 실내 대안 연결
# ---------------------------------------------------------------------------



def region_of(addr: str | None) -> tuple[str | None, str | None]:
    """주소 → (시, 읍면동). 예: '제주 제주시 애월읍 하귀2리' → ('제주시', '애월읍')."""
    if not addr:
        return None, None
    a = str(addr).replace("제주특별자치도", " ")
    si = "제주시" if "제주시" in a else "서귀포시" if "서귀포시" in a else None
    m = re.search(r"([가-힣]{1,4}(?:읍|면))(?=\s|$|\d)", a)
    if m:
        return si, m.group(1)
    m = re.search(r"(?:제주시|서귀포시)\s*([가-힣]{1,5}\d?동)(?=\s|$|\d)", a)
    if m:
        return si, m.group(1)
    m = re.search(r"\(([가-힣]{1,5}\d?동)[,)]", a)   # 도로명 주소 끝의 '(연동)'
    if m:
        return si, m.group(1)
    return si, None




def _read_csv(path: str) -> pd.DataFrame | None:
    if not os.path.exists(path):
        return None
    for enc in ("utf-8-sig", "cp949", "euc-kr"):
        try:
            return pd.read_csv(path, encoding=enc, dtype=str, keep_default_na=False)
        except (UnicodeDecodeError, pd.errors.ParserError):
            continue
    return None






def place_types(place_id):
    return _q("""SELECT kto_id, contenttypeid, source_file_id FROM kto_place
                 WHERE matched_place_id=? OR 'KTO-' || kto_id=?""",(place_id,place_id))


def nearby_anchor_locations():
    """주변 CSV에 실제 좌표 열이 있을 때만 위치 후보로 읽는다. 주소·거리로 좌표를 추정하지 않는다."""
    rows=[]
    for source in _q("SELECT file_name FROM source_file WHERE file_kind='nearby_2021'"):
        path=os.path.join(config.ROOT,'data','raw',source['file_name'])
        df=_read_csv(path)
        if df is None: continue
        cols={str(c).strip():c for c in df.columns}
        lat=next((cols[c] for c in ('위도','lat','latitude','mapy') if c in cols),None)
        lon=next((cols[c] for c in ('경도','lon','longitude','mapx') if c in cols),None)
        name=next((cols[c] for c in ('명칭','이름','name') if c in cols),None)
        if not (lat and lon and name): continue
        for i,r in df.iterrows():
            try: y,x=float(r[lat]),float(r[lon])
            except (TypeError,ValueError): continue
            if 32<=y<=35 and 125<=x<=128:
                rows.append(dict(name=str(r[name]),lat=y,lon=x,source=source['file_name'],source_locator=f'row {i+2}'))
    return rows


def parking_rows(lat,lon,radius_km=0.5):
    import math
    try:
        lat,lon=float(lat),float(lon)
        if not (math.isfinite(lat) and math.isfinite(lon)): return []
    except (TypeError,ValueError):return []
    try:
        if radius_km is None:return _q('SELECT * FROM parking_lot')
        dy=radius_km/110.0;dx=radius_km/(110.0*max(.01,math.cos(math.radians(lat))))
        return _q('SELECT * FROM parking_lot WHERE lat BETWEEN ? AND ? AND lon BETWEEN ? AND ?',
                  (lat-dy,lat+dy,lon-dx,lon+dx))
    except sqlite3.OperationalError:
        return []  # 이전 DB/검증 DB에 보조 테이블이 없어도 기존 판정 유지


def parking_anchor_locations():
    """주차장 이름·실제 좌표·행 근거만 기준 위치 후보로 읽는다."""
    try:
        return _q('SELECT parking_lot_id,name,lat,lon,source_file,source_locator,base_date FROM parking_lot ORDER BY name,parking_lot_id')
    except sqlite3.OperationalError:
        return []  # 이전/검증 DB에 주차장 테이블이 없는 경우
