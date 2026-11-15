"""대화형 화면. 판정/파서는 기존 core/apply_form 경로를 사용한다."""
import datetime as dt
from contextlib import nullcontext
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
HOME_CSS="""<style>
.stApp:has(.st-key-home-shell){background:#eaf1ed}
.stApp:has(.st-key-home-shell) .block-container{max-width:820px;padding-top:28px!important}
.stApp:has(.st-key-home-shell) .logo{font-size:27px;letter-spacing:-1.2px}
.stApp:has(.st-key-home-shell) .subtitle{color:#61776b;margin-top:3px}
.stApp:has(.st-key-home-shell) [data-testid=stHorizontalBlock]:has(.logo){margin-bottom:13px}
.stApp:has(.st-key-home-shell) [data-testid=stHorizontalBlock]:has(.logo) button{background:#f8fbf8;border-color:#ceddd3;color:#245a44}
.stApp:has(.st-key-home-shell) [data-testid=stCaptionContainer]{color:#5a7465}
.st-key-home-shell{background:#fffdf8;border:1px solid #d5e2d8;border-radius:30px;padding:34px 36px 30px;box-shadow:0 12px 38px rgba(35,77,53,.06);overflow:hidden}
.st-key-home-shell [data-testid=stVerticalBlock]{gap:0.8rem}
.welcome-hero{position:relative;padding:0 0 23px;isolation:isolate}
.welcome-hero::before{content:"";position:absolute;right:7px;top:25px;width:82px;height:82px;border-radius:50%;background:#f6bc70;z-index:-1}
.welcome-hero::after{content:"";position:absolute;right:12px;top:7px;width:38px;height:19px;border-radius:4px 24px 4px 24px;background:#87a78a;transform:rotate(-23deg);z-index:-1}
.welcome-kicker{display:inline-flex;align-items:center;gap:9px;padding:8px 12px;border-radius:20px;background:#e9f1e8;color:#3f6650;font-size:10px;letter-spacing:2.1px;font-weight:650;margin-bottom:23px}
.welcome-kicker::before{content:"";width:6px;height:6px;border-radius:50%;background:#cf6a37}
.welcome-title{font-size:43px!important;line-height:1.36!important;font-weight:800!important;letter-spacing:-1.8px!important;color:#153f31!important;padding:0!important;margin:0 0 18px!important;max-width:580px;word-break:keep-all}
.welcome-title span{color:#28664b}
.welcome-title .welcome-dot{color:#cd6938}
.welcome-description{font-size:15px;line-height:1.85;color:#62796b;margin:0;word-break:keep-all;max-width:520px}
.welcome-tags{display:flex;gap:7px;flex-wrap:wrap;margin-top:20px}
.welcome-tags span{font-size:11px;line-height:1.5;color:#56725f;border:1px solid #dce5d8;border-radius:6px;padding:5px 9px;background:#f3f6ef}
.st-key-home-options{border-top:1px solid #e3e9dd;padding-top:22px}
.welcome-options-title{font-size:16px;font-weight:750;color:#234b38;letter-spacing:-.3px;margin:0 0 8px}
.st-key-home-options [data-testid=stWidgetLabel] p{font-size:13px;font-weight:650;color:#52695b}
.st-key-home-options [data-testid=stButtonGroup]>div{gap:8px}
.st-key-home-options button[data-variant=pills]{border:1px solid #d3dfd1;background:#fffefa;color:#365744;min-height:42px!important;padding:7px 17px!important;border-radius:14px!important;transition:background .15s,border-color .15s,box-shadow .15s}
.st-key-home-options button[data-variant=pills]:hover{background:#edf4e9;border-color:#91b79a}
.st-key-home-options button[aria-checked=true]{background:#205b40!important;border-color:#205b40!important;color:#fff!important;box-shadow:0 3px 9px rgba(29,83,56,.12)}
.st-key-home-options button[aria-checked=true] p{color:#fff!important}
.st-key-home-options button:focus-visible,.st-key-home-examples button:focus-visible{outline:3px solid #d4824f!important;outline-offset:3px}
.welcome-examples-label{font-size:12px;color:#7c7e64;margin:13px 0 1px}
.st-key-home-examples{gap:8px!important;flex-wrap:wrap!important}
.st-key-home-examples button{background:#f7eddd;border:1px solid #ead6b8;color:#8b522f;border-radius:12px!important;min-height:40px!important;padding:7px 13px!important;font-size:13px}
.st-key-home-examples button:hover{background:#f2dfc4;border-color:#dcb78c;color:#713f24}
.stApp:has(.st-key-home-shell) [data-testid=stBottom],.stApp:has(.st-key-home-shell) [data-testid=stBottomBlockContainer],.stApp:has(.st-key-home-shell) .privacy{background:#eaf1ed!important}
.stApp:has(.st-key-home-shell) [data-testid=stBottomBlockContainer]{max-width:820px;margin:auto;padding-top:14px}
.stApp:has(.st-key-home-shell) [data-testid=stChatInput]{border:1px solid #c2d6c8!important;box-shadow:0 5px 20px rgba(35,77,53,.07);border-radius:20px!important}
.stApp:has(.st-key-home-shell) [data-testid=stChatInputSubmitButton]{background:#205b40!important}
.stApp:has(.st-key-home-shell) .privacy{color:#607b68;width:100%;padding:9px 18px;bottom:0}
.st-key-home-question{margin-top:4px}
.st-key-home-question [data-testid=stChatInput]{min-height:65px}
@media(max-width:640px){
 .stApp:has(.st-key-home-shell) .block-container{padding:19px 14px 145px!important}
 .stApp:has(.st-key-home-shell) .logo{font-size:25px}
 .st-key-home-shell{border-radius:24px;padding:25px 22px 23px}
 .welcome-hero{padding-bottom:20px}
 .welcome-kicker{font-size:9px;letter-spacing:1.6px;padding:7px 10px;margin-bottom:22px}
 .welcome-hero::before{width:48px;height:48px;right:0;top:7px}
 .welcome-hero::after{width:25px;height:13px;right:0;top:-5px}
 .welcome-title{font-size:32px!important;letter-spacing:-1.3px!important;line-height:1.4!important;margin-bottom:16px!important}
 .welcome-description{font-size:13px;line-height:1.8}
 .welcome-tags{margin-top:17px;gap:5px}.welcome-tags span{font-size:10px;padding:4px 7px}
 .st-key-home-options{padding-top:18px}.welcome-options-title{font-size:15px}
 .st-key-home-options [data-testid=stButtonGroup]>div{gap:6px}
 .st-key-home-options button[data-variant=pills]{padding:7px 12px!important;min-height:41px!important}
 .st-key-home-examples button{padding:7px 10px!important}
 .stApp:has(.st-key-home-shell) [data-testid=stBottomBlockContainer]{padding-left:14px;padding-right:14px}
}
@media(max-width:380px){.st-key-home-shell{padding:23px 17px}.welcome-title{font-size:29px!important}.welcome-hero::before{opacity:.55}.welcome-hero::after{opacity:.7}.st-key-home-options button[data-variant=pills]{padding:7px 9px!important}}
</style>"""
st.html(HOME_CSS)
st.session_state.setdefault('conversation',[])
a,b=st.columns([3,1],gap='small',vertical_alignment='center')
with a:st.markdown('<div class="logo">닿는<span>제주</span></div><div class="subtitle">휠체어·유아차 여행 안내</div>',unsafe_allow_html=True)
with b:
 if st.button('자료 안내'):show_information()
 st.caption("LLM 사용 중" if config.llm_enabled() else "규칙 모드")
