"""장소 통합: 파일별 장소 → 장소 마스터, 허브 원본 색인과 매칭, 검토 대기열 생성.

매칭 규칙 (불확실하면 자동 결합하지 않는다)
- 자동연결: 이름 일치(앞의 '제주' 차이 허용) + (거리 ≤ 1km 또는 주소 일치)
            또는 이름 유사도 ≥ 0.85 + 거리 ≤ 300m + 이름 속 숫자 동일
- 검토필요: 이름 유사도 ≥ 0.6 + (거리 ≤ 1km 또는 주소 일치)
            또는 거리 ≤ 150m (이름이 다름)
            또는 이름 일치인데 비교할 좌표·주소가 없음
            또는 자동연결 후보가 2개 이상
- 그 외: 연결 안 함
"""
from __future__ import annotations

import re

from common import (addr_match, haversine_m, name_similarity, norm_name, stable_id)

AUTO, REVIEW, NEW = "자동연결", "검토필요", "신규장소"


def _digits(s):
    return tuple(re.findall(r"\d+", str(s or "")))


def judge(a_name, a_addr, a_lat, a_lon, b_name, b_addr, b_lat, b_lon):
    sim = name_similarity(a_name, b_name)
    dist = haversine_m(a_lat, a_lon, b_lat, b_lon)
    am = addr_match(a_addr, b_addr) if (a_addr and b_addr) else False
    same_digits = _digits(norm_name(a_name)) == _digits(norm_name(b_name))
    if sim == 1.0 and ((dist is not None and dist <= 1000) or am):
        return AUTO, sim, dist, am, "이름 일치 + 위치/주소 확인"
    if sim >= 0.85 and dist is not None and dist <= 300 and same_digits:
        return AUTO, sim, dist, am, "이름 유사 + 300m 이내"
    if sim == 1.0 and dist is None and not (a_addr and b_addr):
        return REVIEW, sim, dist, am, "이름은 같으나 비교할 좌표·주소 없음"
    if sim >= 0.6 and ((dist is not None and dist <= 1000) or am):
        return REVIEW, sim, dist, am, "이름 부분 유사 + 위치/주소 근접"
    if dist is not None and dist <= 150:
        return REVIEW, sim, dist, am, "이름은 다르나 150m 이내"
    if sim == 1.0:
        return REVIEW, sim, dist, am, "이름은 같으나 거리가 멀거나 주소 불일치"
    return None, sim, dist, am, ""


def build_places(file_places: list[dict], index_rows: list[dict], index_sf: str | None,
                 index_base_date: str | None):
    """
    file_places: [{key, name, address, lat, lon, coord_source, bundle, base_date, sources:[...]}]
    index_rows : parse_index 결과
    반환: places, links, reviews
    """
    places, links, reviews = [], [], []
    used_index = {}

    for fp in file_places:
        pid = stable_id("JBF", norm_name(fp["name"]), fp["bundle"])
        place = dict(place_id=pid, name=fp["name"], name_norm=norm_name(fp["name"]),
                     address=fp.get("address"), lat=fp.get("lat"), lon=fp.get("lon"),
                     coord_source=fp.get("coord_source"), bundle=fp["bundle"],
                     detail_level="상세파일있음", base_date=fp.get("base_date"),
                     overview=fp.get("overview"), mobility_note=fp.get("mobility_note"),
                     recommended_course=fp.get("recommended_course"),
                     full_course=fp.get("full_course"))
        fp["place_id"] = pid
        for s in fp["sources"]:
            links.append(dict(
                link_id=stable_id("LNK", pid, s["source_file_id"], s.get("locator", "")),
                place_id=pid, source_file_id=s["source_file_id"],
                source_locator=s.get("locator"), raw_name=s.get("raw_name"),
                raw_address=s.get("raw_address"), raw_lat=s.get("raw_lat"),
                raw_lon=s.get("raw_lon"), link_method=s.get("method"),
                link_status=s.get("status", AUTO)))

        # 허브 원본 색인과 매칭
        cands = []
        for ir in index_rows:
            res, sim, dist, am, why = judge(fp["name"], fp.get("address"), fp.get("lat"),
                                            fp.get("lon"), ir["name"], ir["address"],
                                            ir["lat"], ir["lon"])
            if res:
                cands.append((res, sim, dist, am, why, ir))
        autos = [c for c in cands if c[0] == AUTO]
        if len(autos) == 1:
            res, sim, dist, am, why, ir = autos[0]
            used_index[ir["row_no"]] = pid
            links.append(dict(
                link_id=stable_id("LNK", pid, index_sf, ir["row_no"]), place_id=pid,
                source_file_id=index_sf, source_locator=f"row {ir['row_no']}",
                raw_name=ir["name"], raw_address=ir["address"], raw_lat=ir["lat"],
                raw_lon=ir["lon"], link_method=f"색인매칭: {why}", name_sim=round(sim, 3),
                dist_m=None if dist is None else round(dist, 1), addr_match=int(am),
                link_status=AUTO))
            if place["lat"] is None and ir["lat"] is not None:
                place["lat"], place["lon"], place["coord_source"] = ir["lat"], ir["lon"], "허브 원본 색인"
            if not place["address"] and ir["address"]:
                place["address"] = ir["address"]
        elif cands:
            reviews.append(dict(
                review_id=stable_id("RV", "match", pid), review_type="장소매칭", place_id=pid,
                source_file_id=index_sf,
                detail=f"'{fp['name']}'과 색인 후보 연결이 불확실 (자동연결 후보 {len(autos)}개)",
                candidates="; ".join(
                    f"{c[5]['name']}(row {c[5]['row_no']}, 유사도 {c[1]:.2f}, "
                    f"거리 {'-' if c[2] is None else round(c[2])}m, {c[4]})" for c in cands),
                status="미검토"))
        places.append(place)

    # 색인에만 있는 장소
    for ir in index_rows:
        if ir["row_no"] in used_index:
            continue
        pid = stable_id("JBF", norm_name(ir["name"]), "index", ir["row_no"])
        places.append(dict(place_id=pid, name=ir["name"], name_norm=norm_name(ir["name"]),
                           address=ir["address"], lat=ir["lat"], lon=ir["lon"],
                           coord_source="허브 원본 색인" if ir["lat"] is not None else None,
                           bundle="2019-2020(색인)", detail_level="색인만(상세파일 미수집)",
                           base_date=index_base_date))
        links.append(dict(link_id=stable_id("LNK", pid, index_sf, ir["row_no"]), place_id=pid,
                          source_file_id=index_sf, source_locator=f"row {ir['row_no']}",
                          raw_name=ir["name"], raw_address=ir["address"], raw_lat=ir["lat"],
                          raw_lon=ir["lon"], link_method="색인 원본 행", link_status=NEW))
    return places, links, reviews


def find_duplicates(places: list[dict]):
    """같은 장소로 의심되는 쌍: 이름 일치(번호 동일) 또는 50m 이내 좌표."""
    out = []
    for i in range(len(places)):
        for j in range(i + 1, len(places)):
            a, b = places[i], places[j]
            sim = name_similarity(a["name"], b["name"])
            dist = haversine_m(a["lat"], a["lon"], b["lat"], b["lon"])
            same_digits = _digits(a["name_norm"]) == _digits(b["name_norm"])
            if (sim == 1.0 and same_digits) or (dist is not None and dist <= 50):
                out.append((a, b, sim, dist,
                            "이름 동일" if sim == 1.0 else "좌표 50m 이내(이름 다름) — 원본 좌표 오류 가능"))
    return out
