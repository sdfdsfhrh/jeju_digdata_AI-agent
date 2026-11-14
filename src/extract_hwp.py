"""HWP 무장애여행 문서에서 접근성 정보 추출.

두 가지 양식을 구분해서 처리한다.
- general_2021  : 2021년 '무장애여행일반정보' — 정해진 표 양식 (요약표·추천대상표·상세표)
- narrative_2019: 2019~2020년 '무장애여행정보_장소' — 서술형 글 + 소형 표

원칙
- 원본에 없는 값은 만들지 않는다. 못 찾으면 상태 '미확인' + extraction_failure에 기록.
- 모든 값에 원본 위치(locator)와 근거 문장(evidence)을 남긴다.
- 서술문에서 규칙으로 뽑은 값은 verify_status='검토필요(서술문)'으로 표시한다.
"""
from __future__ import annotations

import re

from common import (COND, NO, UNK, VERIFY_RULE, VERIFY_TEMPLATE, YES, map_status,
                    parse_number)


# ---------------------------------------------------------------------------
# 공통
# ---------------------------------------------------------------------------
def detect_kind(doc) -> str:
    tables = doc.tables()
    t0 = tables.get(0, {})
    # 2021 일반정보: 요약표 첫 머리칸이 '개요' 또는 '주요 콘텐츠'(위미동백나무군락 등 일부 파일)
    if re.sub(r"\s", "", t0.get((1, 0), "")) in ("개요", "주요콘텐츠"):
        return "general_2021"
    text = doc.plain_text()
    if "이동약자를 위한 안내" in text or "보조기기 이용인 추천코스" in text:
        return "narrative_2019"
    return "unknown"


class Result:
    """추출 결과 컨테이너."""

    def __init__(self, kind):
        self.kind = kind
        self.place = {}
        self.items = []        # accessibility_item 후보
        self.details = []      # facility_detail
        self.measures = []     # measurement
        self.targets = []      # target_recommendation
        self.conflicts = []    # (topic, a, loc_a, b, loc_b, note)
        self.failures = []     # (item, reason, locator)

    def add_item(self, category, item, raw, locator, method, evidence=None,
                 status=None, reason=None, applies_to="대상 장소", unit=None):
        if status is None:
            status, reason = map_status(raw)
            if status is None:
                status, reason = UNK, "원본 값이 상태어가 아님 → 미확인 (원본 값 보존)"
        self.items.append(dict(
            category=category, item=item, status=status, status_reason=reason,
            value_num=parse_number(raw) if raw not in (None, "") else None,
            value_unit=unit, value_raw=raw, evidence=evidence or raw,
            applies_to=applies_to, source_locator=locator, extract_method=method,
            verify_status=VERIFY_TEMPLATE if method == "template" else VERIFY_RULE))


def _sq(x):
    return re.sub(r"\s", "", x or "")


def _find(grid, text, start_row=0, exact=True):
    """표에서 글자가 같은 칸 찾기. 공백 차이는 무시한다."""
    key = _sq(text)
    for (r, c) in sorted(grid):
        if r < start_row:
            continue
        v = _sq(grid[(r, c)])
        if (v == key) if exact else (key in v):
            return r, c
    return None


def _below(grid, rc):
    if rc is None:
        return None, None
    r, c = rc
    return grid.get((r + 1, c)), f"r{r + 1} c{c}"


def _right(grid, rc):
    if rc is None:
        return None, None
    r, c = rc
    for cc in range(c + 1, c + 8):
        if (r, cc) in grid:
            return grid[(r, cc)], f"r{r} c{cc}"
    return None, None


