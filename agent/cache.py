"""작은 SQLite 캐시: 같은 LLM 요청·날씨 조회를 반복 호출하지 않게 해서 비용과 지연을 줄인다.

저장 내용: 요청 해시 → 응답 텍스트, 저장 시각. 개인정보는 저장하지 않는다
(LLM에 보내는 내용 자체가 조건·장소명·공개 데이터뿐임).
"""
from __future__ import annotations

import hashlib
import os
import sqlite3
import time
import datetime as dt

from . import config


def _con():
    os.makedirs(os.path.dirname(config.CACHE_PATH), exist_ok=True)
    con = sqlite3.connect(config.CACHE_PATH)
    con.execute("CREATE TABLE IF NOT EXISTS cache (k TEXT PRIMARY KEY, v TEXT, ts REAL)")
    con.execute("CREATE TABLE IF NOT EXISTS usage (day TEXT PRIMARY KEY, n INTEGER)")
    con.execute('''CREATE TABLE IF NOT EXISTS token_usage (
        id INTEGER PRIMARY KEY, day TEXT, provider TEXT, model TEXT,
        input_tokens INTEGER, output_tokens INTEGER, estimated_krw REAL)''')
    return con


def usage_day():
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).strftime('%Y-%m-%d')


# 기본 모델 일반 텍스트 단가(USD/100만 토큰). 공식 문서 확인: 2026-11-07.
# https://developers.openai.com/api/docs/models/gpt-6-luna
# https://ai.google.dev/gemini-api/docs/pricing
# https://platform.claude.com/docs/en/models/haiku-5-5/overview
PRICES = {('gemini','gemini-3.5-flash-lite'): (0.30,2.50),
          ('gemini','gemini-3.1-flash-lite'): (0.25,1.50),
          ('openai','gpt-6-luna'): (0.10,0.50),
          ('claude','claude-haiku-5-5'): (0.10,0.50),
          ('openai','gpt-4o-mini'): (0.15,0.60),
          ('gemini','gemini-2.5-flash-lite'): (0.10,0.40),
          ('claude','claude-haiku-4-5'): (1.0,5.0)}


def record_tokens(provider, model, input_tokens, output_tokens):
    price = PRICES.get((provider,model))
    # 긴 문맥은 전체 요청에 상위 단가 적용. 무료 할당·캐시 할인은 참고 추정에서 제외.
    if input_tokens is not None:
        if (provider,model) == ('claude','claude-haiku-5-5') and input_tokens > 100_000:
            price = (0.50,2.50)
        elif (provider,model) == ('openai','gpt-6-luna') and input_tokens > 272_000:
            price = (0.20,0.75)
    cost = None
    if price and input_tokens is not None and output_tokens is not None:
        cost = (input_tokens*price[0]+output_tokens*price[1])/1_000_000*config.LLM_USD_KRW
    try:
        con = _con()
        try:
            con.execute('INSERT INTO token_usage(day,provider,model,input_tokens,output_tokens,estimated_krw) VALUES (?,?,?,?,?,?)',
                        (usage_day(),provider,model,input_tokens,output_tokens,cost))
            con.commit()
        finally:
            con.close()
    except sqlite3.Error:
        pass


def monthly_usage():
    month = usage_day()[:7]
    try:
        con = _con()
        calls = con.execute('SELECT COALESCE(SUM(n),0) FROM usage WHERE day LIKE ?', (month+'%',)).fetchone()[0]
        row = con.execute('''SELECT COUNT(*), COALESCE(SUM(input_tokens),0), COALESCE(SUM(output_tokens),0),
                             COALESCE(SUM(estimated_krw),0), COUNT(estimated_krw) FROM token_usage WHERE day LIKE ?''', (month+'%',)).fetchone()
        con.close()
        return dict(month=month,calls=calls,input_tokens=row[1],output_tokens=row[2],estimated_krw=row[3],
                    unpriced_calls=max(0,calls-row[4]),available=True)
    except sqlite3.Error:
        return dict(month=month,available=False)


def usage_text():
    u = monthly_usage()
    if not u['available']:
        return '이번 달 LLM 사용량 미확인(저장소 읽기 실패)'
    return (f"이번 달({u['month']}, 한국시간) LLM 호출 {u['calls']:,}회 · "
            f"토큰 기반 추정 비용 {u['estimated_krw']:,.2f}원(참고용"+
            (f", 비용 미산정 {u['unpriced_calls']}회" if u['unpriced_calls'] else '') + ')')


def key(*parts) -> str:
    return hashlib.sha256("␟".join(str(p) for p in parts).encode("utf-8")).hexdigest()


def get(k: str, max_age_sec: float | None = None):
    try:
        con = _con()
        row = con.execute("SELECT v, ts FROM cache WHERE k=?", (k,)).fetchone()
        con.close()
    except sqlite3.Error:
        return None
    if not row:
        return None
    if max_age_sec is not None and time.time() - row[1] > max_age_sec:
        return None
    return row[0]


def put(k: str, v: str):
    try:
        con = _con()
        con.execute("INSERT OR REPLACE INTO cache VALUES (?,?,?)", (k, v, time.time()))
        con.commit()
        con.close()
    except sqlite3.Error:
        pass


def count_call() -> int:
    """오늘 LLM 호출 수를 1 늘리고 늘린 값을 반환."""
    day = usage_day()
    try:
        con = _con()
        con.execute("INSERT INTO usage VALUES (?, 1) ON CONFLICT(day) DO UPDATE SET n = n + 1", (day,))
        n = con.execute("SELECT n FROM usage WHERE day=?", (day,)).fetchone()[0]
        con.commit()
        con.close()
        return n
    except sqlite3.Error:
        return 0


def today_calls() -> int:
    day = usage_day()
    try:
        con = _con()
        row = con.execute("SELECT n FROM usage WHERE day=?", (day,)).fetchone()
        con.close()
        return row[0] if row else 0
    except sqlite3.Error:
        return 0


# ---------------------------------------------------------------------------
# 차단기: 외부 호출이 한 번 실패하면 잠시 다시 부르지 않는다 (DLP·오프라인 환경에서 대기 시간 방지)
# ---------------------------------------------------------------------------
_blocked: dict[str, tuple[float, str]] = {}
BLOCK_SEC = 300


def blocked(name: str) -> str | None:
    """차단 중이면 사유를, 아니면 None."""
    v = _blocked.get(name)
    if v and time.time() < v[0]:
        return v[1]
    return None


def block(name: str, reason: str):
    _blocked[name] = (time.time() + BLOCK_SEC, reason)


def friendly_error(e: Exception) -> str:
    """예외를 사용자가 이해할 수 있는 짧은 문장으로."""
    n, m = type(e).__name__, str(e)
    if "Proxy" in n or "Connection" in n or "Tunnel" in m:
        return "외부 연결 실패(인터넷 차단·보안정책·네트워크 문제)"
    if "Timeout" in n:
        return "응답 시간 초과"
    if "HTTP 401" in m or "HTTP 403" in m:
        return "API 키 오류 또는 권한 없음(키·결제 상태 확인)"
    if "HTTP 429" in m:
        return "호출 한도 초과(잠시 후 다시 시도)"
    return f"외부 호출 실패({n})"
