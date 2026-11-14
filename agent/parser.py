"""사용자 요청 → 조건(Request). LLM이 있으면 LLM으로, 없거나 실패하면 키워드 규칙으로 정리한다.

LLM 결과도 그대로 믿지 않는다: 허용된 값만 남기고 나머지는 버린다(validate).
화면의 선택 입력(form)이 있으면 문장보다 선택 입력을 우선한다.
"""
from __future__ import annotations

import datetime as dt
import re
import unicodedata
from dataclasses import asdict, dataclass, field

from . import llm

KST = dt.timezone(dt.timedelta(hours=9))

USER_TYPES = ["수동휠체어", "전동휠체어", "보행약자", "시니어", "영유아동반", "시각장애", "청각장애"]
NEEDS = ["장애인화장실", "parking_general", "parking_disabled", "장애인주차장"]
TIME_SLOTS = {"오전": (9, 10, 11), "오후": (13, 14, 15, 16, 17), "종일": (10, 11, 12, 13, 14, 15, 16)}
THEMES = {
    "해안": ["해안", "바다", "바닷가", "해변", "해수욕장", "포구", "항구", "방파제", "등대", "해안길"],
    "마을": ["마을", "골목", "벽화", "돌담", "밭담"],
    "숲·자연": ["숲", "나무", "동백", "공원", "저수지", "생태", "오름", "목장"],
    "역사·문화": ["역사", "문화", "사찰", "항일", "환해장성", "유적", "공연"],
}


@dataclass
class Request:
    text: str = ""
    user_type: str | None = None
    needs: list = field(default_factory=list)       # 반드시 있어야 하는 시설
    date: str | None = None                          # YYYYMMDD
    time_slot: str = "종일"
    region: str | None = None                        # 제주시 / 서귀포시 / 읍면동 이름
    themes: list = field(default_factory=list)
    anchor: str | None = None
    companion: str | None = None                     # senior / None
    activity: str | None = None                      # walk / indoor / None
    parsed_by: str = "규칙"                          # 규칙 / LLM / 화면선택

    def is_empty(self) -> bool:
        return not (self.user_type or self.needs or self.date or self.region or self.themes or self.anchor or self.companion or self.activity)

    def to_dict(self):
        return asdict(self)


# ---------------------------------------------------------------------------
# 규칙 기반 파서
# ---------------------------------------------------------------------------
_TYPE_WORDS = [
    ("전동휠체어", r"전동\s*휠체어|전동휠|전동\s*스쿠터"),
    ("수동휠체어", r"휠체어"),
    ("영유아동반", r"유아차|유모차|아기|영유아|아이랑|애기|베이비"),
    ("시각장애", r"시각|시각장애|안내견|저시력"),
    ("청각장애", r"청각|청각장애|수어|보청기"),
    ("보행약자", r"지팡이|목발|보행\s*(?:보조|약자|불편)|걷기\s*(?:힘든|불편)|다리가\s*불편"),
    ("시니어", r"어르신|노인|부모님|할머니|할아버지|시니어|엄마|아빠|어머니|아버지"),
]


def _today():
    return dt.datetime.now(KST).date()


def parse_date(text: str) -> str | None:
    t = text or ""
    base = _today()
    m = re.search(r"(\d{1,2})\s*일\s*(?:뒤|후)", t)
    if m:
        return (base + dt.timedelta(days=int(m.group(1)))).strftime('%Y%m%d')
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", t)
    if m:
        try:
            return dt.date(*map(int, m.groups())).strftime('%Y%m%d')
        except ValueError:
            return None
    if "모레" in t:
        return (base + dt.timedelta(days=2)).strftime("%Y%m%d")
    if "내일" in t:
        return (base + dt.timedelta(days=1)).strftime("%Y%m%d")
    if "오늘" in t:
        return base.strftime("%Y%m%d")
    m = re.search(r"(\d{1,2})\s*월\s*(\d{1,2})\s*일", t) or re.search(r"\b(\d{1,2})[/.](\d{1,2})\b", t)
    if m:
        mo, d = int(m.group(1)), int(m.group(2))
        try:
            cand = dt.date(base.year, mo, d)
        except ValueError:
            return None
        if cand < base - dt.timedelta(days=1):
            cand = dt.date(base.year + 1, mo, d)
        return cand.strftime("%Y%m%d")
    return None


