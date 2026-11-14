import os,sys,json
from pathlib import Path
from unittest.mock import patch
from agent import config,core
from validate_agent import QUESTIONS
config.DB_PATH=str(Path(sys.argv[1]).resolve())
qs=['한림공원 휠체어로 갈 수 있어?','협재해수욕장 휠체어로 갈 수 있어?','성산일출봉 휠체어로 갈 수 있어?']+QUESTIONS
out=[]
with patch.object(config,'KMA_SERVICE_KEY',''),patch.object(config,'KTO_SERVICE_KEY',''):
 for q in qs:
  r=core.run(q,use_llm=False)
  out.append({'question':q,'results':[{'name':x['place']['name'],'grade':x['grade'],'needs':[(n['item'],n['status'],n['effective']) for n in x['access']['needs']],'states':[(t['item'],t['status']) for t in x['access']['table']]} for x in r['results']]})
Path(sys.argv[2]).write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
print('completed',len(out))
