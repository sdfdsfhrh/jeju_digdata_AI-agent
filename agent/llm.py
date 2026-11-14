"""LLM 연결 (선택 기능). OpenAI / Gemini / Claude 중 .env에서 고른 하나를 HTTP로 호출한다.

설계 원칙 (비용·안정성)
- LLM은 '판단'을 하지 않는다. 사용자 문장 → 조건(JSON) 정리, 계산된 결과 → 쉬운 문장 요약 두 가지만 맡는다.
- 키가 없거나, 호출이 실패하거나, 하루 호출 상한을 넘으면 None을 돌려주고 호출한 쪽은 규칙 기반으로 대신한다.
- 같은 요청은 캐시에서 꺼내 쓰므로 다시 과금되지 않는다.
- 제공자별 SDK 없이 requests만 사용 → 설치가 단순하다.
"""
from __future__ import annotations

import json
import re

from . import cache, config
from .llm_errors import LLMAPIError

try:
    import requests
except ImportError:  # requests가 없으면 LLM 기능만 꺼진다
    requests = None


class LLMStatus:
    last_error: str = ""
    last_from_cache: bool = False
    last_error_detail: dict = {}


def _post(url, headers, body):
    r = requests.post(url, headers=headers, json=body, timeout=config.LLM_TIMEOUT)
    if r.status_code != 200:
        try:payload=r.json()
        except (ValueError,TypeError):payload={}
        raise LLMAPIError(r.status_code,payload) from None
    d = r.json()
    p = config.LLM_PROVIDER
    usage = d.get('usageMetadata', {}) if p == 'gemini' else d.get('usage', {})
    if p == 'openai':
        incoming, outgoing = usage.get('prompt_tokens'), usage.get('completion_tokens')
    elif p == 'gemini':
        incoming, outgoing = usage.get('promptTokenCount'), usage.get('candidatesTokenCount')
        if outgoing is not None:
            outgoing += usage.get('thoughtsTokenCount', 0)
    else:
        incoming, outgoing = usage.get('input_tokens'), usage.get('output_tokens')
        if incoming is not None:
            incoming += usage.get('cache_creation_input_tokens',0) + usage.get('cache_read_input_tokens',0)
    cache.record_tokens(p,config.llm_model(),incoming,outgoing)
    return d


def _call(system: str, user: str, want_json: bool, max_tokens: int) -> str:
    p, key, model = config.LLM_PROVIDER, config.LLM_API_KEY, config.llm_model()
    if p == "openai":
        body = dict(model=model, temperature=0, max_tokens=max_tokens,
                    messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
        if model == "gpt-6-luna":
            # GPT-6는 짧은 문장 변환에 추론을 끄고 새 출력 토큰 인자를 사용.
            body.pop("temperature")
            body["max_completion_tokens"] = body.pop("max_tokens")
            body["reasoning_effort"] = "none"
        if want_json:
            body["response_format"] = {"type": "json_object"}
        d = _post("https://api.openai.com/v1/chat/completions",
                  {"Authorization": f"Bearer {key}"}, body)
        return d["choices"][0]["message"]["content"]
    if p == "gemini":
        body = dict(systemInstruction={"parts": [{"text": system}]},
                    contents=[{"role": "user", "parts": [{"text": user}]}],
                    generationConfig={"temperature": 0, "maxOutputTokens": max_tokens,
                                      **({"responseMimeType": "application/json"} if want_json else {})})
        d = _post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                  {"x-goog-api-key": key}, body)
        return "".join(part.get("text", "") for part in d["candidates"][0]["content"]["parts"])
    if p == "claude":
        body = dict(model=model, max_tokens=max_tokens, temperature=0, system=system,
                    messages=[{"role": "user", "content": user}])
        if model == "claude-haiku-5-5":
            # 공식 이행 가이드: 샘플링 인자를 보내면 오류. 짧은 작업은 낮은 effort.
            body.pop("temperature")
            body["output_config"] = {"effort": "low"}
        d = _post("https://api.anthropic.com/v1/messages",
                  {"x-api-key": key, "anthropic-version": "2023-06-01"}, body)
        return "".join(b.get("text", "") for b in d["content"] if b.get("type") == "text")
    raise RuntimeError(f"알 수 없는 LLM_PROVIDER: {p}")


