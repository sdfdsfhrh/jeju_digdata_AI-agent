"""주차 문맥·두 줄 표시·주차장 기준 위치 및 기존 장소 판정 회귀."""
import io,json
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch
from agent import anchor,config,core,data,parking,parser
from cli import show


def main():
    probes={
      '유아차로 갈 만한 곳 렌트카로 가요':['parking_general'],
      '휠체어로 갈 곳 장애인 주차 필요':['parking_disabled'],
      '휠체어로 주차 필요한 곳':['parking_disabled'],
      '부모님이랑 차 가져가서 걷기 좋은 곳':['parking_general'],
      '유아차로 주차 필요':['parking_general'],
      '어르신 주차 필요':['parking_general'],
      '주차 표지 필요':['parking_disabled'],
      '장애인 주차구역 필요':['parking_disabled'],
      '일반 주차 필수 휠체어 이용':['parking_general'],
      '자차로 가요':['parking_general'],
      '렌터카로 가요':['parking_general'],
      '운전해서 가요':['parking_general'],
      '차로 가요':['parking_general'],
      '렌트카로 가요 장애인 주차 필요':['parking_general','parking_disabled'],
    }
    for q,expected in probes.items():
        assert parser.rule_parse(q,[]).needs==expected,(q,parser.rule_parse(q,[]).needs)
        assert parser.validate(dict(needs=['parking_disabled','parking_general']),q,[]).needs==expected,q
        with patch.object(parser.llm,'ask_json',return_value=dict(needs=['parking_disabled','parking_general'])):
            r,_=parser.parse(q,[],use_llm=True)
            assert set(r.needs)==set(expected) and r.parsed_by.startswith('LLM'),q
    assert parser.rule_parse('유아차로 갈 만한 곳',[]).needs==[]
    assert parser.validate(dict(needs=['parking_general']),'유아차로 갈 만한 곳',[]).needs==[]
    candidates=data.parking_anchor_locations()
    lot=next(r for r in candidates if '공영' in r['name'] and r['name'].endswith('주차장') and anchor.choose(r['name'],candidates) is not None and anchor.choose(r['name'],data.all_places()) is None)
    questions=list(probes)[:4]+[lot['name']+' 근처 산책','한림공원 휠체어로 갈 수 있어?']
    reports=[]
    with patch.object(config,'KMA_SERVICE_KEY',''),patch.object(config,'KTO_SERVICE_KEY',''):
        for q in questions:
            r=core.run(q,use_llm=False)
            assert all(s['ok'] for s in r['trace'])
            if q.startswith(lot['name']):
                assert r['anchor']['source'].startswith('주차장 CSV')
                assert any(s['tool']=='anchor_parking_lot' for s in r['trace'])
            for item in r['results']:
                display=parking.display_info(item['access'])
                assert [x['text'].split(':')[0] for x in display['lines']]==['일반 주차','장애인 주차']
                if item['access']['parking']['disabled']['original_status']=='있음':assert display['notice']==parking.DISABLED_NOTICE
            with redirect_stdout(io.StringIO()) as buf:show(r)
            if r['results']:assert '일반 주차:' in buf.getvalue() and '장애인 주차:' in buf.getvalue()
            reports.append(dict(question=q,needs=r['request']['needs'],anchor=r.get('anchor'),top=[(x['place']['name'],x['grade']) for x in r['results']],summary=r['summary']))
        baseline=core.run(questions[-1],use_llm=False)
    before=json.loads(Path('docs/REGRESSION_BASELINES.json').read_text(encoding='utf-8'))[0]['signature']
    actual=[(r['place']['place_id'],r['grade'],[(t['item'],t['status']) for t in r['access']['table']]) for r in baseline['results']]
    assert json.loads(json.dumps(actual,ensure_ascii=False))==before,'한림공원 순서/등급/시설 상태 변경'
    with patch.object(data,'all_places',return_value=[]),patch.object(data,'nearby_anchor_locations',return_value=[]),patch.object(data,'parking_anchor_locations',return_value=[lot]),patch.object(anchor,'keyword_search') as api:
        assert anchor.resolve(lot['name'],core.Tracer())['source'].startswith('주차장 CSV');api.assert_not_called()
    fake=dict(needs=[dict(condition_key='parking_general')],parking=dict(general=dict(display='미확인'),disabled=dict(original_status='미확인',supplement=None)))
    view=parking.display_info(fake)
    assert not view['lines'][0]['reference'] and view['lines'][1]['reference'] and view['notice'] is None
    fake['needs']=[dict(condition_key='parking_disabled')]
    view=parking.display_info(fake);assert view['lines'][0]['reference'] and not view['lines'][1]['reference'] and view['notice']
    from app_results import compact
    from copy import deepcopy
    card=deepcopy(baseline['results'][0])
    for row in card['access']['table']:
        if row['item']=='장애인주차장':row['status']='미확인'
    for general in ['있음','近처 있음(모의주차장 120m)'.replace('近','근'),'미확인']:
        card['access']['parking']['general']['display']=general
        text=compact(card)
        assert '일반 주차 '+general in text and '장애인 주차 미확인' in text,text
    import csv
    rows=list(csv.DictReader(Path('docs/data_sources.csv').open(encoding='utf-8-sig')))
    assert len(rows)==5 and set(rows[0])=={'데이터番号'.replace('番号','번호'),'데이터명','제공처','기준일','등록일','출처URL','확인일'}
    assert all(row['데이터명'] for row in rows)  # 사용자가 입력한 출처 메타데이터는 허용한다.
    from build_db import public_source_lookup
    mock=dict(번호='mock-bundle',데이터명='무장애여행 일반정보 2021',수집기간='2026-01-01',public_url='https://example.test/source')
    assert public_source_lookup([mock],'general_2021','모의공원') is mock
    assert public_source_lookup([mock],'points_2021','모의공원') is None
    assert public_source_lookup([mock,mock.copy()],'general_2021','모의공원') is None
    Path('output/validation/parking_context.json').write_text(json.dumps(reports,ensure_ascii=False,indent=2),encoding='utf-8')
    print('PASS: 주차 문맥14개 규칙/LLM·6질문 실행·두 줄/참고/표지 안내·주차장 위치조회/API 생략·한림공원 회귀·출처표5행')
    print('주차장 기준 질문:',questions[4])

if __name__=='__main__':main()
