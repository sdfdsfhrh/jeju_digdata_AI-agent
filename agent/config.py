"""설정 우선순위: 환경변수, .env, .env.eval, Streamlit Secrets."""
from __future__ import annotations

import os
from pathlib import Path


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API_KEY_NAMES = frozenset(("LLM_API_KEY", "OPENAI_API_KEY", "KMA_SERVICE_KEY", "KTO_SERVICE_KEY", "VWORLD_API_KEY"))
# Snapshot before Streamlit loads Secrets into its environment.
_ENVIRONMENT = dict(os.environ)


def _read_settings(path):
    settings = {}
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except FileNotFoundError:
        return settings
    for line in lines:
        name, separator, value = line.strip().partition("=")
        if separator and not name.startswith("#"):
            settings[name.strip()] = value.split(" #", 1)[0].strip().strip('"').strip("'")
    return settings


_LOCAL = _read_settings(Path(ROOT) / ".env")
_EVAL = _read_settings(Path(ROOT) / ".env.eval")
_SECRET_NAMES = API_KEY_NAMES | {"LLM_DAILY_LIMIT", "VWORLD_SERVICE_URL"}
_SECRETS = {}
try:
    import streamlit as st

    for name in _SECRET_NAMES:
        value = st.secrets.get(name)
        if isinstance(value, (str, int)):
            _SECRETS[name] = str(value).strip()
except (ImportError, FileNotFoundError):
    pass


def get(key: str, default: str = "") -> str:
    sources = (_ENVIRONMENT, _LOCAL)
    if key in _SECRET_NAMES or key in {"LLM_PROVIDER", "LLM_MODEL"}:
        sources += (_EVAL, _SECRETS)
    for source in sources:
        value = source.get(key, "").strip()
        if value:
            return value
    return default


# --- LLM (선택) ---
LLM_PROVIDER = get("LLM_PROVIDER", "none").lower()      # none / openai / gemini / claude
LLM_API_KEY = get("LLM_API_KEY")
LLM_MODEL = get("LLM_MODEL")                             # 비우면 제공자별 저가 기본 모델
LLM_TIMEOUT = float(get("LLM_TIMEOUT", "20"))
def parse_daily_limit(value):
    return max(0, int(value or '0'))   # 빈 값·0: 제한 없음


LLM_DAILY_LIMIT = parse_daily_limit(get("LLM_DAILY_LIMIT", "30" if _SECRETS.get("OPENAI_API_KEY") else "0"))
if get("OPENAI_API_KEY"):
    LLM_PROVIDER, LLM_API_KEY = "openai", get("OPENAI_API_KEY")
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
