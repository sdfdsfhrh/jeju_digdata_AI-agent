"""Agent 실행부: 목표 설정 → 도구 선택·실행 → 판정·순위 → 설명.

자율 수행 범위
- Agent가 스스로 하는 일: 조건 정리, 어떤 도구를 어떤 장소에 쓸지 결정, 데이터 조회, 규칙 판정, 순위, 설명 작성.
- Agent가 하지 않는 일: 원본에 없는 사실 생성, '미확인'을 '없음/있음'으로 단정, 예약·결제 등 외부 행동.
- 모든 단계는 trace(실행 기록)에 남아 화면에 그대로 보인다.
"""
from __future__ import annotations

import json
import re
import time

from . import adaptive, cache, config, data, llm, place_query, tools, indoor, visit_assessment, anchor as anchor_tools, anchored, recommendation, missing_place
from .parser import Request, apply_form, parse, normalize

TOP_N = 3

_WD = "월화수목금토일"


def fmt_date(d: str | None) -> str:
    """'20261107' → '11월 7일(토)'."""
    import datetime as dt
    try:
        x = dt.datetime.strptime(d, "%Y%m%d")
        return f"{x.month}월 {x.day}일({_WD[x.weekday()]})"
    except (TypeError, ValueError):
        return d or ""   # 상세 조사(주변시설·날씨)를 하는 상위 장소 수


class Tracer:
    def __init__(self, progress=None):
        self.steps = []
        self.progress = progress

    def notify(self, text):
        if self.progress:
            self.progress(text)

    def note(self, tool, purpose, output):
        self.steps.append(dict(no=len(self.steps) + 1, tool=tool, purpose=purpose,
                               input="중간 결과 확인", output=output, ok=True, ms=0))

    def run(self, tool: str, purpose: str, fn, *args, input_desc="", summarize=None):
        self.notify(purpose)
        t0 = time.perf_counter()
        try:
            out = fn(*args)
            ok, err = True, ""
        except data.DataError:
            raise
        except Exception as e:  # 도구 하나가 실패해도 Agent 전체는 멈추지 않는다
            out, ok, err = None, False, f"{type(e).__name__}: {e}"
        ms = round((time.perf_counter() - t0) * 1000)
        self.steps.append(dict(no=len(self.steps) + 1, tool=tool, purpose=purpose, input=input_desc,
                               output=(summarize(out) if (ok and summarize) else err or "완료"),
                               ok=ok, ms=ms))
        return out


def _rank_key(r):
    return (not r.get("requested_place", False), r["place"].get("_alternative_group_priority", 0), tools.GRADE_ORDER[r["grade"]], (2 if r.get("slope_penalty") else 1 if r.get("slope_unknown") else 0),
            r["place"].get("_distance_km", 0), tools.GRADE_ORDER.get(r.get("relaxed_grade"), 0), -len(r["theme_hits"]), -r["access"]["comfort"],
            len(r["caution_list"]), r["place"]["name"])


def _rank_reason(r):
    parts = [f"등급 '{r['grade']}'"]
    if r.get("requested_place"):
        parts.append("질문에서 지정한 장소 우선 조회")
    if r.get("slope_unknown"):
        parts.append("경사 측정값 없음(안전 확인 아님)")
    if not r.get("slope_unknown") and not r.get("slope_penalty") and r.get("wheelchair_user"):
        parts.append("코스 경사 측정값 있음·참고 기준 이하(안전 보장 아님)")
    if r.get("slope_penalty"):
        parts.append(f"휠체어 코스 경사 {r['route']['max_slope']:g}° > 4.76° → 같은 등급 내 후순위(등급 유지)")
    if "_distance_km" in r["place"]:
        parts.append(f"지정 장소에서 직선거리 {r['place']['_distance_km']:.2f} km(이동 경로 미검증)")
    if r["theme_hits"]:
        parts.append(f"요청 성격 일치({', '.join(r['theme_hits'])})")
    parts.append(f"편의 점수 {r['access']['comfort']}/4(장애인 화장실·주차)")
    parts.append(f"주의 {len(r['caution_list'])}건")
    return " · ".join(parts)


