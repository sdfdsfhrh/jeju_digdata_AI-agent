"""실제 API 호출 없이 제한 없음·토큰 집계·월별 경계·캐시를 검증한다."""
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from agent import cache, config, llm


def main():
    assert config.parse_daily_limit('') == 0
    assert config.parse_daily_limit('0') == 0
    assert config.parse_daily_limit('3') == 3
    with tempfile.TemporaryDirectory(dir=Path(__file__).parent/'output') as folder, patch.object(config,'CACHE_PATH',str(Path(folder)/'cache.sqlite')), \
         patch.object(config,'LLM_PROVIDER','openai'), patch.object(config,'LLM_MODEL','gpt-4o-mini'), \
         patch.object(config,'LLM_API_KEY','local-test'), patch.object(config,'LLM_USD_KRW',1400), \
         patch.object(cache,'usage_day',return_value='2026-11-07'):
        payload={'choices':[{'message':{'content':'정상'}}], 'usage':{'prompt_tokens':1000,'completion_tokens':200}}
        fake=Mock(status_code=200,json=lambda:payload)
        with patch.object(llm.requests,'post',return_value=fake) as post, patch.object(config,'LLM_DAILY_LIMIT',0), \
             patch.object(cache,'today_calls',return_value=999999):
            assert llm.ask('test','test1')=='정상'
            assert llm.ask('test','test1')=='정상' and post.call_count==1
            u=cache.monthly_usage()
            assert u['calls']==1 and u['input_tokens']==1000 and u['output_tokens']==200
            assert abs(u['estimated_krw']-0.378)<0.00001
            assert llm.ask('test','test2')=='정상' and post.call_count==2
            assert '참고용' in cache.usage_text()
        with patch.object(config,'LLM_DAILY_LIMIT',2):
            assert llm.ask('test','test3') is None
            assert '상한' in llm.LLMStatus.last_error
        with patch.object(cache,'usage_day',return_value='2026-12-01'):
            assert cache.monthly_usage()['calls']==0
        cache.count_call()  # 이전 기록처럼 토큰 없는 호출
        cache.record_tokens('openai','알수없는모델',100,50)
        assert cache.monthly_usage()['unpriced_calls']==1
        # 제공자별 usage 형식 해석
        for provider, model, usage in [
            ('gemini','gemini-2.5-flash-lite',{'usageMetadata':{'promptTokenCount':10,'candidatesTokenCount':5,'thoughtsTokenCount':2}}),
            ('claude','claude-haiku-4-5',{'usage':{'input_tokens':10,'output_tokens':7}})]:
            response=Mock(status_code=200,json=lambda u=usage:u)
            with patch.object(config,'LLM_PROVIDER',provider), patch.object(config,'LLM_MODEL',model), patch.object(llm.requests,'post',return_value=response):
                llm._post('mock',{}, {})
        assert cache.monthly_usage()['output_tokens']==464
    print('통과: 빈 값/0 무제한·큰 호출 수에서도 진행·양수 일일 제한·캐시 제외·실제 토큰 비용·월 경계·미산정 표시·3개 제공자 usage')


if __name__=='__main__':
    main()
