"""지도 표시만 검증. Agent/DB 결과는 변경하지 않는다."""
import copy,json
from pathlib import Path
import map_display as m


def sample(raws,whole=''):
 p=[dict(point_id=str(i),seq=i+1,lat=33.4+i*.001,lon=126.5,label='',description=t,file_name='test.csv',source_locator=f'row {i+2}') for i,t in enumerate(raws)]
 return dict(place=dict(name='모의',overview=whole),access=dict(table=[]),route=dict(points=p,course_slopes=[]))

def main():
 for raws,level in [(['계단','일반'],2),(['계단','남녀 분리 화장실'],2),(['계단','휠체어길 있음'],1),(['휠체어길 있음','계단','일반'],1),(['휠체어길 있음','일반','계단'],2),(['단차 경사로','일반'],1),(['계단 없음','일반'],0)]:
  model=m.prepare(sample(raws));assert max((x['level'] for x in model['segments']),default=0)==level
 whole=m.prepare(sample(['계단','일반'],'휠체어길 있음'))
 assert whole['whole_alt'] and whole['segments'][0]['level']==2
 assert '우회 정보 없음' in whole['warnings'][0]['reason']
 missing=sample(['일반','계단','일반']);missing['route']['points'][1]['lat']=None
 assert not m.prepare(missing)['segments']
 nofacility=m.prepare(sample(['장애인 화장실 없음','장애인 주차장 없음']))
 assert not nofacility['facilities']
 slope=sample(['오르막','일반']);slope['route']['course_slopes']=[dict(point='1',value=11,evidence='test.csv [row 2]')]
 assert m.prepare(slope)['warnings'][0]['value']=='경사 11°'
 from agent import data,adaptive
 from agent.parser import Request
 res=dict(results=adaptive.evaluate([dict(p) for p in data.detailed_places() if p['name'] in ('한림공원','협재해수욕장')],Request(user_type='수동휠체어')))
 reports=[]
 for name in ['한림공원','협재해수욕장']:
  r=next(x for x in res['results'] if x['place']['name']==name);before=copy.deepcopy(r)
  model=m.prepare(r);assert r==before
  assert [w['number'] for w in model['warnings']]==list(range(1,len(model['warnings'])+1))
  assert all(w['source'] and w['quote'] for w in model['warnings'])
  assert any(x['label']=='화장실' for x in model['facilities']) and any(x['label']=='주차' for x in model['facilities'])
  if name=='한림공원':
   split=next(w for w in model['warnings'] if '좌측 계단길' in w['quote'])
   assert split['color']==m.ORANGE and '휠체어길로 우회' in split['reason']
   assert any(w['color']==m.RED and '우회 정보 없음' in w['reason'] for w in model['warnings'])
  deck=json.loads(m.deck(model).to_json());assert deck['layers'][0]['widthMinPixels']>=6
  assert deck['layers'][0]['widthUnits']=='pixels'
  assert all(l.get('radiusUnits')=='pixels' for l in deck['layers'] if l['@@type']=='ScatterplotLayer')
  assert all(l.get('characterSet')=='auto' for l in deck['layers'] if l['@@type']=='TextLayer')
  assert not any(l.get('getFillColor')==[255,255,255,230] for l in deck['layers'])
  reports.append(dict(name=name,count=model['count'],warnings=len(model['warnings']),omitted=model['omitted'],zoom=model['view'].zoom))
 Path('output/validation/map_display_report.json').write_text(json.dumps(reports,ensure_ascii=False,indent=2),encoding='utf-8')
 print('PASS: 지점 인접 우회/전체설명 분리·파일별 연결·좌표 누락·시설 부재·원문/번호·불변·6px 선')

if __name__=='__main__':main()