def normalize(text):
    return unicodedata.normalize('NFKC', text or '')


def nearby_fields(text):
    text=normalize(text)
    match=re.search(r'^(.+?)\s*(?:근처|주변|가까운|인근)',text)
    anchor=match.group(1).strip(' ,.!?') if match else None
    if anchor:
        anchor=re.sub(r'^(?:오늘|내일|모레)\s*','',anchor)
        anchor=re.sub(r'(?:에서|으로부터|의)\s*$','',anchor).strip()
    senior=bool(re.search(r'60\s*대|70\s*대|어르신|부모님|어머니|아버지|할머니|할아버지|엄마|아빠',text))
    activity=('indoor' if re.search(r'실내|비(?:가)?\s*오면',text) else
              'walk' if re.search(r'산책|걷기|걷는|바다\s*(?:보기|보러)',text) else None)
    return anchor or None, 'senior' if senior else None, activity


def parking_needs(text):
    """원문에 명시된 차량 이동/주차 문맥을 두 조건으로 분리한다."""
    t=normalize(text)
    general=bool(re.search(r'렌트카|렌터카|자차|운전|(?<![가-힣])차(?:를)?\s*가져가|(?<![가-힣])차로\s*가|일반\s*주차',t))
    disabled=bool(re.search(r'장애인\s*(?:전용)?\s*주차|주차\s*표지',t))
    if '주차' in t and not disabled:
        if re.search(r'휠체어|장애',t) and not re.search(r'일반\s*주차',t):disabled=True
        else:general=True
    return (['parking_general'] if general else [])+(['parking_disabled'] if disabled else [])


def rule_parse(text: str, regions: list[str]) -> Request:
    t = normalize(text)
    r = Request(text=t, parsed_by="규칙")
    r.anchor,r.companion,r.activity=nearby_fields(t)
    for ut, pat in _TYPE_WORDS:
        if re.search(pat, t):
            r.user_type = ut
            break
    if r.user_type is None and r.companion=="senior":
        r.user_type="시니어"
    if re.search(r"화장실", t):
        r.needs.append("장애인화장실")
    r.needs.extend(parking_needs(t))
    r.date = parse_date(t)
    if re.search(r"오전|아침", t):
        r.time_slot = "오전"
    elif re.search(r"오후|점심|저녁", t):
        r.time_slot = "오후"
    for reg in sorted(regions, key=len, reverse=True):     # 긴 이름 먼저(예: '서귀포시' > '서귀포')
        core = reg[:-1] if (reg.endswith(("읍", "면", "동")) and len(reg) > 2) or reg == "서귀포시" else reg
        if reg in t or (len(core) >= 2 and core in t):
            r.region = reg
            break
    for th, words in THEMES.items():
        if any(w in t for w in words):
            r.themes.append(th)
    return r


# ---------------------------------------------------------------------------
# LLM 파서 (선택)
# ---------------------------------------------------------------------------
LLM_SYSTEM = f"""너는 제주 무장애 여행 요청을 조건 JSON으로 바꾸는 도구다. 추측하지 말고 문장에 있는 것만 채워라.
반드시 아래 키만 가진 JSON 하나만 출력한다.
주차는 일반 주차 parking_general과 명시적인 장애인 주차 parking_disabled로 나눈다.
렌트카/렌터카/자차/운전/차 가져가/차로 가는 parking_general이다.
장애인 주차/장애인 주차구역/주차 표지는 parking_disabled이다.
일반 주차를 명시하지 않은 주차 요청은 같은 문장에 휠체어·장애가 있으면 parking_disabled, 그 외 유아차·어르신만 있으면 parking_general이다. 두 종류를 함께 요구하면 둘 다 포함한다. 유아차/휠체어 자체는 차량 이동 표현이 아니다.
장애인주차장은 과거 입력 호환용이며 새 JSON에서는 parking_disabled를 사용한다.
{{"user_type": {USER_TYPES} 중 하나 또는 null,
 "needs": {NEEDS}의 부분집합 (명시한 시설 요구와 위 차량 이동·주차 문맥 규칙 적용),
 "date_text": 날짜 표현 원문(예: "내일", "11월 8일") 또는 null,
 "time_slot": "오전" | "오후" | "종일",
 "region": 지역명 원문 또는 null,
 "themes": {list(THEMES)}의 부분집합,
 "anchor": 근처/주변/가까운/인근 앞의 기준 장소명 원문 또는 null,
 "companion": "senior"(60대·70대·어르신·부모님·어머니·아버지·할머니) 또는 null,
 "activity": "walk"(산책·걷기·바다 보기) | "indoor"(실내·비 오면) | null}}"""


