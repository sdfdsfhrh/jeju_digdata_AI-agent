"""시설 타일 표시·아이콘·원본 결과 불변·상세 화면 연결 검사."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import xml.etree.ElementTree as ET
from agent import core,config
import facility_tiles as tiles

def main():
    for name in tiles.ICONS:
        root=ET.fromstring((tiles.ROOT/(name+'.svg')).read_text(encoding='utf8'))
        assert root.tag.endswith('svg') and 'http' not in tiles.icon(name).split('src="',1)[1].split('"',1)[0]
    assert 'MIT License' in (tiles.ROOT/'LICENSE.tabler-icons').read_text(encoding='utf8')
    with patch.object(config,'KMA_SERVICE_KEY',''),patch.object(config,'KTO_SERVICE_KEY',''):
        res=core.run('한림공원 휠체어로 갈 수 있어?',use_llm=False)
    r=deepcopy(res['results'][0]);before=deepcopy(r)
    html=tiles.markup(r)
    assert r==before and html.count('class="facility-box')==3
    assert '<details' in html and '<summary' in html and '날짜별 예보 보기' in html
    for s in tiles.STATES:assert 'data:image/svg+xml;base64,' in tiles.state(s) and s in tiles.state(s)
    for sky,icon in [('맑음','sun'),('구름많음','cloud'),('흐림','cloud'),('비','cloud-rain'),('천둥·번개','cloud-storm')]:
        assert tiles.weather_icon(dict(status='조회됨',sky=sky))==icon
    assert tiles.weather_icon(dict(status='미확인'))=='question-mark'
    assert tiles.weather_icon(dict(status='조회됨',sky='흐림',precip=True))=='cloud-rain'
    r['weather']=dict(status='조회됨',sky='비',pop_max=60,cautions=['기존 비 주의 문구'])
    advice=dict(best=dict(date='2026-11-11',pop=10),rows=[dict(date='2026-11-11',pop=10,forecast_type='단기'),dict(date='2026-11-12',pop=None,forecast_type='미확인')])
    before=deepcopy((r,advice));html=tiles.markup(r,advice)
    assert (r,advice)==before and '강수 60%' in html and '11/11(수) 방문 추천' in html
    assert '실외 코스 주의' in html and '미확인%' not in html and '기존 비 주의 문구' not in html
    assert '방문 추천' not in tiles.markup(r,{})
    assert '11/11(수)' in tiles.forecast_table(r['weather'],{},'20261111')
    from streamlit.testing.v1 import AppTest
    with patch.object(config,'llm_enabled',return_value=False):
        at=AppTest.from_file(str(Path('app.py').resolve()),default_timeout=30).run()
        at.session_state['conversation']=[dict(question=res['request']['text'],result=res)];at.run()
        assert not at.exception
        assert any('class="facility-panel"' in x.value for x in at.markdown)
        assert not any(x.value.startswith('날씨: ') for x in at.caption)
    print('PASS: 로컬 SVG/MIT·상태4종·날씨 아이콘·추천일 조건·날씨 펼침·입력 불변·상세 AppTest')

if __name__=='__main__':main()
