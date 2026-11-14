"""Agent 도구. 각 도구는 데이터를 조회·계산해서 {결과, 근거, 한계}를 돌려준다.

판정 원칙
- 상태값 4종(있음/없음/조건부/미확인)을 그대로 쓴다. '미확인'은 '없음'이 아니다.
- 필수 시설이 '없음'이면 조건 미충족, '미확인'이면 확인 필요(제외하지 않음), 대체시설이 있으면 조건부.
- 수치(경사각 등)는 원본 값과 참고 기준을 나란히 보여 주고, 기준 초과는 '주의'로만 표시한다(제외하지 않음).
"""
from __future__ import annotations

import re

from . import data, weather
from .parser import THEMES, TIME_SLOTS, Request

YES, NO, COND, UNK = "있음", "없음", "조건부", "미확인"

# 등급 (순서가 곧 우선순위)
G_OK, G_COND, G_CHECK, G_FAIL = "조건 충족", "조건부 충족", "확인 필요", "조건 미충족"
GRADE_ORDER = {G_OK: 0, G_COND: 1, G_CHECK: 2, G_FAIL: 3}

WHEEL = {"수동휠체어", "전동휠체어"}
MOBILITY = WHEEL | {"보행약자", "시니어", "영유아동반"}

# 경사 참고 기준: 「장애인·노인·임산부 등의 편의증진 보장에 관한 법률 시행규칙」 경사로 기울기 1/12 이하
# (건축물 경사로 기준이므로 산책로에 그대로 적용되는 법적 기준은 아님 → '참고'로만 사용)
SLOPE_REF_DEG = 4.76
SLOPE_REF_TEXT = "경사로 기울기 1/12(약 4.8°) — 편의증진법 시행규칙의 건축물 경사로 기준을 참고로 사용"

# 코스 지점 설명에서 이동 주의 문구를 찾는 단어 (원문을 그대로 보여 주기 위한 검색어일 뿐 판정어가 아님)
CAUTION_WORDS = r"경사|오르막|내리막|계단|단차|턱|비포장|울퉁|자갈|모래|판석|잔디|접근\s*불가|접근불가|접근\s*어려|좁|차량|횡단보도\s*없"

# 날씨 주의 임계값 (기획서·매뉴얼에 명시)
POP_CAUTION = 60      # 강수확률(%) 이상이면 실외 코스 주의
WIND_CAUTION = 9.0    # 풍속(m/s) 이상이면 해안 코스 강풍 주의


def ev(file_name, locator, text=None):
    """근거 표기 한 줄."""
    s = f"{file_name or '원본 파일 미상'} [{locator or '위치 미상'}]"
    return s + (f" “{str(text)[:80]}”" if text not in (None, "") else "")


# ---------------------------------------------------------------------------
# 1. 후보 검색
# ---------------------------------------------------------------------------
def all_regions() -> list[str]:
    regs = {"제주시", "서귀포시"}
    for p in data.detailed_places():
        si, emd = data.region_of(p.get("address"))
        if emd:
            regs.add(emd)
    return sorted(regs)


def _theme_hits(p: dict, themes: list[str]) -> list[str]:
    text = " ".join(str(p.get(k) or "") for k in ("name", "overview", "recommended_course", "full_course"))
    hits = []
    for th in themes:
        words = THEMES.get(th, [])
        if any(w in text for w in words) or (th == "해안" and re.search(r"[가-힣]항(?:과|길|\s|$)", p.get("name", ""))):
            hits.append(th)
    return hits


def search_places(req: Request) -> dict:
    places = [dict(p) for p in data.detailed_places()]   # 캐시 원본을 건드리지 않도록 복사
    limits = []
    cands = places
    if req.region:
        cands = [p for p in places if req.region in (data.region_of(p.get("address"))) or
                 (p.get("address") and req.region in p["address"])]
        if not cands:
            limits.append(f"'{req.region}' 지역에 상세정보가 있는 장소 없음 (조건 완화 여부는 Agent가 판단)")
    for p in cands:
        p["_theme_hits"] = _theme_hits(p, req.themes)
    if req.themes and not any(p["_theme_hits"] for p in cands):
        limits.append(f"요청한 성격({', '.join(req.themes)})과 맞는 장소가 없어 성격 조건은 순위에만 반영하지 않음")
    counts = data.place_counts()
    limits.append(f"상세 접근성 정보가 있는 {len(places)}곳만 판정 대상 "
                  f"(색인만 있는 {counts.get('색인만(상세파일 미수집)', 0)}곳은 근거 부족으로 제외)")
    return dict(candidates=cands, n_total=len(places), n_after_region=len(cands), limits=limits)


