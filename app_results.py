"""모바일 중심 결과 화면. 판단은 Agent 결과만 표시한다."""
import html
import json
import datetime as dt
import streamlit as st
import pydeck as pdk
import pandas as pd
import map_display
import map_background
import map_icons
import result_view as view
from agent import recommendation, parking

CSS='''<style>
.block-container{max-width:1100px!important}
.app-chips{display:flex;gap:8px;flex-wrap:wrap;margin:18px 0 16px}
.app-chip{background:#e9f1ff;color:#245784;border-radius:20px;padding:7px 12px;font-size:13px;font-weight:600}
.app-card{background:white;border:1px solid #e2e6eb;border-radius:12px;padding:20px;margin:0 0 10px}
.app-name{font-size:18px;font-weight:700;color:#20282f;margin-bottom:10px;line-height:1.45}
.app-body{font-size:15px;line-height:1.65;word-break:keep-all;overflow-wrap:anywhere}
.app-meta{font-size:13px;line-height:1.7;color:#5f6b76;margin-top:8px;word-break:keep-all}
.app-decision{border-radius:12px;padding:16px 18px;margin:12px 0 16px}
.app-green{color:#236438;background:#edf7ee}.app-orange{color:#915309;background:#fff5e6}.app-red{color:#a12836;background:#fff0f1}
.app-status-green{color:#236438}.app-status-orange{color:#915309}.app-status-red{color:#a12836}
.app-tiles{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin:14px 0 20px}
.app-tile{background:#f6f8fa;border-radius:12px;padding:16px 8px;text-align:center;min-width:0}
.app-tile-label{font-size:13px;color:#606c76;margin-bottom:8px}.app-tile-value{font-size:15px;font-weight:600;overflow-wrap:anywhere}
.app-note{font-size:13px;color:#77818a;line-height:1.7;margin:16px 0}
.app-warning{border:1px solid #e5e8ec;border-left:3px solid #dc941d;border-radius:12px;padding:14px 16px;margin:10px 0;background:white}
.app-warning-red{border-left-color:#b52e40}
button{min-height:44px!important;border-radius:12px!important}
[data-testid="stVerticalBlockBorderWrapper"]{border-radius:12px!important}
@media(max-width:640px){.app-card{padding:16px}.app-tiles{gap:6px}.app-tile{padding:14px 4px}.app-chip{padding:6px 10px}}
</style>'''

def esc(value):return html.escape(str(value),quote=True)

def visual(result):
    order=recommendation.assessment_order(result)
    return ('green','✓') if order<2 else ('red','×') if order==3 else ('orange','?')

def counts(result):
    if not result.get('course_counts'):recommendation.annotate(result)
    return result['course_counts']

def status(result,item):
    return next((t['status'] for t in result['access']['table'] if t['item']==item),'미확인')

def weather_value(result):
    w=result.get('weather') or {}
    pop=w.get('pop_max')
    if w.get('status')=='조회됨' and pop is not None:return f'강수 {pop}%'
    return '미확인'

def compact(result):
    slope=result['route'].get('max_slope');c=counts(result)
    def val(item):
        s=status(result,item)
        return {'있음':'✓','없음':'×','조건부':'조건부','미확인':'미확인'}.get(s,'미확인')
    general=(result['access'].get('parking',{}).get('general') or {}).get('display','미확인')
    line=f"일반 주차 {general} · 장애인 주차 {val('장애인주차장')} · 화장실 {val('장애인화장실')} · 최대 경사 "+(f'{slope:g}°' if slope is not None else '미확인')
    line+=' · 어려운 구간 '+(str(c['red'])+'곳' if c['known'] else '미확인')
    if result['place'].get('_distance_km') is not None:line+=f" · {result['place']['_distance_km']:.1f}km"
    return line