# ---------------------------------------------------------------------------
# 2021 양식
# ---------------------------------------------------------------------------
def extract_general_2021(doc) -> Result:
    res = Result("general_2021")
    tables = doc.tables()
    g = tables[0]
    T = "T0"

    def loc(x):
        return f"{T} {x}" if x else None

    res.place["name"] = g.get((0, 0), "").strip()
    ov, _ = _right(g, _find(g, "개요"))
    if ov is None:  # 일부 파일은 같은 칸 제목이 '주요 콘텐츠'
        ov, _ = _right(g, _find(g, "주요 콘텐츠"))
    res.place["overview"] = ov
    addr_cell, addr_loc = _right(g, _find(g, "주소"))
    if addr_cell:
        res.place["address"] = addr_cell.split("\n")[0].strip()
        res.place["address_note"] = addr_cell
    else:
        res.failures.append(("주소", "요약표에서 '주소' 칸을 찾지 못함", T))
    for key, label in (("recommended_course", "추천코스"), ("full_course", "전체코스")):
        v, _ = _right(g, _find(g, label))
        res.place[key] = v

    # --- 장애인 주차장 (요약표) ---
    prk = _find(g, "주차장")
    start = prk[0] if prk else 0
    v, l = _below(g, _find(g, "장애인 주차장 유무", start))
    if v is None and prk:
        # 제목 문구가 다른 문서 대비: '주차장' 행의 첫 번째 머리칸(c1) 바로 아래 값을 사용하고,
        # 그 머리칸 문구를 근거로 남긴다
        head = g.get((prk[0], 1), "")
        if "장애인" in head and "대수" not in head:
            v, l = _below(g, (prk[0], 1))
            if v is not None:
                res.add_item("주차", "장애인주차장", v, loc(l), "template",
                             evidence=f"머리칸 '{head}' 아래 값 '{v}'")
    elif v is not None:
        res.add_item("주차", "장애인주차장", v, loc(l), "template")
    if v is None:
        res.failures.append(("장애인주차장 유무", "요약표 칸을 찾지 못함", T))
        res.add_item("주차", "장애인주차장", None, None, "template", status=UNK,
                     reason="요약표에서 해당 칸을 찾지 못함 (추출 실패)")
    cnt, lc = _below(g, _find(g, "장애인 주차 대수", start))
    if cnt is not None:
        res.add_item("주차", "장애인주차 면수", cnt, loc(lc), "template", unit="면/대")
    ploc, pl = _below(g, _find(g, "위치", start))
    res.place["parking_location"] = ploc

    # --- 장애인 화장실 (요약표) ---
    wc = _find(g, "화장실")
    ws = wc[0] if wc else start
    toilet_head = _find(g, "장애인 화장실", ws) or _find(g, "추천 장애인 화장실", ws)
    tv, tl = _below(g, toilet_head)
    if toilet_head is None:
        res.failures.append(("장애인화장실", "요약표에서 화장실 머리칸을 찾지 못함", T))
    status, reason = map_status(tv)
    evidence = tv
    # '-'/공란이면 개요 문장에 명시적 표현이 있는지만 확인 (추론하지 않음)
    if status == UNK and ov and re.search(r"장애인\s*화장실이\s*없", ov):
        status, reason = NO, "요약표는 '-'이나 개요에 '장애인 화장실이 없' 명시"
        evidence = ov
    res.add_item("화장실", "장애인화장실", tv, loc(tl), "template", evidence=evidence,
                 status=status, reason=reason)
    gv, gl = _below(g, _find(g, "구분", ws))
    if gv is not None and str(gv).strip() not in ("", "-"):
        res.add_item("화장실", "장애인화장실 남녀구분", gv, loc(gl), "template",
                     status=YES if "구분" in gv else None,
                     reason=f"원본 '{gv}'" if "구분" in gv else None)
    wloc, _ = _below(g, _find(g, "위치", ws))
    res.place["toilet_location"] = wloc
    alt, al = _right(g, _find(g, "주변(대체) 화장실", ws))
    if alt and alt.strip() not in ("-", ""):
        res.add_item("화장실", "대체 화장실 안내", alt, loc(al), "template",
                     status=COND, reason="원본에 주변(대체) 화장실 위치가 명시됨",
                     applies_to="대체시설")

    # --- 기타 요약 항목 ---
    for label, item in (("보조기기 대여", "보조기기 대여"), ("편의/부대시설", "편의/부대시설"),
                        ("해설사", "해설사"), ("관람료", "관람료"), ("휴무일", "휴무일")):
        v, l = _right(g, _find(g, label))
        if v is None:
            res.failures.append((item, "요약표 칸을 찾지 못함", T))
            continue
        cat = "보조기기" if item == "보조기기 대여" else "운영"
        if item in ("관람료", "휴무일"):
            res.place[item] = v
        else:
            res.add_item(cat, item, v, loc(l), "template")

    # --- 추천 대상 표 ---
    for tno, t in tables.items():
        if t.get((0, 0), "").strip() != "추천 대상":
            continue
        group = None
        for r in sorted({rc[0] for rc in t}):
            if r < 2:
                continue
            c0 = t.get((r, 0), "").strip()
            c1 = t.get((r, 1), "").strip()
            if c0:
                group = c0
            target = c1 or c0
            mark = t.get((r, 2), "").strip()
            res.targets.append(dict(
                target_group=group, target=target, mark_raw=mark,
                marked="표시있음" if mark else "표시없음",
                note_raw=t.get((r, 3), "").strip(), source_locator=f"T{tno} r{r}"))

    # --- 상세표 (구분/항목/내용/단위) ---
    summary_parking_cnt = parse_number(cnt) if cnt else None
    for tno, t in tables.items():
        hdr = {t.get((1, c), "").strip(): c for c in range(8)}
        if "항목" not in hdr or "내용" not in hdr:
            continue
        title = t.get((0, 0), "").strip()
        is_alt = int("대체" in title)
        vcol, ucol = hdr["내용"], hdr.get("단위")
        grp = None
        rows = sorted({rc[0] for rc in t})
        for r in rows:
            if r < 2:
                continue
            c0 = t.get((r, 0), "").strip()
            if c0:
                grp = c0
            item = t.get((r, 1), "").strip()
            if not item:
                continue  # 사진 캡션 등
            val = t.get((r, vcol), "").strip()
            unit = t.get((r, ucol), "").strip() if ucol is not None else ""
            num = parse_number(val)
            res.details.append(dict(
                facility_title=title, is_alternative=is_alt, grp=grp, item=item,
                value_raw=val, unit=unit, value_num=num, source_locator=f"T{tno} r{r}"))
            if num is not None and unit in ("m", "cm", "도", "개"):
                res.measures.append(dict(
                    kind=("[대체시설] " if is_alt else "") + f"{title.split('–')[0].strip()} / {grp} / {item}",
                    value=num,
                    unit=unit, raw_text=val, source_locator=f"T{tno} r{r}",
                    extract_method="template"))
            # 주차장 상세표와 요약표 면수 비교 (출처 내 충돌)
            if (title.startswith("주차장") and grp == "장애인 주차 구역" and item == "주차면수"
                    and num is not None and summary_parking_cnt is not None
                    and num != summary_parking_cnt):
                res.conflicts.append((
                    "장애인주차 면수(요약표 vs 상세표)", cnt, f"T0 {lc}", val, f"T{tno} r{r}",
                    f"상세표 제목: {title}"))
    if not res.details:
        res.failures.append(("상세표", "구분/항목/내용 양식의 상세표를 찾지 못함", "전체"))
    return res


