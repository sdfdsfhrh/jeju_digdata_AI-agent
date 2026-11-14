"""질문 속 DB 장소명 우선 조회. 비슷하다는 이유만으로 다른 장소로 연결하지 않는다."""
import re
import math
from . import data


def normalized(text):
    return re.sub(r"[\s·~()（）,]", "", text).replace("제주특별자치도", "").replace("제주", "")


def lookup(text):
    query = normalized(text)
    matches = []
    for p in data.all_places():
        name = normalized(p["name"])
        # 괄호 안 설명은 별칭에서만 제외한다. 모호한 부분문자열 근사 매칭은 하지 않는다.
        alias = normalized(re.sub(r"\([^)]*\)|\[[^]]*\]", "", p["name"]))
        if any(len(n) >= 2 and n in query for n in (name, alias)):
            p['location_evidence'] = data.place_evidence(p['place_id'])
            matches.append(p)
    if matches:
        matches.sort(key=lambda p: (-len(normalized(p['name'])), p['name'], p['place_id']))
        groups=[]
        for key in dict.fromkeys(normalized(p['name']) for p in matches):
            same=[p for p in matches if normalized(p['name'])==key]
            detailed=sum(p['detail_level']=='상세파일있음' for p in same)
            groups.append(dict(name=same[0]['name'],detailed=detailed,indexed=len(same)-detailed,place_ids=[p['place_id'] for p in same]))
        return dict(matches=matches,groups=groups,message="질문에 DB 장소명 일치: " + ', '.join(
            f"{g['name']}(상세 {g['detailed']}, 목록 {g['indexed']})" for g in groups))
    return dict(matches=[], message="질문과 일치하는 DB 장소명이 없어 일반 조건 검색으로 안내합니다.")


def classify(place):
    """관광공사 유형 코드 우선, 허브는 본 장소명에 명시된 유형어만 사용."""
    codes={'12':('관광지','관광지'), '14':('관광지','문화시설'), '15':('관광지','축제·공연'),
           '25':('관광지','여행코스'), '28':('관광지','레포츠'), '32':('편의','숙박'),
           '38':('편의','쇼핑'), '39':('편의','음식점·카페')}
    rows=data.place_types(place['place_id'])
    known=[r for r in rows if r['contenttypeid'] in codes]
    if known:
        groups={codes[r['contenttypeid']][0] for r in known}
        if len(groups)==1:
            r=known[0];group,label=codes[r['contenttypeid']]
            return dict(group=group,label=label,evidence=[f"kto_list.csv [contentid={r['kto_id']}; contenttypeid={r['contenttypeid']}] {label}"])
        return dict(group='미확인',label='유형 출처 충돌',evidence=[str(r) for r in known])
    if not any('kto_' not in p['file_name'] for p in data.place_evidence(place['place_id'])):
        return dict(group='미확인',label='유형 미확인',evidence=[])
    name=place['name']
    for group,label,words in [('편의','음식점·카페',('음식점','식당','카페')),('편의','숙박',('호텔','펜션','리조트','숙박')),
        ('관광지','관광지·코스',('공원','박물관','폭포','해수욕장','해변','산책로','마을','밭담길','해안길','코스','휴양림','전시관','습지','숲길','문화거리','오름','민속'))]:
        if any(w in name for w in words):
            return dict(group=group,label=label,evidence=[f"허브 원문 장소명 ‘{name}’의 유형어",*data.place_evidence(place['place_id'])])
    return dict(group='미확인',label='유형 미확인',evidence=[])


