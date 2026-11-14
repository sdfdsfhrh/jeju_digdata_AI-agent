"""대화형 화면. 판정/파서는 기존 core/apply_form 경로를 사용한다."""
import datetime as dt
import streamlit as st
from agent import config,core,data
from agent.parser import TIME_SLOTS
from ui_controls import question_form
from chat_footer import show_information,SOURCE_CREDIT
import chat_view
st.set_page_config(page_title='닿는제주',page_icon='♿',layout='centered')
CSS="""<style>
#MainMenu,footer,[data-testid=stToolbar],[data-testid=stStatusWidget],.stDeployButton,header[data-testid=stHeader]{display:none!important}
.block-container{max-width:720px;padding:30px 20px 130px!important}
[data-testid=stHorizontalBlock]:has(.logo){flex-wrap:nowrap!important}[data-testid=stHorizontalBlock]:has(.logo)>[data-testid=stColumn]{min-width:0!important;flex:1!important}[data-testid=stHorizontalBlock]:has(.logo)>[data-testid=stColumn]:last-child{flex:0 0 100px!important;width:100px!important}.logo{color:#085041;font-size:23px;font-weight:800}.logo span{color:#D85A30}.subtitle{font-size:12px;color:#79887e}
.eyebrow{letter-spacing:3px;color:#74887b;font-size:12px;margin:48px 0 24px}.hero{font-size:42px;line-height:1.4;letter-spacing:-1.5px;font-weight:800;color:#183F32;margin:0 0 18px}.intro{color:#6b7d72;line-height:1.8;margin-bottom:24px}
button{min-height:44px!important;border-radius:24px!important} [data-testid=stPills]{flex-wrap:wrap!important}
[data-testid=stChatMessageContent]{min-width:0!important;width:100%!important}[data-testid=stChatMessage] p{white-space:normal!important;overflow-wrap:anywhere!important;word-break:break-word!important}[data-testid=stChatMessage]{background:white;border:1px solid #e1e6de;border-radius:24px;padding:20px;margin:18px 0}
[data-testid=stChatMessage]:has([data-testid=stChatMessageAvatarUser]){background:#085041;color:white;margin-left:auto!important;width:82%!important;max-width:82%!important;box-sizing:border-box;border-bottom-right-radius:5px}
[data-testid=stChatMessage]:has([data-testid=stChatMessageAvatarUser]) p{color:white}
[data-testid=stChatMessageAvatarUser],[data-testid=stChatMessageAvatarAssistant]{display:none}
[data-testid=stChatInput]{border-radius:26px!important;background:white;border:1px solid #cdd9cd!important}
[data-testid=stChatInputSubmitButton]{background:#085041!important;color:white!important;border-radius:18px!important}
.privacy{position:fixed;bottom:4px;left:50%;transform:translateX(-50%);width:min(1160px,96vw);font-size:10px;line-height:1.45;white-space:normal;word-break:keep-all;text-align:center;color:#748575;background:#F7F6F2;z-index:999;padding:4px}
[data-testid=stBottomBlockContainer]{padding-bottom:42px!important;background:#F7F6F2}
.place-card{border:1px solid #e0e6dc;border-radius:18px;padding:18px;background:white;margin:12px 0}.place-heading{font-size:20px;font-weight:750;display:flex;justify-content:space-between;gap:10px;align-items:center}.place-card p{font-size:13px;color:#718175;margin:12px 0}.badge{font-size:12px;padding:6px 9px;border-radius:20px;white-space:nowrap}.ok{background:#085041;color:white}.care{background:#dcebdd;color:#28513b}.check{background:#fae7dd;color:#a54521}.hard{background:#f8dddd;color:#a32f39}.facilities{display:flex;flex-wrap:wrap;gap:8px}.facility{font-size:12px;color:#295c49}.muted{color:#8c948e}.required{color:#a32f39!important}
iframe{border-radius:18px}.app-tiles{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:6px}.app-tile{background:#f4f6f1;padding:12px 5px;border-radius:12px;font-size:13px}.app-tile-value{overflow-wrap:anywhere}.app-decision{background:#e5eee4;padding:15px;border-radius:12px;margin:12px 0}.app-note{font-size:11px;color:#7c887e;line-height:1.7}.app-warning{padding:12px;border:1px solid #e4e6df;border-radius:12px;margin:10px 0}.app-meta{font-size:12px;color:#778579}
@media(max-width:640px){.privacy{font-size:8px;line-height:1.5;width:calc(100vw - 20px)}.block-container{padding:20px 12px 140px!important}.hero{font-size:32px}.eyebrow{margin-top:32px}.place-heading{font-size:18px}[data-testid=stChatMessage]{padding:12px}.facility{font-size:11px}}
</style>"""
st.markdown(CSS,unsafe_allow_html=True)
st.session_state.setdefault('conversation',[])
a,b=st.columns([3,1],gap='small',vertical_alignment='center')
with a:st.markdown('<div class="logo">닿는<span>제주</span></div><div class="subtitle">휠체어·유아차 여행 안내</div>',unsafe_allow_html=True)
with b:
 if st.button('자료 안내'):show_information()
history=st.session_state['conversation']
if not history:st.markdown('<div class="eyebrow">JEJU, BARRIER-FREE</div><div class="hero">바퀴가 닿는 제주,<br>먼저 확인하고 떠나요.</div><div class="intro">경사, 계단, 화장실, 주차를 원본 조사 자료로 알려 드려요.</div>',unsafe_allow_html=True)
st.session_state.pop('more_who',None)  # 이전 화면 세션의 숨은 선택값 제거
st.pills('누구와',['휠체어','유아차','어르신'],key='who')
st.pills('언제',['오늘','내일','이번 주말','날짜'],key='when')
today=dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date()
date=None;slot=None
if st.session_state.get('when')=='날짜':
 date=st.date_input('방문 날짜',value=None,min_value=today,max_value=today+dt.timedelta(days=10))
 slot=st.selectbox('시간대',['문장에서 자동']+list(TIME_SLOTS))
EXAMPLES=[('해안 산책로 ↗','수동휠체어로 갈 수 있는 해안 산책로 추천해줘'),('협재해수욕장 ↗','협재해수욕장 휠체어로 갈 수 있어?'),('한림공원 ↗','한림공원 휠체어로 갈 수 있어?')]
if not history:
 with st.container(horizontal=True):
  for label,q in EXAMPLES:
   if st.button(label):st.session_state['pending']=q
question=st.chat_input('어디로 가고 싶으세요?') or st.session_state.pop('pending',None)
if question:
 form=question_form(question,st.session_state.get('who'),st.session_state.get('when'),date,slot,today)
 with st.spinner('자료를 확인하고 있어요…'):
  try:
   res=core.run(question,form=form,use_llm=config.llm_enabled())
   history.append(dict(question=question,result=res));st.session_state['res']=res
  except data.DataError as e:st.error(str(e))
 st.rerun()
for i,turn in enumerate(history):
 with st.chat_message('user'):st.write(turn['question'])
 with st.chat_message('assistant'):chat_view.render(turn['result'],i)
notice='개인정보는 입력하지 마세요 · '+SOURCE_CREDIT
st.markdown('<div class="privacy">'+notice+'</div>',unsafe_allow_html=True)
