"""중간 결과에 따른 추가 조사. 원래 요청의 시설 상태·등급은 보존한다."""
from dataclasses import replace

import datetime as dt
import re
from . import config, tools, weather, indoor


def evaluate(candidates, req):
    results = []
    for p in candidates:
        acc = tools.check_accessibility(p, req)
        route = tools.check_route(p, req)
        results.append(dict(place=p, indoor_evidence=indoor.evidence(p), grade=acc["grade"], access=acc, route=route,
                            theme_hits=p.get("_theme_hits", []), wheelchair_user=req.user_type in tools.WHEEL,
                            slope_unknown=req.user_type in tools.WHEEL and not route["course_slopes"],
                            slope_penalty=req.user_type in tools.WHEEL and bool(route["over_ref"])))
    return results


def relax(req, initial, tr):
    """시설을 먼저 지키도록 지역부터, 이후 필수 시설을 입력 순서로 하나씩 완화한다."""
    if any(r["grade"] == tools.G_OK for r in initial) or not (req.region or req.needs):
        tr.note("decide_relaxation", "초기 판정 결과로 재검색 필요성 판단",
                "조건 충족 장소가 있거나 완화할 조건이 없어 재검색하지 않음")
        return initial, [], req
    current = replace(req, needs=list(req.needs), themes=list(req.themes))
    changes, results = [], initial
    actions = ([('지역', req.region)] if req.region else []) + [('필수 시설', n) for n in req.needs]
    for kind, value in actions:
        if kind == '필수 시설' and any(r.get('relaxed_grade', r['grade']) == tools.G_COND for r in results):
            tr.note('decide_relaxation', '조건부 충족 장소가 있어 필수 시설 유지',
                    '조건부 충족 1곳 이상 → 필수 시설 완화 중단(지역 완화는 유지)')
            break
        if kind == '지역':
            current = replace(current, region=None)
        else:
            current = replace(current, needs=[n for n in current.needs if n != value])
        changes.append(f"{kind} '{value}' 해제")
        found = tr.run("search_places_relaxed", "직전 조건 충족 0곳 → 조건 하나를 풀고 다시 검색",
                       tools.search_places, current, input_desc=" → ".join(changes),
                       summarize=lambda x: f"{len(x['candidates'])}곳 재검색")
        if found is None:
            break
        relaxed = tr.run("check_relaxed_accessibility", "재검색 후 남은 필수 조건의 충족 여부 확인",
                         evaluate, found["candidates"], current,
                         summarize=lambda x: f"완화 조건 충족 {sum(r['grade'] == tools.G_OK for r in x)}곳")
        if relaxed is None:
            break
        # 완화 결과를 원래 필수 조건 충족으로 오해하지 않도록 원래 요청으로 다시 판정한다.
        results = evaluate(found["candidates"], req)
        by_id = {r["place"]["place_id"]: r["grade"] for r in relaxed}
        for r in results:
            r["relaxed_grade"] = by_id[r["place"]["place_id"]]
        if any(r["grade"] == tools.G_OK for r in relaxed):
            break
    return results, changes, current


def toilet_alternative(place):
    nearby = tools.find_nearby(place)
    if not nearby.get("available", bool(nearby.get("rows"))):
        return dict(options=[], message="주변정보 없음(데이터 미보유) → 장애인 화장실 대안 확인 불가")
    options = nearby["toilet"]
    if not options:
        return dict(options=[], message="주변정보에서 장애인 화장실 ● 표시 업체를 찾지 못함 "
                    "(실제 시설이 없다는 뜻은 아님)")
    descriptions = [f"{v['name']} / {v['address'] or '주소 미확인'} / "
                    f"전화 {v['phone'] or '미확인'} / 근거 {v['evidence']}" for v in options]
    return dict(options=options, message="주변 장애인 화장실 대안: " + "; ".join(descriptions)
                + " — 영업·화장실 이용 가능 여부와 이동 경로는 방문 전 확인 필요")


