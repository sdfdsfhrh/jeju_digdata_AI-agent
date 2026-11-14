"""외부 통신 없이 단기·중기 원형 JSON 응답과 장소명 분기를 검증한다."""
import datetime as dt
import json
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import Mock, patch

from agent import adaptive, config, core, data, place_query, weather
from agent.parser import Request


NOW = dt.datetime(2026, 11, 6, 19, tzinfo=weather.KST)


def response(url, **kwargs):
    if 'getVilageFcst' in url:
        items = []
        for day in range(4):
            date = (NOW.date() + dt.timedelta(days=day)).strftime('%Y%m%d')
            for hour in (10, 13):
                for category, value in dict(POP=50-day*5, WSD=2, PTY=0, SKY=3, TMP=18).items():
                    items.append(dict(fcstDate=date, fcstTime=f'{hour:02d}00', category=category, fcstValue=str(value)))
    elif 'getMidLandFcst' in url:
        row = dict(regId=weather.MID_LAND_REG)
        for day in range(4, 11):
            if day <= 7:
                row.update({f'rnSt{day}Am': 10, f'rnSt{day}Pm': 30, f'wf{day}Am': '구름많음', f'wf{day}Pm': '흐리고 비'})
            else:
                row.update({f'rnSt{day}': 40, f'wf{day}': '흐림'})
        items = [row]
    else:
        items = [{**{f'taMin{day}': 10 for day in range(4, 11)},
                  **{f'taMax{day}': 18 for day in range(4, 11)}}]
    return Mock(json=lambda: dict(response=dict(header=dict(resultCode='00'), body=dict(items=dict(item=items)))), text='')


def main():
    checks = []
    with ExitStack() as stack:
        stack.enter_context(patch.object(config, 'KMA_SERVICE_KEY', 'local-test'))
        stack.enter_context(patch.object(weather, 'now_kst', return_value=NOW))
        stack.enter_context(patch.object(weather.cache, 'get', return_value=None))
        stack.enter_context(patch.object(weather.cache, 'put'))
        stack.enter_context(patch.object(weather.cache, 'blocked', return_value=None))
        stack.enter_context(patch.object(weather.cache, 'block'))
        get = stack.enter_context(patch.object(weather.requests, 'get', side_effect=response))
        for day in (0, 3):
            date = (NOW.date() + dt.timedelta(days=day)).strftime('%Y%m%d')
            with patch.object(weather, 'now_kst', return_value=NOW.replace(hour=9) if day == 0 else NOW):
                w = weather.forecast(33.4,126.5,date)
            assert w['forecast_type'] == '단기' and w['wind_max'] == 2
        checks.append('0일·3일 단기 시간별 응답 해석')
        am = weather.forecast(33.4,126.5,'20261110',hours=(9,10),address='서귀포시')
        pm = weather.forecast(33.4,126.5,'20261110',hours=(13,14),address='제주시')
        assert am['pop_max'] == 10 and pm['pop_max'] == 30
        assert am['temp_reg_id'] == '11G00401' and pm['temp_reg_id'] == '11G00201'
        assert am['forecast_type'] == '중기' and am['wind_max'] is None
        assert am['temp_range'] == (10,18) and am['base'] == '202611061800 발표'
        checks.append('4일 중기 오전/오후 구분·기온·제주/서귀포 구역·18시 발표')
        for day in (8,10):
            date = (NOW.date() + dt.timedelta(days=day)).strftime('%Y%m%d')
            w = weather.forecast(33.4,126.5,date,hours=(9,10))
            assert w['pop_max'] == 40 and '하루' in w['precision']
        checks.append('8일·10일 중기 하루 단위·풍속 미제공')
        count = get.call_count
        assert '예보 범위 밖' in weather.forecast(33.4,126.5,'20261117')['reason']
        assert get.call_count == count
        checks.append('10일 초과 → API 호출 없이 미확인')
        denied = Mock(json=lambda: dict(response=dict(header=dict(resultCode='30'))), text='')
        with patch.object(weather.requests,'get',return_value=denied):
            assert '중기예보 활용신청 필요' in weather.forecast(33.4,126.5,'20261110')['reason']
        checks.append('중기 미신청 오류 안내')
        assert weather._mid_base(NOW.replace(hour=9)) == '202611060600'
        assert weather._mid_base(NOW.replace(hour=3)) == '202611051800'
        checks.append('06시/18시 최근 발표 및 새벽 전날 발표')
        p = data.detailed_places()[0]
        req = Request(text='언제 가기 좋은 날',time_slot='오전')
        advice = adaptive.recommend_day(p,req)
        assert advice['status'] == '추천' and len(advice['rows']) == 7
        assert advice['best']['pop'] == 10 and '보장하지' in advice['message']
        checks.append('7일 강수확률 표·최저 확률 날짜 추천')
        res = core.run('행원리 풍차마을 언제 휠체어로 갈까', use_llm=False)
        assert '행원리' in res['results'][0]['place']['name']
        assert res['day_recommendation']['status'] == '추천'
        assert all(s['ok'] for s in res['trace'])
        with patch.object(weather.requests,'get', side_effect=RuntimeError('모의 연결 실패')):
            advice = adaptive.recommend_day(p,req)
            assert advice['status'] == '미확인'
        checks.append('날짜 추천 전체 조회 실패 시 추천 생략')
    assert place_query.lookup('제주 행원리풍차마을 화장실 있어?')['matches']
    r = core.run('행원리 풍차마을 화장실 있어?',use_llm=False)
    assert r['results'][0]['requested_place']
    r = core.run('항공우주박물관 휠체어 가능?',use_llm=False)
    assert r['named_places'] and '판정 불가' in r['summary']
    nearby_ids = {p['place_id'] for p in place_query.nearby_candidates(r['named_places'][0])['candidates']}
    assert all(x['place']['place_id'] in nearby_ids and '_distance_km' in x['place'] for x in r['results'])
    r = core.run('한라산 유모차 가능?',use_llm=False)
    assert not r['named_places'] and r['judgment_missing'] and r['summary'].startswith('한라산은 영유아동반 이용 여부를 판단할 조사 자료가 없어요.')
    assert any('경사 측정값 없음(안전 확인 아님)' in x['rank_reason'] for x in core.run('수동휠체어',use_llm=False)['results'])
    checks.append('상세 장소 우선·색인 장소 위치/좌표 거리 대안·DB 미등록·경사 미측정 안내')
    out = Path(__file__).parent / 'output' / 'validation'
    out.mkdir(exist_ok=True,parents=True)
    (out/'weather_place_checks.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2),encoding='utf-8')
    print('\n'.join('통과: '+c for c in checks))


if __name__ == '__main__':
    with patch.object(config,'KMA_SERVICE_KEY',''):
        main()
