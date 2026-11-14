"""인증정보 없는 오류 분류와 중기06/18시·지역·날짜 매핑 검증."""
import datetime as dt
from unittest.mock import patch
from agent import llm,config,weather,cache
from agent.llm_errors import classify,LLMAPIError

def main():
    examples=[(429,'rate_limit_exceeded','tokens','요청 한도'),
      (429,'insufficient_quota','insufficient_quota','잔액·계정 할당 부족'),
      (429,'credit_balance_exhausted','insufficient_quota','잔액 부족'),
      (404,'model_not_found','invalid_request_error','모델·권한'),
      (403,None,None,'접근 권한'),(401,None,None,'키 인증'),(429,None,None,'한도 원인 미확인')]
    for http,code,kind,expected in examples:
        detail=classify(http,{'error':dict(code=code,type=kind,message='')})
        assert detail['category']==expected
    secret='private-test-value'
    with patch.object(config,'LLM_API_KEY',secret):
        error=LLMAPIError(401,{'error':dict(code=secret,message='bad API key '+secret)})
        assert secret not in str(error) and secret not in str(error.detail)
    with patch.object(llm,'_call',side_effect=LLMAPIError(429,{'error':dict(code='rate_limit_exceeded',type='tokens')})),patch.object(cache,'count_call'),patch.object(cache,'block'):
        ok,msg=llm.test_connection(fresh=True)
        assert not ok and 'rate_limit_exceeded' in msg and llm.LLMStatus.last_error_detail['category']=='요청 한도'
    now=dt.datetime(2026,11,8,20,tzinfo=weather.KST);calls=[]
    def items(url,params,group,fresh=False):
        calls.append((url,params.copy()))
        first=5 if params['tmFc'].endswith('1800') else 4
        if 'getMidLandFcst' in url:
            row={}
            for n in range(first,11):
                if n<=7:row.update({f'rnSt{n}Am':n,f'rnSt{n}Pm':n+10,f'wf{n}Am':'구름많음',f'wf{n}Pm':'흐림'})
                else:row.update({f'rnSt{n}':n+20,f'wf{n}':'흐림'})
        else:row={**{f'taMin{n}':n for n in range(first,11)},**{f'taMax{n}':n+10 for n in range(first,11)}}
        return [row]
    with patch.object(config,'KMA_SERVICE_KEY','test-only'),patch.object(weather,'now_kst',return_value=now),patch.object(weather,'_items',side_effect=items):
        four=weather.forecast(33.4,126.5,'20261112',hours=(13,),address='서귀포시')
        assert four['status']=='조회됨' and four['day_index']==4 and four['pop_max']==14
        assert four['base']=='202611080600 발표' and four['temp_reg_id']=='11G00401'
        assert four['attempted_base']=='202611081800' and four['fallback_note']
        five=weather.forecast(33.4,126.5,'20261113',hours=(9,),address='제주시')
        assert five['base']=='202611081800 발표' and five['pop_max']==5 and five['temp_reg_id']=='11G00201'
        eight=weather.forecast(33.4,126.5,'20261116',hours=(9,),address='제주시')
        assert eight['pop_max']==28 and '하루' in eight['precision']
        assert all(p['regId']=='11G00000' for u,p in calls if 'getMidLandFcst' in u)
        with patch.object(weather,'now_kst',return_value=now.replace(day=9,hour=3)):
            dawn=weather.forecast(33.4,126.5,'20261113',hours=(9,))
            assert dawn['day_index']==5 and dawn['pop_max']==5
        with patch.object(weather,'_items',return_value=[{}]):
            missing=weather.forecast(33.4,126.5,'20261112')
            assert missing['status']=='미확인' and '06시 보완도 실패' in missing['reason']
    print('PASS: LLM 원인7종·키 비노출·실제 점검 캐시 우회·18시D4누락→06시D4·D5최신발표·새벽 매핑·지역코드·빈 값 미확인')

if __name__=='__main__':main()
