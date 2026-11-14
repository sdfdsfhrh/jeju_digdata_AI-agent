"""대화별 결과 표시. 판정은 기존 Agent 결과를 그대로 쓴다."""
import streamlit as st
import re
from app_results import esc,counts,status,recommendation_map,detail
import map_background
import leaflet_map
from agent import recommendation,data
from agent import missing_place

import caution_view as cv

def card(r,missing_context=None):
 order=recommendation.assessment_order(r)
 reason=cv.reason(cv.groups(r))
 if missing_context:reason=missing_place.distance(missing_context,r)+' · '+reason
 park=(r['access'].get('parking') or {}).get('general') or {}
 facilities=[('주차',park.get('status','미확인')),('장애인 주차',status(r,'장애인주차장')),('장애인 화장실',status(r,'장애인화장실'))]
 glyph={'있음':'✓','없음':'✕','미확인':'?','조건부':'!'}
 classes={'있음':' yes','조건부':' partial'}
 items=''.join(f'<span class="simple-chip{classes.get(v,"")}" aria-label="{esc(k+" "+v)}">{esc(k)} {glyph.get(v,"?")}</span>' for k,v in facilities)
 missing=' · '.join(recommendation.missing_required(r))
 st.markdown(cv.CSS+'<div class="place-card"><div class="place-heading">'+esc(r['place']['name'])+'</div><p style="color:'+cv.COLORS[order]+'">● '+cv.WORDS[order]+' · '+esc(reason)+'</p><div class="facilities">'+items+'</div>'+('<p class="required">'+esc(missing)+'</p>' if missing else '')+'</div>',unsafe_allow_html=True)

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
 missing_context=res.get('missing_place')
 if missing_context:
  st.write(missing_context['message'])
  location=missing_context.get('location')
  if location:st.markdown('**'+missing_context['alternatives_heading']+'**')
  else:st.write(f"'{missing_context['name']}'의 위치를 찾지 못했습니다. 근처 지역명(예: 중문)으로 다시 물어봐 주세요.")
  if missing_context.get('radius_km')==10:st.caption('5km 안에 판정 가능한 장소가 없어 10km까지 넓혔어요.')
  if location and '지역명 사전' in location.get('source',''):
   st.caption('질문 장소의 실좌표가 없어 지역 대표 위치 기준으로 거리를 표시합니다. '+location['source'])
  elif location:
   st.caption('회색 별표: '+missing_context['name']+' · 위치 출처: '+str(location.get('source') or location.get('coord_source') or '연결된 위치 자료')+' · 직선거리는 실제 이동 경로가 아닙니다.')
 else:st.write(' '.join(re.split(r'(?<=[.!?])\s+',summary)[:2]))
 results=res.get('results',[])[:5]
 if not results:
  if missing_context and missing_context.get('location'):
   if leaflet_map.enabled():leaflet_map.show([],key=ns+'missing-location',queried_target=missing_context['location'])
   st.write('가까운 판정 가능 장소를 보유 자료에서 찾지 못했어요.')
  return
 named=any(r.get('requested_place') for r in results)
 selected=results[0] if named else None
 if not named:
  selected_id=st.session_state.get(ns+'selected')
  selected=next((r for r in results if r['place']['place_id']==selected_id),None)
  if leaflet_map.enabled():leaflet_map.show(results,key=ns+'overview',selected_id=selected_id,queried_target=(missing_context or {}).get('location'))
  else:
   target=(missing_context or {}).get('location')
   map_background.show(recommendation_map(results,selected_id,target),key=ns+'overview',mode='list',bounds=[r['place'] for r in (results[:3] if target else results)]+([target] if target else []))
  visible=st.session_state.get(ns+'visible',3 if missing_context else 1)
  for r in results[:visible]:
   card(r,missing_context)
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
