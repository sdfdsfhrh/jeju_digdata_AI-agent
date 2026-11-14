"""LLM 오류 본문의 코드로 원인을 구분. 원문 본문·키·계정 ID는 기록하지 않는다.

공식: https://developers.openai.com/api/docs/guides/error-codes (2026-11-08)
"""
import re
from . import config

def safe_code(value):
    value=str(value or '')
    for name in ('LLM_API_KEY','KMA_SERVICE_KEY','KTO_SERVICE_KEY'):
        secret=getattr(config,name,'')
        if secret and secret in value:return '비공개값 생략'
    return value if re.fullmatch(r'[A-Za-z0-9_.-]{1,80}',value) and not value.startswith(('sk-','AIza','org-','proj_')) else '미제공'

def classify(status,payload):
    error=payload.get('error',{}) if isinstance(payload,dict) else {}
    if not isinstance(error,dict):error={}
    code=safe_code(error.get('code') or error.get('status'))
    kind=safe_code(error.get('type'))
    raw=str(error.get('message') or '').lower()  # 분류에만 쓰며 반환/저장하지 않음.
    combined=(code+' '+kind+' '+raw).lower()
    retry=False
    if 'credit_balance_exhausted' in combined or 'credit balance is too low' in combined:
        category='잔액 부족';message='선불 크레딧 잔액 소진. 결제·잔액 확인 필요'
    elif any(x in combined for x in ('organization_spend_limit_exceeded','project_spend_limit_exceeded','budget_exceeded')):
        category='계정 결제 한도';message='제공자 계정/프로젝트의 결제 한도 도달. 앱의 월 차단 기능 아님'
    elif 'organization_usage_limit_exceeded' in combined:
        category='계정 사용 한도';message='제공자가 정한 계정 사용 할당 도달'
    elif 'insufficient_quota' in combined or 'check your plan and billing' in combined:
        category='잔액·계정 할당 부족';message='요청 속도 제한과 다름. 잔액/결제/할당의 세부 원인은 응답만으로 확정 불가'
    elif any(x in combined for x in ('rate_limit_exceeded','rate_limit_error','slow_down','too many requests')):
        category='요청 한도';message='요청/토큰 속도 제한. 잠시 뒤 다시 시도';retry=True
    elif code in ('model_not_found','model_not_available') or ('model' in raw and any(x in raw for x in ('access','permission','not exist'))):
        category='모델·권한';message='모델 미존재 또는 계정 모델 권한 없음(응답으로 둘을 확정 구분하지 못할 수 있음)'
    elif status==401:
        category='키 인증';message='API 키 인증 실패. 키 값은 표시하지 않음'
    elif status==403:
        category='접근 권한';message='API/지역/프로젝트 접근 권한 확인 필요(모델 권한으로 단정하지 않음)'
    elif status==429 or code=='RESOURCE_EXHAUSTED':
        category='한도 원인 미확인';message='한도 응답이지만 요청 속도/잔액/할당 세부 원인 미제공'
    else:
        category='기타 API 오류';message='응답 코드·요청 설정을 확인하세요'
    return dict(http_status=status,code=code,type=kind,category=category,message=message,retryable=retry)

def describe(detail):
    return f"HTTP {detail['http_status']} · 코드 {detail['code']} · 유형 {detail['type']} · 분류: {detail['category']} — {detail['message']}"

class LLMAPIError(RuntimeError):
    def __init__(self,status,payload):
        self.detail=classify(status,payload)
        super().__init__(describe(self.detail))
