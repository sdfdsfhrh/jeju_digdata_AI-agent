"""실제 LLM 실행 결과와 새 추천 순위 표 저장(키 출력 없음)."""
import json
from pathlib import Path
from agent import core
from result_view import full_text

QUESTIONS=['휠체어가 갈 수 있는 곳 해안가 산책하고 싶어','장애인 주차 필수 휠체어가 갈 수 있는 곳 해안가 산책하고 싶어','한림공원 휠체어로 갈 수 있어?']

def main():
    table=[]
    for i,q in enumerate(QUESTIONS,1):
        res=core.run(q,use_llm=True)
        Path(f'output/validation/fix27_actual_{i}.json').write_text(json.dumps(res,ensure_ascii=False,indent=2),encoding='utf-8')
        Path(f'docs/sample_results/fix27_{i}_20261108.txt').write_text(full_text(res),encoding='utf-8')
        table += [f'#### 질문 {i}: {q}',f"실제 실행 모드: {res['mode']} / 조건 해석: {res['request']['parsed_by']}",'|순위|장소|이용 판단|빨강 구간|주황 구간|시설 등급(보존)|','|---|---|---|---:|---:|---|']
        for r in res['results'][:5]:
            c=r['course_counts'];red=c['red'] if c['known'] else '미확인';orange=c['orange'] if c['known'] else '미확인'
            table.append(f"|{r['rank']}|{r['place']['name']}|{r['use_assessment']['text'].split(' — ')[0]}|{red}|{orange}|{r['grade']}|")
        table.append('')
        print('saved',i,res['mode'],flush=True)
    Path('output/validation/fix27_ranking_tables.md').write_text('\n'.join(table),encoding='utf-8')

if __name__=='__main__':main()