def nearby_candidates(anchor, limit=5):
    def valid(p):
        try: return -90<=float(p['lat'])<=90 and -180<=float(p['lon'])<=180
        except (KeyError,TypeError,ValueError): return False
    if not valid(anchor):
        return dict(candidates=[],reason='지정 장소 좌표 미확인 → 거리 대안 생략')
    rows=[]
    for value in data.detailed_places():
        if value['place_id']==anchor['place_id'] or not valid(value): continue
        a,b=math.radians(float(anchor['lat'])),math.radians(float(value['lat']))
        dlat=b-a;dlon=math.radians(float(value['lon'])-float(anchor['lon']))
        h=math.sin(dlat/2)**2+math.cos(a)*math.cos(b)*math.sin(dlon/2)**2
        km=6371*2*math.asin(min(1,math.sqrt(h)))
        p=dict(value);p['_distance_km']=km
        p['_distance_source']=f"기준: {anchor.get('coord_source') or '좌표 출처 미확인'} / 후보: {p.get('coord_source') or '좌표 출처 미확인'}"
        rows.append(p)
    anchor_type=classify(anchor)
    for p in rows: p['_place_type']=classify(p)
    rows.sort(key=lambda p:(p['_distance_km'],p['name']))
    if anchor_type['group']=='관광지':
        tourism=[p for p in rows if p['_place_type']['group']=='관광지'][:limit]
        unknown=[p for p in rows if p['_place_type']['group']=='미확인'][:max(0,limit-len(tourism))]
        convenience=[p for p in rows if p['_place_type']['group']=='편의'][:3]
        for p in unknown: p['_alternative_group_priority']=1
        selected=tourism+unknown+convenience
        reason=f'관광지 질문 → 관광지 주변 대안 {len(tourism)}곳 우선, 유형 미확인 {len(unknown)}곳, 근처 식사·편의 장소 {len(convenience)}곳 별도. 각 분류 안에서 직선거리 후보 선정 후 등급·경사·거리 순(이동 경로 미검증)'
        for p in convenience: p['_separate_convenience']=True
    else:
        selected=rows[:limit]
        reason=f'지정 장소 기준 직선거리 가까운 {len(selected)}곳 선정 → 시설 등급·같은 등급 경사·거리 순(이동 경로 미검증)'
    for p in selected:
        p['_distance_evidence'] = [dict(name=x['name'],lat=x['lat'],lon=x['lon'],
            coord_source=x.get('coord_source'),sources=data.place_evidence(x['place_id'])) for x in (anchor,p)]
    return dict(candidates=selected,reason=reason)




def local_alternatives(place):
    si, emd = data.region_of(place.get('address'))
    if not emd:
        return [], '주소에서 읍·면·동을 확인할 수 없어 같은 지역 대안 연결 불가'
    candidates = [dict(p) for p in data.detailed_places()
                  if data.region_of(p.get('address')) == (si, emd)]
    return candidates, f"같은 {si or ''} {emd}의 상세 장소 {len(candidates)}곳 (거리·접근 경로 검증 아님)"


def resolve_address(place):
    """표시·지역 대안용 주소 보완. 동명 기록을 시설 판정 출처로 합치지 않는다."""
    if place.get('address'):
        return dict(address=place['address'],evidence=[dict(source='장소 주소',address=place['address'],rows=data.place_evidence(place['place_id']))],reason='장소 자체 주소')
    candidates=data._q("""SELECT l.raw_address address,s.file_name,l.source_locator FROM place_source_link l
        LEFT JOIN source_file s USING(source_file_id) WHERE l.place_id=? AND l.raw_address IS NOT NULL AND l.raw_address!=''""",(place['place_id'],))
    for row in data._q("SELECT addr address,'kto_list.csv' file_name,'contentid='||kto_id source_locator FROM kto_place WHERE matched_place_id=? AND addr IS NOT NULL AND addr!=''",(place['place_id'],)):
        candidates.append(row)
    same=[x for x in data.all_places() if normalized(x['name'])==normalized(place['name']) and x.get('address')]
    for x in same:
        candidates.append(dict(address=x['address'],place_id=x['place_id'],file_name='동명 색인 기록',source_locator=str(data.place_evidence(x['place_id'])),lat=x.get('lat'),lon=x.get('lon')))
    if not candidates:return dict(address=None,evidence=[],reason='원본·연결 기록·동명 색인에 주소 없음')
    def distance(row):
        try:
            return (float(row['lat'])-float(place['lat']))**2+(float(row['lon'])-float(place['lon']))**2
        except (KeyError,TypeError,ValueError):return float('inf')
    candidates.sort(key=lambda x:(distance(x),x.get('source_locator',''),x['address']))
    chosen=candidates[0]
    return dict(address=chosen['address'],evidence=[dict(chosen,selected=True),*[dict(x,selected=False) for x in candidates[1:]]],reason='보유 주소 중 대표 좌표에 가까운 동명 기록 우선(장소 연결 확정 아님)')


def with_address(place):
    out=dict(place)
    proof=resolve_address(out)
    out['address']=proof['address'];out['_address_evidence']=proof
    return out
