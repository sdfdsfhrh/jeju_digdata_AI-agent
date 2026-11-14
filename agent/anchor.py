"""기준 위치 찾기. 공개 위치만 사용하며 주소/거리만으로 업체 좌표를 만들지 않는다."""
import json
import math
import re
from difflib import SequenceMatcher
from urllib.parse import unquote
import requests
from . import cache, config, data, place_query

# 지역 중심을 계산한 값이 아닌 대표 관광지/색인 지점. 출처: 2026-11-07 로컬 허브 원본.
# 중문: 2019/022-1.csv 순서1(주상절리), 애월: 허브 원본 색인 애월한담공원,
# 성산: 2019/050-1.csv 순서1(우도성산항여객터미널), 함덕:2019/038-1.csv 순서1,
# 협재:2019/010-1.csv 순서1, 서귀포시내:2019/021-1.csv 순서1(천지연폭포).
REGIONS={
 '중문':(33.23850291,126.4261621,'주상절리(산책로)','2019/022-1.csv 순서1'),
 '애월':(33.46195313,126.3106147,'애월한담공원','무장애여행정보.csv row 50(허브 원본 색인)'),
 '성산':(33.47272849,126.9342364,'우도성산항여객터미널','2019/050-1.csv 순서1'),
 '함덕':(33.54426065,126.6744194,'함덕서우봉해변','2019/038-1.csv 순서1'),
 '협재':(33.3928886,126.2391044,'협재해수욕장','2019/010-1.csv 순서1'),
 '서귀포시내':(33.24392097,126.5600397,'천지연폭포','2019/021-1.csv 순서1'),
}
# 대표 지역 연결만 허용, 이 좌표를 호텔/일출봉 실좌표로 표시하지 않는다.
# 신라호텔 중문 소재: 공식 호텔 주소 https://www.shillahotels.com/ko/theshilla/jeju/m/introduction/about.do
REGION_ALIASES={'신라호텔':'중문','제주신라호텔':'중문','성산일출봉':'성산','중문관광단지':'중문','서귀포':'서귀포시내'}
URL='https://apis.data.go.kr/B551011/KorService2/searchKeyword2'
VWORLD_URL='https://api.vworld.kr/req/search'
JEJU_BOX=(125.95,33.05,127.05,34.05)


def valid(lat,lon):
    try: return 32<=float(lat)<=35 and 125<=float(lon)<=128
    except (TypeError,ValueError): return False


def km(a,b):
    lat1,lat2=math.radians(float(a['lat'])),math.radians(float(b['lat']))
    h=math.sin((lat2-lat1)/2)**2+math.cos(lat1)*math.cos(lat2)*math.sin(math.radians(float(b['lon'])-float(a['lon']))/2)**2
    return 6371*2*math.asin(min(1,math.sqrt(h)))


def external_valid(lat,lon):
    if not valid(lat,lon):return False
    west,south,east,north=JEJU_BOX
    return west<=float(lon)<=east and south<=float(lat)<=north


def _search(provider,name,api_key,url,params,parse):
    if not api_key:return dict(rows=[],reason=provider+' 키 없음 → 생략')
    key='anchor-search-v3:'+provider+':'+name
    try:
        cached=cache.get(key,max_age_sec=900)
        if cached:return json.loads(cached)
    except (ValueError,TypeError):pass
    try:
        response=requests.get(url,params=params,timeout=4,allow_redirects=False)
        response.raise_for_status()
        rows=parse(response.json())
        rows=[r for r in rows if isinstance(r.get('name'),str) and r['name'] and external_valid(r.get('lat'),r.get('lon'))]
        result=dict(rows=rows,reason=f'{provider} 제주 범위 후보 {len(rows)}건')
        cache.put(key,json.dumps(result,ensure_ascii=False))
        return result
    except (requests.RequestException,ValueError,KeyError,TypeError,AttributeError):
        return dict(rows=[],reason=provider+' 사용 불가 → 생략')


def keyword_search(name):
    api_key=config.KTO_SERVICE_KEY
    def parse(value):
        payload=value['response']
        if str(payload['header']['resultCode']) not in ('00','0000','0'):raise ValueError()
        items=payload['body'].get('items') or {}
        rows=items.get('item',[]) if isinstance(items,dict) else []
        if isinstance(rows,dict):rows=[rows]
        return [dict(name=r.get('title'),lat=r.get('mapy'),lon=r.get('mapx'),contentid=r.get('contentid')) for r in rows]
    return _search('관광공사 국문 관광정보',name,api_key,URL,dict(serviceKey=unquote(api_key or ''),MobileOS='ETC',MobileApp='JejuBarrierFree',_type='json',areaCode=39,keyword=name,numOfRows=30,pageNo=1),parse)


def vworld_search(name):
    api_key=config.get('VWORLD_API_KEY')
    def parse(value):
        payload=value['response']
        if payload['status']=='NOT_FOUND':return []
        if payload['status']!='OK':raise ValueError()
        return [dict(name=re.sub(r'<[^>]*>','',r.get('title') or ''),lat=r['point']['y'],lon=r['point']['x'],contentid=r.get('id')) for r in payload['result']['items']]
    params=dict(service='search',request='search',version='2.0',crs='EPSG:4326',format='json',type='place',query=name,bbox=','.join(map(str,JEJU_BOX)),size=30,key=api_key)
    if config.get('VWORLD_SERVICE_URL'):params['domain']=config.get('VWORLD_SERVICE_URL')
    return _search('브이월드 검색',name,api_key,VWORLD_URL,params,parse)


