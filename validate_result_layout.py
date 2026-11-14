"""화면 표시·주소 보완·비 예보 날짜 재조회. 시설 등급은 기존 검증과 대조."""
import copy,datetime as dt,json
from pathlib import Path
from unittest.mock import patch
from agent import adaptive,config,core,place_query,visit_assessment
from agent.parser import Request
import map_display as m
import result_view as view
from validate_map_display import sample


def main():
    value=sample(['계단','계단','급경사 오르막','계단'])
    value['route']['points'][1]['lat']=value['route']['points'][0]['lat']+.0001
    model=m.prepare(value)
    assert any(w['count']==2 and len(w['sources'])==2 for w in model['warnings'])
    assert [w['level'] for w in model['warnings']]==sorted((w['level'] for w in model['warnings']),reverse=True)
    assert [w['number'] for w in model['warnings']]==list(range(1,len(model['warnings'])+1))
    assert all('우회 정보 없음' in w['title'] for w in model['warnings'])
    # 이유만 같고 원문이 다른 지점은 합치지 않는다.
    separate=sample(['동굴 계단','정자 계단'])
    separate['route']['points'][1]['lat']=separate['route']['points'][0]['lat']+.0001
    assert len(m.prepare(separate)['warnings'])==2
    with patch.object(config,'KMA_SERVICE_KEY',''),patch.object(config,'KTO_SERVICE_KEY',''):
        named=core.run('한림공원 휠체어로 갈 수 있어?',use_llm=False)
    assert named['goal'].startswith('한림공원 — 수동휠체어 이용 가능 여부 확인')
    top=named['results'][0]
    assert '한림읍' in top['place']['address'] and top['place']['_address_evidence']['evidence'][0]['selected']
    assert all(r.get('use_assessment') for r in named['results'])
    difficult=next(r for r in named['results'] if '정낭' in r['place']['name'])
    assert '확인 필요' in difficult['use_assessment']['text']
    assert any('30' in str(p.get('description'))+str(p.get('label')) for p in difficult['route']['points'])
    before=copy.deepcopy(top);model=m.prepare(top);m.deck(model);assert top==before
    assert [w['color'] for w in model['warnings']]==sorted([w['color'] for w in model['warnings']],key=lambda c:0 if c==m.RED else 1)
    model2=m.prepare(top);assert model['view'].zoom<15 and model['entrance']['label']=='입구'
    assert all('label_offset' in f for f in model['facilities'])
    assert ' (참고)' not in view.facility_text(top)
    assert '장소 전용 여부 미확인' not in view.facility_text(top)
    assert len(view.facts(top))==3 and '이 답에 쓰인 데이터:' in view.copy_text(named)
    now=dt.datetime(2026,11,8,8,tzinfo=dt.timezone(dt.timedelta(hours=9)))
    def forecast(lat,lon,date,hours,address=None):
        n=(dt.datetime.strptime(date,'%Y%m%d').date()-now.date()).days
        return dict(status='조회됨',pop_max=5 if n==6 else 10 if n==4 else 60,forecast_type='단기' if n<=3 else '중기',precision='모의')
    with patch.object(config,'KMA_SERVICE_KEY','mock'),patch.object(adaptive.weather,'now_kst',return_value=now),patch.object(adaptive.weather,'forecast',side_effect=forecast) as get:
        days=adaptive.recommend_rain_days(top['place'],Request(date='20261109',time_slot='오후'))
        assert get.call_count==11 and days['choices'][0]['date']=='2026-11-14' and days['choices'][1]['date']=='2026-11-12'
        assert all(r['date']!='2026-11-09' for r in days['choices'])
        assert '강수 5%' in days['message']
    with patch.object(config,'KMA_SERVICE_KEY','mock'),patch.object(adaptive.weather,'now_kst',return_value=now),patch.object(adaptive.weather,'forecast',return_value=dict(status='미확인',reason='자료없음')):
        assert '자료가 없습니다' in adaptive.recommend_rain_days(top['place'],Request())['reason']
    req=Request(date='20261109',time_slot='오후',user_type='수동휠체어',needs=['장애인화장실'])
    wet=dict(status='조회됨',sky='비',pop_max=60,cautions=['실외 주의'],precip=['비'])
    with patch.object(config,'KMA_SERVICE_KEY','mock'),patch.object(config,'KTO_SERVICE_KEY',''),patch.object(adaptive.tools,'check_weather',return_value=wet),patch.object(adaptive,'recommend_rain_days',return_value=days):
        rain=core.run('한림공원 휠체어 내일 오후',use_llm=False)
        assert any(s['tool']=='recommend_rain_days' and '날씨 나쁨 → 다른 날짜 자동 조회' in s['purpose'] for s in rain['trace'])
        assert rain['day_recommendation']['choices']
    print('PASS: 중복30m/다른원문분리/빨강우선/번호·색/주소근거/계단30/요약·시설중복/10일최저2일/trace')

if __name__=='__main__':main()
