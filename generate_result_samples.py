"""실제 실행 결과·표시 텍스트 저장. 인증정보는 저장하지 않는다."""
import json,sys
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
from agent import core
import result_view

def main():
    target=Path('docs/sample_results');target.mkdir(parents=True,exist_ok=True)
    checks=Path('output/validation');checks.mkdir(parents=True,exist_ok=True)
    for name,q in [('hanlim','한림공원 휠체어로 갈 수 있어?'),('coastal','내일 오후 수동휠체어로 장애인 화장실 있는 해안 산책로')]:
        res=core.run(q,use_llm=True)
        (checks/(name+'_layout.json')).write_text(json.dumps(res,ensure_ascii=False,indent=2),encoding='utf-8')
        (target/(name+'_20261108.txt')).write_text(result_view.full_text(res),encoding='utf-8')
        print(name,res['mode'],len(res['results']),res['elapsed_ms'],res['goal'])

if __name__=='__main__':main()