def ask(system: str, user: str, want_json=False, max_tokens=600) -> str | None:
    """LLM 호출. 실패하면 None (호출한 쪽에서 규칙 기반으로 대신 처리)."""
    LLMStatus.last_error, LLMStatus.last_from_cache = "", False
    LLMStatus.last_error_detail = {}
    if not config.llm_enabled():
        LLMStatus.last_error = "LLM 미설정(.env의 LLM_PROVIDER·LLM_API_KEY)"
        return None
    if requests is None:
        LLMStatus.last_error = "requests 패키지 없음"
        return None
    k = cache.key(config.LLM_PROVIDER, config.llm_model(), system, user, want_json)
    hit = cache.get(k)
    if hit is not None:
        LLMStatus.last_from_cache = True
        return hit
    why = cache.blocked("llm")
    if why:
        LLMStatus.last_error = f"{why} — {cache.BLOCK_SEC // 60}분간 재시도 안 함"
        return None
    if config.LLM_DAILY_LIMIT > 0 and cache.today_calls() >= config.LLM_DAILY_LIMIT:
        LLMStatus.last_error = f"오늘 LLM 호출 상한({config.LLM_DAILY_LIMIT}회) 도달"
        return None
    try:
        cache.count_call()
        out = _call(system, user, want_json, max_tokens)
    except Exception as e:  # 네트워크 차단(DLP 등), 키 오류, 시간 초과 모두 여기서 처리
        LLMStatus.last_error = str(e) if isinstance(e,LLMAPIError) else cache.friendly_error(e)
        if isinstance(e,LLMAPIError):LLMStatus.last_error_detail=e.detail
        cache.block("llm", LLMStatus.last_error)
        return None
    cache.put(k, out)
    return out


def ask_json(system: str, user: str, max_tokens=400) -> dict | None:
    out = ask(system, user, want_json=True, max_tokens=max_tokens)
    if out is None:
        return None
    m = re.search(r"\{.*\}", out, re.S)
    try:
        return json.loads(m.group(0) if m else out)
    except (json.JSONDecodeError, AttributeError):
        LLMStatus.last_error = "LLM 응답이 JSON 형식이 아님"
        return None


def test_connection(fresh=False) -> tuple[bool, str]:
    """매뉴얼의 '키 설정 확인' 단계에서 쓰는 1회 호출 테스트."""
    if fresh:
        if not config.llm_enabled():return False,'LLM 미설정'
        if requests is None:return False,'requests 패키지 없음'
        if config.LLM_DAILY_LIMIT>0 and cache.today_calls()>=config.LLM_DAILY_LIMIT:
            return False,f'오늘 LLM 호출 상한({config.LLM_DAILY_LIMIT}회) 도달'
        try:
            cache.count_call()
            out=_call('짧게 답하라.',"연결 확인: '정상'이라고만 답하라.",False,10)
            LLMStatus.last_error_detail={};LLMStatus.last_error='';LLMStatus.last_from_cache=False
            return True,f'{config.LLM_PROVIDER}/{config.llm_model()} 실제 응답 정상(캐시 아님)'
        except Exception as e:
            LLMStatus.last_error_detail=e.detail if isinstance(e,LLMAPIError) else {}
            LLMStatus.last_error=str(e) if isinstance(e,LLMAPIError) else cache.friendly_error(e)
            cache.block('llm',LLMStatus.last_error)
            return False,LLMStatus.last_error
    out = ask("짧게 답하라.", "연결 확인: '정상'이라고만 답하라.", max_tokens=10)
    if out is None:
        return False, LLMStatus.last_error
    return True, f"{config.LLM_PROVIDER}/{config.llm_model()} 응답 정상"