def chips(res):
    req=res['request'];labels=[req.get('user_type') or '이용자 유형 미지정']
    themes=req.get('themes') or []
    if '해안' in themes:labels.append('해안 산책' if req.get('activity')=='walk' or any(w in req.get('text','') for w in ['산책','걷']) else '해안')
    else:labels+=themes
    if req.get('anchor'):labels.append(req['anchor']+' 근처')
    names={'parking_disabled':'장애인 주차','장애인주차장':'장애인 주차','parking_general':'일반 주차','장애인화장실':'장애인 화장실'}
    labels += [names.get(n,n)+' 필수' for n in req.get('needs',[])]
    if req.get('date'):
        d=dt.datetime.strptime(req['date'],'%Y%m%d');labels.append(f'{d.month}/{d.day} '+req.get('time_slot',''))
        if res['results']:labels.append(weather_value(res['results'][0]))
    st.markdown('<div class="app-chips">'+''.join('<span class="app-chip">'+esc(x)+'</span>' for x in dict.fromkeys(labels))+'</div>',unsafe_allow_html=True)

def recommendation_map(results,selected_id=None,queried_target=None):
    pins=[]
    for r in results:
        p=r['place']
        if not map_display.valid(p):continue
        color,_=visual(r)
        pins.append(dict(lat=p['lat'],lon=p['lon'],place_id=p['place_id'],number=str(r['rank']),color={'green':[8,80,65,255],'orange':[216,90,48,255],'red':[176,42,57,255]}[color],info=p['name']+' · '+view.conclusion(r)))
    target=[dict(queried_target,label='★ '+queried_target['name'])] if queried_target and map_display.valid(queried_target) else []
    viewstate=map_display.fit(pins+target)
    leaders=[]
    for pin in pins:pin.update(position=[pin['lon'],pin['lat']],offset=[0,0])
    for pin in pins:
        selected=pin['place_id']==selected_id
        pin['icon']=map_icons.pin(pin['color'],pin['number'])
        pin['size']=58 if selected else 44
        pin['tint']=[255,255,255,255 if selected_id is None or selected else 90]
    return pdk.Deck(layers=[pdk.Layer('PathLayer',leaders,get_path='path',get_color=[120,130,140],get_width=1,width_min_pixels=1),
        pdk.Layer('IconLayer',pins,id='recommendation-pins',get_position='position',get_icon='icon',get_color='tint',get_size='size',get_pixel_offset='offset',pickable=True),
        pdk.Layer('TextLayer',target,id='queried-place',get_position='[lon, lat]',get_text='label',get_color=[100,100,100],get_size=19,get_text_anchor='middle')],
        initial_view_state=viewstate,map_provider='carto',map_style='light',tooltip={'text':'{info}'})


def route_map(result,overview=None,namespace=""):
    model=map_display.prepare(result)
    import leaflet_map
    if leaflet_map.enabled():
        leaflet_map.show([result],key=namespace+'course-'+str(result['place']['place_id']))
        return model
    chart=map_display.deck(model)
    # 상세 화면에는 해당 코스만 표시한다. 추천 전체 핀을 경계 계산에 포함하지 않는다.
    bounds=model['bounds']+[dict(lon=w['display_position'][0],lat=w['display_position'][1]) for w in model['warnings'] if w.get('display_position')]
    map_background.show(chart,key=namespace+'app-course-'+str(result['place']['place_id']),mode='course',bounds=bounds)
    if result['route']['points']:st.caption('초록 편한 구간 · 주황 주의(경사·우회) · 빨강 어려움(우회 정보 없음)')
    else:st.caption('코스 조사자료 없음 · 대표 위치만 표시')
    return model


def warning(w):
    color,icon=('red','×') if w['level']==2 else ('orange','!')
    label=f"{icon} {w['number']}. {w['title']}"
    if w['count']>1:label+=f" · 같은 내용 지점 {w['count']}곳"
    st.markdown('<div class="app-warning '+('app-warning-red' if color=='red' else '')+'"><div class="app-body app-status-'+color+'">'+esc(label)+'</div><div class="app-meta">'+esc('“'+w['quote']+'”')+'</div></div>',unsafe_allow_html=True)

