"""보조 기능 제거 뒤 유지해야 하는 결과·화면·데이터 계약 검증."""
import json
from pathlib import Path
from unittest.mock import patch
from agent import core,config


def main():
    before=json.loads(Path('docs/REGRESSION_BASELINES.json').read_text(encoding='utf-8'))
    after=[]
    with patch.dict(config._FILE_API_KEYS, {"VWORLD_API_KEY": ""}),patch.object(config,'KMA_SERVICE_KEY',''),patch.object(config,'KTO_SERVICE_KEY',''):
        for row in before:
            result=core.run(row['question'],use_llm=False)
            signature=[(r['place']['place_id'],r['grade'],[(t['item'],t['status']) for t in r['access']['table']]) for r in result['results']]
            assert json.loads(json.dumps(signature,ensure_ascii=False))==row['signature']
            assert all(step['ok'] for step in result['trace'])
            assert result['limits'][-1]=='응급 상황에서는 119에 연락하세요.'
            after.append(dict(question=row['question'],signature=signature,trace=[s['tool'] for s in result['trace']],limits=result['limits']))
    Path('output/validation/feature_removal_after.json').write_text(json.dumps(after,ensure_ascii=False,indent=2),encoding='utf-8')
    print('PASS: 지정2질문 기존 순서·등급·시설 상태 유지, trace 정상, 마지막119 안내')

if __name__=='__main__':main()
