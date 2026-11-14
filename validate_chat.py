"""대화 화면·기록·상세 분리·규칙 결과 보존 검사."""
from pathlib import Path
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from agent import config,core
import map_background

def main():
 with patch.object(config,'KMA_SERVICE_KEY',''),patch.object(config,'KTO_SERVICE_KEY',''),patch.object(config,'llm_enabled',return_value=False):
  res=core.run('한림공원 휠체어로 갈 수 있어?',use_llm=False)
  with patch.object(map_background,'show'),patch.object(core,'run',return_value=res):
   at=AppTest.from_file(str(Path('app.py').resolve()),default_timeout=30).run()
   assert not at.exception and len(at.chat_input)==1 and not at.title
   assert not any(x.label=='데이터·시스템 정보' for x in at.expander)
   assert not any('01 장소를 말하고' in x.value for x in at.markdown)
   assert not any(x.label=='이용자 유형' for x in at.selectbox)
   assert not any(b.label=='더보기' for b in at.button)
   at.chat_input[0].set_value('한림공원 휠체어로 갈 수 있어?').run()
   assert not at.exception and len(at.chat_message)==2
   at.chat_input[0].set_value('한림공원 다시 확인').run()
   assert not at.exception and len(at.chat_message)==4
   assert len(at.session_state['conversation'])==2
   assert sum(b.label=='원문 근거' for b in at.button)==2
   assert not any('외부 API로' in m.value for m in at.markdown)
   at.session_state['conversation']=[];at.run()
   next(b for b in at.button if b.label=='협재해수욕장 ↗').click().run()
   assert not at.exception and at.session_state['conversation'][0]['question'].startswith('협재')
 from ui_controls import question_form
 from agent.parser import apply_form,rule_parse
 for text,who,want in [('산책','휠체어','수동휠체어'),('전동휠체어 산책','휠체어','전동휠체어'),('시각장애 여행','휠체어','시각장애'),('청각장애 여행','어르신','청각장애'),('산책','어르신','시니어')]:
  assert apply_form(rule_parse(text,[]),question_form(text,who)).user_type==want
 import chat_view
 assert chat_view.sensory_question(dict(request=dict(text='저시력 어머니와 여행')))
 fake=dict(item_id='KTO-test',item='점자블록',value_raw='입구 점자블록 설치',origin='한국관광공사',file_name='kto_detail.csv',source_locator='row 2')
 with patch.object(chat_view.data,'items',return_value=[fake]):
  assert chat_view.sensory_sources(dict(results=[dict(place=dict(name='모의장소',place_id='mock'))]))==[('모의장소',fake)]
 with patch.object(config,'llm_enabled',return_value=False),patch.object(map_background,'show'):
  at=AppTest.from_file(str(Path('app.py').resolve()),default_timeout=30).run()
  from copy import deepcopy
  sensory=deepcopy(res);sensory['request']['text']='한림공원 시각장애 안내';sensory['request']['user_type']='시각장애'
  at.session_state['conversation']=[dict(question=sensory['request']['text'],result=sensory)];at.run()
  assert not at.exception and any(x.value==chat_view.SENSORY_NOTICE for x in at.info)
 with patch.object(config,'llm_enabled',return_value=False):
  at=AppTest.from_file(str(Path('app.py').resolve()),default_timeout=30).run()
  at.session_state['res']=res
  next(b for b in at.button if b.label=='자료 안내').click().run()
  assert not at.exception
  assert any('Agent 작업 과정' in x.value for x in at.markdown)
  assert any('이 답에 쓰인 데이터:' in x.value for x in at.caption)
  assert any('공공데이터포털 주차장정보' in x.value for x in at.caption)
 print('PASS: 대화 입력·2개 기록·상세 widget 분리·바로가기 실행·키 없는 안내')
if __name__=='__main__':main()
