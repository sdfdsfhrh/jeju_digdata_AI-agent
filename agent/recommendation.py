"""추천 질문 전용 정렬. 원래 시설 판정·등급은 수정하지 않는다."""
from . import course_profile, visit_assessment

STATE={'있음':0,'조건부':1,'미확인':2,'없음':3}

def assessment_order(result):
    text=(result.get('use_assessment') or {}).get('text','')
    decision=text.split(' — ')[0].split(': ',1)[-1]
    if decision.startswith('어려움'):return 3
    if decision.startswith('가능'):
        return 1 if '(' in decision else 0
    return 2

def annotate(result,req=None):
    if not result.get('use_assessment') and req is not None:
        result['use_assessment']=visit_assessment.assess(result,req)
    profile=course_profile.prepare(result)
    result['course_counts']=dict(red=sum(s['level']==2 for s in profile['segments']) if profile['segments'] else None,
        orange=sum(s['level']==1 for s in profile['segments']) if profile['segments'] else None,known=bool(profile['segments']),
        unit='원본 파일별 연속 조사 지점 사이 구간(중복 주의 마커 수 아님)')
    return result

def red_band(result):
    red=result['course_counts']['red']
    return 0 if red==0 else 1 if red is None else 2 if red<=2 else 3


def facility_stage(result):
    return max((STATE.get(n['effective'],2) for n in result['access']['needs']),default=0)


def missing_required(result):
    labels={'parking_disabled':'장애인 주차','장애인주차장':'장애인 주차','parking_general':'일반 주차','장애인화장실':'장애인 화장실'}
    return [labels.get(n.get('condition_key') or n['item'],n['item'])+' 없음(필수 조건)'
            for n in result['access']['needs'] if n['effective']=='없음']


def key(result):
    counts=result['course_counts'];stage=facility_stage(result)
    distance=result['place'].get('_distance_km')
    # 필수 조건 미충족은 전체 맨 뒤. 같은 빨강 구간 안에서는 충족/조건부/미확인 순.
    return (bool(missing_required(result)),red_band(result),stage,assessment_order(result),
            counts['orange'] if counts['orange'] is not None else float('inf'),
            distance if distance is not None else float('inf'),result['place']['name'])


def order(results,req):
    for r in results:annotate(r,req)
    return sorted(results,key=key)

def reason(r):
    c=r['course_counts']
    note=" · 경사 측정값 없음(안전 확인 아님)" if r["route"].get("max_slope") is None else ""
    red=c['red'] if c['known'] else '미확인';orange=c['orange'] if c['known'] else '미확인'
    return f"필수 미충족 {'있음(맨 뒤)' if missing_required(r) else '없음'} → 빨강 {red}구간(범주 {red_band(r)}) → 같은 범주 내 필수시설 상태 → {r['use_assessment']['text'].split(' — ')[0]} → 주황 {orange}구간 → 직선거리(없는 값은 미확인)"+note
