"""대화별 결과 표시. 판정은 기존 Agent 결과를 그대로 쓴다."""
import streamlit as st
import re
from app_results import esc,counts,status,recommendation_map,detail
import map_background
from agent import recommendation,data

def card(r):
 order=recommendation.assessment_order(r)
 label=['가능','일부 주의','확인 필요','어려움'][order]
 cls=['ok','care','check','hard'][order]
 c=counts(r);slope=r['route'].get('max_slope')
 reason=('어려운 구간 '+str(c['red'])+'곳' if c['known'] else '어려운 구간 미확인')+' · '+(f'최대 경사 {slope:g}°' if slope is not None else '경사 정보 없음')
 park=(r['access'].get('parking') or {}).get('general') or {}
 facilities=[('일반 주차',park.get('display','미확인')),('장애인 주차',status(r,'장애인주차장')),('장애인 화장실',status(r,'장애인화장실'))]
 items=''.join('<span class="facility '+('muted' if v in ['없음','미확인'] else '')+'">'+esc(('Ⓟ ' if k=='일반 주차' else '♿ ')+k+': '+v)+'</span>' for k,v in facilities)
 missing=' · '.join(recommendation.missing_required(r))
 st.markdown('<div class="place-card"><div class="place-heading">'+esc(r['place']['name'])+'<span class="badge '+cls+'">'+label+'</span></div><p>'+esc(reason)+'</p><div class="facilities">'+items+'</div>'+('<p class="required">'+esc(missing)+'</p>' if missing else '')+'</div>',unsafe_allow_html=True)

SENSORY_NOTICE='현재 자료는 경사·계단·화장실·주차 등 이동 정보 중심이라 시각·청각 안내 시설은 확인이 어려워요. 원문에 있는 정보만 보여 드려요.'
SENSORY_ITEMS={'점자블록','오디오가이드','큰글자','점자홍보물','수어안내','영상안내','보청시설','시각장애 기타','청각장애 기타','안내견 동반','안내요원','유도안내'}

def sensory_question(res):
 import unicodedata
 req=res.get('request',{})
 return req.get('user_type') in ('시각장애','청각장애') or bool(re.search('시각|청각|안내견|저시력|수어|보청기',unicodedata.normalize('NFKC',req.get('text',''))))

def sensory_sources(res):
 rows=[]
 for r in res.get('results',[])[:5]:
  for item in data.items(r['place']['place_id']):
   if str(item.get('item_id','')).startswith('KTO-') and item.get('item') in SENSORY_ITEMS and str(item.get('value_raw') or '').strip():
    rows.append((r['place']['name'],item))
 return rows

def render(res,index):
 ns='chat-'+str(index)+'-'
 if sensory_question(res):
  st.info(SENSORY_NOTICE)
  rows=sensory_sources(res)
  if rows:
   with st.expander('관광공사 시각·청각 관련 원문'):
    for name,item in rows:
     st.write(name+' · '+item['item'])
     st.text(item['value_raw'])
     st.caption('출처: '+str(item.get('origin'))+' · '+str(item.get('file_name'))+' · '+str(item.get('source_locator'))+' · 기준일 '+str(item.get('display_base_date') or '미확인'))
  else:st.caption('이번 답변 장소의 관광공사 관련 항목 원문을 보유하고 있지 않습니다.')
 summary=res.get('explanation') or res.get('summary','')
 st.write(' '.join(re.split(r'(?<=[.!?])\s+',summary)[:2]))
 results=res.get('results',[])[:5]
 if not results:return
 named=any(r.get('requested_place') for r in results)
 selected=results[0] if named else None
 if not named:
  selected_id=st.session_state.get(ns+'selected')
  selected=next((r for r in results if r['place']['place_id']==selected_id),None)
  map_background.show(recommendation_map(results,selected_id),key=ns+'overview',mode='list',bounds=[r['place'] for r in results])
  visible=st.session_state.get(ns+'visible',1)
  for r in results[:visible]:
   card(r)
   if st.button('자세히 · '+r['place']['name'],key=ns+str(r['place']['place_id'])):
    st.session_state[ns+'selected']=r['place']['place_id'];st.rerun()
  if visible<len(results) and st.button(f'다음 장소 {len(results)-visible}곳 보기',key=ns+'next'):
   st.session_state[ns+'visible']=len(results);st.rerun()
 if selected:
  if named:card(selected)
  with st.container(border=True):
   if not named:
    st.markdown('#### '+selected['place']['name'])
    if st.button('상세 접기',key=ns+'close'):
     st.session_state.pop(ns+'selected',None);st.rerun()
   detail(selected,res,named=named,namespace=ns)