# ---------------------------------------------------------------------------
# 2019~2020 서술형
# ---------------------------------------------------------------------------
SECTION_HEADERS = ("이용안내", "주차장", "편의시설 및 부대시설 안내", "보조기기 이용인 추천코스",
                   "장애인화장실 정보", "접근성정보 및 콘텐츠", "접근성 및 콘텐츠", "주변 관광지 안내")
ANGLE_RE = re.compile(r"(오르막|내리막|경사)[^.。\n]{0,20}?(\d+(?:\.\d+)?)\s*(?:°|도)")
ANGLE_RE2 = re.compile(r"(\d+(?:\.\d+)?)\s*(?:~\s*(\d+(?:\.\d+)?))?\s*°")
LEN_RE = re.compile(r"길이\s*(\d+(?:\.\d+)?)\s*m")
DOOR_RE = re.compile(r"출입문\s*폭\s*(\d+(?:\.\d+)?)\s*cm")
STEP_RE = re.compile(r"턱[^.\n]{0,10}?(\d+(?:\.\d+)?)\s*cm")


def _sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.다])\s+|\n", text) if s.strip()]


def extract_narrative_2019(doc, expected_name=None) -> Result:
    res = Result("narrative_2019")
    blocks = doc.blocks

    # 1) 섹션 나누기: 1칸짜리 제목 표(r0 c1)를 섹션 제목으로 본다
    section = "머리말"
    seq = []   # (section, text, locator)
    for i, b in enumerate(blocks):
        t = b.text.strip()
        if not t:
            continue
        if b.kind == "cell" and b.row == 0 and b.col == 1 and (
                t in SECTION_HEADERS or t.endswith(" 정보")):
            section = t
            continue
        loc = f"T{b.table_no} r{b.row} c{b.col}" if b.kind == "cell" else f"P{b.order}"
        if t.startswith("그림"):
            continue
        seq.append((section, t, loc, b))

    # 2) 장소명
    name = None
    if expected_name:
        for _, t, _, _ in seq:
            if expected_name.replace(" ", "") in t.replace(" ", ""):
                name = t
                break
    if name is None:
        for s, t, _, b in seq:
            if s == "머리말" and b.kind == "para" and len(t) <= 25 and not re.match(r"^\d", t) \
                    and ":" not in t and "목차" not in t and "콘텐츠" not in t:
                name = t
                break
    res.place["name"] = name
    if not name:
        res.failures.append(("장소명", "문서 머리말에서 장소명을 찾지 못함", "머리말"))

    # 3) 이동약자 안내 문단
    for k, (s, t, loc, _) in enumerate(seq):
        if t.startswith("이동약자를 위한 안내"):
            body = t.split(":", 1)[1].strip() if ":" in t else ""
            if not body and k + 1 < len(seq):
                body = seq[k + 1][1]
            res.place["mobility_note"] = body
            break

    # 4) 키:값 줄과 2열 표 (주변 관광지 섹션은 다른 장소 정보라서 제외)
    EXCLUDE = ("주변 관광지 안내",)
    kv = {}
    cells = {}
    for s_, t, loc, b in seq:
        if b.kind == "cell" and s_ not in EXCLUDE:
            cells[(b.table_no, b.row, b.col)] = (t, loc)
    for (tno, r, c), (v, loc) in cells.items():
        if c == 0 and (tno, r, 1) in cells:
            kv.setdefault(re.sub(r"\s", "", v), (cells[(tno, r, 1)][0], f"T{tno} r{r}"))
    for s_, t, loc, b in seq:
        if s_ in EXCLUDE:
            continue
        m = re.match(r"^([가-힣A-Za-z ()]{2,15}?)\s*:\s*(.+)$", t)
        if m and b.kind == "para":
            kv.setdefault(re.sub(r"\s", "", m.group(1)), (m.group(2).strip(), loc))
    # 표 머리글 단어는 값으로 쓰지 않음
    kv = {k: v for k, v in kv.items() if v[0].strip() not in ("요금", "구분", "항목", "내용")}
    # 보조기기 표는 값 칸이 비어 있어도 항목 자체는 기록해야 하므로 별도로 수집
    assist_cells = {}
    for (tno, r, c), (v, loc) in cells.items():
        if c == 0:
            assist_cells[re.sub(r"\s", "", v)] = ("" if (tno, r, 1) not in cells else cells[(tno, r, 1)][0], f"T{tno} r{r}")

    for key, field in (("주소", "address"), ("관람시간", "관람시간"), ("관람료", "관람료"),
                       ("전화", "phone"), ("문의", "phone"), ("홈페이지", "homepage")):
        if key in kv and field not in res.place:
            res.place[field] = kv[key][0].split("\n")[0].strip() if field == "address" else kv[key][0]
    if "address" not in res.place:
        res.failures.append(("주소", "주소 항목을 찾지 못함", "전체"))

    # 5) 보조기기 표 (칸이 비어 있으면 아이콘 그림일 가능성 → 미확인)
    assist_keys = ("휠체어대여", "유아차대여", "자동심실제세동기(AED)", "전동휠체어급속충전기",
                   "수직이동설비", "승강기")
    found_assist = False
    raw_tables = doc.tables()
    assist_src = {}
    for tno, t in raw_tables.items():
        for (r, c), v in t.items():
            key = re.sub(r"\s", "", v)
            if c == 0 and key in assist_keys:
                assist_src[key] = (t.get((r, 1), ""), f"T{tno} r{r}")
    for k in assist_keys:
        if k in assist_src:
            found_assist = True
            raw, loc = assist_src[k]
            st, rs = map_status(raw)
            if st == UNK and (raw or "").strip() == "":
                rs = "원본 칸 비어 있음 (아이콘 그림으로 표시됐을 가능성, 판독 불가)"
            res.add_item("보조기기", k, raw, loc, "template", status=st or UNK, reason=rs)
    if "보조기기및편의장비" in kv:
        raw, loc = kv["보조기기및편의장비"]
        res.add_item("보조기기", "보조기기 및 편의장비(전체)", raw, loc, "rule")
        found_assist = True
    if not found_assist:
        res.failures.append(("보조기기", "보조기기 정보를 찾지 못함", "전체"))

    # 선택 방문지인 바움커피박물관을 본 대상 빛의벙커 시설로 섞지 않는다.
    if expected_name and "빛의벙커" in expected_name.replace(" ", ""):
        filtered=[]; optional=False
        for entry in seq:
            section_,text_,loc_,block_=entry
            if re.match(r"2[.]\s*바움",text_): optional=True
            if section_ in ("보조기기 이용인 추천코스","장애인화장실 정보","접근성 정보 및 콘덴츠"):
                optional=False
            if not optional: filtered.append(entry)
        seq=filtered
    if not res.place.get("overview"):
        res.place["overview"] = next((t for sec,t,_,b in seq if sec=="머리말" and t.startswith("[")), None)
    # 빛의벙커의 보조기기 표는 명칭/수량/위치의 4열 양식.
    if not found_assist:
        for tno,table in raw_tables.items():
            for (rr,cc),value in table.items():
                if cc==1 and value.strip() in ("수동휠체어","유아차") and table.get((rr,2),"").strip():
                    item="휠체어대여" if value.strip()=="수동휠체어" else "유아차대여"
                    raw=table[(rr,2)]
                    res.add_item("보조기기",item,raw,f"T{tno} r{rr} c2","rule",status=YES if re.search(r"[1-9]",raw) else UNK,
                                 reason="보조기기 수량 표 원문")
                    found_assist=True
        if found_assist:
            res.failures=[f for f in res.failures if f[0]!="보조기기"]
    # 6) 문장 단위 규칙
    park_done = toilet_done = seat_done = ramp_done = False
    seen_meas = set()

    def add_meas(kind, value, unit, sent, loc):
        key = (kind, value, unit, sent)
        if key in seen_meas:
            return  # 같은 문장이 문서에 반복된 경우 1번만 기록
        seen_meas.add(key)
        res.measures.append(dict(kind=kind, value=value, unit=unit, raw_text=sent,
                                 source_locator=loc, extract_method="rule"))

    for s, t, loc, b in seq:
        if s in EXCLUDE:
            continue
        for sent in _sentences(t):
            # 경사로 (출입 경사로 이용 + 도움 필요 표현 → 조건부)
            if not ramp_done and "경사로" in sent and re.search(r"이용|입장|진입", sent):
                cond = re.search(r"도움|동행|주의", t)  # 같은 문단의 뒤 문장까지 확인
                res.add_item("경사로", "출입 경사로", sent, loc, "rule", evidence=sent,
                             status=COND if cond else YES,
                             reason="같은 문단에 경사로 이용 + 도움/주의 필요 명시" if cond
                             else "서술문에 경사로 이용 명시")
                ramp_done = True
            # 장애인 주차
            if not park_done and "장애인" in sent and "주차" in sent:
                m = re.search(r"장애인\s*(?:전용)?\s*주차\s*구역\s*(\d+)\s*(대|면)", sent)
                if m:
                    res.add_item("주차", "장애인주차장", m.group(0), loc, "rule", evidence=sent,
                                 status=YES, reason="서술문에 장애인주차구역 수량 명시")
                    res.add_item("주차", "장애인주차 면수", m.group(1), loc, "rule",
                                 evidence=sent, unit=m.group(2))
                    park_done = True
                elif re.search(r"장애인\s*(?:전용)?\s*주차\s*구역\s*(?:은|이|는)?\s*없", sent):
                    res.add_item("주차", "장애인주차장", "없음", loc, "rule", evidence=sent,
                                 status=NO, reason="서술문에 장애인주차구역 없음 명시")
                    park_done = True
            # 휠체어 관람석
            if not seat_done and "휠체어" in sent and "관람석" in sent:
                st = NO if re.search(r"없", sent) else YES
                res.add_item("관람", "휠체어 관람석", sent, loc, "rule", evidence=sent,
                             status=st, reason=f"서술문 '{'없' if st == NO else '있'}' 표현")
                seat_done = True
            # 경사각 / 길이 / 출입문 폭 / 턱
            for m in ANGLE_RE.finditer(sent):
                add_meas("경사각", float(m.group(2)), "도", sent, loc)
            if not ANGLE_RE.search(sent) and re.search(r"경사|오르막|내리막", sent):
                for m in ANGLE_RE2.finditer(sent):
                    kind = f"경사각(범위 {m.group(1)}~{m.group(2)})" if m.group(2) else "경사각"
                    add_meas(kind, float(m.group(1)), "도", sent, loc)
            for m in LEN_RE.finditer(sent):
                if "경사" in sent:
                    add_meas("경사로 길이", float(m.group(1)), "m", sent, loc)
            for m in DOOR_RE.finditer(sent):
                kind = "장애인화장실 출입문 폭" if s == "장애인화장실 정보" else "출입문 폭"
                add_meas(kind, float(m.group(1)), "cm", sent, loc)
            for m in STEP_RE.finditer(sent):
                add_meas("턱 높이", float(m.group(1)), "cm", sent, loc)
        # 장애인화장실 섹션
        if s == "장애인화장실 정보" and not toilet_done:
            if re.search(r"장애인\s*화장실[^.]{0,10}없", t):
                res.add_item("화장실", "장애인화장실", "없음", loc, "rule", evidence=t,
                             status=NO, reason="장애인화장실 섹션에 '없음' 명시")
            else:
                res.add_item("화장실", "장애인화장실", t, loc, "rule", evidence=t, status=YES,
                             reason="'장애인화장실 정보' 섹션에 위치·치수 서술이 있음")
            toilet_done = True
        if s == "장애인화장실 정보" and ("위치" in t) and "toilet_location" not in res.place:
            res.place["toilet_location"] = t
        if s == "보조기기 이용인 추천코스" and "recommended_course" not in res.place:
            res.place["recommended_course"] = t

    if not park_done:
        res.add_item("주차", "장애인주차장", None, None, "rule", status=UNK,
                     reason="서술문에서 장애인주차 관련 문장을 찾지 못함")
        res.failures.append(("장애인주차장", "관련 문장 없음", "전체"))
    if not toilet_done:
        res.add_item("화장실", "장애인화장실", None, None, "rule", status=UNK,
                     reason="'장애인화장실 정보' 섹션 없음")
        res.failures.append(("장애인화장실", "섹션 없음", "전체"))
    if not ramp_done:
        res.add_item("경사로","출입 경사로",None,"전체","rule",status=UNK,
                     reason="본 대상의 출입 경사로 명시 없음(선택 방문지·다른 시설 제외)")
        res.failures.append(("출입 경사로","본 대상의 명시 근거 없음","전체"))
    indoor_text=next(((t,loc) for sec,t,loc,b in seq if sec not in EXCLUDE and re.search(r"전시실에 입장|갤러리룸",t)),None)
    if indoor_text:
        res.add_item("공간","실내공간",indoor_text[0],indoor_text[1],"rule",status=YES,
                     reason="본 대상 전시실·갤러리룸 원문(전체 여정 실내라는 뜻 아님)")
    return res
