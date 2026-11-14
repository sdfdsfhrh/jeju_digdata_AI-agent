"""지정 장소의 주소 보완·거리 대안·이용 판단 회귀 검증(외부 호출 없음)."""
from unittest.mock import patch
from agent import core, config, data, place_query, tools


def main():
    with patch.object(config, 'KMA_SERVICE_KEY', ''), patch.object(config, 'llm_enabled', return_value=False):
        result = core.run('한림공원 휠체어로 갈 수 있어?', use_llm=False)
    top = result['results'][0]
    assert top['place']['name']=='한림공원' and top['requested_place']
    assert '한림공원(상세 1, 목록 2)' in result['summary']
    assessment=top['use_assessment']
    assert assessment['text'].startswith('휠체어 이용: 가능(일부 구간 주의)')
    assert '10개 측정값(최대 11°)' in assessment['text']
    assert '계단길·휠체어길 분리' in assessment['text'] and assessment['evidence']
    assert place_query.classify(top['place'])['group']=='관광지'
    assert all(r['place']['_place_type']['group']!='편의' for r in result['results'][1:])
    assert any(r['place']['name']=='우무 본점' and r['place']['_place_type']['group']=='편의' for r in result['convenience_results'])
    for code,group in [('12','관광지'),('14','관광지'),('32','편의'),('38','편의'),('39','편의')]:
        with patch.object(data,'place_types',return_value=[dict(kto_id='mock',contenttypeid=code)]):
            kind=place_query.classify(dict(place_id='mock',name='유형을 이름으로 추정하지 않음'))
            assert kind['group']==group and 'contenttypeid='+code in kind['evidence'][0]
    with patch.object(data,'place_types',return_value=[]),patch.object(data,'place_evidence',return_value=[]):
        assert place_query.classify(dict(place_id='mock',name='어떤 장소'))['group']=='미확인'
    pool=place_query.nearby_candidates(top['place'])['candidates']
    assert {r['place']['place_id'] for r in result['results'][1:]} <= {p['place_id'] for p in pool}
    assert all('_distance_km' in r['place'] and 'km' in r['rank_reason'] for r in result['results'][1:])
    base=result['results'][1]
    rows=[]
    for unknown,penalty,km in [(True,False,1),(False,True,0.1),(False,False,5),(False,False,2)]:
        r=dict(base, requested_place=False, slope_unknown=unknown,slope_penalty=penalty)
        r['place']=dict(base['place'],_distance_km=km);rows.append(r)
    ordered=sorted(rows,key=core._rank_key)
    assert [r['place']['_distance_km'] for r in ordered]==[2,5,1,0.1]
    dates=data.source_date_ranges()
    assert any(f"허브 {dates['hub']['lo']}~{dates['hub']['hi']}" in s and f"관광공사 수정일 {dates['kto']['lo']}~{dates['kto']['hi']}" in s for s in result['limits'])
    print('PASS: 장소명 묶음·주소 출처 보완·거리 및 경사 순위·원문 이용 판단·출처별 기준일')

if __name__=='__main__': main()