def _collect_cautions(acc, route, req):
    out = []
    for n in acc["needs"]:
        if n["effective"] == tools.UNK:
            out.append(f"{n['item']} 정보 없음(미확인) — 방문 전 전화·현장 확인 필요")
        elif n["effective"] == tools.NO:
            out.append(f"{n['item']} 없음 (원본 명시)")
        elif n["note"]:
            out.append(n["note"])
    if route["relevant"] and route["over_ref"]:
        vals = sorted({s["value"] for s in route["over_ref"]}, reverse=True)
        out.append(f"참고 기준(약 4.8°)을 넘는 경사 수치 {len(route['over_ref'])}개 "
                   f"(최대 {vals[0]:g}°, 값: {', '.join(f'{v:g}°' for v in vals[:4])})")
    if req.user_type in tools.MOBILITY:
        for c in route["cautions"]:
            if any(w in c["text"] for w in ("접근불가", "접근 불가", "단차", "계단", "비포장", "접근 어려")):
                out.append(f"코스 지점 {c['seq']}: {c['text'][:60]}")
    for c in acc.get("conflicts", []):
        out.append(f"원본 정보 불일치: {c['topic']} — {c['value_a']} ({c['source_a']}) / "
                   f"{c['value_b']} ({c['source_b']}) — 방문 전 확인 필요")
    return out


