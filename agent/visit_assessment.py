"""장소명 질문용 이용 판단. 시설 조건 등급과 구분하며 안전을 보장하지 않는다."""
from . import tools
import re
from collections import defaultdict


def assess(result, req):
    route=result['route']; evidence=[]; parts=[]
    over=route['over_ref']
    if over:
        parts.append(f"경사 참고 기준 초과 {len(over)}개 측정값(최대 {route['max_slope']:g}°)")
        evidence += [s['evidence'] for s in over]
    elif route['max_slope'] is None:
        parts.append('경사 측정값 없음(안전 확인 아님)')
    else:
        parts.append(f"기록된 경사 측정값은 참고 기준 이하(최대 {route['max_slope']:g}°, 안전 보장 아님)")
        evidence += [s['evidence'] for s in route['course_slopes']]
    split=[]; steps=[]; available=[]
    for p in route['points']:
        text=' '.join(filter(None,[p.get('label'),p.get('description')]))
        proof=tools.ev(p['file_name'],p['source_locator'],text)
        if '계단' in text: steps.append(proof)
        if '계단' in text and '휠체어' in text and any(w in text for w in ['좌측','우측','왼쪽','오른쪽','우회']): split.append(proof)
        if '휠체어' in text and any(w in text for w in ['접근가능','접근 가능','진입가능','진입 가능']): available.append(proof)
    evidence += available
    if split:
        parts.append('계단길·휠체어길 분리 지점 있음');evidence+=split
    elif steps:
        parts.append('계단 지점 있음');evidence+=steps
    for item,label in [('장애인화장실','장애인 화장실'),('장애인주차장','장애인 주차')]:
        value=next((v for v in result['access']['table'] if v['item']==item),None)
        if value:
            parts.append(label+' '+value['status'])
            if value.get('evidence'): evidence.append(value['evidence'])
    # 대안의 원문 계단 다수는 다른 구간의 이용 가능 문장으로 덮지 않는다.
    many=[]
    groups=defaultdict(list)
    for point in route['points']:groups[point.get('file_name') or '원본'].append(point)
    for points in groups.values():
        points.sort(key=lambda p:int(p.get('seq') or 0))
        for i,point in enumerate(points):
            raw=' '.join(str(point.get(k) or '') for k in ('label','description','detail_raw'))
            counts=re.findall(r'계단\s*(\d+)\s*(?:개|단)?|(\d+)\s*계단',raw)
            if not any(int(a or b)>=20 for a,b in counts):continue
            nearby=' '.join(' '.join(str(p.get(k) or '') for k in ('label','description','detail_raw')) for p in points[max(0,i-1):i+2])
            if re.search(r'휠체어\s*길|우회|경사로|엘리베이터|분리',nearby):continue
            many.append(tools.ev(point['file_name'],point['source_locator'],raw))
    if many and not result.get('requested_place'):
        parts.append('계단 다수·인접 지점 우회 정보 없음');evidence+=many
    if req.user_type in tools.WHEEL:
        prefix='휠체어 이용: '
        if many and not result.get('requested_place'):
            judgment='확인 필요(계단 다수·우회 정보 없음)'
        elif available or split:
            judgment='가능(일부 구간 주의)'
        elif over or steps:
            judgment='확인 필요(주의 구간 있음)'
        else:
            judgment='확인 필요(이용 범위 정보 부족)'
    else:
        prefix='이용 판단: ';judgment='확인 필요(시설·구간 조건 확인)'
    return dict(text=prefix+judgment+' — '+', '.join(parts),evidence=list(dict.fromkeys(evidence)),
                limit='원문에 기록된 일부 시설·구간 기준이며 전체 코스 이용 가능·안전을 보장하지 않음')
