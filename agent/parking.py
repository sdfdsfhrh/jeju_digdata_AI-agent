"""일반/장애인 주차를 분리하고 외부 주차장 보완은 별도 근거로 표시한다."""
import json
import re
from . import data
from .anchor import km,valid


def nearby(place,radius_km=.5,limit=2,disabled_only=False):
    if not valid(place.get('lat'),place.get('lon')):return []
    options=[]
    for r in data.parking_rows(place['lat'],place['lon'],radius_km):
        if disabled_only and r['disabled_status']!='있음':continue
        distance=km(place,r)
        if radius_km is not None and distance>radius_km:continue
        fees=json.loads(r.get('fees_json') or '{}')
        fee_summary=r.get('fee_info') or '요금 미확인'
        if fee_summary!='무료':
            for t,amount,label in [('주차기본시간','주차기본요금','기본'),('추가단위시간','추가단위요금','추가')]:
                if fees.get(amount):fee_summary+=f" · {label} {fees.get(t) or '시간 미확인'}분 {fees[amount]}원"
        view=dict(r,fee_summary=fee_summary,distance_km=distance,distance_m=round(distance*1000),
                  evidence=f"{r['source_file']} [{r['source_locator']}] {r['name']}; 障害人区画={r['disabled_raw'] or '공란'}; 기준일 {r['base_date']}".replace('障害人区画','장애인전용구역'))
        options.append(view)
    return sorted(options,key=lambda r:(r['distance_km'],r['name'],r['parking_lot_id']))[:limit]


def own_general(place):
    proofs=[]
    for r in data.items(place['place_id']):
        # 장애인전용 부재만으로 일반 주차장 존재를 추론하지 않는다.
        if '장애인' in r['item'] or '대체' in r['item']:continue
        raw=str(r.get('value_raw') or '')
        if raw.strip() in ('','-','미확인') or r.get('status')=='없음':continue
        if '주차' in r['item']:raw=r['item']+' '+raw
        proofs.append((raw,f"{r.get('file_name')} [{r.get('source_locator')}]"))
    for r in data.points(place['place_id']):
        raw=' '.join(str(r.get(k) or '') for k in ('label','description','detail_raw'))
        proofs.append((raw,f"{r.get('file_name')} [{r.get('source_locator')}]"))
    if place.get('overview'):proofs.append((place['overview'],' / '.join(str(e) for e in data.place_evidence(place['place_id']))))
    for raw,source in proofs:
        if not re.search(r'주차',raw):continue
        if re.search(r'주변|인근|근처|대체|주차\s*(?:공간|장|구역)?\s*(?:할|를)?\s*(?:수)?\s*(?:은|는|이|가)?\s*(?:없|불가|미설치)|주차.*(?<!\d)0\s*(?:대|면)',raw):continue
        if re.search(r'주차',re.sub(r'장애인\s*(?:전용)?\s*주차(?:장|구역|면수)?[^/\n]*','',raw)):
            dates={r.get('base_date') for r in data.source_files(place['place_id']) if r['file_name'] in source and r.get('base_date')}
            return dict(raw=raw,evidence=source+' “'+raw+'”',base_date=next(iter(dates)) if len(dates)==1 else None)
    return None


def assess(place,disabled):
    original=disabled.get('status','미확인')
    external=nearby(place)
    disabled_near=nearby(place,disabled_only=True) if original=='미확인' else []
    evidence=own_general(place)
    general=dict(item='일반주차',condition_key='parking_general',status='미확인',effective='미확인',display='미확인',raw=None,evidence=None,source=None,base_date=None,verify='규칙 판정',reason='원문·근처 주차 근거 미확인',options=[])
    if evidence:
        general.update(status='있음',effective='있음',display='있음',raw=evidence['raw'],evidence=evidence['evidence'],source='장소 원문',base_date=evidence['base_date'],reason='장소 자체 주차 언급')
    elif original=='있음':
        general.update(status='있음',effective='있음',display='있음(장애인 주차구역 근거)',raw=disabled.get('raw'),evidence=disabled.get('evidence'),source=disabled.get('source'),base_date=disabled.get('base_date'),reason='장소 장애인 주차 있음 → 일반 주차 존재 근거')
    elif external:
        descriptions=[f"{r['name']} {r['distance_m']}m · {r['spaces'] if r['spaces'] is not None else '미확인'}면 · {r['fee_summary']}" for r in external]
        general.update(status='조건부',effective='조건부',display='근처 있음('+ ' / '.join(descriptions)+')',raw=' / '.join(descriptions),evidence=' / '.join(r['evidence'] for r in external),
                       source='공공데이터포털 주차장 보조 자료',reason='500m 이내 외부 주차장(장소 전용·이동 경로 미검증)',options=external,
                       base_date=' / '.join(sorted({r['base_date'] for r in external})))
    supplement=('근처 장애인 주차 있음('+ ' / '.join(f"{r['name']}, {r['distance_m']}m" for r in disabled_near)+')') if disabled_near else None
    return dict(general=general,disabled=dict(original_status=original,effective='조건부' if disabled_near else original,supplement=supplement,options=disabled_near),nearby=external,
                limits=['근처 주차장은 장소 전용이 아닐 수 있습니다. 500m는 직선거리이며 실제 이동 경로·빈자리·현재 요금/운영은 확인 필요.',
                        '장애인전용구역 N은 해당 외부 주차장 기준이며 장소의 장애인 주차 상태를 바꾸지 않습니다. 공란도 없음이 아닙니다.'])


DISABLED_NOTICE='장애인 전용 주차구역은 장애인자동차표지를 부착한 차량만 이용할 수 있어요.'


def display_info(access):
    """판정은 그대로 두고 두 줄의 표시·참고 여부만 정리한다."""
    park=access.get('parking') or {}
    requested={n.get('condition_key') or n.get('item') for n in access.get('needs',[])}
    general_requested='parking_general' in requested
    disabled_requested=bool(requested & {'parking_disabled','장애인주차장'})
    original=(park.get('disabled') or {}).get('original_status')
    if original is None:
        original=next((r['status'] for r in access.get('table',[]) if r['item']=='장애인주차장'),'미확인')
    supplement=(park.get('disabled') or {}).get('supplement')
    general=(park.get('general') or {}).get('display','미확인')
    disabled=original+((' · '+supplement) if supplement else '')
    return dict(lines=[dict(text='일반 주차: '+general,reference=not general_requested),dict(text='장애인 주차: '+disabled,reference=not disabled_requested)],notice=DISABLED_NOTICE if disabled_requested or original=='있음' or supplement else None)
