"""화면 선택 우선·지도 범위·좌표 표시·가로 카드 전달 회귀."""
import datetime as dt,json
from pathlib import Path
from unittest.mock import patch
from ui_controls import form_values
from agent.parser import Request,apply_form
from agent import core,config
import map_background,map_display,app_results

def main():
 today=dt.date(2026,11,9)
 assert form_values(today=today)==dict(user_type=None,date=None,time_slot=None)
 req=apply_form(Request(user_type='전동휠체어',date='20261110'),form_values('유아차',when='오늘',today=today))
 assert (req.user_type,req.date)==('영유아동반','20261109')
 assert form_values(when='이번 주말',today=today)['date']=='20261114'
 assert form_values(when='날짜',date=today,slot='오후',today=today)['time_slot']=='오후'
 assert form_values(when='내일',slot='오후',today=today)['time_slot'] is None
 with patch.object(config,'KMA_SERVICE_KEY',''),patch.object(config,'KTO_SERVICE_KEY',''):
  res=core.run('한림공원 휠체어로 갈 수 있어?',use_llm=False)
 r=res['results'][0];model=map_display.prepare(r);chart=json.loads(map_display.deck(model).to_json())
 assert any(l.get('id')=='entrance-circle' and l['@@type']=='ScatterplotLayer' for l in chart['layers'])
 assert all(f['label_offset']==[0,20] for f in model['facilities'])
 with patch('leaflet_map.enabled',return_value=False),patch.object(map_background,'show') as show,patch.object(app_results.st,'caption'):
  app_results.route_map(r,overview=res['results'])
  args=show.call_args
  assert args.kwargs['mode']=='course' and args.kwargs['bounds']
  assert not any(l.type=='IconLayer' and l.id=='recommendation-pins' for l in args.args[0].layers)
 html=Path('map_component/index.html').read_text(encoding='utf8')
 assert "fitBounds(args.bounds" in html and "args.mode==='list'" in html
 assert "scroll-snap-type:x mandatory" in html and "get_pixel_offset" in Path('app_results.py').read_text(encoding='utf8')
 assert map_background.tile_spec()==['white']
 assert not map_background.valid_tile(['white',19,1,1])
 from validate_chat import main as chat_test
 chat_test()
 print('PASS: 칩 폼값·지도 코스 범위·대화 화면')

if __name__=='__main__':main()
