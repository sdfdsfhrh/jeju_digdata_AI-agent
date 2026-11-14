"""CSV 전처리: 파일 종류 판별 + 표준 행으로 변환.

판별하는 CSV 종류 (헤더 기준)
- index       : 무장애 여행지 정보(통합)       장소명,주소,위도,경도
- nearby_2021 : 2021 무장애여행주변정보            구분,명칭,거리(km),주소,전화번호,휠체어 진입,장애인 화장실,데이터기준일자
- points_2021 : 2021 무장애여행위치정보            순서,위도,경도,구분,설명,포인트,상세정보,전체코스여부,추천코스여부,데이터기준일자
- points_2019 : 2019~2020 장소별 지점 CSV          ID,lat,lon,title,Description,Image,Point,info,A,B,etc
- kto_list / kto_detail : 한국관광공사 API 수집본 (옵션)
"""
from __future__ import annotations

import re

from common import UNK, YES, parse_number


def detect_csv_kind(cols: list[str]) -> str:
    c = set(cols)
    if {"장소명", "주소", "위도", "경도"} <= c:
        return "index"
    if {"구분", "명칭", "휠체어 진입", "장애인 화장실"} <= c:
        return "nearby_2021"
    if {"순서", "위도", "경도", "전체코스여부", "추천코스여부"} <= c:
        return "points_2021"
    if {"아이디", "위도", "경도"} <= c or {"장소명칭", "장소상세정보", "무장애관광정보"} <= c:
        return "points_2019"
    if {"ID", "lat", "lon", "etc"} <= c and ({"title", "Title"} & c):
        return "points_2019"
    if {"contentid", "contenttypeid", "mapx", "mapy", "title"} <= c:
        return "kto_list"
    if {"contentid", "exit", "restroom", "parking"} <= c:
        return "kto_detail"
    return "unknown"


def _f(x):
    try:
        v = float(str(x).strip())
        return v
    except (TypeError, ValueError):
        return None


def _mark(raw):
    """주변정보의 ● 표시: ●=있음, 공란=미확인 (공란이 '없음'인지 '조사 안 함'인지 원본에서 구분 불가)."""
    t = (raw or "").strip()
    if t in ("●", "O", "o", "○", "있음"):
        return YES
    return UNK


def parse_index(df):
    rows = []
    for i, r in df.iterrows():
        rows.append(dict(row_no=i + 2, name=r["장소명"].strip(), address=r["주소"].strip() or None,
                         lat=_f(r["위도"]), lon=_f(r["경도"])))
    return rows


def parse_nearby(df):
    rows = []
    for i, r in df.iterrows():
        rows.append(dict(
            row_no=i + 2, category=r["구분"].strip(), name=r["명칭"].strip(),
            distance_km=_f(r.get("거리(km)")), address=r["주소"].strip(),
            phone=r.get("전화번호", "").strip() or None,
            wheelchair_entry=_mark(r["휠체어 진입"]), wheelchair_entry_raw=r["휠체어 진입"],
            accessible_toilet=_mark(r["장애인 화장실"]), accessible_toilet_raw=r["장애인 화장실"],
            base_date=(r.get("데이터기준일자") or "").strip() or None))
    return rows


ANGLE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:°|˚|도)")
STEP = re.compile(r"턱[^,.]{0,8}?(\d+(?:\.\d+)?)\s*cm")


def _yn(v, yes_token):
    t = (v or "").strip()
    if t == yes_token:
        return "예"
    if t == "":
        return "미확인"
    return "아니오" if t.upper() in ("N", "X") else f"원본:{t}"


def _measures_from_text(text, seq, lat, lon, loc):
    out = []
    if not text:
        return out
    # '360도 조망'처럼 경사와 무관한 '도'를 피하려고 경사 관련 단어가 있을 때만 각도로 본다
    if re.search(r"경사|오르막|내리막", text):
        for m in ANGLE.finditer(text):
            out.append(dict(kind="경사각", value=float(m.group(1)), unit="도", raw_text=text,
                            point_seq=seq, lat=lat, lon=lon, source_locator=loc,
                            extract_method="rule"))
    for m in STEP.finditer(text):
        out.append(dict(kind="턱 높이", value=float(m.group(1)), unit="cm", raw_text=text,
                        point_seq=seq, lat=lat, lon=lon, source_locator=loc,
                        extract_method="rule"))
    return out


