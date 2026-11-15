"""설정 읽기: .env 파일 → 환경변수. API 키는 코드에 넣지 않는다.

.env 예시는 프로젝트 최상위의 .env.example 참고.
python-dotenv 없이도 동작하도록 간단한 .env 파서를 직접 둔다.
"""
from __future__ import annotations

import os
from pathlib import Path

from eval_env import read_eval_env

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API_KEY_NAMES = frozenset(("LLM_API_KEY", "OPENAI_API_KEY", "KMA_SERVICE_KEY", "KTO_SERVICE_KEY", "VWORLD_API_KEY"))
_FILE_API_KEYS: dict[str, str] = {}


def _load_dotenv(path: str):
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            v = v.split(" #", 1)[0]  # 값 뒤 주석 제거
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k in API_KEY_NAMES:
                _FILE_API_KEYS[k] = v
            else:
                os.environ.setdefault(k, v)


_load_dotenv(os.path.join(ROOT, ".env"))


# Load private settings on Streamlit Community Cloud.
try:
    import streamlit as st

    for name in ("OPENAI_API_KEY", "KMA_SERVICE_KEY", "VWORLD_API_KEY"):
        value = st.secrets.get(name)
        if isinstance(value, str) and value.strip() and not _FILE_API_KEYS.get(name):
            _FILE_API_KEYS[name] = value.strip()
    limit = st.secrets.get("LLM_DAILY_LIMIT", 30)
    if str(limit).isdigit():
        os.environ.setdefault("LLM_DAILY_LIMIT", str(limit))
except (ImportError, FileNotFoundError):
    pass


def get(key: str, default: str = "") -> str:
    if key in API_KEY_NAMES:
        return _FILE_API_KEYS.get(key, default).strip()
    return os.environ.get(key, default).strip()


# --- LLM (선택) ---
LLM_PROVIDER = get("LLM_PROVIDER", "none").lower()      # none / openai / gemini / claude
LLM_API_KEY = get("LLM_API_KEY")
LLM_MODEL = get("LLM_MODEL")                             # 비우면 제공자별 저가 기본 모델
LLM_TIMEOUT = float(get("LLM_TIMEOUT", "20"))
def parse_daily_limit(value):
    return max(0, int(value or '0'))   # 빈 값·0: 제한 없음


LLM_DAILY_LIMIT = parse_daily_limit(get("LLM_DAILY_LIMIT"))
if get("OPENAI_API_KEY"):
    LLM_PROVIDER, LLM_API_KEY = "openai", get("OPENAI_API_KEY")
else:
    try:
        evaluation = read_eval_env(Path(ROOT) / ".env.eval")
    except (OSError, ValueError):
        evaluation = {}
    if evaluation.get("OPENAI_API_KEY"):
        LLM_PROVIDER, LLM_API_KEY = "openai", evaluation["OPENAI_API_KEY"]
        LLM_MODEL = ""
        LLM_DAILY_LIMIT = parse_daily_limit(evaluation["LLM_DAILY_LIMIT"])
LLM_USD_KRW = float(get('LLM_USD_KRW') or '1400')  # 실시간 환율이 아닌 참고용 가정

# 공식 일반 텍스트 가격·지원 일정 확인: 2026-11-07 (HANDOFF §6-9 출처).
# Gemini 2.5 신규 키 404, 더 저렴한 3.1은 실호출 503 두 차례. 정상 확인한 3.5 사용.
DEFAULT_MODELS = {
    "openai": "gpt-6-luna",
    "gemini": "gemini-3.5-flash-lite",
    "claude": "claude-haiku-5-5",
}

# --- 기상청 단기예보 (선택) ---
KMA_SERVICE_KEY = get("KMA_SERVICE_KEY")                # 공공데이터포털 '기상청_단기예보 조회서비스' 인증키(Decoding)
KTO_SERVICE_KEY = get("KTO_SERVICE_KEY")                # 한국관광공사 무장애 여행 정보

# --- 경로 ---
DB_PATH = get("DB_PATH") or os.path.join(ROOT, "output", "jeju_bf.sqlite")
EXTRA_DIR = get("EXTRA_DIR") or os.path.join(ROOT, "data", "extra")
CACHE_PATH = os.path.join(ROOT, "output", "agent_cache.sqlite")


def llm_enabled() -> bool:
    return LLM_PROVIDER in DEFAULT_MODELS and bool(LLM_API_KEY)


def llm_model() -> str:
    return LLM_MODEL or DEFAULT_MODELS.get(LLM_PROVIDER, "")
