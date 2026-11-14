"""기준 장소 주변 추천. 기존 접근성 등급/상태를 바꾸지 않고 거리·보행 근거로 별도 정렬한다."""
import re
import time
from . import adaptive, anchor, config, data, indoor, place_query, tools, visit_assessment, recommendation

SENIOR_LIMIT='어르신 보행 기준은 별도 공식 기준이 없어 경사·계단·화장실·쉼터 정보로 판단했습니다. 개인 건강 상태에 따라 다를 수 있습니다.'


def own_evidence(p):
    rows=[]
    for v in data.points(p['place_id']):
        text=' '.join(str(v.get(k) or '') for k in ('label','description','detail_raw'))
        rows.append((text,tools.ev(v['file_name'],v['source_locator'],text)))
    for v in data.items(p['place_id']):
        if v.get('value_raw'):
            text=str(v['value_raw']);rows.append((text,tools.ev(v['file_name'],v['source_locator'],text)))
    return rows


def walking_features(p):
    risk=[];rest=[]
    for raw,proof in own_evidence(p):
        # 명시적 부재를 위험/휴식시설 있음으로 뒤집지 않는다.
        risktext=re.sub(r'(?:계단|급경사)\s*(?:은|이|가)?\s*(?:없음|없다|없습니다|없으며|없고|없는|없어)','',raw)
        resttext=re.sub(r'(?:쉼터|벤치|그늘)\s*(?:은|이|가)?\s*(?:없음|없다|없습니다|없으며|없고|없는|없어)','',raw)
        if re.search(r'계단|급경사|(?:접근|진입|이용)\s*불가',risktext):risk.append(proof)
        if re.search(r'쉼터|벤치|그늘',resttext):rest.append(proof)
    return dict(risk_evidence=list(dict.fromkeys(risk)),rest_evidence=list(dict.fromkeys(rest)))


def candidate_pool(location,req,tr,judgment_missing=False):
    choices=[]
    for original in data.detailed_places():
        p=dict(original)
        if location.get('place_id')==p['place_id']:continue
        if not anchor.valid(p.get('lat'),p.get('lon')):continue
        kind=place_query.classify(p)
        if kind['group']=='편의':continue
        text=' '.join(str(p.get(k) or '') for k in ('name','overview','recommended_course','full_course'))
        walktype=bool(re.search(r'산책|올레|공원|해안|숲길|걷기',text))
        if req.activity=='indoor':
            proof=indoor.evidence(p)
            if not proof:continue
        elif not judgment_missing and kind['group']!='관광지' and not walktype:continue
        if not req.activity=='indoor':proof=[]
        p['_distance_km']=anchor.km(location,p);p['_place_type']=kind
        p['_distance_evidence']=[dict(name=location['name'],lat=location['lat'],lon=location['lon'],coord_source=location['source'],sources=location['evidence']),
                                 dict(name=p['name'],lat=p['lat'],lon=p['lon'],coord_source=p.get('coord_source'),sources=data.place_evidence(p['place_id']))]
        p['_theme_hits']=tools._theme_hits(p,req.themes)
        choices.append(p)
    radii=[];selected=[]
    minimum=1 if judgment_missing else 3
    for radius in ((5,10) if judgment_missing else (5,10,15)):
        selected=[p for p in choices if p['_distance_km']<=radius]
        radii.append(dict(radius_km=radius,count=len(selected)))
        tr.note('filter_anchor_distance','후보 거리 필터 → 관광/보행 유형·실내 근거·직선거리 확인',f'{radius}km 이내 {len(selected)}곳'+(' → 다음 반경 조사' if len(selected)<minimum and radius<(10 if judgment_missing else 15) else ''))
        if len(selected)>=minimum:break
    return dict(candidates=selected,radius_km=radius,radii=radii,message=(f'가까운 후보가 부족해 반경을 5km에서 {radius}km로 넓혔습니다. ' if radius>5 else '')+
                f'직선거리 {radius}km 이내 판정 가능 후보 {len(selected)}곳. 실제 이동 경로·거리는 미검증.')


def slope_group(r):
    return 2 if r['route']['over_ref'] else 1 if r['route']['max_slope'] is None else 0


def toilet_status(r):
    return next((v['status'] for v in r['access']['table'] if v['item']=='장애인화장실'),tools.UNK)


def senior_key(r):
    return (bool(r['walking']['risk_evidence']),slope_group(r),
            {tools.YES:0,tools.COND:1,tools.UNK:2,tools.NO:3}[toilet_status(r)],
            -bool(r['walking']['rest_evidence']),r['place']['_distance_km'],r['place']['name'])