def validate(d: dict, text: str, regions: list[str]) -> Request | None:
    if not isinstance(d, dict):
        return None
    text=normalize(text)
    r = Request(text=text, parsed_by="LLM")
    anchor,companion,activity=nearby_fields(text)
    # 새 필드는 허용값과 원문 의도를 함께 대조. LLM이 임의 기준 장소를 만들지 못하게 한다.
    proposed=d.get('anchor')
    r.anchor=normalize(proposed).strip() if isinstance(proposed,str) and anchor and normalize(proposed).replace(' ','')==anchor.replace(' ','') else anchor
    r.companion=d.get('companion') if d.get('companion')=='senior' and companion else companion
    r.activity=d.get('activity') if d.get('activity') in ('walk','indoor') and d.get('activity')==activity else activity
    if d.get("user_type") in USER_TYPES:
        r.user_type = d["user_type"]
    if r.user_type is None and r.companion=="senior":
        r.user_type="시니어"
    r.needs = [x for x in (d.get("needs") or []) if x in NEEDS]
    # 주차 종류는 LLM 제안 대신 동일한 원문 문맥 규칙으로 검증한다.
    r.needs=[n for n in r.needs if n not in ('parking_general','parking_disabled','장애인주차장')]
    r.needs += [n for n in rule_parse(text,regions).needs if n in ('parking_general','parking_disabled')]
    r.date = parse_date(str(d.get("date_text") or "")) or parse_date(text)
    r.time_slot = d.get("time_slot") if d.get("time_slot") in TIME_SLOTS else "종일"
    reg = str(d.get("region") or "")
    r.region = next((x for x in regions if reg and (x == reg or x.startswith(reg) or reg.startswith(x))), None)
    r.themes = [x for x in (d.get("themes") or []) if x in THEMES]
    return r


def parse(text: str, regions: list[str], use_llm: bool = True) -> tuple[Request, str]:
    """반환: (Request, 처리 설명)."""
    text=normalize(text)
    rule = rule_parse(text, regions)
    if not use_llm or not text.strip():
        return rule, "키워드 규칙으로 조건 정리"
    d = llm.ask_json(LLM_SYSTEM, text)
    if d is None:
        return rule, f"키워드 규칙으로 조건 정리 (LLM 미사용: {llm.LLMStatus.last_error})"
    r = validate(d, text, regions)
    if r is None:
        return rule, "LLM 응답 검증 실패 → 키워드 규칙 사용"
    # LLM이 놓친 필수 시설은 규칙 결과로 보완 (요구를 빠뜨리는 쪽이 더 위험)
    r.needs = sorted(set(r.needs) | set(rule.needs))
    return r, "LLM으로 조건 정리 후 허용값 검증" + (" (캐시)" if llm.LLMStatus.last_from_cache else "")


def apply_form(req: Request, form: dict | None) -> Request:
    """화면에서 직접 고른 값이 있으면 그 값을 우선한다."""
    if not form:
        return req
    if form.get("user_type") in USER_TYPES:
        req.user_type = form["user_type"]
    if form.get("needs") is not None:
        req.needs = sorted(set(req.needs) | {x for x in form["needs"] if x in NEEDS})
    if form.get("date"):
        req.date = form["date"]
    if form.get("time_slot") in TIME_SLOTS:
        req.time_slot = form["time_slot"]
    if form.get("region"):
        req.region = form["region"]
    if form.get("themes"):
        req.themes = [x for x in form["themes"] if x in THEMES]
    if any(form.get(k) for k in ("user_type", "needs", "date", "region", "themes")):
        req.parsed_by = req.parsed_by + "+화면선택"
    return req