# ---------------------------------------------------------------------------
# 2. 접근성 판정
# ---------------------------------------------------------------------------
def check_accessibility(p: dict, req: Request) -> dict:
    rows = data.items(p["place_id"])
    by_item = {}
    for r in rows:
        by_item.setdefault(r["item"], r)       # 같은 항목이 여러 출처면 첫 번째(양식 추출)를 대표로
    alt = by_item.get("대체 화장실 안내")

    def item_view(name, r=None):
        r = r if r is not None else by_item.get(name)
        if r is None:
            return dict(item=name, status=UNK, reason="원본에 해당 항목 없음", evidence=None, raw=None)
        return dict(item=name, status=r["status"], reason=r["status_reason"], raw=r["value_raw"],
                    evidence=ev(r["file_name"], r["source_locator"], r["evidence"]),
                    source=r.get('origin', '제주데이터허브(필수)'), base_date=r.get('display_base_date'),
                    verify=r["verify_status"])

    from . import parking
    parking_info = parking.assess(p, item_view('장애인주차장'))
    need_res = []
    for n in req.needs:
        if n=='parking_general':
            v=dict(parking_info['general'])
        else:
            v=item_view('장애인주차장' if n=='parking_disabled' else n)
        v['condition_key']=n
        effective, note = v['status'], ''
        if n=='parking_general' and v['status']==COND:
            note=v['display']+' — 외부 주차장, 실제 이동 경로 확인 필요'
        if n in ('parking_disabled','장애인주차장') and parking_info['disabled']['supplement']:
            effective=COND;note=parking_info['disabled']['supplement']+' — 장소 자체 상태는 미확인 유지'
            v['evidence']=' / '.join(x for x in [v.get('evidence'),*(r['evidence'] for r in parking_info['disabled']['options'])] if x)
        if n == "장애인화장실" and v["status"] in (NO, UNK) and alt is not None:
            effective = COND
            note = f"현장 장애인 화장실 {v['status']} → 원본에 안내된 대체 화장실 이용: {alt['value_raw']}"
        need_res.append(dict(v, effective=effective, note=note,
                             alt_evidence=ev(alt["file_name"], alt["source_locator"], alt["value_raw"])
                             if note and n == "장애인화장실" and alt else None))

    effs = [x["effective"] for x in need_res]
    if NO in effs:
        grade = G_FAIL
    elif UNK in effs:
        grade = G_CHECK
    elif COND in effs:
        grade = G_COND
    else:
        grade = G_OK

    shown = ["장애인주차장", "장애인주차 면수", "장애인화장실", "대체 화장실 안내", "보조기기 대여",
             "해설사", "편의/부대시설", "출입 경사로", "휠체어 관람석", "휠체어대여", "출입구", "접근로", "엘리베이터", "유아차대여"]
    table = [item_view(r['item'], r) for r in rows if r['item'] in shown]
    for n in ("장애인주차장", "장애인화장실"):
        if n not in by_item:
            table.append(item_view(n))
    table.append(dict(parking_info['general']))
    unknown = [t["item"] for t in table if t["status"] == UNK]
    # 편의 점수: 필수로 고르지 않았어도 화장실·주차 상태를 순위에 반영 (있음 2, 조건부 1, 미확인 0, 없음 -1)
    pts = {YES: 2, COND: 1, UNK: 0, NO: -1}
    comfort = 0
    for n in ("장애인화장실", "장애인주차장"):
        st = by_item[n]["status"] if n in by_item else UNK
        if n == "장애인화장실" and st in (NO, UNK) and alt is not None:
            st = COND
        if n=='장애인주차장':
            if 'parking_general' in req.needs:st=parking_info['general']['effective']
            elif parking_info['disabled']['supplement']:st=COND
        comfort += pts.get(st, 0)
    known_core = sum(1 for n in ("장애인주차장", "장애인화장실")
                     if by_item.get(n) and by_item[n]["status"] != UNK)
    return dict(grade=grade, needs=need_res, table=table, unknown=unknown, known_core=known_core,
                comfort=comfort, parking=parking_info,
                alt_toilet=alt["value_raw"] if alt else None,
                conflicts=data.conflicts(p["place_id"]))