def order_results(results,req,judgment_missing=False):
    for r in results:r['walking']=walking_features(r['place'])
    if req.user_type in tools.WHEEL:
        results=recommendation.order(results,req)
    elif req.companion=='senior' and req.activity=='walk':
        results.sort(key=senior_key)
    else:
        results.sort(key=lambda r:(tools.GRADE_ORDER[r['grade']],slope_group(r),r['place']['_distance_km'],r['place']['name']))
    if judgment_missing:
        results.sort(key=lambda r:int(r['place']['_distance_km']))
    return results[:5]


def run(req,tr,started,use_llm=True,judgment_missing=False):
    from .core import _collect_cautions, explain
    from . import missing_place
    goal=f"{req.anchor} 근처에서 {req.user_type or '동행자'}와 {'실내 공간' if req.activity=='indoor' else '산책·방문'}할 장소 찾기"
    limits=['직선거리·대표 좌표 기반으로 실제 이동 경로를 검증하지 않았습니다. 미측정은 안전 확인이 아닙니다.']
    if req.companion=='senior':limits.append(SENIOR_LIMIT)
    dates=data.source_date_ranges()
    limits.append(f"출처별 데이터 기준일: 허브 {dates['hub']['lo']}~{dates['hub']['hi']}; 관광공사 수정일 {dates['kto']['lo']}~{dates['kto']['hi']}. 현장 상태는 재확인 필요")
    limits.append('허브가 핵심·필수 데이터, 관광공사는 보조 출처. 기존 시설 상태·등급은 그대로 유지합니다.')
    location=tr.run('resolve_anchor','기준 위치 찾기 → DB → 주변 CSV → 주차장 → 브이월드 → 관광공사 → 지역 대표 좌표',anchor.resolve,req.anchor,tr,
                    input_desc=req.anchor,summarize=lambda x:x['source'] if x else '위치 없음')
    notices=[];results=[];radius=None
    if judgment_missing:notices.append(f"'{req.anchor}'의 판정 데이터가 없습니다. 해당 장소의 접근성을 판정하지 않고 근처 판정 가능 장소를 안내합니다.")
    if not location:
        notices.append(f"'{req.anchor}'의 위치를 찾지 못했습니다. 근처 지역명(예: 중문)으로 다시 물어봐 주세요")
    else:
        notices.insert(0,f"기준 위치: {req.anchor}(출처: {location['source']}, 좌표 근사)")
        pool=tr.run('anchor_candidate_pool','기준 위치 확인 후 후보 거리 필터',candidate_pool,location,req,tr,judgment_missing,summarize=lambda x:x['message'])
        if pool:
            radius=pool['radius_km'];notices.append(pool['message'])
            judged=tr.run('check_anchor_accessibility','반경 후보의 기존 시설·경사 판정(등급·상태 보존)',adaptive.evaluate,pool['candidates'],req) or []
            purpose=('휠체어 추천 → 필수 미충족 맨 뒤·빨강 범주·시설 상태·이용 판단·주황·거리' if req.user_type in tools.WHEEL else '보행 조건 정렬 → 주의 명시·경사·화장실·휴식·거리(등급 변경 없음)')
            results=tr.run('rank_walking_conditions',('1km 거리 구간 우선 → 구간 내 기존 판정 순서' if judgment_missing else purpose),order_results,judged,req,judgment_missing,
                           summarize=lambda x:f'{len(x)}곳 표시; '+('필수 미충족 맨 뒤·빨강 범주·시설 상태·이용 판단·주황·거리 순' if req.user_type in tools.WHEEL else '어르신 산책 전용 순위' if req.companion=='senior' and req.activity=='walk' else '기존 시설 등급·경사·거리 순')) or []
        if not results:notices.append(f'반경 {radius or 15}km까지 보유 데이터에서 해당 활동의 판정 가능 장소를 찾지 못했습니다. 실제 장소가 없다는 뜻은 아닙니다.')
    for i,r in enumerate(results,1):
        p=r['place'];r['rank']=i
        r['place']=place_query.with_address(r['place'])
        p=r['place']
        r['caution_list']=_collect_cautions(r['access'],r['route'],req)
        r['rank_reason']=(f"원문 주의 명시 {'있음' if r['walking']['risk_evidence'] else '미발견(안전 확인 아님)'} · 경사 단계 {slope_group(r)+1}/3 · 장애인 화장실 {toilet_status(r)} · "
                          f"휴식 근거 {'있음' if r['walking']['rest_evidence'] else '미확인'} · 직선거리 {p['_distance_km']:.2f} km · 등급 {r['grade']} 유지")
        assessment=visit_assessment.assess(r,req)
        if req.user_type not in tools.WHEEL:
            conclusion=('확인 필요(계단·급경사 등 주의 구간)' if r['walking']['risk_evidence'] else
                        '확인 필요(경사 측정값 없음)' if r['route']['max_slope'] is None else '검토 가능(현장 확인 필요)')
            assessment['text']=('어르신 산책: ' if req.companion=='senior' else '이용 판단: ')+conclusion+' — '+assessment['text'].split(' — ',1)[-1]
        assessment['evidence']+=r['walking']['risk_evidence']+r['walking']['rest_evidence']
        r['use_assessment']=assessment
        if req.user_type in tools.WHEEL:
            recommendation.annotate(r,req)
            r['rank_reason']=recommendation.reason(r)
        if judgment_missing:
            distance=p['_distance_km']
            r['rank_reason']=f'{int(distance)}~{int(distance)+1}km 직선거리 구간 우선 · 같은 구간은 기존 판정 순서'
        r['caution_list']+=['원문 주의: '+proof for proof in r['walking']['risk_evidence'][:3]]
        park=r['access'].get('parking',{})
        if park:tr.note('check_parking','주차 종류 분리·500m 외부 근거 확인',p['name']+': 일반 '+park['general']['display']+' / 장애인 현장 '+park['disabled']['original_status']+' / '+(park['disabled']['supplement'] or '근처 보완 없음'))
        r['nearby']=tr.run('find_nearby','주변 시설 자료 보유 및 대체시설 표시 확인',tools.find_nearby,p,input_desc=p['name'],summarize=tools.nearby_summary)
        if req.date and config.KMA_SERVICE_KEY:
            r['weather']=tr.run('check_weather','날씨 확인 → 방문 날짜·시간대 기존 예보 도구',tools.check_weather,p,req,input_desc=p['name']+' '+req.date,
                               summarize=tools.weather_summary) or dict(status=tools.UNK,reason='날씨 도구 실패',cautions=[])
        else:
            reason='방문 날짜 미지정' if not req.date else '기상청 키 없음'
            r['weather']=dict(status=tools.UNK,reason=reason,cautions=[])
            tr.note('check_weather','날씨 확인 → 날짜·키 유무 확인',p['name']+': '+reason+' → 건너뜀')
        r['caution_list']=r['weather'].get('cautions',[])+r['caution_list']
        advice=adaptive.rain_advice(r['weather'])
        if advice:
            r['rain_days']=tr.run('recommend_rain_days','날씨 나쁨 → 다른 날짜 자동 조회',adaptive.recommend_rain_days,p,req,input_desc=p['name'],summarize=lambda x:x.get('message') or x.get('reason'))
            r['caution_list'].insert(0,advice)
            r['indoor_alternative']=tr.run('find_indoor_alternative','비 예보 → 같은 지역 원문 실내 근거 대안 추가',indoor.alternatives,p,req,input_desc=p['name'],summarize=lambda x:x['message'])
            if r.get('indoor_alternative'): r['indoor_alternative']['activity']='indoor'
            notices.append(p['name']+': '+advice)
            if r.get('rain_days'):notices.append(r['rain_days'].get('message') or r['rain_days'].get('reason','다른 날짜 예보 미확인'))
    missing_context=missing_place.context(req.anchor,req,location,radius) if judgment_missing else None
    explanation=None
    if missing_context:
        explanation,how=tr.run('explain_missing_place','질문 장소 조사 자료 없음 → 가까운 대안임을 먼저 설명',
            lambda:explain(req,goal,results,limits,use_llm=use_llm,missing_context=missing_context),summarize=lambda x:x[1])
    summary=((explanation+'\n\n') if explanation else '')+'\n\n'.join(notices)
    if results:
        summary+='\n\n'+'\n'.join(f"{r['rank']}. {r['place']['name']} — "+(missing_place.distance(missing_context,r) if missing_context else f"{r['place']['_distance_km']:.2f} km")+f", {r['use_assessment']['text']}" for r in results)
    if req.companion=='senior':summary+='\n\n'+SENIOR_LIMIT
    tr.note('explain_anchor','거리·보행 판정 원문으로 결론 우선 안내','규칙 문장 사용, 외부 사실 추가 없음')
    limits.append('응급 상황에서는 119에 연락하세요.')
    return dict(request=req.to_dict(),effective_request=req.to_dict(),relaxations=[],named_places=[],named_groups=[],convenience_results=[],
                missing_place=missing_context,explanation=explanation,judgment_missing=judgment_missing,display_n=5,anchor=location,anchor_query=req.anchor,anchor_radius_km=radius,day_recommendation=next((r.get('rain_days') for r in results if r.get('rain_days')),None),goal=goal,results=results,summary=summary,limits=limits,
                trace=tr.steps,mode='LLM' if use_llm and config.llm_enabled() and req.parsed_by.startswith('LLM') else '규칙',
                slowest_step=max(tr.steps,key=lambda s:s['ms'],default=None),elapsed_ms=round((time.perf_counter()-started)*1000))
