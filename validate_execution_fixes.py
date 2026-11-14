"""실행 피드백 회귀 검증(외부 호출 없음)."""
import datetime as dt
import io
from contextlib import redirect_stdout
from unittest.mock import patch
from agent import adaptive, config, core, data, tools, weather
from agent.explanation_check import issues
from agent.parser import Request
import cli


def main():
    with patch.object(config, 'KMA_SERVICE_KEY', ''):
        res = core.run('수동휠체어 화장실 바다', use_llm=False)
        from agent import recommendation
        assert [recommendation.key(r) for r in res['results']]==sorted(recommendation.key(r) for r in res['results'])
        # 장소명 질문의 기존 순위 키는 세 경사 범주 순서를 유지.
        base = res['results'][0]
        samples = [dict(base, slope_unknown=False, slope_penalty=True),
                   dict(base, slope_unknown=True, slope_penalty=False),
                   dict(base, slope_unknown=False, slope_penalty=False)]
        assert sorted(samples, key=core._rank_key) == samples[::-1]
        unmeasured = next(p for p in data.detailed_places() if p['place_id'].startswith('KTO-'))
        with patch.object(data, 'detailed_places', return_value=(unmeasured,)):
            unknown = core.run('수동휠체어', use_llm=False)
            assert '경사 정보 없음' in unknown['summary'] and '경사 측정값이 있는 장소' in unknown['summary']
            assert any('주변정보 없음(데이터 미보유)' in s['output'] for s in unknown['trace'] if s['tool']=='find_nearby')
            captured=io.StringIO()
            with redirect_stdout(captured): cli.show(unknown)
            assert '주변정보 없음(데이터 미보유)' in captured.getvalue()
        with patch.object(data, 'nearby', return_value=[]):
            with patch.object(data, 'source_files', return_value=[]):
                missing = tools.find_nearby(unmeasured)
                assert tools.nearby_summary(missing) == '주변정보 없음(데이터 미보유)'
            with patch.object(data, 'source_files', return_value=[{'file_kind':'nearby_2021'}]):
                assert '● 0곳' in tools.nearby_summary(tools.find_nearby(unmeasured))
        payload = core._compact(Request(needs=['장애인화장실']), '', res['results'])
        need = payload['top'][0]['needs'][0]
        assert {'value_raw', 'source', 'evidence', 'all_sources'} <= need.keys()
        assert payload['top'][0]['related_evidence']
        name = payload['top'][0]['name']
        status = need['status']
        assert not issues(f'{name}. 장애인화장실: {status}', payload)
        wrong = '없음' if status != '없음' else '있음'
        assert issues(f'{name}. 장애인화장실: {wrong}', payload)
        outside = next(p['name'] for p in data.all_places() if all(p['name'] not in t['name'] for t in payload['top']))
        assert issues(outside, payload)
        payload['top'][0]['related_location'] = outside
        assert not issues(outside, payload), '원문 위치에 나온 대안 장소는 허용'
        res['day_recommendation'] = {'rows':[dict(date='2026-11-07', pop=None, forecast_type='단기', precision='', reason='') ]}
        out = io.StringIO()
        with redirect_stdout(out): cli.show(res)
        assert '미확인%' not in out.getvalue()
        updates=[]
        progress_res=core.run('내일 수동휠체어', use_llm=False, progress=updates.append)
        assert len(updates)>5 and progress_res['slowest_step']['ms'] == max(s['ms'] for s in progress_res['trace'])
    now = dt.datetime(2026,11,7,12,30,tzinfo=weather.KST)
    assert weather.remaining_hours((10,12,13,16), now) == (13,16)
    req=Request(text='언제', time_slot='오전')
    with patch.object(config,'KMA_SERVICE_KEY','mock'), patch.object(weather,'now_kst',return_value=now), \
         patch.object(weather,'forecast',return_value={'status':'조회됨','pop_max':0}) as call:
        days=adaptive.recommend_day({'name':'모의','lat':33,'lon':126},req)
        assert not days['rows'][0]['eligible'] and days['best']['date']=='2026-11-08'
        assert call.call_count==6
    with patch.object(weather,'now_kst',return_value=now), patch.object(weather,'_short') as short:
        value=weather.forecast(33,126,'20261107',hours=(9,10,11))
        assert value['status']=='미확인' and not short.called
    print('통과: 경사 3단계·미측정 요약·주변정보 미보유/0건·원문/출처·설명 장소명/상태어 대조·미확인 표기·지난 시간 제외·진행 알림/시간')


if __name__=='__main__':
    main()