def run(text: str = "", form: dict | None = None, use_llm: bool = True, progress=None) -> dict:
    t_start = time.perf_counter()
    text = normalize(text)
    tr = Tracer(progress)
    regions = tr.run("list_regions", "지역 이름 목록 준비(조건 해석용)", tools.all_regions,
                     summarize=lambda x: f"{len(x)}개 지역")

    # 1) 목표 설정: 요청 → 조건
    def _parse():
        r, how = parse(text, regions, use_llm=use_llm and config.llm_enabled())
        return apply_form(r, form), how
    parsed = tr.run("parse_request", "요청 문장을 조건으로 정리", _parse, input_desc=text[:60],
                    summarize=lambda x: x[1])
    req: Request = parsed[0] if parsed else Request(text=text)
    goal = (f"{req.user_type or '이용자 유형 미지정'} 이용자가 "
            f"{'·'.join(req.needs) + ' 필수' if req.needs else '필수 조건 없이'} "
            f"{req.region or '제주 전역'}에서 갈 만한 무장애 장소 찾기"
            + (f" ({fmt_date(req.date)} {req.time_slot})" if req.date else ""))

    if req.anchor:
        return anchored.run(req,tr,t_start,use_llm=use_llm)

    named = tr.run("lookup_named_place", "일반 추천 전에 질문 속 DB 장소명(상세+색인) 확인",
                   place_query.lookup, text, input_desc=text[:80], summarize=lambda x: x['message'])
    named = named or dict(matches=[], message="장소명 도구 실패 → 일반 검색")
    missing_target = anchor_tools.missing_judgment_target(text) if not named['matches'] else None
    if missing_target:
        req.anchor=missing_target
        return anchored.run(req,tr,t_start,use_llm=use_llm,judgment_missing=True)
    if named['matches']:
        target=named['matches'][0]
        goal=f"{target['name']} — {req.user_type or '이용자'} 이용 가능 여부 확인"+(f" ({fmt_date(req.date)})" if req.date else '')
    named_details = [p for p in named['matches'] if p['detail_level'] == '상세파일있음']
    indexed = [p for p in named['matches'] if p['detail_level'] != '상세파일있음']
    missing_context = missing_place.context(indexed[0]['name'], req, indexed[0]) if indexed and not named_details else None
    if missing_context:
        req.anchor=indexed[0]['name']
        return anchored.run(req,tr,t_start,use_llm=use_llm,judgment_missing=True)
    # 2) 후보 검색
    found = tr.run("search_places", "상세 접근성 정보가 있는 장소 중 후보 찾기", tools.search_places, req,
                   input_desc=f"지역={req.region or '전체'}, 성격={req.themes or '없음'}",
                   summarize=lambda x: f"{x['n_total']}곳 중 {x['n_after_region']}곳 후보")
    limits = list(found["limits"]) if found else []
    name_notices = []
    if indexed and not named_details:
        for p in indexed:
            name_notices.append(f"{p['name']}: 위치는 있으나 접근성 상세정보가 없어 판정 불가. 주소: {p.get('address') or '미확인'}")
    elif not named['matches'] and text.strip():
        name_notices.append(named['message'])
    if named['matches']:
        anchor = (named_details or indexed)[0]
        nearby = tr.run('find_named_nearby_alternatives', '장소 지정 질문 → 해당 좌표 주변 상세 대안 선정',
                        place_query.nearby_candidates, anchor, input_desc=anchor['name'], summarize=lambda x:x['reason'])
        found = dict(candidates=(nearby or {}).get('candidates', []))
        name_notices.append(named['message'])
        name_notices.append((nearby or {}).get('reason', '거리 대안 조회 실패'))
    if named_details:
        candidates = {p['place_id']: p for p in (found or {}).get('candidates', [])}
        candidates.update({p['place_id']: p for p in named_details})
        found = dict(candidates=list(candidates.values()))
    results = tr.run("check_accessibility + check_route", "후보 전체의 필수 시설·코스 경사 조사",
                     adaptive.evaluate, found["candidates"] if found else [], req) or []

    if named["matches"]:
        relaxations, effective_req = [], req
        tr.note('decide_relaxation', '장소명 질문은 지정 장소 주변 대안으로 범위 유지', '거리 기준 후보에서 판정, 제주 전역 편의 점수 검색으로 확대하지 않음')
    else:
        results, relaxations, effective_req = adaptive.relax(req, results, tr)
    if named_details:
        by_id = {r['place']['place_id']: r for r in results}
        for r in adaptive.evaluate(named_details, req):
            r['requested_place'] = True
            by_id[r['place']['place_id']] = r
        results = list(by_id.values())
    for r in results:
        r['place']=place_query.with_address(r['place'])
        r['use_assessment']=visit_assessment.assess(r,req)
        if r.get('requested_place'):
            r['use_assessment'] = tr.run('assess_named_visit', '필수 조건 등급만으로 이용 가능을 오해하지 않도록 원문 구간·시설 근거 종합',
                visit_assessment.assess, r, req, input_desc=r['place']['name'], summarize=lambda x:x['text'])
            if r.get('use_assessment'):
                name_notices.append(r['use_assessment']['text'])
    notices = list(name_notices)
    limits.extend(name_notices)
    if relaxations:
        relaxation_notice = "원래 조건 충족 0곳 → " + " → ".join(relaxations) + ". 완화 검색의 대안이며 표시 등급은 원래 필수 시설 기준을 유지합니다."
        notices.append(relaxation_notice)
        limits.append(relaxation_notice)
    for r in results:
        r["caution_list"] = _collect_cautions(r["access"], r["route"], req)
        if relaxations:
            r["caution_list"].insert(0, relaxation_notice)
    if named["matches"]:tr.note("rank_slope", "코스 조사 결과에 따라 같은 등급 내 순위 조정",
            f"휠체어 기준 초과 {sum(bool(r.get('slope_penalty')) for r in results)}곳 후순위; 측정값 있음·기준 이하 → 측정값 없음 → 측정값 있음·기준 초과(등급 유지)")

    # 관광지 대안과 음식·숙박·쇼핑은 별도 표시. 등급·경사 규칙은 각 목록 안에서 유지.
    convenience_results=[r for r in results if r['place'].get('_separate_convenience')]
    results=[r for r in results if not r['place'].get('_separate_convenience')]
    convenience_results.sort(key=_rank_key)
    for i,r in enumerate(convenience_results,1): r['rank'],r['rank_reason']=i,_rank_reason(r)
    # 3) 순위
    if not named['matches']:
        if req.themes and any(r['theme_hits'] for r in results):
            results=[r for r in results if r['theme_hits']]
            tr.note('filter_recommendation_theme','새 정렬에서 성격 점수를 쓰지 않으므로 기존 성격 일치 후보 안에서 추천','요청 성격 '+', '.join(req.themes)+' 일치 '+str(len(results))+'곳')
        results=tr.run('rank_recommendations','추천 질문 → 필수 미충족 맨 뒤 → 빨강 범주·같은 범주 내 시설 상태·이용 판단·주황·거리 순 정렬',recommendation.order,results,req,summarize=lambda x:f'{len(x)}곳; 시설 상태·등급 변경 없음') or []
    else:
        results.sort(key=_rank_key)
    for i, r in enumerate(results, 1):
        recommendation.annotate(r,req)
        r['rank'],r['rank_reason']=i,(recommendation.reason(r) if not named['matches'] else _rank_reason(r))

    if results and results[0].get("slope_unknown"):
        measured = next((r for r in results if r["route"]["max_slope"] is not None), None)
        message = f"1위 {results[0]['place']['name']}: 경사 정보 없음(안전 확인 아님). "
        message += (f"경사 측정값이 있는 장소 중 최상위: {measured['place']['name']}({measured['grade']}, 최대 {measured['route']['max_slope']:g}°)."
                    if measured else "후보 중 경사 측정값이 있는 장소를 찾지 못했습니다.")
        notices.append(message)
        tr.note('explain_unknown_slope', '상위 장소 경사 미측정 → 측정 장소 최상위도 함께 안내', message)
    if results:
        top = results[0]
        toilet = next(t for t in top["access"]["table"] if t["item"] == "장애인화장실")
        if toilet["status"] in (tools.NO, tools.UNK):
            alternative = tr.run("find_toilet_alternative",
                                 f"1위 현장 장애인 화장실 {toilet['status']} → 주변 ● 업체 추가 조사",
                                 adaptive.toilet_alternative, top["place"], input_desc=top["place"]["name"],
                                 summarize=lambda x: x["message"])
            top["toilet_alternative"] = alternative
            if alternative:
                notices.append(alternative["message"])
                top["caution_list"].insert(0, alternative["message"])
        else:
            tr.note("decide_toilet_alternative", "1위 화장실 상태로 추가 조사 결정",
                    f"현장 화장실 {toilet['status']} → 추가 대안 조사 불필요")

    # 4) 상위 장소 상세 조사 (도구 선택: 필요한 것만)
    for r in results[:TOP_N]:
        p = r["place"]
        park=r['access'].get('parking',{})
        if park:tr.note('check_parking','주차 조건 분리 → 원문 우선, 부족할 때500m 보조 조회',p['name']+': 일반 '+park['general']['display']+' / 장애인 현장 '+park['disabled']['original_status']+' / '+(park['disabled']['supplement'] or '장애인 근처 보완 없음'))
        r["nearby"] = tr.run("find_nearby", "주변 대체시설(휠체어 진입·장애인 화장실 표시 업체)",
                             tools.find_nearby, p, input_desc=p["name"],
                             summarize=tools.nearby_summary)
        if req.date and config.KMA_SERVICE_KEY:
            r["weather"] = tr.run("check_weather", "방문일 기상청 단기·중기예보", tools.check_weather, p, req,
                                  input_desc=f"{p['name']} {req.date} {req.time_slot}",
                                  summarize=tools.weather_summary)
            if r["weather"]:   # 날씨 주의는 당일 안전과 직결되므로 맨 앞에 둔다
                r["caution_list"] = r["weather"].get("cautions", []) + r["caution_list"]
        else:
            reason = "방문 날짜 미지정" if not req.date else "기상청 키 없음"
            r["weather"] = dict(status=tools.UNK, reason=reason, cautions=[])
        advice = adaptive.rain_advice(r["weather"] or {})
        if advice:
            r["indoor_alternative"] = tr.run("find_indoor_alternative", "비 예보 → 같은 읍·면·동의 실내 근거·필수 시설 대안 추가 조사",
                                                indoor.alternatives,p,req,input_desc=p["name"],summarize=lambda x:x["message"])
            if r["indoor_alternative"]:
                notices.append(r["indoor_alternative"]["message"])
            notices.append(f"{p['name']}: {advice}")
            r["caution_list"].insert(0, advice)
            r['rain_days']=tr.run('recommend_rain_days','날씨 나쁨 → 다른 날짜 자동 조회',adaptive.recommend_rain_days,p,req,input_desc=p['name']+' 오늘~10일 뒤',summarize=lambda x:x.get('message') or x.get('reason'))
        else:
            tr.note("decide_rain_action", "날씨 중간 결과로 날짜 변경 안내 여부 결정",
                    f"{p['name']}: " + ((r["weather"] or {}).get("reason", "비 예보·강수 기준 해당 없음")
                    + " → 날짜 변경 분기 건너뜀"))

    day_recommendation = None
    rainy=next((r.get('rain_days') for r in results if r.get('rain_days')),None)
    if rainy:
        day_recommendation=rainy
        notices.append(rainy.get("message") or rainy.get("reason","다른 날짜 예보 미확인"))
    elif results and adaptive.wants_day_advice(req):
        day_recommendation = tr.run('recommend_visit_day', '날짜 미지정·이번 주/주말/언제 요청 → 1위 장소의 향후 7일 강수확률 비교',
                                    adaptive.recommend_day, results[0]['place'], req,
                                    input_desc=results[0]['place']['name'],
                                    summarize=lambda x: x.get('message') or x.get('reason'))
        if day_recommendation and day_recommendation.get('message'):
            notices.append(day_recommendation['message'])
    else:
        tr.note('decide_visit_day', '날짜 추천 필요성 판단', '특정 날짜 지정 또는 판정 후보 없음 → 7일 추천 생략')
    # 5) 설명
    summary, how = tr.run("explain", "원문·출처가 포함된 판정 JSON으로 설명 작성 및 대조",
                          lambda: explain(req, goal, results, limits, use_llm=use_llm, missing_context=missing_context),
                          summarize=lambda x: x[1])
    explanation=summary
    if notices:
        summary = (summary+"\n\n"+"\n\n".join(notices)) if missing_context else ("\n\n".join(notices)+"\n\n"+summary)

    if req.is_empty():
        limits.insert(0, "요청에서 이용자 유형·필수 시설·지역·날짜를 찾지 못해 전체 후보를 필수 미충족·빨강 범주·이용 판단 등의 추천 순서로 보여 줌")
    if not req.needs:
        limits.insert(0, "필수 시설을 지정하지 않은 '조건 충족'은 시설 조건의 빈 집합 판정이며 이용 가능·안전 확인이 아님")
    dates = data.source_date_ranges()
    limits += [f"출처별 데이터 기준일: 허브 {dates['hub']['lo']}~{dates['hub']['hi']}; 관광공사 수정일 {dates['kto']['lo']}~{dates['kto']['hi']}. 현장 조사일·현재 상태 보장 아님",
               "제주데이터허브가 핵심·필수 데이터이며 한국관광공사는 보조 출처. 같은 항목은 콘텐츠 기준일이 최신인 출처 우선(현장 조사일 아님). 출처 간 차이는 검토 필요",
               "허브 추천 대상 표(●)는 모든 장소·유형에 표시되어 있어 판단에 사용하지 않음"]
    limits.append('응급 상황에서는 119에 연락하세요.')
    return dict(request=req.to_dict(), effective_request=effective_req.to_dict(), relaxations=relaxations,
                convenience_results=convenience_results, named_places=indexed, named_groups=named.get('groups', []), day_recommendation=day_recommendation,
                missing_place=missing_context, judgment_missing=bool(missing_context), goal=goal, results=results, summary=summary, explanation=explanation, limits=limits,
                slowest_step=max(tr.steps, key=lambda s: s["ms"], default=None),
                trace=tr.steps, mode=("LLM" if not cache.blocked("llm") else "규칙(LLM 연결 실패)")
                if use_llm and config.llm_enabled() else "규칙",
                elapsed_ms=round((time.perf_counter() - t_start) * 1000))