# ---------------------------------------------------------------------------
# 3. 코스 경사·주의 지점
# ---------------------------------------------------------------------------
def check_route(p: dict, req: Request) -> dict:
    ms = data.measures(p["place_id"])
    slopes = []
    for m in ms:
        if m["unit"] == "도" and ("경사" in m["kind"] or "각도" in m["kind"]):
            slopes.append(dict(value=m["value"], kind=m["kind"], alt="[대체시설]" in m["kind"],
                               point=m.get("point_seq"), raw=m["raw_text"],
                               evidence=ev(m["file_name"], m["source_locator"], m["raw_text"])))
    course = [s for s in slopes if not s["alt"]]
    over = [s for s in course if s["value"] > SLOPE_REF_DEG]
    pts = data.points(p["place_id"])
    cautions = []
    for c in pts:
        text = f"{c.get('label') or ''} {c.get('description') or ''}".strip()
        if c.get("label") == "삭제" or not text:
            continue
        if re.search(CAUTION_WORDS, text):
            cautions.append(dict(seq=c["seq"], text=text, lat=c["lat"], lon=c["lon"],
                                 evidence=ev(c["file_name"], c["source_locator"], text)))
    limits = []
    if not pts:
        limits.append("위치정보(코스 지점) 없음 → 코스 경사·주의 지점 확인 불가")
    elif not course:
        limits.append("코스 경사각 수치가 원본에 없음 (경사가 없다는 뜻은 아님)")
    relevant = req.user_type in MOBILITY or req.user_type is None
    return dict(course_slopes=course, alt_slopes=[s for s in slopes if s["alt"]],
                max_slope=max((s["value"] for s in course), default=None),
                over_ref=over, cautions=cautions, points=pts, relevant=relevant,
                ref=SLOPE_REF_TEXT, limits=limits)


# ---------------------------------------------------------------------------
# 4. 주변 대체시설
# ---------------------------------------------------------------------------
def find_nearby(p: dict) -> dict:
    rows = data.nearby(p["place_id"])
    available = bool(rows) or any(f["file_kind"] == "nearby_2021" for f in data.source_files(p["place_id"]))
    if not available:
        return dict(available=False, rows=[], wheel=[], toilet=[], limits=["주변정보 없음(데이터 미보유)"])
    view = [dict(category=r["category"], name=r["name"], distance_km=r["distance_km"],
                 wheelchair_entry=r["wheelchair_entry"], accessible_toilet=r["accessible_toilet"],
                 address=r["address"], phone=r["phone"],
                 evidence=ev(r["file_name"], r["source_locator"])) for r in rows]
    return dict(available=True, rows=view,
                wheel=[v for v in view if v["wheelchair_entry"] == YES],
                toilet=[v for v in view if v["accessible_toilet"] == YES],
                limits=["주변정보의 빈칸은 '없음'이 아니라 '미확인'(조사 여부를 원본에서 구분할 수 없음)"])


# ---------------------------------------------------------------------------
# 폐기된 도구 구간
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 6. 날씨
# ---------------------------------------------------------------------------
def check_weather(p: dict, req: Request) -> dict:
    if not req.date:
        return dict(status=UNK, reason="방문 날짜가 정해지지 않음", cautions=[])
    w = weather.forecast(p.get("lat"), p.get("lon"), req.date,
                         TIME_SLOTS.get(req.time_slot, TIME_SLOTS["종일"]), address=p.get("address"))
    cautions = []
    if w.get("status") == "조회됨":
        if w["pop_max"] >= POP_CAUTION or w["precip"] != ["없음"]:
            cautions.append(f"비/눈 가능(강수확률 최대 {w['pop_max']}%, {', '.join(w['precip'])}) — 실외 노면이 미끄러울 수 있음")
        if w.get("wind_max") is not None and w["wind_max"] >= WIND_CAUTION and "해안" in _theme_hits(p, ["해안"]):
            cautions.append(f"강풍(최대 {w['wind_max']}m/s) — 해안 코스 주의")
        if w.get("wind_note"):
            cautions.append(w["wind_note"])
    w["cautions"] = cautions
    return w


def nearby_summary(value):
    if not value.get("available", bool(value.get("rows"))):
        return "주변정보 없음(데이터 미보유)"
    return f"주변 휠체어 진입 ● {len(value['wheel'])}곳, 장애인 화장실 ● {len(value['toilet'])}곳"


def weather_summary(value):
    if not value:return '미확인: 날씨 도구 실패'
    parts=[value.get('status','미확인')]
    if value.get('reason'):parts.append(value['reason'])
    elif value.get('pop_max') is not None:parts.append(value.get('forecast_type','')+' 강수 '+str(value['pop_max'])+'%')
    if value.get('base'):parts.append(value['base'])
    if value.get('fallback_note'):parts.append(value['fallback_note'])
    return ' · '.join(parts)
