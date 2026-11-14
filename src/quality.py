"""데이터 품질 검증: 실제 계산값과 '미실행(사유)'를 구분해서 보고."""
from __future__ import annotations

import json
import os

import pandas as pd

CORE_ITEMS = ["장애인주차장", "장애인화장실"]


def _q(con, sql):
    return pd.read_sql(sql, con)


def run_quality(con, out_dir, duplicates, kto_enabled):
    m = {}

    def put(key, value, note=""):
        note = str(note)
        parts = note.split(", ")
        if len(parts) > 10:   # 목록이 길면 앞 10개만 + 개수
            note = ", ".join(parts[:10]) + f" 외 {len(parts) - 10}건"
        m[key] = {"value": value, "note": note}

    place = _q(con, "SELECT * FROM place")
    sf = _q(con, "SELECT * FROM source_file")
    items = _q(con, "SELECT * FROM accessibility_item")
    links = _q(con, "SELECT * FROM place_source_link")
    conf = _q(con, "SELECT * FROM conflict")
    fails = _q(con, "SELECT * FROM extraction_failure")

    put("전체 장소 수", int(len(place)),
        "; ".join(f"{k}: {v}" for k, v in place["detail_level"].value_counts().items()))
    put("중복 의심 장소 쌍", len(duplicates),
        "; ".join(f"{a['name']}↔{b['name']}({why}, {0 if d is None else round(d)}m)"
                  for a, b, s, d, why in duplicates))

    put("원본 파일 수", int(len(sf)),
        "; ".join(f"{k}: {v}" for k, v in sf["file_kind"].value_counts().items()))
    put("추출 실패 파일 수", int((sf["parse_status"] == "실패").sum()),
        "부분성공 " + str(int((sf["parse_status"] == "부분성공").sum())) + "건")
    put("추출 실패 항목 수", int(len(fails)),
        "; ".join(f"{r.item}({r.reason})" for r in fails.itertuples())[:500])

    detail = place[place["detail_level"] == "상세파일있음"]
    if len(detail) == 0:
        put("접근성 항목별 결측률", "미실행", "상세파일이 있는 장소가 없음")
    else:
        rates = {}
        for it in CORE_ITEMS:
            sub = items[(items["item"] == it) & (items["place_id"].isin(detail["place_id"]))]
            known = sub[sub["status"] != "미확인"]["place_id"].nunique()
            rates[it] = f"{round(100 * (1 - known / len(detail)), 1)}% ({len(detail) - known}/{len(detail)}곳 미확인)"
        for it, sub in items.groupby("item"):
            if it in CORE_ITEMS:
                continue
            unk = (sub["status"] == "미확인").mean()
            rates[it] = f"미확인 {round(100 * unk, 1)}% (n={len(sub)})"
        put("접근성 항목별 결측률", rates, "결측 = 상태 '미확인'(정보 없음). '없음'(시설 없음)은 결측이 아님")
    put("상태별 항목 수", items["status"].value_counts().to_dict() if len(items) else {},
        "검토필요: " + str(int(items["verify_status"].str.startswith("검토필요").sum())) + "건")

    idx_links = links[links["link_method"].fillna("").str.startswith("색인매칭")]
    b2019 = detail[detail["bundle"] == "2019-2020"]
    if len(b2019) == 0:
        put("장소 매칭 성공률(상세파일↔색인)", "미실행", "2019-2020 상세파일 장소가 없음")
    else:
        ok = idx_links[idx_links["place_id"].isin(b2019["place_id"])]["place_id"].nunique()
        put("장소 매칭 성공률(상세파일↔색인)", f"{round(100 * ok / len(b2019), 1)}% ({ok}/{len(b2019)})",
            "2021년 묶음은 허브 원본 색인에 없으므로 분모에서 제외")
    rv = _q(con, "SELECT review_type, COUNT(*) n FROM review_queue GROUP BY review_type")
    put("검토 대기 건수", dict(zip(rv["review_type"], rv["n"].astype(int))), "")

    put("출처 내 정보 충돌 건수", int((conf["topic"].fillna("").str.contains("요약표 vs 상세표")).sum()),
        "같은 파일 안 요약표와 상세표 값이 다른 경우")
    if kto_enabled:
        comp = _q(con, "SELECT * FROM kto_hub_comparison")
        put("출처 간 정보 충돌 건수(허브↔관광공사)",
            int((comp["judgement"].str.startswith("불일치")).sum()) if len(comp) else 0,
            f"비교 {len(comp)}건 / " + "; ".join(
                f"{k}: {v}" for k, v in comp["judgement"].value_counts().items()) if len(comp) else "비교 0건")
    else:
        put("출처 간 정보 충돌 건수(허브↔관광공사)", "미실행", "--with-kto 옵션을 켜지 않음 (기본값: 관광공사 데이터 미사용)")

    put("좌표가 없는 장소 수", int(place["lat"].isna().sum()),
        ", ".join(place[place["lat"].isna()]["name"].tolist()))
    put("데이터 기준일 누락(장소)", int(place["base_date"].isna().sum()),
        ", ".join(place[place["base_date"].isna()]["name"].tolist()))
    put("데이터 기준일 누락(원본 파일)", int(sf["base_date"].isna().sum()),
        ", ".join(sf[sf["base_date"].isna()]["file_name"].tolist()))
    targets = _q(con, "SELECT place_id, marked FROM target_recommendation")
    if len(targets):
        allmarked = targets.groupby("place_id")["marked"].apply(lambda s: (s == "표시있음").all()).sum()
        put("추천대상 표가 전부 '●'인 장소 수", int(allmarked),
            "모든 유형에 ●가 있으면 변별력이 없을 수 있음 → 원본 양식 확인 필요")

    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "quality_report.json"), "w", encoding="utf-8") as f:
        json.dump(m, f, ensure_ascii=False, indent=2, default=str)
    lines = ["# 데이터 품질 검증 보고서", "", "| 항목 | 값 | 비고 |", "|---|---|---|"]
    for k, v in m.items():
        val = v["value"]
        if isinstance(val, dict):
            val = "<br>".join(f"{a}: {b}" for a, b in val.items())
        lines.append(f"| {k} | {val} | {str(v['note']).replace('|', '/')} |")
    with open(os.path.join(out_dir, "quality_report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return m
