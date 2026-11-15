"""배경 타일만 처리. 키는 서버 메모리에 두고 이미지 바이트만 컴포넌트로 전달한다."""
import base64
from collections import deque
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlsplit

import requests
import streamlit as st
import streamlit.components.v1 as components
import pydeck as pdk
from agent import config

# 공식 WMTS 가이드: https://www.vworld.kr/dev/v4dv_wmtsguide_s001.do
# {key}/{layer}/{tileMatrix=z}/{tileRow=y}/{tileCol=x}.{tileType}
# 공식 현재 레이어는 Base/white/midnight/Hybrid/Satellite. gray는 별도 목록에 없음.
LAYERS={'Base':'png','white':'png','midnight':'png','Satellite':'jpeg','Hybrid':'png'}
FAILURES=deque(maxlen=20)  # 좌표·오류 종류만. URL/키/응답 원문은 기록하지 않음.
ROOT=Path(__file__).resolve().parent
_component=components.declare_component('jeju_map',path=str(ROOT/'map_component'))

def tile_spec(style='일반'):
    return ['Satellite','Hybrid'] if style=='위성' else ['Base']

def valid_tile(t):
    return isinstance(t,list) and len(t)==4 and t[0] in LAYERS and all(type(x) is int for x in t[1:]) and 6<=t[1]<=(18 if t[0] in ('white','midnight') else 19) and all(0<=x<2**t[1] for x in t[2:])

@st.cache_data(ttl=300,max_entries=512,show_spinner=False)
def _tile(layer,z,x,y,origin,_key):
    """예외 URL/본문을 절대 화면·로그로 내보내지 않는다. 캐시는 메모리에만 둔다."""
    try:
        # 등록 서비스 URL은 실제 운영 URL만 설정. 다른 도메인을 가장하지 않는다.
        registered=config.get('VWORLD_SERVICE_URL') or origin
        parts=urlsplit(registered)
        headers={'Referer':registered+'/'} if parts.scheme in ('http','https') and parts.netloc and '\n' not in registered and '\r' not in registered else {}
        url=f'https://api.vworld.kr/req/wmts/1.0.0/{_key}/{layer}/{z}/{y}/{x}.{LAYERS[layer]}'
        r=requests.get(url,headers=headers,timeout=(3,5))
        b=r.content
        png=b.startswith(b'\x89PNG\r\n\x1a\n');jpeg=b.startswith(b'\xff\xd8\xff')
        if r.status_code!=200 or not (png or jpeg) or len(b)>2_000_000:
            FAILURES.append((layer,z,x,y,'HTTP '+str(r.status_code) if r.status_code!=200 else '이미지 아닌 응답'))
            return None
        return 'data:image/'+('png' if png else 'jpeg')+';base64,'+base64.b64encode(b).decode('ascii')
    except Exception as e:
        FAILURES.append((layer,z,x,y,type(e).__name__))
        return None

def fetch_tiles(tiles,origin,key):
    safe=[t for t in tiles[:40] if valid_tile(t)]
    with ThreadPoolExecutor(max_workers=6) as pool:
        values=list(pool.map(lambda t:_tile(*t,origin,_key=key),safe))
    return {'/'.join(map(str,t)):v for t,v in zip(safe,values)},any(v is None for v in values)

def show(deck,*,key,height=360,start_view=None,mode='course',bounds=None,cards=None,heading='',selected_id=None):
    """pydeck JSON을 로컬 deck.gl 컴포넌트로 렌더. TileLayer 오류도 자동 대체한다."""
    style=st.radio('배경지도', ['일반','위성'],horizontal=True,key='map-style-'+key,label_visibility='collapsed')
    key_value=config.get('VWORLD_API_KEY')
    state_key='map-tiles-'+key
    state=st.session_state.setdefault(state_key,{'tiles':{},'fallback':False,'request':None})
    # 인증 키 변경 시 이전 이미지/실패 캐시를 세션에서 재사용하지 않는다.
    fingerprint=__import__('hashlib').sha256(key_value.encode()).hexdigest()[:12]
    if state.get('fingerprint')!=fingerprint:
        state.update(tiles={},fallback=False,request=None,fingerprint=fingerprint)
        _tile.clear()
    if state['fallback']:
        st.caption('브이월드 타일 응답: ' + (state.get('reason') or '확인 불가'))
    if key_value and state['fallback'] and st.button('브이월드 다시 시도',key='retry-'+key):
        state.update(tiles={},fallback=False,request=None,reason='')
        _tile.clear()
        st.rerun()
    payload=json.loads(deck.to_json())
    # 키가 들어간 URL은 pydeck JSON·HTML·브라우저 요청에 만들지 않는다.
    payload['layers']=[json.loads(pdk.Layer('TileLayer',data='vworld://'+layer+'/{z}/{x}/{y}',id='background-'+layer,min_zoom=6,max_zoom=18 if layer=='white' else 19,tile_size=256).to_json()) for layer in tile_spec(style)]+payload['layers']
    value=_component(spec=payload,height=height,provider='브이월드' if key_value and not state['fallback'] else 'CARTO',style=style,
                     tiles=state['tiles'],fallback=state['fallback'],failure_reason=state.get('reason',''),start_view=start_view,mode=mode,bounds=bounds or [],cards=cards or [],heading=heading,selected_id=selected_id,responsive=True,key=key,default=None)
    if isinstance(value,dict) and value.get('id')!=state['request'] and value.get('selected') is not None:
        state['request']=value.get('id')
        return value['selected']
    if isinstance(value,dict) and value.get('id')!=state['request'] and isinstance(value.get('tiles'),list) and key_value and not state['fallback']:
        state['request']=value.get('id')
        with st.spinner('배경지도 불러오는 중…'):
            tiles,failed=fetch_tiles(value['tiles'],str(value.get('origin',''))[:300],key_value)
        state['tiles'].update(tiles)
        state['fallback']=failed
        if failed:state['reason']=FAILURES[-1][-1] if FAILURES else '타일 로딩 실패'
        st.rerun()

