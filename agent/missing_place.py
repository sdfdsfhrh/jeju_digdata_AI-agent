"""위치는 찾았으나 판정 자료가 없는 질문의 안내. 시설 판정은 하지 않는다."""

def context(name, req, location=None, radius=None):
    user = req.user_type or '휠체어'
    if '휠체어' in user:user='휠체어'
    last=name[-1:]
    particle='는' if last and '가'<=last<='힣' and (ord(last)-ord('가'))%28==0 else '은'
    return dict(name=name, location=location, radius_km=radius,
                message=f'{name}{particle} {user} 이용 여부를 판단할 조사 자료가 없어요.',
                alternatives_heading='근처에서 확인 가능한 곳이에요.',
                instruction='질문한 장소는 판정하지 않는다. 자료 없음 안내를 맨 먼저, alternatives_heading을 바로 다음 문장으로 말한 뒤 대안 목록을 제시한다. 1위 소개로 시작하지 않는다.')

def introduction(ctx):
    if not ctx.get('location'):
        return ctx['message']+f"\n\n'{ctx['name']}'의 위치를 찾지 못했습니다. 근처 지역명(예: 중문)으로 다시 물어봐 주세요."
    return ctx['message']+'\n\n'+ctx['alternatives_heading']

def distance(ctx, result):
    km=result['place'].get('_distance_km')
    return f"{ctx['name']}에서 약 {km:.2f} km(직선)" if km is not None else f"{ctx['name']}에서 거리 미확인"
