"""Leaflet 표시 전용. 기존 course_profile/판정을 다시 계산하지 않는다."""
import json
from pathlib import Path
import streamlit.components.v1 as components
from agent import config,recommendation
import map_display
from leaflet_tiles import server
ROOT=Path(__file__).resolve().parent

def enabled():return config.get('MAP_ENGINE','leaflet').lower()!='pydeck'

def payload(results,selected_id=None,queried_target=None):
 places=[]
 for r in results:
  p=r['place']
  if not map_display.valid(p):continue
  model=map_display.prepare(r);model.pop('view',None)
  places.append(dict(id=p['place_id'],name=p['name'],lat=p['lat'],lon=p['lon'],rank=r.get('rank',len(places)+1),assessment=['가능','일부 주의','확인 필요','어려움'][recommendation.assessment_order(r)],model=model))
 target=None
 if queried_target and map_display.valid(queried_target):
  target={k:queried_target.get(k) for k in ('name','lat','lon','source')}
 return dict(places=places,selected=selected_id,queried_target=target,vworld=bool(config.get('VWORLD_API_KEY')))

def show(results,*,key,selected_id=None,queried_target=None):
 args=payload(results,selected_id,queried_target)
 try:args['server']=server()
 except OSError:
  args['server']=None
  args['vworld']=False
 source=(ROOT/'static/leaflet_map.html').read_text(encoding='utf8')
 # 문자열을 script 문맥에 안전하게 넣는다. 공개 장소/코스 데이터만 전달.
 source=source.replace('__LEAFLET_CSS__',(ROOT/'static/vendor/leaflet.css').read_text(encoding='utf8')).replace('__LEAFLET_JS__',(ROOT/'static/vendor/leaflet.js').read_text(encoding='utf8').replace('//# sourceMappingURL=leaflet.js.map',''))
 source=source.replace('__PAYLOAD__',json.dumps(args,ensure_ascii=False,default=str).replace('<',chr(92)+'u003c'))
 components.html(source,height=520,scrolling=False)
