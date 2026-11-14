"""공통 유틸: 상태값 규칙, 이름 정규화, 거리 계산, CSV 인코딩 자동 판별, 로그."""
from __future__ import annotations

import hashlib
import logging
import math
import os
import re

import pandas as pd

# ---------------------------------------------------------------------------
# 상태값 (4종) — '정보 없음'과 '시설 없음'을 구분한다
# ---------------------------------------------------------------------------
YES = "있음"        # 원본이 시설·조건이 있다고 명시
NO = "없음"         # 원본이 시설이 없다고 명시 (시설 없음)
COND = "조건부"     # 시설은 있으나 원본에 제약·도움 필요 등이 명시
UNK = "미확인"      # 원본에 정보가 없거나 공란·'-'·판독 불가 (정보 없음)

STATUS_RULES = [
    (YES, "원본에 시설/조건이 있다고 명시됨", "있음, 설치, 가능, ●, 'N면/N대'(N>0)"),
    (NO, "원본에 시설이 없다고 명시됨 (시설 없음)", "없음, 미설치, 불가, '0대'"),
    (COND, "시설은 있으나 제약이 명시됨", "'동행인 도움 필요', '대체 화장실 이용'"),
    (UNK, "원본에 정보가 없음 (정보 없음 ≠ 시설 없음)", "공란, '-', 그림만 있음, 추출 실패"),
]

YES_WORDS = {"있음", "설치", "가능", "●", "O", "o", "유", "설치됨"}
NO_WORDS = {"없음", "미설치", "불가", "불가능", "X", "x", "무", "해당없음"}
DASH_WORDS = {"-", "―", "–", "—", "_"}

# 추출 방식별 검증 상태
VERIFY_TEMPLATE = "자동추출(양식)"     # 정해진 표 양식에서 읽음 → 신뢰도 높음
VERIFY_RULE = "검토필요(서술문)"       # 자유 서술문에서 규칙으로 뽑음 → 사람 검토 필요
VERIFY_CONFLICT = "검토필요(충돌)"


def map_status(raw) -> tuple[str | None, str]:
    """원본 값 → (상태, 사유). 상태를 판정할 수 없는 일반 텍스트면 상태 None."""
    if raw is None or (isinstance(raw, float) and math.isnan(raw)):
        return UNK, "원본 공란"
    t = str(raw).strip()
    if t == "":
        return UNK, "원본 공란"
    if t in DASH_WORDS:
        return UNK, "원본 '-' 표기 (해당없음/정보없음 구분 불가)"
    if t in YES_WORDS:
        return YES, f"원본 '{t}'"
    if t in NO_WORDS:
        return NO, f"원본 '{t}'"
    m = re.fullmatch(r"약?\s*(\d+)\s*(면|대|개|곳)?.*", t)
    if m:
        return (YES, f"원본 수량 '{t}'") if int(m.group(1)) > 0 else (NO, f"원본 수량 '{t}'")
    return None, "텍스트 값 (상태 판정 안 함)"


def parse_number(raw) -> float | None:
    """'81', '약 10대(공터주차)', '13도' 같은 값에서 첫 숫자만 꺼낸다. 없으면 None."""
    if raw is None:
        return None
    m = re.search(r"(\d+(?:\.\d+)?)", str(raw))
    return float(m.group(1)) if m else None


# ---------------------------------------------------------------------------
# 이름·주소 정규화, 거리
# ---------------------------------------------------------------------------
NAME_DROP = ["제주특별자치도", "_무장애여행일반정보", "_무장애여행주변정보",
             "_무장애여행위치정보", "무장애여행정보_", "무장애여행정보"]


def norm_name(s) -> str:
    s = "" if s is None else str(s)
    for w in NAME_DROP:
        s = s.replace(w, "")
    s = re.sub(r"\(.*?\)", "", s)
    s = re.sub(r"[\s_\-·•.,'‘’\"“”]", "", s)
    return s.lower()


def name_variants(s) -> set[str]:
    """'제주아리랑공연장' ↔ '아리랑공연장'처럼 앞의 '제주'만 다른 경우도 같은 후보로 본다."""
    n = norm_name(s)
    out = {n}
    if n.startswith("제주") and len(n) > 4:
        out.add(n[2:])
    return out


def name_similarity(a, b) -> float:
    from difflib import SequenceMatcher

    va, vb = name_variants(a), name_variants(b)
    if va & vb:
        return 1.0
    return max(SequenceMatcher(None, x, y).ratio() for x in va for y in vb)


def addr_tokens(addr) -> set[str]:
    """주소에서 읍·면·동·리·로·길 단위 토큰만 뽑는다 (비교용)."""
    if not addr:
        return set()
    toks = re.findall(r"[가-힣0-9]+(?:읍|면|동|리|로|길)", str(addr))
    return {t for t in toks if t not in ("제주특별자치도",)}


def addr_match(a, b) -> bool:
    ta, tb = addr_tokens(a), addr_tokens(b)
    return len(ta & tb) >= 2 or (len(ta & tb) >= 1 and min(len(ta), len(tb)) == 1)


def haversine_m(lat1, lon1, lat2, lon2) -> float | None:
    try:
        lat1, lon1, lat2, lon2 = map(float, (lat1, lon1, lat2, lon2))
    except (TypeError, ValueError):
        return None
    if any(math.isnan(x) for x in (lat1, lon1, lat2, lon2)):
        return None
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def stable_id(prefix: str, *parts) -> str:
    h = hashlib.sha1("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:8]
    return f"{prefix}-{h}"


def file_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# CSV 읽기 (제주데이터허브 파일은 CP949인 경우가 많음)
# ---------------------------------------------------------------------------
def read_csv_auto(path: str) -> tuple[pd.DataFrame, str]:
    last = None
    for enc in ("utf-8-sig", "cp949", "euc-kr"):
        try:
            df = pd.read_csv(path, encoding=enc, dtype=str, keep_default_na=False)
            df.columns = [c.strip() for c in df.columns]
            return df, enc
        except (UnicodeDecodeError, pd.errors.ParserError) as e:
            last = e
    raise ValueError(f"CSV 인코딩 판별 실패: {last}")


def setup_logger(log_dir: str) -> logging.Logger:
    os.makedirs(log_dir, exist_ok=True)
    logger = logging.getLogger("jeju_bf")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    fh = logging.FileHandler(os.path.join(log_dir, "build.log"), encoding="utf-8", mode="w")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(sh)
    return logger