def choose_external(name,rows):
    def norm(s):
        return place_query.normalized(s).casefold().replace('제주','')
    key=norm(name)
    if not key:return None
    matches=[(SequenceMatcher(None,key,norm(r['name'])).ratio(),r) for r in rows if external_valid(r.get('lat'),r.get('lon'))]
    score,row=max(matches,key=lambda pair:pair[0],default=(0,None))
    return row if score>=0.8 else None


def choose(name,rows):
    key=place_query.normalized(name)
    def names(row):
        return [place_query.normalized(row['name']),place_query.normalized(re.sub(r'\([^)]*\)|\[[^]]*\]','',row['name']))]
    exact=[r for r in rows if key in names(r) and valid(r.get('lat'),r.get('lon'))]
    if exact:
        exact.sort(key=lambda r:r.get('detail_level')!='상세파일있음')
        if any(km(exact[0],r)>0.5 for r in exact[1:]):return None
        return exact[0]
    scored=sorted([(max(SequenceMatcher(None,key,n).ratio() for n in names(r)),r) for r in rows if valid(r.get('lat'),r.get('lon'))],key=lambda x:x[0],reverse=True)
    if len(key)>=4 and scored and scored[0][0]>=0.9 and (len(scored)<2 or scored[0][0]-scored[1][0]>=0.07): return scored[0][1]
    return None


def resolve(name,tr):
    rows=data.all_places()
    match=choose(name,rows)
    tr.note('anchor_db','기준 위치 찾기 → DB 장소명·보수적 유사도와 좌표 확인',match['name'] if match else '일치·유일한 유사 좌표 없음 → 주변 CSV 조사')
    if match:
        return dict(name=name,matched_name=match['name'],lat=float(match['lat']),lon=float(match['lon']),source='우리 DB '+(match.get('coord_source') or ''),
                    evidence=data.place_evidence(match['place_id']),approximate=True,place_id=match['place_id'])
    nearby=data.nearby_anchor_locations();match=choose(name,nearby)
    tr.note('anchor_nearby_csv','DB 위치 없음 → 주변정보 CSV 이름·실제 좌표 열 확인',match['name'] if match else f'이름·실제좌표 일치 없음(좌표 보유 후보 {len(nearby)}건) → 주차장 이름·좌표 조사')
    if match:
        return dict(name=name,matched_name=match['name'],lat=match['lat'],lon=match['lon'],source='주변정보 CSV '+match['source'],evidence=[match],approximate=True)
    parking=data.parking_anchor_locations();match=choose(name,parking)
    tr.note('anchor_parking_lot','주변정보 CSV 위치 없음 → parking_lot 이름·기존 유사도 기준·실제 좌표 확인',match['name'] if match else f'유일한 일치 좌표 없음(후보 {len(parking)}건) → 브이월드 위치 검색')
    if match:
        return dict(name=name,matched_name=match['name'],lat=float(match['lat']),lon=float(match['lon']),source='주차장 CSV '+match['source_file'],evidence=[match],approximate=True)
    for tool,search,source in [('anchor_vworld',vworld_search,'브이월드 검색'),('anchor_kto',keyword_search,'한국관광공사 searchKeyword2')]:
        api=search(name);match=choose_external(name,api['rows'])
        tr.note(tool,'앞 단계에서 위치 미확인 → 제주 장소 검색',source+' 일치' if match else api['reason'])
        if match:
            return dict(name=name,matched_name=match['name'],lat=float(match['lat']),lon=float(match['lon']),source=source,evidence=[dict(match,source=source)],approximate=True)
    compact=re.sub(r'\s','',name).replace('제주특별자치도','')
    compact=re.sub(r'(읍|면|동)$','',compact)
    region=compact if compact in REGIONS else REGION_ALIASES.get(compact)
    if region:
        lat,lon,landmark,proof=REGIONS[region]
        source=f'지역명 사전: {region} 대표지점 {landmark}({proof}), 지정 장소 실좌표 아님'
        tr.note('anchor_region','상위 위치 출처 실패 → 출처가 있는 지역 대표 좌표로 근사',source)
        return dict(name=name,matched_name=landmark,lat=lat,lon=lon,source=source,evidence=[proof],approximate=True,region=region)
    tr.note('anchor_region','상위 출처 실패 → 지역명 사전 최종 확인','대응 지역 없음 → 임의 위치를 만들지 않고 종료')
    return None


def missing_judgment_target(text):
    m=re.match(r'^(.+?)\s*(?:수동\s*휠체어|전동\s*휠체어|휠체어|유아차|유모차).*(?:갈\s*수|가능|접근)',text)
    name=m.group(1).strip() if m else text.strip().rstrip('?!？ ')
    # 장소명만 입력해도 일반 지역 추천으로 바꾸지 않는다. 활동·조건 문장은 제외.
    if not m and (len(name)>30 or re.search(r'근처|주변|추천|산책|필수|있는|갈\s*만|가고|싶|필요',name)):
        return None
    if m or re.fullmatch(r'[가-힣A-Za-z0-9·& -]{2,30}',name) and not re.search(r'휠체어|유아차|유모차|장애인|화장실|갈 곳|어디|알려|보여|가능|갈 수|안녕',name):
        return name
    return None