# ---------------------------------------------------------------------------
# 설명: LLM이 있으면 계산된 결과만 요약하게 하고, 없으면 문장 틀을 쓴다
# ---------------------------------------------------------------------------
EXPLAIN_SYSTEM = """너는 무장애 여행 안내 도우미다. 아래 JSON은 프로그램이 원본 데이터로 이미 판정한 결과다.
규칙: JSON에 없는 사실을 절대 추가하지 마라. '미확인'은 '없다'고 말하지 말고 '정보가 없어 확인 필요'라고 말하라.
한국어로 3~4문장, 쉬운 말로, 1위 장소의 이용 범위와 주의 구간을 설명하라. 시설 상태 목록과 날씨는 별도로 표시되므로 반복 나열하지 마라. 목표·도구 선택·기술적인 순위 규칙·처리시간은 쓰지 마라.
missing_place가 있으면 그 장소의 조사 자료가 없다는 message를 먼저, alternatives_heading을 다음에 말하라. top은 질문한 장소가 아니라 가까운 대안이며 질문한 장소의 이용 가능 여부를 추측하지 마라. 1위 소개로 시작하지 마라."""


def _compact(req, goal, results, missing_context=None):
    return dict(goal=goal, user_type=req.user_type, needs=req.needs, missing_place=missing_context, top=[
        dict(rank=r["rank"], name=r["place"]["name"], grade=r["grade"],
             needs=[dict(item=n["item"], status=n["effective"], original_status=n["status"],
                         value_raw=n.get("raw"), source=n.get("source"), evidence=n.get("evidence"),
                         base_date=n.get("base_date"), alt_evidence=n.get("alt_evidence"), note=n["note"],
                         all_sources=[dict(value_raw=v.get("raw"), source=v.get("source"), evidence=v.get("evidence"),
                                           status=v["status"], base_date=v.get("base_date"))
                                      for v in r["access"]["table"] if v["item"] == n["item"]])
                    for n in r["access"]["needs"]],
             related_evidence=[dict(item=v["item"], value_raw=v["value_raw"], source=v.get("origin"),
                                    file_name=v.get("file_name"), source_locator=v.get("source_locator"),
                                    evidence=v.get("evidence"), status=v["status"])
                               for v in data.items(r["place"]["place_id"])
                               if any(word in v["item"] for word in ("화장실", "주차"))],
             use_assessment=r.get("use_assessment"), distance_km=r["place"].get("_distance_km"), parking=r["access"].get("parking"), rank_reason=r["rank_reason"], address=r["place"].get("address"),
             cautions=r["caution_list"][:5], max_slope=r["route"]["max_slope"])
        for r in results[:TOP_N]])