history=st.session_state['conversation']
today=dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date()
date=None;slot=None
EXAMPLES=[('해안 산책로 ↗','수동휠체어로 갈 수 있는 해안 산책로 추천해줘'),('협재해수욕장 ↗','협재해수욕장 휠체어로 갈 수 있어?'),('한림공원 ↗','한림공원 휠체어로 갈 수 있어?')]
with st.container(key='home-shell') if not history else nullcontext():
 if not history:
  st.markdown('<div class="welcome-hero"><div class="welcome-kicker">JEJU, BARRIER-FREE</div><h1 class="welcome-title">바퀴가 닿는 제주,<br><span>먼저 확인하고 떠나요<span class="welcome-dot">.</span></span></h1><p class="welcome-description">경사, 계단, 화장실, 주차를<br>원본 조사 자료로 알려 드려요.</p><div class="welcome-tags"><span>코스와 경사</span><span>주차와 화장실</span><span>방문일 날씨</span></div></div>',unsafe_allow_html=True)
 with st.container(key='home-options') if not history else nullcontext():
  if not history:st.markdown('<div class="welcome-options-title">어떤 여행을 준비하시나요?</div>',unsafe_allow_html=True)
  st.session_state.pop('more_who',None)  # 이전 화면 세션의 숨은 선택값 제거
  st.pills('누구와',['휠체어','유아차','어르신'],key='who')
  st.pills('언제',['오늘','내일','이번 주말','날짜'],key='when')
  if st.session_state.get('when')=='날짜':
   date=st.date_input('방문 날짜',value=None,min_value=today,max_value=today+dt.timedelta(days=10))
   slot=st.selectbox('시간대',['문장에서 자동']+list(TIME_SLOTS))
 if not history:
  st.markdown('<div class="welcome-examples-label">이런 질문으로 시작해 보세요</div>',unsafe_allow_html=True)
  with st.container(horizontal=True,key='home-examples'):
   for label,q in EXAMPLES:
    if st.button(label):st.session_state['pending']=q
with st.container(key='home-question') if not history else nullcontext():
 question=st.chat_input('어디로 가고 싶으세요?') or st.session_state.pop('pending',None)
if question:
 form=question_form(question,st.session_state.get('who'),st.session_state.get('when'),date,slot,today)
 with st.spinner('자료를 확인하고 있어요…'):
  try:
   city = {'서귀포시': '서귀포시', '서귀포': '서귀포시', '제주시': '제주시'}.get(question.strip())
   if city:
    form['region'] = city
   res=core.run('' if city else question,form=form,use_llm=config.llm_enabled())
   history.append(dict(question=question,result=res));st.session_state['res']=res
  except data.DataError as e:st.error(str(e))
 st.rerun()
for i,turn in enumerate(history):
 with st.chat_message('user'):st.write(turn['question'])
 with st.chat_message('assistant'):chat_view.render(turn['result'],i)
notice='개인정보는 입력하지 마세요 · '+SOURCE_CREDIT
st.markdown('<div class="privacy">'+notice+'</div>',unsafe_allow_html=True)
