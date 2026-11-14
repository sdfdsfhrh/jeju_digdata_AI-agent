"""모델 이행 시 요청 인자와 긴 문맥 비용 검증. 실제 API 호출 없음."""
import tempfile
from pathlib import Path
from unittest.mock import patch
from agent import cache, config, llm


def main():
    responses = {
        'openai': {'choices': [{'message': {'content': '{"ok":true}'}}]},
        'gemini': {'candidates': [{'content': {'parts': [{'text': '{"ok":true}'}]}}]},
        'claude': {'content': [{'type': 'thinking'}, {'type': 'text', 'text': '{"ok":true}'}]},
    }
    with patch.object(config, 'LLM_MODEL', ''):
        for provider in responses:
            with patch.object(config, 'LLM_PROVIDER', provider), patch.object(llm, '_post', return_value=responses[provider]) as post:
                assert llm._call('JSON', '점검', True, 100) == '{"ok":true}'
                body = post.call_args.args[2]
                if provider == 'openai':
                    assert body['reasoning_effort'] == 'none'
                    assert body['max_completion_tokens'] == 100 and 'max_tokens' not in body
                elif provider == 'claude':
                    assert 'temperature' not in body and body['output_config']['effort'] == 'low'
                else:
                    assert body['generationConfig']['responseMimeType'] == 'application/json'
    with tempfile.TemporaryDirectory(dir='output') as folder, patch.object(config, 'CACHE_PATH', str(Path(folder)/'usage.sqlite')), patch.object(config, 'LLM_USD_KRW', 1):
        cache.record_tokens('claude', 'claude-haiku-5-5', 100001, 1000)
        cache.record_tokens('openai', 'gpt-6-luna', 272001, 1000)
        assert abs(cache.monthly_usage()['estimated_krw'] - (0.0525005 + 0.0551502)) < 1e-9
    print('통과: 기본 모델 요청 호환·JSON·추론 블록 제외·긴 문맥 단가')


if __name__ == '__main__':
    main()
