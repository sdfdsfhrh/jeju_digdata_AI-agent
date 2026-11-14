"""조사 자료 없는 장소를 다른 장소의 판정으로 오인하지 않도록 검증."""
import json
from unittest.mock import patch
from agent import core, config, missing_place, place_query
from agent.parser import Request
import leaflet_map

def main():
    with patch.dict(config._FILE_API_KEYS, {"VWORLD_API_KEY": ""}),patch.object(config,'KMA_SERVICE_KEY',''),patch.object(config,'KTO_SERVICE_KEY',''):
        runs=[core.run(q,use_llm=False) for q in ['성산일출봉','성산일출봉 휠체어로 갈 수 있어?','한라산 휠체어로 갈 수 있어?','한림공원 휠체어로 갈 수 있어?']]
        for res in runs[:3]:
            ctx=res['missing_place']
            assert res['summary'].startswith(ctx['message'])
            assert not any(r.get('requested_place') for r in res['results'])
            assert all(s['ok'] for s in res['trace'])
        for res in runs[:2]:
            ctx=res['missing_place']
            assert res['results'] and ctx['alternatives_heading'] in res['summary']
            assert all(missing_place.distance(ctx,r) in res['summary'] for r in res['results'])
            payload=leaflet_map.payload(res['results'],queried_target=ctx['location'])
            assert payload['queried_target']['name']=='성산일출봉'
            assert len(payload['places'])==len(res['results'])
            assert config.get('VWORLD_API_KEY') not in json.dumps(payload) if config.get('VWORLD_API_KEY') else True
        assert not runs[2]['results'] and runs[2]['missing_place']['location'] is None
        with patch.object(core.anchored.anchor,'resolve',return_value=None):
            absent=core.run('모의호텔 휠체어로 갈 수 있어?',use_llm=False)
            assert not absent['results'] and '위치를 찾지 못했습니다' in absent['summary']
        assert not runs[3]['judgment_missing'] and runs[3]['results'][0]['requested_place']
        assert runs[3]['results'][0]['place']['name']=='한림공원'
        # 색인 전용 기록도 별도 맥락을 전달한다. 등급·시설 판정은 기존 경로 그대로.
        indexed=next(p for p in core.data.all_places() if p['detail_level']!='상세파일있음' and
                     not any(x['detail_level']=='상세파일있음' for x in place_query.lookup(p['name'])['matches']))
        res=core.run(indexed['name']+' 휠체어로 갈 수 있어?',use_llm=False)
        assert res['missing_place'] and res['summary'].startswith(res['missing_place']['message'])
    req=Request(text='성산일출봉 휠체어로 갈 수 있어?',user_type='수동휠체어')
    ctx=runs[1]['missing_place'];results=runs[1]['results']
    with patch.object(config,'llm_enabled',return_value=True),patch.object(core.llm,'ask',return_value='1위는 빛의 벙커입니다.') as ask:
        text,_=core.explain(req,'목표',results,[],missing_context=ctx)
        assert text.startswith(ctx['message']) and '1위는' not in text
        sent=json.loads(ask.call_args.args[1]);assert sent['missing_place']['name']=='성산일출봉'
        assert sent['missing_place']['instruction'] and sent['top'][0]['distance_km'] is not None
    with patch.object(config,'llm_enabled',return_value=True),patch.object(core.llm,'ask',return_value=missing_place.introduction(ctx)):
        text,how=core.explain(req,'목표',results,[],missing_context=ctx)
        assert how.startswith('LLM 요약') and text.startswith(ctx['message'])
    from pathlib import Path
    from streamlit.testing.v1 import AppTest
    with patch.object(config,'llm_enabled',return_value=False),patch.object(leaflet_map,'show') as draw:
        at=AppTest.from_file(str(Path('app.py').resolve()),default_timeout=30).run()
        at.session_state['conversation']=[dict(question=req.text,result=runs[1])];at.run()
        assert not at.exception
        texts=[x.value for x in at.markdown]
        first=next(i for i,v in enumerate(texts) if ctx['message'] in v)
        heading=next(i for i,v in enumerate(texts) if ctx['alternatives_heading'] in v)
        card=next(i for i,v in enumerate(texts) if 'place-card' in v and '성산일출봉에서 약' in v)
        assert first<heading<card
        assert draw.call_args.kwargs['queried_target']['name']=='성산일출봉'
    print('PASS: 장소명 단독·자료없음 3질문·색인 전용·LLM 전달/순서 검증·대안 거리·질문 위치 지도·한림공원 유지')

if __name__=='__main__':main()