def evidence(result,model):
    distance_evidence=result["place"].get("_distance_evidence") or []
    if distance_evidence:
        origin=distance_evidence[0]
        st.caption("위치 출처: "+str(origin.get("coord_source") or "미확인")+" · 기준 장소: "+origin["name"])
    st.write('시설 조건 등급: '+result['grade'])
    for proof in (result.get('use_assessment') or {}).get('evidence',[]):st.caption(proof)
    st.dataframe(pd.DataFrame([dict(항목=t['item'],상태=t['status'],원문=t.get('raw'),출처=t.get('source'),근거=t.get('evidence'),기준일=t.get('base_date')) for t in result['access']['table']]),hide_index=True,use_container_width=True)
    for w in model['warnings']:
        st.write(str(w['number'])+'. '+w['title'])
        st.write('원문: '+w['quote'])
        for text in w.get('additional_quotes',[]):st.write(text)
        for source in w['sources']:st.caption(source)
        if w.get('alternative'):st.write('우회 원문: '+w['alternative']);st.caption(w['alternative_source'])
    p=result['place']
    if p.get('_address_evidence'):st.json(p['_address_evidence'],expanded=False)
    st.write(view.facility_text(result))
    notice=parking.display_info(result['access'])['notice']
    if notice:st.caption(notice)
    w=result.get('weather') or {}
    st.write('날씨: '+(w.get('reason') or w.get('precision') or '미확인'))
    if w.get('status')=='조회됨':st.json(w,expanded=False)
    for conflict in result['access'].get('conflicts',[]):st.write('출처 간 차이: '+str(conflict))

def detail(result,res,named=False,overview=None,namespace=""):
    import caution_view as cv
    p=result['place']
    model=route_map(result,overview,namespace)
    grouped=cv.groups(result,model)
    order=recommendation.assessment_order(result)
    reason=cv.explanation(grouped)
    bg=('#e5eee4','#e5eee4','#fff0d8','#fae7e7')[order]
    st.markdown(cv.CSS+f'<div class="simple-decision" style="background:{bg};color:{cv.COLORS[order]}"><strong>{cv.WORDS[order]}</strong><div>{esc(cv.reason(grouped))}</div><div>{esc(reason)}</div></div>',unsafe_allow_html=True)
    if result.get('requested_place') or result is res['results'][0]:
        advice=res.get('day_recommendation') or {}
    else:advice=result.get('rain_days') or {}
    from facility_tiles import markup
    st.markdown(markup(result,advice,res['request'].get('date')),unsafe_allow_html=True)
    st.markdown('#### 주의할 곳')
    st.markdown(cv.markup(grouped),unsafe_allow_html=True)
    local=dict(res,results=[result],convenience_results=[],day_recommendation=advice)
    copy='\n'.join(['닿는제주',p['name'],view.conclusion(result),reason,view.facility_text(result),view.weather_line(local),view.sources(local)[0]])
    cols=st.columns(2)
    with cols[0]:view.copy_button(copy,key=namespace+str(p["place_id"]))
    proof_key=namespace+'app-proof-'+str(p['place_id'])
    with cols[1]:
        if st.button('원문 근거',key='open-'+proof_key,use_container_width=True):st.session_state[proof_key]=not st.session_state.get(proof_key,False)
    if st.session_state.get(proof_key):
        with st.container(border=True):evidence(result,model)
    sources=view.sources(local)[0].removeprefix('이 답에 쓰인 데이터: ').split(' / ')
    lead='제주데이터허브' if '제주데이터허브' in sources[0] else sources[0]
    credit=lead+(f' 외 {len(sources)-1}곳' if len(sources)>1 else '')
    st.markdown('<div class="app-note">원문 기록 기준이며 안전을 보장하지 않아요 · 출처: '+esc(credit)+'</div>',unsafe_allow_html=True)
    if res.get('convenience_results'):
        with st.expander('근처 식사·편의 장소'):
            for r in res['convenience_results']:
                q=r['place'];distance=q.get('_distance_km')
                st.write(q['name']+' · '+q.get('_place_type',{}).get('label','유형 미확인')+' · '+(f'{distance:.2f}km' if distance is not None else '거리 미확인'))

