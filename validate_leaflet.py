"""로컬 Leaflet 자산·키 비노출·공통 분류 보존·롤백 검사."""
from pathlib import Path
from unittest.mock import patch
import json,requests,base64
from agent import config,core,course_profile
import leaflet_map,leaflet_tiles,map_display

def main():
 with patch.object(config,'KMA_SERVICE_KEY',''),patch.object(config,'KTO_SERVICE_KEY',''):
  r=core.run('한림공원 휠체어로 갈 수 있어?',use_llm=False)['results'][0]
 p=leaflet_map.payload([r]);m=p['places'][0]['model'];original=course_profile.prepare(r)
 assert [(x['path'],x.get('level')) for x in m['segments']]==[(x['path'],x.get('level')) for x in original['segments']]
 assert [x['number'] for x in m['warnings']]==[x['number'] for x in original['warnings']]
 assert not config.get('VWORLD_API_KEY') or config.get('VWORLD_API_KEY') not in json.dumps(p)
 assert all((Path('static/vendor')/n).is_file() for n in ['leaflet.js','leaflet.css','LICENSE.leaflet'])
 template=Path('static/leaflet_map.html').read_text(encoding='utf8')
 assert 'flyToBounds' in template and 'duration:1.5' in template and '500' in template and '전체 보기' in template
 assert '위성지도는 브이월드 키 필요' in template and 'tileerror' in template
 assert '69be4aecf9f814ba45d585801a5aa41e79b16fc88eafec5b1954a9f06a69e6be' in Path('leaflet_tiles.py').read_text(encoding='utf8')
 with patch.object(config,'get',return_value=''):assert not leaflet_map.payload([r])['vworld']
 assert 'cdn.jsdelivr' not in template and 'unpkg' not in template
 with patch.object(config,'get',side_effect=lambda key,default='': 'pydeck' if key=='MAP_ENGINE' else default):assert not leaflet_map.enabled()
 service=leaflet_tiles.server();url=f"http://127.0.0.1:{service['port']}/{service['token']}"
 assert requests.get(url+'/static/vendor/leaflet.js',timeout=5).status_code==200
 assert requests.get(url+'/tile/Base/999/0/0',timeout=5).status_code==404
 # 브라우저 z/x/y → 서버 WMTS z/y/x, Origin:null 및 키 비노출 회귀.
 image='data:image/png;base64,'+base64.b64encode(Path('static/preview_normal.png').read_bytes()).decode()
 with patch('map_background._tile',return_value=image) as fetch:
  response=requests.get(url+'/tile/Base/8/218/102',headers={'Origin':'null'},timeout=5)
  assert response.status_code==200 and response.headers['Access-Control-Allow-Origin']=='*'
  assert fetch.call_args.args[:4]==('Base',8,218,102)
  assert fetch.call_args.args[4].startswith('http://')
 import map_background
 map_background._tile.clear()
 class ImageReply:
  status_code=200
  content=Path('static/preview_normal.png').read_bytes()
 with patch.object(map_background.requests,'get',return_value=ImageReply()) as upstream:
  assert map_background._tile('Base',8,218,102,'http://127.0.0.1:18768',_key='test-key')
  assert upstream.call_args.args[0].endswith('/Base/8/102/218.png'),'WMTS 타일 행·열 순서 오류'
 map_background._tile.clear()
 target=dict(name='자료없는장소',lat=33.46,lon=126.93,source='모의 공개 좌표')
 assert leaflet_map.payload([r],queried_target=target)['queried_target']==target
 assert 'queried-place' in template and '★' in template and 'latLngToContainerPoint' in template
 assert 'updateWhenZooming:false' in template and "if(!current(e.coords.z))return" in template
 with patch.object(leaflet_map.components,'html') as render:
  leaflet_map.show([r],key='test');html=render.call_args.args[0]
  assert '__LEAFLET_JS__' not in html and 'L.map' in html and '__PAYLOAD__' not in html
  assert not config.get('VWORLD_API_KEY') or config.get('VWORLD_API_KEY') not in html
 print('PASS: Leaflet local assets·flyTo·fallback·기존 구간/번호 보존·키 비노출·pydeck 롤백·로컬 전달 서버')
if __name__=='__main__':main()
