"""기준 위치+동행자+활동 흐름 회귀 검증. 외부 API는 모의 응답만 사용한다."""
import datetime as dt
import json
from pathlib import Path
from unittest.mock import Mock,patch
import requests
from agent import anchor,anchored,config,core,data,indoor,parser,place_query

QUERIES=[
 '제주 신라호텔 근처에 ６０대 어머니 모시고 산책할 만한 곳 추천해줘',
 '중문 근처 부모님이랑 걷기 좋은 곳',
 '성산일출봉 주변 유아차로 산책할 곳 내일 오후',
 '애월 근처 비 오면 갈 만한 실내',
 '없는장소123 근처 산책',
 '한림공원 휠체어로 갈 수 있어?',
]


def main():
    out=Path('output/validation/anchor');out.mkdir(exist_ok=True,parents=True)
    with patch.dict(config._FILE_API_KEYS, {"VWORLD_API_KEY": ""}),patch.object(config,'KTO_SERVICE_KEY',''),patch.object(config,'KMA_SERVICE_KEY',''):
        runs=[core.run(q,use_llm=False) for q in QUERIES]
        missing=core.run('신라호텔 휠체어로 갈 수 있어?',use_llm=False)
    assert all(s['ok'] for r in runs for s in r['trace'])
    first=runs[0]
    assert '６０' not in first['request']['text'] and '60대' in first['request']['text']
    assert first['request']['anchor']=='제주 신라호텔' and first['request']['companion']=='senior' and first['request']['activity']=='walk'
    assert 3<=len(first['results'])<=5 and all(place_query.classify(r['place'])['group']!='편의' for r in first['results'])
    assert '지정 장소 실좌표 아님' in first['anchor']['source']
    assert [r['rank'] for r in first['results']]==list(range(1,len(first['results'])+1))
    assert first['results']==sorted(first['results'],key=anchored.senior_key)
    for r in first['results']:
        assert r['use_assessment']['evidence']
        assert r['grade']==r['access']['grade']
        assert r['place']['_distance_km']<=first['anchor_radius_km']
    import io
    from contextlib import redirect_stdout
    from cli import show
    with redirect_stdout(io.StringIO()) as rendered: show(first)
    assert '기준 위치:' in rendered.getvalue() and '거리 근거:' in rendered.getvalue()
    assert anchored.SENIOR_LIMIT in first['summary']
    assert all(any(s['tool']==tool for s in first['trace']) for tool in ('resolve_anchor','filter_anchor_distance','rank_walking_conditions','check_weather'))
    assert runs[1]['anchor']['region']=='중문'
    assert runs[2]['request']['user_type']=='영유아동반' and runs[2]['request']['date']==(parser._today()+dt.timedelta(days=1)).strftime('%Y%m%d')
    assert runs[2]['request']['time_slot']=='오후' and runs[2]['request']['anchor']=='성산일출봉'
    assert runs[3]['request']['activity']=='indoor'
    assert all(indoor.evidence(r['place']) for r in runs[3]['results'])
    assert not runs[4]['results'] and "'없는장소123'의 위치를 찾지 못했습니다" in runs[4]['summary']
    assert runs[5]['results'][0]['requested_place'] and 'anchor' not in runs[5]
    # 2026-11-07 변경 전 고정 DB(221곳)의 한림공원 질문 결과. output 스냅샷 배포 불필요.
    baseline={'results': [('JBF-4998b8c1', '조건 충족'), ('JBF-882a33d7', '조건 충족'), ('JBF-bcb8a016', '조건 충족'), ('JBF-3f1b231c', '조건 충족'), ('JBF-2923ca6a', '조건 충족'), ('JBF-10951b7b', '조건 충족')], 'convenience_results': [('KTO-2853621', '조건 충족'), ('KTO-2871986', '조건 충족'), ('JBF-efbfbba4', '조건 충족')]}
    for key in ('results','convenience_results'):
        assert [(r['place']['place_id'],r['grade']) for r in runs[5][key]]==baseline[key]
    assert runs[5]['results'][0]['use_assessment']['text']=='휠체어 이용: 가능(일부 구간 주의) — 경사 참고 기준 초과 10개 측정값(최대 11°), 계단길·휠체어길 분리 지점 있음, 장애인 화장실 있음, 장애인 주차 있음'
    assert '판정 데이터가 없습니다' in missing['summary'] and missing['results']
    checked=parser.validate(dict(anchor='허위 장소',companion='other',activity='other'),QUERIES[0],[])
    assert checked.anchor=='제주 신라호텔' and checked.companion=='senior' and checked.activity=='walk'
    with patch.object(parser.llm,'ask_json',return_value=dict(anchor='제주 신라호텔',companion='senior',activity='walk',user_type='시니어',needs=[])):
        parsed,_=parser.parse(QUERIES[0],[],use_llm=True)
        assert parsed.anchor=='제주 신라호텔' and parsed.companion=='senior' and parsed.activity=='walk'
    # 조회 순서: DB가 맞으면 뒤 단계 호출 없음, CSV 실제 좌표, API, 지역대표, 실패.
    point=dict(place_id='mock',name='모의공원',lat=33.4,lon=126.5,detail_level='상세파일있음',coord_source='mock row1')
    with patch.object(data,'all_places',return_value=[point]),patch.object(data,'place_evidence',return_value=[]),patch.object(anchor,'keyword_search') as api:
        assert anchor.resolve('모의 공원',core.Tracer())['place_id']=='mock';api.assert_not_called()
    csv_point=dict(name='모의호텔',lat=33.4,lon=126.5,source='nearby.csv',source_locator='row 2')
    with patch.object(data,'all_places',return_value=[]),patch.object(data,'nearby_anchor_locations',return_value=[csv_point]),patch.object(anchor,'keyword_search') as api:
        assert anchor.resolve('모의호텔',core.Tracer())['source'].startswith('주변정보 CSV');api.assert_not_called()
    with patch.object(data,'all_places',return_value=[]),patch.object(data,'nearby_anchor_locations',return_value=[]),patch.object(anchor,'keyword_search',return_value=dict(rows=[dict(csv_point,contentid='1')],reason='모의 API')):
        assert anchor.resolve('모의호텔',core.Tracer())['source']=='한국관광공사 searchKeyword2'
    reply=Mock(json=lambda:dict(response=dict(header=dict(resultCode='0000'),body=dict(items=dict(item=[dict(title='모의호텔',mapy=33.4,mapx=126.5,contentid='1')])))))
    with patch.object(config,'KTO_SERVICE_KEY','mock-key'),patch.object(anchor.cache,'get',return_value=None),patch.object(anchor.cache,'put'),patch.object(anchor.requests,'get',return_value=reply) as get:
        assert anchor.keyword_search('모의호텔')['rows']
        assert get.call_args.kwargs['params']['areaCode']==39
    with patch.object(config,'KTO_SERVICE_KEY','mock-key'),patch.object(anchor.cache,'get',return_value=None),patch.object(anchor.requests,'get',side_effect=requests.RequestException('SECRET_URL')):
        assert 'SECRET_URL' not in str(anchor.keyword_search('모의호텔'))
    # 반경 5→10→15km 확대를 각각 검사.
    places=[dict(point,place_id=str(i),lat=33.4+delta) for i,delta in enumerate((.02,.07,.12))]
    tr=core.Tracer()
    with patch.object(data,'detailed_places',return_value=places),patch.object(data,'place_evidence',return_value=[]),patch.object(place_query,'classify',return_value=dict(group='관광지',label='공원',evidence=[])):
        pool=anchored.candidate_pool(dict(name='기준',lat=33.4,lon=126.5,source='mock',evidence=[]),parser.Request(activity='walk'),tr)
        assert [r['count'] for r in pool['radii']]==[1,2,3] and pool['radius_km']==15
    # 위험 명시→경사→화장실→휴식→거리의 우선순위와 기존 등급 불변.
    base=first['results'][0]
    def record(risk=False,slope=None,toilet='있음',rest=False,distance=1):
        r=dict(base);r['place']=dict(base['place'],_distance_km=distance)
        r['walking']=dict(risk_evidence=['원문 계단'] if risk else [],rest_evidence=['원문 벤치'] if rest else [])
        r['route']=dict(base['route'],max_slope=slope,over_ref=[{}] if slope and slope>4.76 else [])
        r['access']=dict(base['access'],table=[dict(item='장애인화장실',status=toilet)])
        return r
    assert anchored.senior_key(record(slope=None)) < anchored.senior_key(record(risk=True,slope=1))
    assert anchored.senior_key(record(slope=1,distance=10)) < anchored.senior_key(record(slope=None)) < anchored.senior_key(record(slope=8))
    assert anchored.senior_key(record(toilet='있음')) < anchored.senior_key(record(toilet='조건부')) < anchored.senior_key(record(toilet='미확인'))
    assert anchored.senior_key(record(rest=True,distance=10)) < anchored.senior_key(record(rest=False,distance=1))
    with patch.object(anchored,'own_evidence',return_value=[('계단이 없는 길, 벤치 없음','모의 원문')]):
        negative=anchored.walking_features(point)
        assert not negative['risk_evidence'] and not negative['rest_evidence']
    with patch.object(anchored,'own_evidence',return_value=[('급경사, 그늘과 벤치 있음','모의 원문')]):
        positive=anchored.walking_features(point)
        assert positive['risk_evidence'] and positive['rest_evidence']
    # 날씨/비 분기: 실제 예보 도구는 모의, 실내 대안 함수는 기존 도구 사용 여부 확인.
    wet=dict(status='조회됨',cautions=['비 주의'],pop_max=80,precip=['비'])
    with patch.dict(config._FILE_API_KEYS, {"VWORLD_API_KEY": ""}),patch.object(config,'KTO_SERVICE_KEY',''),patch.object(config,'KMA_SERVICE_KEY','mock'),patch.object(anchored.tools,'check_weather',return_value=wet),patch.object(anchored.indoor,'alternatives',return_value=dict(options=[],message='모의 실내 대안')) as alternatives:
        rainy=core.run('중문 근처 부모님 산책 내일 오후',use_llm=False)
        assert alternatives.called and rainy['results'][0]['indoor_alternative']['activity']=='indoor'
    (out/'cases.json').write_text(json.dumps([dict(question=q,result=r) for q,r in zip(QUERIES,runs)],ensure_ascii=False,indent=2),encoding='utf-8')
    print('PASS: 지정6질문·NFKC/LLM스키마·위치순서/오류비밀보호·반경확대·보행정렬·등급유지·비/실내·한림공원회귀')

if __name__=='__main__': main()