def template_summary(req, goal, results) -> str:
    if not results:
        return "조건에 맞는 후보 장소가 없습니다. 지역이나 필수 조건을 줄여 다시 찾아보세요."
    top = results[0]
    lines = [f"목표: {goal}."]
    if req.is_empty():
        lines.append("요청에서 조건을 찾지 못해 필수 시설을 지정하지 않은 후보를 빨강 구간 범주와 이용 판단 등으로 정렬합니다.")
    lines += [
             f"1순위는 **{top['place']['name']}**({top['grade']})입니다."]
    if not req.needs:
        acc = {t["item"]: t["status"] for t in top["access"]["table"]}
        lines.append(f"장애인 화장실 {acc.get('장애인화장실', '미확인')}, 장애인 주차장 {acc.get('장애인주차장', '미확인')}"
                     + (f"(대체 화장실: {top['access']['alt_toilet']})" if top["access"]["alt_toilet"] else "") + ".")
    for n in top["access"]["needs"]:
        if n["effective"] == tools.UNK:
            lines.append(f"{n['item']}은(는) 원본에 정보가 없어 방문 전 확인이 필요합니다.")
        elif n["note"]:
            lines.append(n["note"] + ".")
        else:
            lines.append(f"{n['item']}: {n['effective']}.")
    w = top.get("weather") or {}
    if w.get("status") == "조회됨":
        wind = f"풍속 최대 {w['wind_max']:g}m/s" if w.get('wind_max') is not None else w.get('wind_note', '풍속 미확인')
        lines.append(f"{fmt_date(req.date)} {req.time_slot} {w.get('forecast_type', '')} 예보: {w['sky']}, 강수확률 최대 {w['pop_max']}%, {wind}. {w.get('precision', '')}")
    elif req.date:
        lines.append(f"날씨는 확인하지 못했습니다({w.get('reason', '미확인')}). 출발 전 예보를 확인하세요.")
    if top["caution_list"]:
        lines.append("주의: " + "; ".join(top["caution_list"][:3]) + ".")
    others = [f"{r['place']['name']}({r['grade']})" for r in results[1:TOP_N]]
    if others:
        lines.append("다른 후보: " + ", ".join(others) + ".")
    return " ".join(lines)


