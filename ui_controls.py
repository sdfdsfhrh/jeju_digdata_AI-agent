"""화면 선택값만 기존 apply_form에 전달. 문장 파싱/판정 규칙은 변경하지 않는다."""
import datetime as dt

def form_values(who=None,more=None,when=None,date=None,slot=None,today=None):
 today=today or dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date()
 day={'오늘':today,'내일':today+dt.timedelta(days=1),'이번 주말':today+dt.timedelta(days=0 if today.weekday()==6 else (5-today.weekday())%7)}.get(when)
 if when=='날짜':day=date
 return {'user_type':{'휠체어':'수동휠체어','유아차':'영유아동반','어르신':'시니어'}.get(who) or more,'date':day.strftime('%Y%m%d') if day else None,'time_slot':slot if when=='날짜' and slot!='문장에서 자동' else None}


def question_form(question,who=None,when=None,date=None,slot=None,today=None):
 """UI 선택 전달만 조정. 전동/감각장애 문장은 기존 규칙 파서가 읽도록 둔다."""
 from agent.parser import rule_parse
 form=form_values(who,None,when,date,slot,today)
 parsed=rule_parse(question,[])
 if parsed.user_type in ('시각장애','청각장애') or (who=='휠체어' and parsed.user_type=='전동휠체어'):
  form['user_type']=None
 return form
