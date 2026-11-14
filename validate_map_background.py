"""배경 교체·타일 실패·키 비노출·표시만 변경되는지 검증(외부 호출 없음)."""
import json
from pathlib import Path
from unittest.mock import patch,Mock
import pydeck as pdk
import map_background as bg
import map_display
import map_icons

def main():
    assert bg.tile_spec()==['white'] and bg.tile_spec('위성')==['Satellite','Hybrid']
    assert not bg.valid_tile(['Base',12,-1,3]) and not bg.valid_tile(['gray',12,1,2])
    assert not bg.valid_tile(['Base',True,1,2])
    secret='synthetic-map-test-secret'
    # 비이미지 오류·HTTP 오류·통신 예외는 본문/URL을 노출하지 않고 실패로 반환.
    for response in [Mock(status_code=403,content=secret.encode()),Mock(status_code=200,content=b'<ExceptionReport/>')]:
        bg._tile.clear()
        with patch.object(bg.requests,'get',return_value=response):assert bg._tile('Base',12,1,2,'http://localhost:18768',_key=secret) is None
    bg._tile.clear()
    with patch.object(bg.requests,'get',side_effect=RuntimeError(secret)):
        assert bg._tile('Base',12,1,2,'http://localhost:18768',_key=secret) is None
    state={};calls=[]
    chart=pdk.Deck(layers=[],initial_view_state=pdk.ViewState(latitude=33.4,longitude=126.5,zoom=10))
    response={'id':'one','tiles':[['Base',12,1,2]],'origin':'http://localhost:18768'}
    def component(**kwargs):calls.append(kwargs);return response
    with patch.object(bg.st,'session_state',state),patch.object(bg.st,'radio',return_value='일반'),patch.object(bg,'_component',side_effect=component),patch.object(bg.st,'rerun'),patch.object(bg,'fetch_tiles',return_value=({},True)),patch.object(bg.config,'get',return_value=secret):
        bg.show(chart,key='test');bg.show(chart,key='test')
    assert calls[0]['provider']=='브이월드' and calls[1]['provider']=='CARTO'
    assert secret not in json.dumps(calls)
    assert calls[0]['spec']['layers'][0]['@@type']=='TileLayer'
    calls.clear()
    with patch.object(bg.st,'session_state',{}),patch.object(bg.st,'radio',return_value='위성'),patch.object(bg,'_component',side_effect=component),patch.object(bg.config,'get',return_value=''),patch.object(bg,'fetch_tiles') as fetch:
        bg.show(chart,key='empty');assert calls[0]['provider']=='CARTO';fetch.assert_not_called()
    from agent import core,config
    with patch.object(config,'KMA_SERVICE_KEY',''),patch.object(config,'KTO_SERVICE_KEY',''):
        result=core.run('한림공원 휠체어로 갈 수 있어?',use_llm=False)['results'][0]
    model=map_display.prepare(result)
    chart=json.loads(map_display.deck(model).to_json())
    border,colored=chart['layers'][:2]
    assert border['getWidth']>colored['getWidth']>=6
    assert colored['capRounded'] and colored['jointRounded']
    assert colored['data']==model['segments']
    assert any(l['@@type']=='IconLayer' for l in chart['layers'])
    assert map_icons.pin([10,20,30,255],1)['anchorY']==48
    frontend=Path('map_component/index.html').read_text(encoding='utf8')
    assert 'args.spec.mapStyle' in frontend and 'tile.openstreetmap.org/{z}/{x}/{y}.png' in frontend
    assert '© OpenStreetMap 기여자' in frontend and 'getMapboxMap' in frontend
    assert 'rastertiles/voyager' not in frontend
    print('PASS: 키 없음·타일 실패 CARTO 대체, 키 비노출, WMTS 순서/범위, 둥근 선·흰 테두리·아이콘, 구간 데이터 불변')

if __name__=='__main__':main()
