"""비 예보에 실내 공간이 명시된 같은 읍면동 대안 조사. 안전·전체 실내를 추정하지 않는다."""
import re
from . import data, tools, place_query


def evidence(place):
    # 다른 관광지/주변시설 설명은 읽지 않는다. 본 장소 코스 지점만 조사.
    found=[]
    for p in data.points(place['place_id']):
        text=' '.join(filter(None,[p.get('label'),p.get('description'),p.get('detail_raw')]))
        label=p.get('label') or ''
        if '성산항' in place['name'] and '선박 화장실' in label: break
        explicit=re.search(r'실내|대합실|전시관\s*(?:입구|진입)|본관\s*입구',text)
        if explicit and not re.search(r'야외.*전시|화장실',text):
            # 박물관의 본관/전시관, 대합실, 명시적인 실내 공간만. 단순 전시회는 제외.
            if '본관' in text and '박물관' not in place['name']: continue
            found.append(dict(kind='실내 공간 포함(전체 코스 실내 아님)', raw=text,
                              source=tools.ev(p['file_name'],p['source_locator'],text)))
    for v in data.items(place['place_id']):
        if v['item']=='실내공간' and v['status']=='있음':
            found.append(dict(kind='실내 공간 포함(전체 코스 실내 아님)',raw=v['value_raw'],
                              source=tools.ev(v['file_name'],v['source_locator'],v['evidence'])))
    return found[:3]


def alternatives(place, req):
    place=place_query.with_address(place)
    si,area=data.region_of(place.get('address'))
    if not (si and area):
        return dict(options=[],message='같은 읍·면·동을 확인할 주소가 없어 실내 대안 조사 불가')
    options=[]
    for p in data.detailed_places():
        p=place_query.with_address(p)
        if p['place_id']==place['place_id'] or data.region_of(p.get('address'))!=(si,area): continue
        proof=evidence(p)
        if not proof: continue
        acc=tools.check_accessibility(p,req)
        if acc['grade'] not in (tools.G_OK,tools.G_COND): continue
        route=tools.check_route(p,req)
        options.append(dict(place=p,grade=acc['grade'],evidence=proof,max_slope=route['max_slope'],
                            slope_group=(2 if route['over_ref'] else 1 if route['max_slope'] is None else 0) if req.user_type in tools.WHEEL else 0))
    options.sort(key=lambda p:(tools.GRADE_ORDER[p['grade']],p['slope_group'],p['place']['name']))
    options=options[:3]
    message=(f"비 예보: 같은 {si} {area}에서 원문에 실내 공간이 명시되고 필수 시설 조건을 충족/조건부 충족하는 대안: "
             +', '.join(f"{o['place']['name']}({o['grade']})" for o in options)
             +'. 장소 성격은 실내 대안으로 변경하며, 경사 측정값·이동 조건은 재확인해야 합니다. 실내 공간을 포함한다는 뜻이며 전체 코스·주차장부터의 이동은 실외일 수 있습니다. 이동 경로·운영·현장 상태 확인 필요.') if options else f'같은 {si} {area}에서 실내 근거와 필수 시설 조건을 갖춘 대안을 데이터에서 찾지 못했습니다(실제 장소가 없다는 뜻 아님).'
    return dict(options=options,message=message)