def explain(req, goal, results, limits, use_llm=True, missing_context=None) -> tuple[str, str]:
    if missing_context:
        # 접두 안내는 규칙으로 고정한다. LLM에도 같은 맥락을 전달하고 순서를 검증한다.
        fallback=missing_place.introduction(missing_context)
        if not results:fallback+='\n\n가까운 판정 가능 장소를 보유 자료에서 찾지 못했어요.'
        if use_llm and config.llm_enabled() and results:
            payload=_compact(req,goal,results,missing_context)
            out=llm.ask(EXPLAIN_SYSTEM,json.dumps(payload,ensure_ascii=False),max_tokens=500)
            from .explanation_check import issues
            problems=issues(out,payload) if out else []
            if out and re.sub(r'\s+', ' ', out.strip()).startswith(missing_context['message']+' '+missing_context['alternatives_heading']) and not problems:
                return out.strip(),'LLM 요약 (판정 자료 없음·대안 맥락 및 안내 순서 대조)'
            reason=('LLM 응답 없음: '+llm.LLMStatus.last_error if not out else
                    '; '.join(problems) if problems else '첫 안내 또는 대안 제목 순서 불일치')
            return fallback,'자료 없음 안내 문장 틀 ('+reason+')'
        return fallback,'자료 없음 안내 문장 틀 (규칙 모드)'
    if not results:
        return template_summary(req, goal, results), "후보 없음 → 안내 문장"
    if use_llm and config.llm_enabled():
        out = llm.ask(EXPLAIN_SYSTEM, json.dumps(_compact(req, goal, results), ensure_ascii=False), max_tokens=500)
        if out:
            from .explanation_check import issues
            problems = issues(out, _compact(req, goal, results))
            if problems:
                return template_summary(req, goal, results), "설명문 대조 실패 → 문장 틀: " + "; ".join(problems)
            return out.strip(), "LLM 요약 (판정 결과 JSON만 전달)" + (" (캐시)" if llm.LLMStatus.last_from_cache else "")
        return template_summary(req, goal, results), f"문장 틀 사용 (LLM 실패: {llm.LLMStatus.last_error})"
    return template_summary(req, goal, results), "문장 틀 사용 (규칙 모드)"