def parse_points_2021(df):
    pts, meas = [], []
    base_col = [c for c in df.columns if c.startswith("데이터기준일자")]
    for i, r in df.iterrows():
        loc = f"row {i + 2}"
        lat, lon = _f(r["위도"]), _f(r["경도"])
        desc = (r.get("설명") or "").strip()
        label = (r.get("구분") or "").strip()
        detail = (r.get("상세정보") or "").strip()
        pts.append(dict(seq=int(_f(r["순서"]) or i + 1), lat=lat, lon=lon, label=label,
                        description=desc, detail_raw=detail,
                        in_full_course=_yn(r.get("전체코스여부"), "Y"),
                        in_recommended_course=_yn(r.get("추천코스여부"), "Y"),
                        base_date=(r[base_col[0]].strip() if base_col else None) or None,
                        source_locator=loc))
        meas += _measures_from_text(f"{label} {desc}".strip(), r["순서"], lat, lon, loc)
    return pts, meas


def parse_points_2019(df):
    """etc 칸에 범례가 들어 있음: '접근성정보:1', '장애인화장실:2', '전체코스:A', '추천코스:B'."""
    if "아이디" in df.columns or "장소명칭" in df.columns:
        points=[]; measures=[]
        for i,r in df.iterrows():
            label=r.get("장소명",r.get("장소명칭","")) or ""
            desc=r.get("장소설명",r.get("장소상세정보","")) or ""
            detail=r.get("무장애관광정보","") or ""
            lat,lon=_f(r.get("위도")),_f(r.get("경도")); loc=f"row {i+2}"
            points.append(dict(seq=i+1,lat=lat,lon=lon,label=label,description=desc,detail_raw=detail,
                               in_full_course="미확인",in_recommended_course=_yn(r.get("추천코스여부"),"Y"),
                               base_date=r.get("데이터기준일자") or None,source_locator=loc))
            measures+=_measures_from_text(f"{label} {desc} {detail}",i+1,lat,lon,loc)
        return points,measures
    df=df.rename(columns={"Title":"title"})
    legend_info, legend_rows, full_tok, rec_tok = {}, {}, "A", "B"
    for legend_idx,e in enumerate(df["etc"],2):
        e = (e or "").strip()
        m = re.match(r"^(.+?)\s*:\s*([0-9A-Za-z]+)", e)
        if not m:
            continue
        label, code = m.group(1).strip(), m.group(2)
        if label.startswith("전체코스"):
            full_tok = code
        elif label.startswith("추천코스"):
            rec_tok = code
        else:
            legend_info[code] = label
            legend_rows[code] = legend_idx
    pts, meas = [], []
    for i, r in df.iterrows():
        loc = f"row {i + 2}"
        lat, lon = _f(r["lat"]), _f(r["lon"])
        info = (r.get("info") or "").strip()
        detail = legend_info.get(info, f"코드 {info}") if info else ""
        if info in legend_info:
            detail += f" (info={info}; etc 범례 row {legend_rows[info]})"
            loc += f"; info={info}; legend row {legend_rows[info]} etc"
        title = (r.get("title") or "").strip()
        desc = (r.get("Description") or "").strip()
        pts.append(dict(seq=int(_f(r["ID"]) or i + 1), lat=lat, lon=lon, label=title,
                        description=desc, detail_raw=detail,
                        in_full_course=_yn(r.get("A"), full_tok),
                        in_recommended_course=_yn(r.get("B"), rec_tok),
                        base_date=None, source_locator=loc))
        meas += _measures_from_text(f"{title} {desc}".strip(), r["ID"], lat, lon, loc)
    return pts, meas