def rain_advice(weather):
    if weather.get("status") != "조회됨":
        return None
    if (weather.get("pop_max") is not None and weather["pop_max"] >= tools.POP_CAUTION) or any(
            p in ("비", "비/눈", "소나기") for p in weather.get("precip", [])):
        return "비 예보·강수 가능성이 있어 실외 코스 이용에 주의가 필요합니다."
    return None


def wants_day_advice(req):
    return not req.date or bool(re.search(r"이번\s*주|주말|언제|가기\s*좋은\s*날", req.text))


def recommend_day(place, req, horizon=7, alternative=False):
    if not config.KMA_SERVICE_KEY:
        return dict(status="미확인", reason="기상청 키 없음 → 좋은 날 추천 생략", rows=[])
    now = weather.now_kst()
    today = now.date()
    rows = []
    for offset in range(horizon):
        day = today + dt.timedelta(days=offset)
        # 주말/이번 주 표현에는 해당 기간 안에서만 추천한다.
        eligible = True
        if not alternative and "주말" in req.text:
            eligible = day.weekday() >= 5
        if not alternative and re.search(r"이번\s*주", req.text):
            eligible = eligible and day.isocalendar()[:2] == today.isocalendar()[:2]
        if alternative and day.strftime('%Y%m%d')==req.date:eligible=False
        hours = tools.TIME_SLOTS.get(req.time_slot, tools.TIME_SLOTS["종일"])
        if offset == 0:
            hours = weather.remaining_hours(hours, now)
        if not hours:
            rows.append(dict(date=day.isoformat(), status="미확인", pop=None, forecast_type="단기", precision="남은 시간대 없음",
                             reason="오늘 요청 시간대가 모두 지남 → 비교 제외", eligible=False))
            continue
        value = weather.forecast(place.get("lat"), place.get("lon"), day.strftime("%Y%m%d"),
                                 hours,
                                 address=place.get("address"))
        rows.append(dict(date=day.isoformat(), status=value.get("status"), pop=value.get("pop_max"),
                         forecast_type=value.get("forecast_type", "미확인"), precision=value.get("precision", ""),
                         reason=value.get("reason", ""), base=value.get("base"), fallback_note=value.get("fallback_note"), eligible=eligible))
    valid = [r for r in rows if r['eligible'] and r['status'] == '조회됨' and r['pop'] is not None]
    if not valid:
        return dict(status="미확인", reason="대상 날짜 예보 조회 실패·자료 없음 → 추천 생략", rows=rows)
    choices=sorted(valid,key=lambda r:(r['pop'],r['date']))[:2 if alternative else 1]
    best=choices[0]
    return dict(status="추천", rows=rows, best=best, choices=choices,
                message=f"{place['name']}: 조회 가능한 대상 날짜 중 {best['date']}의 강수확률이 가장 낮습니다({best['pop']}%). "
                "맑음·이동 안전을 보장하지 않으며, 시간별 단기예보와 구역 단위 중기예보의 정밀도가 다릅니다. "
                + ("일부 날짜는 미확인으로 비교에서 제외했습니다." if len(valid) < sum(r['eligible'] for r in rows) else ""))


def recommend_rain_days(place,req):
    result=recommend_day(place,req,horizon=11,alternative=True)
    if result.get('choices'):
        def label(row):
            day=dt.date.fromisoformat(row['date'])
            return f"{day.month}/{day.day}({'월화수목금토일'[day.weekday()]}) 강수 {row['pop']}% — 이날 방문 추천"
        result['message']=' / '.join(label(r) for r in result['choices'])+'. 예보가 있는 날짜만 비교했으며 맑음·안전을 보장하지 않습니다.'
        missing=[r['date'] for r in result['rows'] if r.get('eligible') and (r['status']!='조회됨' or r['pop'] is None)]
        if missing:result['message']+=' 예보 미확인 날짜: '+', '.join(missing)+'.'
    else:result['reason']='오늘~10일 뒤 예보 범위에서 비교 가능한 다른 날짜 자료가 없습니다. 예보가 없는 범위는 추천하지 않습니다.'
    return result
