"""대표 질문 10개 실제 LLM/규칙 비교. 키·오류 원문은 저장하지 않는다."""
import json
from pathlib import Path
from unittest.mock import patch
from agent import config, core
from agent.parser import Request
from validate_agent import QUESTIONS


def signature(result):
    return [(r['place']['place_id'],r['grade']) for r in result['results']]


def main():
    assert config.llm_enabled(), 'LLM 설정 필요'
    directory=Path('output/validation/llm_comparison')
    directory.mkdir(parents=True, exist_ok=True)
    report=[]
    for i, question in enumerate(QUESTIONS,1):
        live=core.run(question, use_llm=True)
        rule=core.run(question, use_llm=False)
        # 파서 차이와 판정 엔진 차이를 구분: LLM이 해석한 조건을 고정한 규칙 실행.
        with patch.object(core,'parse',return_value=(Request(**live['request']), '비교용 동일 조건')):
            fixed=core.run(question,use_llm=False)
        for mode,res in [('llm',live),('rules',rule)]:
            (directory/f'{i:02}_{mode}.json').write_text(json.dumps(res,ensure_ascii=False,indent=2),encoding='utf-8')
        fields=['user_type','needs','date','time_slot','region','themes']
        row=dict(no=i,question=question or '(빈 문장)',mode=live['mode'], parsed_by=live['request']['parsed_by'],
                 condition_differences={k:{'llm':live['request'][k],'rules':rule['request'][k]} for k in fields if live['request'][k]!=rule['request'][k]},
                 same_ranking=signature(live)==signature(rule), same_conditions_same_ranking=signature(live)==signature(fixed),
                 llm_top=[r['place']['name'] for r in live['results'][:3]],rule_top=[r['place']['name'] for r in rule['results'][:3]],
                 llm_ms=live['elapsed_ms'],rule_ms=rule['elapsed_ms'],slowest=live['slowest_step'],
                 explanation=next(s['output'] for s in live['trace'] if s['tool']=='explain'))
        report.append(row)
        (directory/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(f"{i}/10 {row['mode']} 파서={row['parsed_by']} 순위동일={row['same_ranking']} 동일조건동일순위={row['same_conditions_same_ranking']} {row['llm_ms']}ms",flush=True)
    print('비교 완료: '+str(directory/'report.json'))


if __name__=='__main__': main()
