"""
제주 무장애 여행 통합 DB 구축 (실행 진입점)

사용법
    python build_db.py                              # 기본: data/raw → output/
    python build_db.py --catalog 데이터목록.xlsx     # 허브 데이터 목록으로 데이터번호·기준일 채우기
    python build_db.py --with-kto                   # 한국관광공사 보조 출처 통합(data/extra)

결과
    output/jeju_bf.sqlite          통합 DB
    output/csv/*.csv               테이블별 CSV (엑셀에서 열림, UTF-8 BOM)
    output/review/*.csv            사람이 검토할 목록 (검토 대기열, 추출 실패, 서술문 추출값)
    output/quality_report.md|json  품질 검증 보고서
    data/manifest.generated.csv    파일별 판별 결과 (장소명 수정 시 manifest_override.csv에 적기)
    logs/build.log                 파일별 처리 로그
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
import os
import re
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from common import (UNK, file_sha256, haversine_m, name_similarity, norm_name,  # noqa: E402
                    read_csv_auto, setup_logger, stable_id, STATUS_RULES)
from db import connect, export_csv, write_rows  # noqa: E402
from extract_hwp import detect_kind, extract_general_2021, extract_narrative_2019  # noqa: E402
from hwp_reader import read_hwp  # noqa: E402
from integrate import build_places, find_duplicates  # noqa: E402
from prep_csv import (detect_csv_kind, parse_index, parse_nearby, parse_points_2019,  # noqa: E402
                      parse_points_2021)
from legacy_points import extract_facilities
from raw_scan import scan
from quality import run_quality  # noqa: E402

VERSION = "0.1.0"
SUFFIX = {"general_2021": "무장애여행일반정보", "nearby_2021": "무장애여행주변정보",
          "points_2021": "무장애여행위치정보", "narrative_2019": "무장애여행정보_",
          "points_2019": "무장애여행정보_"}


# ---------------------------------------------------------------------------
# 보조 함수
# ---------------------------------------------------------------------------
def guess_name_from_filename(fn: str):
    base = re.sub(r"^[0-9a-f]{8}-", "", os.path.basename(fn))      # 업로드 접두어 제거
    base = os.path.splitext(base)[0]
    m = re.search(r"(.+?)_무장애여행(일반|주변|위치)정보", base)
    if not m:
        m = re.search(r"무장애여행정보_(.+)$", base)
    name = m.group(1) if m else None
    if name and re.search(r"[가-힣]", name):
        return name.replace("제주특별자치도_", "").strip()
    return None


def load_catalog(path):
    if not path:
        return []
    raw = pd.read_excel(path, header=None, dtype=str) if path.endswith((".xlsx", ".xls")) \
        else pd.read_csv(path, header=None, dtype=str, encoding="utf-8-sig")
    hdr = next(i for i in range(min(10, len(raw))) if "데이터명" in raw.iloc[i].tolist())
    df = raw.iloc[hdr + 1:].copy()
    # 열 이름이 파일마다 조금씩 다름 (번호/No., 수집기간/수집 기간)
    cols = [str(c).replace(" ", "") for c in raw.iloc[hdr].tolist()]
    alias = {"No.": "번호", "NO": "번호", "No": "번호"}
    df.columns = [alias.get(c, c) for c in cols]
    return df[["번호", "데이터명", "수집기간"]].dropna(subset=["데이터명"]).to_dict("records")


def catalog_lookup(catalog, kind, place_name):
    if not catalog:
        return None
    if kind == "index":
        cands = [c for c in catalog if c["데이터명"].strip() == "무장애 여행지 정보(통합)"]
        return cands[0] if cands else None
    suf = SUFFIX.get(kind)
    if not suf or not place_name:
        return None
    scored = []
    for c in catalog:
        nm = c["데이터명"]
        if suf not in nm:
            continue
        core = nm.replace("제주특별자치도_", "").replace(suf, "").strip("_ ")
        scored.append((name_similarity(core, place_name), c))
    scored.sort(key=lambda x: -x[0])
    if scored and scored[0][0] == 1.0:
        return scored[0][1]
    # 한 글자 오타(예: 벌랑/벌낭)처럼 거의 같은 경우: 0.9 이상이고 2등과 차이가 날 때만 (기준일 메타데이터용)
    if scored and scored[0][0] >= 0.9 and (len(scored) == 1 or scored[1][0] < scored[0][0] - 0.05):
        return scored[0][1]
    return None


def public_source_lookup(rows, kind, place_name):
    """개별 공개 출처표 또는 묶음 한 행을 연결한다. 묶음 번호를 개별 번호로 추정하지 않는다."""
    matched=catalog_lookup(rows,kind,place_name)
    if matched:
        return matched
    labels={"index":"무장애 여행지 정보(통합)","general_2021":"무장애여행 일반정보 2021",
            "nearby_2021":"무장애여행 주변정보 2021","points_2021":"무장애여행 위치정보 2021",
            "narrative_2019":"무장애여행정보 2019~20 추가18곳","points_2019":"무장애여행정보 2019~20 추가18곳"}
    label=re.sub(r"\s+","",labels.get(kind,""))
    matches=[row for row in rows if label and re.sub(r"\s+","",row["데이터명"])==label]
    return matches[0] if len(matches)==1 else None


def period_end(period):
    if not period or "자동갱신" in str(period):
        return None
    parts = str(period).split("~")
    return parts[-1].strip() or None


def pick_anchor(points):
    """장소 대표 좌표: '주차' 지점 우선, 없으면 첫 지점."""
    valid = [p for p in points if p["lat"] is not None and p["lon"] is not None]
    if not valid:
        return None
    for p in valid:
        if "주차" in (p["label"] or ""):
            return p
    return sorted(valid, key=lambda p: p["seq"])[0]


# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default="data/raw")
    ap.add_argument("--out", default="output")
    ap.add_argument("--catalog", default=None, help="제주데이터허브 데이터 목록(xlsx/csv) 경로")
    ap.add_argument("--no-catalog", action="store_true", help="catalog를 읽지 않는 제출용 빌드")
    ap.add_argument("--data-sources", default="docs/data_sources.csv", help="사용자가 공개 상세 페이지로 확인한 출처표")
    ap.add_argument("--override", default="data/manifest_override.csv")
    ap.add_argument("--with-kto", action="store_true", help="한국관광공사 보조 출처 통합(data/extra CSV가 있으면 자동)")
    args = ap.parse_args()

    if args.no_catalog and args.catalog:
        ap.error("--no-catalog와 --catalog는 함께 사용할 수 없습니다")
    log = setup_logger("logs")
    log.info(f"시작 v{VERSION} raw={args.raw} catalog={args.catalog} with_kto={args.with_kto}")
    os.makedirs(args.out, exist_ok=True)
    db_path = os.path.join(args.out, "jeju_bf.sqlite")
    if os.path.exists(db_path):
        os.remove(db_path)
    con = connect(db_path)

    catalog = load_catalog(args.catalog) if not args.no_catalog else []
    if args.no_catalog and os.path.exists(args.data_sources):
        df = pd.read_csv(args.data_sources, encoding="utf-8-sig", dtype=str).fillna("")
        df=df.rename(columns={"출처URL":"출처 URL"})
        required = {"데이터번호", "데이터명", "제공처", "기준일", "등록일", "출처 URL"}
        if not required <= set(df.columns):
            raise ValueError("공개 출처표 열이 올바르지 않습니다")
        for _, row in df.iterrows():
            if not all(str(row[k]).strip() for k in ("데이터번호", "데이터명", "제공처", "출처 URL")):
                continue
            if not str(row["출처 URL"]).startswith("https://"):
                raise ValueError("공개 출처 URL은 https 주소여야 합니다")
            catalog.append({"번호": row["데이터번호"], "데이터명": row["데이터명"], "수집기간": row["기준일"], "public_url": row["출처 URL"], "provider": row["제공처"], "registered": row["등록일"]})
    overrides = {}
    if os.path.exists(args.override):
        ov = pd.read_csv(args.override, dtype=str, encoding="utf-8-sig").fillna("")
        overrides = {r["file_name"]: r["place_name"] for _, r in ov.iterrows() if r["place_name"]}

    # ---------------- 1. 파일 스캔·판별·파싱 ----------------
    files, scan_report = scan(args.raw)
    os.makedirs(os.path.join(args.out,"review"),exist_ok=True)
    scan_path=os.path.join(args.out,"review","raw_scan_report.json")
    with open(scan_path,"w",encoding="utf-8") as f:
        json.dump(scan_report,f,ensure_ascii=False,indent=2)
    log.info(f"[입력조사] 장소 폴더 {len(scan_report['place_folders'])}개, 이미지 {scan_report['image_count']}개(내용 미판독)")
    for record in scan_report['files']:
        if record['action']=='제외': log.info(f"[제외] {record['path']}: {record['reason']}")
    sources, parsed = [], {}
    seen_sha = {}
    for entry in files:
        path,fn,folder = entry["path"],entry["relative"],entry["folder"]
        basename=os.path.basename(path)
        sha = file_sha256(path)
        filename_place=guess_name_from_filename(basename)
        place_hint=filename_place or folder or overrides.get(fn) or overrides.get(basename)
        duplicate_key=(sha,norm_name(place_hint or ""))
        if duplicate_key in seen_sha:
            # 내용이 완전히 같은 파일(예: 'xxx (1).csv' 중복 다운로드)은 한 번만 넣는다
            log.warning(f"[중복파일 건너뜀] {fn} = {seen_sha[duplicate_key]} 와 같은 장소·내용 동일")
            scan_report.setdefault("duplicates",[]).append(dict(path=fn,kept=seen_sha[duplicate_key],reason="같은 장소·SHA-256 중복"))
            continue
        seen_sha[duplicate_key] = fn
        sid = stable_id("SF", sha,folder) if folder else stable_id("SF", sha)
        rec = dict(source_file_id=sid, file_name=fn, file_ext=os.path.splitext(fn)[1].lower(),
                   sha256=sha, size_bytes=os.path.getsize(path), parse_status="성공",
                   parse_message="", place_name_declared=None, place_name_source=None)
        try:
            if fn.lower().endswith(".hwp"):
                doc = read_hwp(path)
                kind = detect_kind(doc)
                rec.update(file_kind=kind, reader=f"hwp:{doc.reader}")
                if kind == "general_2021":
                    res = extract_general_2021(doc)
                elif kind == "narrative_2019":
                    res = extract_narrative_2019(doc, expected_name=filename_place or folder)
                else:
                    raise ValueError("알 수 없는 HWP 양식")
                rec["place_name_declared"] = res.place.get("name")
                rec["place_name_source"] = "content"
                rec["_alias"] = guess_name_from_filename(fn)   # 파일명 속 이름 (본문 이름과 다를 수 있음)
                nb_names = []
                for t in doc.tables().values():
                    if t.get((0, 0), "").strip() == "주변 시설 정보":
                        nb_names = [v.strip() for (r, c), v in t.items() if c == 1 and r >= 2 and v.strip()]
                parsed[sid] = dict(kind=kind, res=res, nearby_names=nb_names)
                if res.failures:
                    rec["parse_status"] = "부분성공"
                    rec["parse_message"] = f"추출 실패 항목 {len(res.failures)}개"
            else:
                df, enc = read_csv_auto(path)
                kind = detect_csv_kind(list(df.columns))
                rec.update(file_kind=kind, encoding=enc, reader="csv")
                if kind == "index":
                    parsed[sid] = dict(kind=kind, rows=parse_index(df))
                elif kind == "nearby_2021":
                    parsed[sid] = dict(kind=kind, rows=parse_nearby(df))
                elif kind == "points_2021":
                    pts, meas = parse_points_2021(df)
                    parsed[sid] = dict(kind=kind, points=pts, measures=meas)
                elif kind == "points_2019":
                    pts, meas = parse_points_2019(df)
                    parsed[sid] = dict(kind=kind, points=pts, measures=meas)
                    if any(pt.get("label") or pt.get("description") or pt.get("detail_raw") for pt in pts):
                        parsed[sid]["res"] = extract_facilities(pts, basename)
                        rec["parse_status"] = "부분성공" if parsed[sid]["res"].failures else "성공"
                        rec["parse_message"] = f"지점 원문 시설 추출; 미확인 {len(parsed[sid]['res'].failures)}항목"
                elif kind in ("kto_list", "kto_detail"):
                    parsed[sid] = dict(kind=kind, rows=df.to_dict("records"))
                else:
                    raise ValueError(f"알 수 없는 CSV 양식: {list(df.columns)[:6]}")
            # 파일명 → 장소명 (내용에서 못 얻은 경우)
            if not rec["place_name_declared"]:
                nm = guess_name_from_filename(fn)
                if nm:
                    rec["place_name_declared"], rec["place_name_source"] = nm, "filename"
            if not filename_place and folder:
                rec["place_name_declared"],rec["place_name_source"]=folder,"folder"
                if "res" in parsed.get(sid,{}):
                    rec["_alias"]=parsed[sid]["res"].place.get("name")
                    parsed[sid]["res"].place["name"]=folder
            override_key=fn if fn in overrides else basename if not folder and basename in overrides else None
            if override_key:
                rec["place_name_declared"], rec["place_name_source"] = overrides[override_key], "manifest_override"
        except Exception as e:  # noqa: BLE001
            rec.update(file_kind=rec.get("file_kind", "unknown"), parse_status="실패",
                       parse_message=f"{type(e).__name__}: {e}")
            log.error(f"[실패] {fn}: {e}")
        sources.append(rec)
        log.info(f"[{rec['parse_status']}] {fn} → {rec.get('file_kind')} / 장소명={rec['place_name_declared']}"
                 f" ({rec['place_name_source']}) {rec['parse_message']}")

    with open(scan_path,"w",encoding="utf-8") as f:
        json.dump(scan_report,f,ensure_ascii=False,indent=2)
    by_id = {s["source_file_id"]: s for s in sources}
    index_sf = next((s["source_file_id"] for s in sources if s.get("file_kind") == "index"), None)
    index_rows = parsed[index_sf]["rows"] if index_sf else []
    reviews, failures, conflicts = [], [], []

    # ---------------- 2. 장소명이 없는 CSV 연결 ----------------
    hwp_groups = {sid: p for sid, p in parsed.items() if p["kind"] in ("general_2021", "narrative_2019")}
    for s in sources:
        sid, kind = s["source_file_id"], s.get("file_kind")
        if s["place_name_declared"] or sid not in parsed:
            continue
        if kind == "nearby_2021":   # HWP 안 '주변 시설 정보' 표와 시설명 비교
            names = {r["name"] for r in parsed[sid]["rows"]}
            best = max(((len(names & set(p["nearby_names"])) / max(1, len(names | set(p["nearby_names"]))), hs)
                        for hs, p in hwp_groups.items() if p["nearby_names"]), default=(0, None))
            if best[0] >= 0.6:
                s["place_name_declared"] = hwp_groups[best[1]]["res"].place["name"]
                s["place_name_source"] = f"content_link(주변시설 일치율 {best[0]:.0%})"
        elif kind == "points_2019" and index_rows:   # 첫 지점 좌표 ↔ 색인 좌표
            anchor = pick_anchor(parsed[sid]["points"])
            if anchor:
                ds = []
                for r in index_rows:
                    d = haversine_m(anchor["lat"], anchor["lon"], r["lat"], r["lon"])
                    ds.append((1e9 if d is None else d, r["row_no"], r))   # 거리 0m도 정상 처리
                ds = [(d, r) for d, _, r in sorted(ds, key=lambda x: (x[0], x[1]))]
                d1 = ds[0][0]
                d2 = ds[1][0] if len(ds) > 1 else 1e9
                if d1 <= 500 and d2 > 2 * d1:
                    s["place_name_declared"] = ds[0][1]["name"]
                    s["place_name_source"] = f"geo_link(색인 row {ds[0][1]['row_no']}, {d1:.0f}m)"
        if not s["place_name_declared"] and kind not in ("index", "kto_list", "kto_detail"):
            reviews.append(dict(review_id=stable_id("RV", "file", sid), review_type="파일연결",
                                source_file_id=sid,
                                detail=f"{s['file_name']}({kind})의 장소를 알 수 없음 → manifest_override.csv에 장소명 기입 필요",
                                status="미검토"))
            log.warning(f"[연결실패] {s['file_name']} 장소 미확인")

    # ---------------- 3. 장소 그룹 만들기 ----------------
    groups = []   # {name, kind_bundle, members:[sid]}
    for s in sorted(sources, key=lambda x: 0 if x.get("file_kind") in ("general_2021", "narrative_2019") else 1):
        if s.get("file_kind") in ("index", "kto_list", "kto_detail") or not s["place_name_declared"]:
            continue
        names = {s["place_name_declared"]} | ({s["_alias"]} if s.get("_alias") else set())
        g = next((g for g in groups
                  if any(name_similarity(a, b) == 1.0 for a in g["aliases"] for b in names)), None)
        if g is None and s.get("file_kind") in ("points_2021", "nearby_2021", "points_2019"):
            # 위치·주변 파일 이름이 일반정보와 한두 글자 다른 경우(예: 벌낭/벌랑, '길' 유무).
            # 상세파일 그룹 중 유사도 0.85 이상 후보가 '하나만' 뚜렷할 때만 묶고, 검토 목록에 남긴다.
            scored = sorted(
                ((max(name_similarity(a, b) for a in g_["aliases"] for b in names), g_)
                 for g_ in groups if g_.get("has_main")),
                key=lambda x: -x[0])
            if scored and scored[0][0] >= 0.85 and (len(scored) == 1 or scored[1][0] < scored[0][0] - 0.1):
                sim, g = scored[0]
                reviews.append(dict(
                    review_id=stable_id("RV", "fuzzy", s["source_file_id"]), review_type="파일연결",
                    source_file_id=s["source_file_id"],
                    detail=f"{s['file_name']} → '{g['name']}' 그룹에 이름 유사도로 연결 (유사도 {sim:.2f}). "
                           f"틀리면 manifest_override.csv에 장소명 기입",
                    candidates="; ".join(f"{x[1]['name']}({x[0]:.2f})" for x in scored[:3]),
                    status="미검토"))
                log.info(f"[유사이름연결] {s['file_name']} → {g['name']} (유사도 {sim:.2f})")
        if g is None:
            g = dict(name=s["place_name_declared"], aliases=set(), members=[])
            groups.append(g)
        g["aliases"] |= names
        g["members"].append(s["source_file_id"])
        if s.get("file_kind") in ("general_2021", "narrative_2019"):
            g["has_main"] = True

    file_places = []
    for g in groups:
        fp = dict(name=g["name"], address=None, lat=None, lon=None, coord_source=None,
                  bundle=None, base_date=None, sources=[])
        for sid in g["members"]:
            s, p = by_id[sid], parsed.get(sid, {})
            kind = s["file_kind"]
            fp["bundle"] = fp["bundle"] or ("2021" if kind.endswith("2021") else "2019-2020")
            cat = None
            for alias in [g["name"]] + sorted(g["aliases"]):
                cat = (public_source_lookup if args.no_catalog else catalog_lookup)(catalog, kind, alias)
                if cat:
                    break
            if cat:
                if args.no_catalog:
                    s.update(public_provider=cat["provider"], public_registered_date=cat["registered"], public_source_url=cat["public_url"])
                s["hub_dataset_no"], s["hub_dataset_name"] = cat["번호"], cat["데이터명"]
                s["catalog_period"] = None if args.no_catalog else cat["수집기간"]
                if args.no_catalog and cat["수집기간"]:
                    s["base_date"], s["base_date_source"] = cat["수집기간"], "공개 상세 페이지: " + cat["public_url"]
            if "res" in p:
                pl = p["res"].place
                fp["name"] = pl.get("name") or fp["name"]
                fp["address"] = fp["address"] or pl.get("address")
                for k in ("overview", "mobility_note", "recommended_course", "full_course"):
                    fp[k] = fp.get(k) or pl.get(k)
            if "points" in p:
                a = pick_anchor(p["points"])
                if a and fp["lat"] is None:
                    fp["lat"], fp["lon"] = a["lat"], a["lon"]
                    fp["coord_source"] = f"지점CSV {s['file_name']} 순서 {a['seq']}({a['label']})"
            # 기준일: CSV 행의 데이터기준일자 > 카탈로그 수집기간 끝
            bd = None
            for key in ("rows", "points"):
                vals = {r.get("base_date") for r in p.get(key, []) if r.get("base_date")}
                if vals:
                    bd = max(vals)
            if bd:
                s["base_date"], s["base_date_source"] = bd, "원본 데이터기준일자"
            elif s.get("catalog_period") and period_end(s["catalog_period"]):
                s["base_date"], s["base_date_source"] = period_end(s["catalog_period"]), "카탈로그 수집기간"
            if s.get("base_date"):
                fp["base_date"] = max(filter(None, [fp["base_date"], s["base_date"]]))
            fp["sources"].append(dict(source_file_id=sid, method=s["place_name_source"],
                                      raw_name=s["place_name_declared"], status="자동연결"))
        file_places.append(fp)

    idx_base = None
    if index_sf:
        cat = (public_source_lookup if args.no_catalog else catalog_lookup)(catalog, "index", None)
        s = by_id[index_sf]
        if cat:
            if args.no_catalog:
                s.update(public_provider=cat["provider"], public_registered_date=cat["registered"], public_source_url=cat["public_url"])
            s["hub_dataset_no"], s["hub_dataset_name"], s["catalog_period"] = cat["번호"], cat["데이터명"], None if args.no_catalog else cat["수집기간"]
            idx_base = period_end(cat["수집기간"])
            s["base_date"], s["base_date_source"] = idx_base, ("공개 상세 페이지: " + cat["public_url"]) if args.no_catalog else "카탈로그 수집기간"

    places, links, rv = build_places(file_places, index_rows, index_sf, idx_base)
    reviews += rv
    pid_by_sid = {}
    for fp in file_places:
        for src in fp["sources"]:
            pid_by_sid[src["source_file_id"]] = fp["place_id"]

    # ---------------- 4. 세부 테이블 채우기 ----------------
    items, details, measures, targets, points, nearby = [], [], [], [], [], []
    for sid, p in parsed.items():
        pid = pid_by_sid.get(sid)
        s = by_id[sid]
        if "res" in p:
            res = p["res"]
            for f in res.failures:
                failures.append(dict(fail_id=stable_id("FL", sid, f[0]), source_file_id=sid,
                                     item=f[0], reason=f[1], source_locator=f[2]))
            if pid is None:
                continue
            for i, it in enumerate(res.items):
                items.append(dict(item_id=stable_id("IT", pid, sid, it["item"], i), place_id=pid,
                                  source_file_id=sid, **it))
            for i, d in enumerate(res.details):
                details.append(dict(detail_id=stable_id("DT", pid, sid, i), place_id=pid,
                                    source_file_id=sid, **d))
            for i, m in enumerate(res.measures):
                measures.append(dict(meas_id=stable_id("MS", pid, sid, "h", i), place_id=pid,
                                     source_file_id=sid, **m))
            for i, t in enumerate(res.targets):
                targets.append(dict(rec_id=stable_id("RC", pid, sid, i), place_id=pid,
                                    source_file_id=sid, **t))
            for c in res.conflicts:
                conflicts.append(dict(conflict_id=stable_id("CF", pid, sid, c[0]), place_id=pid,
                                      topic=c[0], value_a=c[1], source_a=f"{s['file_name']} {c[2]}",
                                      value_b=c[3], source_b=f"{s['file_name']} {c[4]}", note=c[5]))
                reviews.append(dict(review_id=stable_id("RV", "cf", pid, c[0]), review_type="출처내충돌",
                                    place_id=pid, source_file_id=sid,
                                    detail=f"{c[0]}: '{c[1]}' vs '{c[3]}' ({c[5]})", status="미검토"))
        if "points" in p and pid:
            for pt in p["points"]:
                points.append(dict(point_id=stable_id("PT", pid, sid, pt["seq"], pt["source_locator"]),
                                   place_id=pid, source_file_id=sid, **pt))
            for i, m in enumerate(p["measures"]):
                measures.append(dict(meas_id=stable_id("MS", pid, sid, "c", i), place_id=pid,
                                     source_file_id=sid, **m))
        elif p["kind"] == "nearby_2021" and pid:
            for r in p["rows"]:
                nearby.append(dict(facility_id=stable_id("NB", pid, sid, r["row_no"]), place_id=pid,
                                   source_file_id=sid, source_locator=f"row {r.pop('row_no')}", **r))

    # 추천대상 표가 전부 ● 인 장소 → 검토
    tdf = pd.DataFrame(targets)
    if len(tdf):
        allm = [pid for pid, sub in tdf.groupby("place_id") if (sub["marked"] == "표시있음").all()]
        n_place = tdf["place_id"].nunique()
        if allm and len(allm) >= 0.8 * n_place:
            # 대부분 장소가 전부 ●이면 장소별로 쌓지 않고 1건으로 요약 (표 자체의 변별력 문제)
            reviews.append(dict(review_id=stable_id("RV", "tg", "all"), review_type="추천표시변별력",
                                detail=f"추천대상 표: {len(allm)}/{n_place}곳이 모든 유형에 '●' → "
                                       "이 표는 장소 간 구분에 쓰기 어려움 (Agent 판정에서 제외 권장)",
                                status="미검토"))
        else:
            for pid in allm:
                reviews.append(dict(review_id=stable_id("RV", "tg", pid), review_type="추천표시변별력",
                                    place_id=pid, detail="추천대상 모든 유형에 '●' — 원본 양식상 의미 확인 필요",
                                    status="미검토"))

    # 중복 의심
    dups = find_duplicates(places)
    for a, b, sim, d, why in dups:
        reviews.append(dict(review_id=stable_id("RV", "dup", a["place_id"], b["place_id"]),
                            review_type="중복의심", place_id=a["place_id"],
                            detail=f"{a['name']} ↔ {b['name']}: {why}",
                            candidates=f"{b['place_id']} (유사도 {sim:.2f}, 거리 {'-' if d is None else round(d)}m)",
                            status="미검토"))

    # 관광공사 자료는 data/extra에 보관하고 허브 DB 저장 후 보조 출처로 통합한다.
    extra_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'extra')
    args.with_kto = args.with_kto or all(os.path.exists(os.path.join(extra_dir, fn))
                                       for fn in ('kto_list.csv', 'kto_detail.csv'))

    # ---------------- 6. 저장 ----------------
    for s_ in sources:
        s_.pop("_alias", None)
    write_rows(con, "source_file", sources)
    write_rows(con, "place", places)
    write_rows(con, "place_source_link", links)
    write_rows(con, "accessibility_item", items)
    write_rows(con, "facility_detail", details)
    write_rows(con, "measurement", measures)
    write_rows(con, "course_point", points)
    write_rows(con, "nearby_facility", nearby)
    write_rows(con, "target_recommendation", targets)
    write_rows(con, "extraction_failure", failures)
    write_rows(con, "review_queue", reviews)
    write_rows(con, "conflict", conflicts)
    write_rows(con, "status_rule", [dict(status=a, meaning=b, examples=c) for a, b, c in STATUS_RULES])
    write_rows(con, "run_info", [dict(key="version", value=VERSION),
                                 dict(key="built_at", value=dt.datetime.now().isoformat(timespec="seconds")),
                                 dict(key="with_kto", value=str(args.with_kto)),
                                 dict(key="catalog", value=str(bool(catalog) and not args.no_catalog))])
    if args.with_kto and all(os.path.exists(os.path.join(extra_dir, fn)) for fn in ('kto_list.csv', 'kto_detail.csv')):
        from kto_merge import merge
        result = merge(con, extra_dir)
        log.info(f"[관광공사 보조 통합] {result}")
    from parking_import import load as load_parking
    parking_report = load_parking(con, extra_dir, log)
    os.makedirs(os.path.join(args.out,'review'),exist_ok=True)
    with open(os.path.join(args.out,'review','parking_import_report.json'),'w',encoding='utf-8') as f:
        json.dump(parking_report,f,ensure_ascii=False,indent=2)
    if args.no_catalog:
        write_rows(con, "run_info", [dict(key="submission_no_catalog", value="True")])
    con.commit()

    tables = ["source_file", "place", "place_source_link", "accessibility_item", "facility_detail",
              "measurement", "course_point", "nearby_facility", "target_recommendation",
              "extraction_failure", "review_queue", "conflict", "status_rule", "parking_lot"]
    if args.with_kto:
        tables += ["kto_place", "kto_accessibility", "kto_hub_comparison"]
    export_csv(con, os.path.join(args.out, "csv"), tables)

    # 검토용 파일
    rdir = os.path.join(args.out, "review")
    os.makedirs(rdir, exist_ok=True)
    q = lambda sql: pd.read_sql(sql, con)  # noqa: E731
    q("""SELECT r.review_type, p.name AS place_name, r.detail, r.candidates, s.file_name, r.status
         FROM review_queue r LEFT JOIN place p ON r.place_id=p.place_id
         LEFT JOIN source_file s ON r.source_file_id=s.source_file_id ORDER BY r.review_type""") \
        .to_csv(os.path.join(rdir, "review_queue.csv"), index=False, encoding="utf-8-sig")
    q("""SELECT p.name AS place_name, a.category, a.item, a.status, a.status_reason, a.value_raw,
                a.evidence, a.applies_to, s.file_name, a.source_locator, a.verify_status
         FROM accessibility_item a JOIN place p ON a.place_id=p.place_id
         JOIN source_file s ON a.source_file_id=s.source_file_id
         ORDER BY p.name, a.category""") \
        .to_csv(os.path.join(rdir, "accessibility_for_review.csv"), index=False, encoding="utf-8-sig")
    q("""SELECT s.file_name, f.item, f.reason, f.source_locator FROM extraction_failure f
         JOIN source_file s ON f.source_file_id=s.source_file_id""") \
        .to_csv(os.path.join(rdir, "extraction_failures.csv"), index=False, encoding="utf-8-sig")
    pd.DataFrame(sources)[["file_name", "file_kind", "place_name_declared", "place_name_source",
                           "parse_status", "parse_message"]] \
        .to_csv("data/manifest.generated.csv", index=False, encoding="utf-8-sig")

    qm = run_quality(con, args.out, dups, args.with_kto)
    con.close()
    log.info(f"완료: 장소 {qm['전체 장소 수']['value']}곳, DB={db_path}")


if __name__ == "__main__":
    main()
