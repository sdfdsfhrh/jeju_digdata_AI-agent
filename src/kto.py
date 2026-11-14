"""[옵션] 한국관광공사 무장애 여행 정보 — 기본 DB와 분리 보관.

- 기본 판정(accessibility_item)에는 섞지 않는다.
- 허브 장소와 매칭되는 곳만 비교표(kto_hub_comparison)를 만든다.
- 출처가 두 개라는 이유로 정확하다고 판단하지 않는다: 판정은 '일치 가능/불일치 가능/비교불가'만 쓰고
  최종 판단은 사람 검토로 넘긴다.
"""
from __future__ import annotations

import re

from common import stable_id
from integrate import AUTO, judge

COMPARE_TOPICS = {"장애인주차장": "parking", "장애인화장실": "restroom"}


def _kto_hint(text):
    """관광공사 서술문에서 있음/없음 단서만 찾는다 (판정이 아니라 비교용 힌트)."""
    if not text:
        return None
    if re.search(r"없음|없습니다|없다|미설치|불가", text):
        return "없음 단서"
    if re.search(r"있음|있습니다|있다|설치|가능|\d+\s*(대|면|개)", text):
        return "있음 단서"
    return None


def build_kto(list_rows, detail_rows, list_sf, detail_sf, places, items):
    kto_places, kto_acc, comps, reviews = [], [], [], []
    detail_by_id = {}
    for d in detail_rows:
        cid = str(d.get("contentid"))
        detail_by_id[cid] = d
        for k, v in d.items():
            if k in ("contentid", "title") or not str(v).strip():
                continue
            kto_acc.append(dict(kto_id=cid, field=k, value_raw=v, source_file_id=detail_sf))

    item_by_place = {}
    for it in items:
        item_by_place.setdefault(it["place_id"], {})[it["item"]] = it

    for r in list_rows:
        cid = str(r.get("contentid"))
        lat, lon = _num(r.get("mapy")), _num(r.get("mapx"))
        best = None
        for p in places:
            res, sim, dist, am, why = judge(r.get("title"), r.get("addr1"), lat, lon,
                                            p["name"], p.get("address"), p.get("lat"),
                                            p.get("lon"))
            if res and (best is None or (res == AUTO and best[0] != AUTO) or sim > best[1]):
                best = (res, sim, dist, p)
        status = best[0] if best else "미매칭(보강 후보)"
        kto_places.append(dict(
            kto_id=cid, title=r.get("title"), addr=r.get("addr1"), lat=lat, lon=lon,
            contenttypeid=r.get("contenttypeid"), modifiedtime=r.get("modifiedtime"),
            matched_place_id=best[3]["place_id"] if best and best[0] == AUTO else None,
            match_status=status, name_sim=round(best[1], 3) if best else None,
            dist_m=round(best[2], 1) if best and best[2] is not None else None,
            data_status="참고용(외부 출처, 기본 판정 미사용)", source_file_id=list_sf))
        if best and best[0] != AUTO:
            reviews.append(dict(review_id=stable_id("RV", "kto", cid), review_type="장소매칭",
                                place_id=best[3]["place_id"], source_file_id=list_sf,
                                detail=f"관광공사 '{r.get('title')}' ↔ 허브 '{best[3]['name']}' 연결 불확실",
                                candidates=f"유사도 {best[1]:.2f}, 거리 {'-' if best[2] is None else round(best[2])}m",
                                status="미검토"))
        if best and best[0] == AUTO:
            pid = best[3]["place_id"]
            d = detail_by_id.get(cid)
            for topic, field in COMPARE_TOPICS.items():
                hub = item_by_place.get(pid, {}).get(topic)
                kraw = (d or {}).get(field)
                if d is None:
                    judgement = "비교불가(관광공사 상세 미수집)"
                elif hub is None:
                    judgement = "비교불가(허브 항목 없음)"
                else:
                    hint = _kto_hint(kraw)
                    if hint is None:
                        judgement = "판단보류(관광공사 원문에 단서 없음)"
                    elif (hint == "없음 단서") == (hub["status"] == "없음"):
                        judgement = "일치 가능(사람 확인 권장)"
                    else:
                        judgement = "불일치 가능(검토 필요)"
                comps.append(dict(place_id=pid, kto_id=cid, topic=topic,
                                  hub_status=hub["status"] if hub else None,
                                  hub_raw=hub["value_raw"] if hub else None, kto_raw=kraw,
                                  judgement=judgement))
    return kto_places, kto_acc, comps, reviews


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None