def render_system(res):
    st.caption(view.sources(res)[0])
    if (res.get('day_recommendation') or {}).get('rows'):
        st.dataframe(pd.DataFrame(res['day_recommendation']['rows']),hide_index=True,use_container_width=True)
    st.markdown('**Agent 작업 과정**')
    st.caption(f"처리 모드: {res['mode']} · {res['elapsed_ms']:,}ms")
    for step in res['trace']:
        st.write(f"{step['no']}. 무엇을: {view.ACTIONS.get(step['tool'],step['purpose'])} · {step['ms']:,}ms")
        st.caption('왜: '+str(step['purpose'])+' / 결과: '+str(step['output']))
    for r in res['results']:
        st.caption(r['place']['name']+' · 순위 근거: '+r['rank_reason'])
    st.json(dict(request=res['request'],named=res.get('named_groups'),anchor=res.get('anchor')),expanded=False)
    st.markdown('**데이터 한계와 판정 규칙**')
    for line in res['limits']:st.caption(line)

def render(res):
    st.markdown(CSS,unsafe_allow_html=True)
    chips(res)
    if not res['results']:
        st.write(res['summary']);return
    named=any(r.get('requested_place') for r in res['results'])
    for group in res.get('named_groups',[]):
        if not group.get('detailed'):st.info(group['name']+' — 위치는 있으나 접근성 상세정보가 없어 판정 불가. 아래는 근처 대안입니다.')
    if named:
        if st.button('← '+res['results'][0]['place']['name'],key='app-home',help='검색 화면으로 돌아가기'):
            st.session_state.pop('res',None);st.rerun()
        detail(res['results'][0],res,named=True)
        return
    if res.get('judgment_missing'):st.info('판정 데이터가 없습니다. 근처 판정 가능 장소를 안내합니다.')
    if res.get('anchor'):st.caption('기준 위치: '+res['anchor_query']+' (좌표 근사)')
    if res.get('relaxations'):st.caption('조건 완화: '+' → '.join(res['relaxations']))
    results=res['results'][:5]
    selected_key='app-selected-'+res['request'].get('text','')
    selected=next((r for r in results if r['place']['place_id']==st.session_state.get(selected_key)),None)
    if selected:
        if st.button('← '+selected['place']['name'],key='app-back',help='목록으로 돌아가기'):
            st.session_state.pop(selected_key,None)
            st.rerun()
        detail(selected,res)
        return
    cards=[]
    for r in results:
        color,icon=visual(r)
        cards.append(dict(place_id=r['place']['place_id'],title=str(r['rank'])+' '+r['place']['name'],decision=icon+' '+view.conclusion(r),color=color,meta=compact(r),missing=' · '.join(recommendation.missing_required(r))))
    theme='해안 산책로' if '해안' in (res['request'].get('themes') or []) else '장소'
    label='휠체어로 갈 만한' if '휠체어' in (res['request'].get('user_type') or '') else '가볼 만한'
    selected_id=st.session_state.get('app-last-selected')
    choice=map_background.show(recommendation_map(results,selected_id),key='recommendation-map',mode='list',bounds=[r['place'] for r in results if map_display.valid(r['place'])],cards=cards,heading=f'{label} {theme} {len(results)}곳',selected_id=selected_id)
    if choice is not None and any(r['place']['place_id']==choice for r in results):
        st.session_state[selected_key]=choice
        st.session_state['app-last-selected']=choice
        st.rerun()
