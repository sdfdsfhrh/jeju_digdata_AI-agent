"""날씨 도구: 기상청 단기예보 조회서비스 (공공데이터포털, 선택 기능).

- 인증키(.env의 KMA_SERVICE_KEY)가 없거나 호출이 실패하면 '미확인'으로 돌려준다 (추측하지 않음).
- 같은 격자·발표시각 결과는 1시간 캐시한다.
- 판단 규칙(실외 코스 주의)은 core.py에서 이 결과로 계산한다.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import re

from . import cache, config

try:
    import requests
except ImportError:
    requests = None

URL = "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst"
KST = dt.timezone(dt.timedelta(hours=9))


def latlon_to_grid(lat: float, lon: float) -> tuple[int, int]:
    """위경도 → 기상청 격자(nx, ny). 기상청 공개 변환식(LCC)."""
    RE, GRID, SLAT1, SLAT2, OLON, OLAT, XO, YO = 6371.00877, 5.0, 30.0, 60.0, 126.0, 38.0, 43, 136
    D = math.pi / 180.0
    re = RE / GRID
    slat1, slat2, olon, olat = SLAT1 * D, SLAT2 * D, OLON * D, OLAT * D
    sn = math.log(math.cos(slat1) / math.cos(slat2)) / math.log(
        math.tan(math.pi * 0.25 + slat2 * 0.5) / math.tan(math.pi * 0.25 + slat1 * 0.5))
    sf = math.tan(math.pi * 0.25 + slat1 * 0.5) ** sn * math.cos(slat1) / sn
    ro = re * sf / math.tan(math.pi * 0.25 + olat * 0.5) ** sn
    ra = re * sf / math.tan(math.pi * 0.25 + lat * D * 0.5) ** sn
    theta = lon * D - olon
    if theta > math.pi:
        theta -= 2 * math.pi
    if theta < -math.pi:
        theta += 2 * math.pi
    theta *= sn
    return int(ra * math.sin(theta) + XO + 0.5), int(ro - ra * math.cos(theta) + YO + 0.5)


def _base_time(now: dt.datetime) -> tuple[str, str]:
    """가장 최근 발표시각 (02,05,08,11,14,17,20,23시, 발표 후 15분 여유)."""
    t = now - dt.timedelta(minutes=15)
    for h in (23, 20, 17, 14, 11, 8, 5, 2):
        if t.hour >= h:
            return t.strftime("%Y%m%d"), f"{h:02d}00"
    y = t - dt.timedelta(days=1)
    return y.strftime("%Y%m%d"), "2300"


SKY = {"1": "맑음", "3": "구름많음", "4": "흐림"}
PTY = {"0": "없음", "1": "비", "2": "비/눈", "3": "눈", "4": "소나기"}


# 공식 활용가이드: 기상청 API허브 공지 50 첨부 「기상청20_중기예보 조회서비스_오픈API활용가이드」
# https://apihub.kma.go.kr/notice.do?seqNotice=50 (첨부 지점코드 포함, 2026-11-06 확인)
# 육상 제주도 11G00000 / 기온 제주 11G00201, 서귀포 11G00401.
MID_URL = "https://apis.data.go.kr/1360000/MidFcstInfoService"
MID_LAND_REG = "11G00000"
MID_TA_REG = {"제주시": "11G00201", "서귀포시": "11G00401"}


def now_kst():
    return dt.datetime.now(KST)


def _mid_base(now):
    if now.hour >= 18:
        return now.strftime("%Y%m%d") + "1800"
    if now.hour >= 6:
        return now.strftime("%Y%m%d") + "0600"
    return (now - dt.timedelta(days=1)).strftime("%Y%m%d") + "1800"


class ForecastError(Exception):
    pass


def _items(url, params, group, fresh=False):
    # 인증키는 캐시 키·오류 메시지에 넣지 않는다.
    ck = cache.key("forecast_v2", url, json.dumps(params, sort_keys=True))
    raw = None if fresh else cache.get(ck, max_age_sec=3600)
    if raw is not None:
        return json.loads(raw)
    why = None if fresh else cache.blocked(group)
    if why:
        raise ForecastError(why)
    if requests is None:
        raise ForecastError("requests 패키지 없음")
    try:
        response = requests.get(url, timeout=10, params=dict(params, serviceKey=config.KMA_SERVICE_KEY,
                                pageNo=1, numOfRows=1000, dataType="JSON"))
        try:
            payload = response.json()["response"]
        except (ValueError, KeyError, TypeError):
            text = response.text
            if group == "kma_mid" and (any(c in text for c in ["SERVICE_ACCESS_DENIED", "SERVICE_KEY_IS_NOT_REGISTERED"])
                                      or re.search(r'<returnReasonCode>\s*(?:20|30|31)\s*</returnReasonCode>', text)):
                raise ForecastError("중기예보 활용신청 필요 — 인증키·승인 여부도 확인하세요")
            raise ForecastError("응답 형식 오류 — 인증키·활용신청 승인 여부 확인")
        code = str(payload.get("header", {}).get("resultCode", "00"))
        if code not in ("00", "0"):
            if group == "kma_mid" and code in ("20", "30", "31", "SERVICE_ACCESS_DENIED_ERROR"):
                raise ForecastError("중기예보 활용신청 필요 — 인증키·승인 여부도 확인하세요")
            raise ForecastError(f"기상청 응답 오류 코드 {code} (키·승인·발표 자료 확인)")
        items = payload["body"]["items"]["item"]
        if isinstance(items, dict):
            items = [items]
        if not isinstance(items, list) or not items:
            raise ForecastError("예보 자료 없음")
        cache.put(ck, json.dumps(items, ensure_ascii=False))
        return items
    except Exception as e:
        msg = str(e) if isinstance(e, ForecastError) else cache.friendly_error(e)
        cache.block(group, msg)
        raise ForecastError(msg) from None


def _short(lat, lon, date, hours, now, fresh):
    nx, ny = latlon_to_grid(lat, lon)
    bd, bt = _base_time(now)
    items = _items(URL, dict(base_date=bd, base_time=bt, nx=nx, ny=ny), "kma_short", fresh)
    rows = {}
    for item in items:
        if item["fcstDate"] == date and int(item["fcstTime"][:2]) in hours:
            rows.setdefault(item["fcstTime"], {})[item["category"]] = item["fcstValue"]
    if not rows:
        raise ForecastError(f"{date} 요청 시간대 단기예보 없음(발표에 따라 3일 뒤 자료가 부족할 수 있음)")
    # 빠진 값을 0으로 대체하지 않는다.
    required = ("POP", "WSD", "PTY", "SKY")
    if any(any(k not in row for k in required) for row in rows.values()):
        raise ForecastError("단기예보 필수 항목 누락")
    sky = [SKY.get(v["SKY"], "미확인") for v in rows.values()]
    precip = sorted({PTY.get(v["PTY"], "미확인") for v in rows.values()} - {"없음"})
    tmp = [float(v["TMP"]) for v in rows.values() if "TMP" in v]
    return dict(status="조회됨", forecast_type="단기", precision="시간별 예보(요청 시간대의 최대값)",
                date=date, hours=f"{min(hours)}~{max(hours)}시", grid=f"{nx},{ny}",
                base=f"{bd} {bt} 발표", pop_max=max(int(v["POP"]) for v in rows.values()),
                wind_max=max(float(v["WSD"]) for v in rows.values()), precip=precip or ["없음"],
                sky=max(sorted(set(sky)), key=sky.count), temp_range=(min(tmp), max(tmp)) if tmp else None,
                source="기상청 단기예보 조회서비스(공공데이터포털)")


class MidFieldError(ForecastError):
    pass


def _mid_at(date,hours,base,address,fresh):
    n=(dt.datetime.strptime(date,'%Y%m%d').date()-dt.datetime.strptime(base[:8],'%Y%m%d').date()).days
    if not 3<=n<=10:
        raise MidFieldError(f'중기 {base} 발표일 기준 {n}일 뒤: 해당 날짜 필드 없음(다른 날짜로 대체하지 않음)')
    land=_items(MID_URL+'/getMidLandFcst',dict(regId=MID_LAND_REG,tmFc=base),'kma_mid',fresh)[0]
    reg=MID_TA_REG['서귀포시' if '서귀포' in (address or '') else '제주시']
    periods=[]
    if n<=7:
        if any(h<12 for h in hours):periods.append(('오전',f'rnSt{n}Am',f'wf{n}Am'))
        if any(h>=12 for h in hours):periods.append(('오후',f'rnSt{n}Pm',f'wf{n}Pm'))
    if not periods or any(k not in land for _,k,_ in periods):
        periods=[('하루',f'rnSt{n}',f'wf{n}')]
    missing=[key for _,pk,wk in periods for key in (pk,wk) if land.get(key) in (None,'')]
    if missing:raise MidFieldError(f'중기 {base} 육상 {MID_LAND_REG}: {date}({n}일 뒤) 필드 미제공: '+', '.join(missing))
    ta=_items(MID_URL+'/getMidTa',dict(regId=reg,tmFc=base),'kma_mid',fresh)[0]
    missing=[k for k in (f'taMin{n}',f'taMax{n}') if ta.get(k) in (None,'')]
    if missing:raise MidFieldError(f'중기 {base} 기온 {reg}: {date} 필드 미제공: '+', '.join(missing))
    try:
        values=[dict(period=label,pop=int(land[pk]),sky=str(land[wk])) for label,pk,wk in periods]
        temp=(float(ta[f'taMin{n}']),float(ta[f'taMax{n}']))
        if any(not 0<=v['pop']<=100 for v in values):raise ValueError()
    except (TypeError,ValueError):raise MidFieldError(f'중기 {base}: 요청 날짜 강수/기온 값 형식 오류') from None
    desc=list(dict.fromkeys(v['sky'] for v in values))
    precip=['비'] if any('비' in x or '소나기' in x for x in desc) else ['눈'] if any('눈' in x for x in desc) else ['없음']
    return dict(status='조회됨',forecast_type='중기',precision='오전/오후 구역 예보' if periods[0][0]!='하루' else '하루 단위 구역 예보(시간대 구분 없음)',
        date=date,hours='/'.join(v['period'] for v in values),base=f'{base} 발표',day_index=n,
        pop_max=max(v['pop'] for v in values),sky=' / '.join(desc),precip=precip,
        wind_max=None,wind_note='중기예보는 풍속 미제공 → 강풍 판단 생략',
        temp_range=temp,periods=values,reg_id=MID_LAND_REG,temp_reg_id=reg,
        source='기상청 중기육상예보·중기기온(공공데이터포털)')


def _mid(lat,lon,date,hours,now,address,fresh):
    base=_mid_base(now)
    try:return _mid_at(date,hours,base,address,fresh)
    except MidFieldError as error:
        # 공식 가이드(상단 URL)의 날짜 번호는 발표일 기준이다.
        # 실제 2026-11-08 18시 응답은4일 뒤 칸을 미제공, 같은 날06시 응답에는 존재함.
        # N+1칸을 N일에 쓰지 않고, 대상 날짜가 있는 최근06시 발표를 명시적으로 추가 조회.
        n=(dt.datetime.strptime(date,'%Y%m%d').date()-dt.datetime.strptime(base[:8],'%Y%m%d').date()).days
        if not (base.endswith('1800') and n==4):raise
        previous=base[:8]+'0600'
        try:out=_mid_at(date,hours,previous,address,fresh)
        except ForecastError as second:
            raise ForecastError(str(error)+' / 같은 날06시 보완도 실패: '+str(second)) from None
        out['fallback_note']='최신18시 발표에 요청 날짜 항목이 없어 같은 날06시 발표 사용(발표일 기준 날짜 유지)'
        out['precision']+=' · 대상 날짜 제공06시 발표'
        out['attempted_base']=base
        return out


def remaining_hours(hours, now):
    """오늘의 예보 시각이 현재 시각보다 이른 구간은 제외(KST)."""
    return tuple(h for h in hours if now.replace(hour=h, minute=0, second=0, microsecond=0) >= now)


def forecast(lat, lon, date, hours=(10, 11, 12, 13, 14, 15, 16), address=None, fresh=False):
    now = now_kst()
    try:
        day = dt.datetime.strptime(date, "%Y%m%d").date()
        offset = (day - now.date()).days
        if offset < 0 or offset > 10:
            return dict(status="미확인", reason="예보 범위 밖(오늘~10일 뒤)")
        if offset == 0:
            hours = remaining_hours(hours, now)
        if not hours:
            return dict(status="미확인", reason="오늘 요청 시간대가 모두 지남 → 비교 제외")
        if lat is None or lon is None:
            return dict(status="미확인", reason="장소 좌표 없음")
        if not config.KMA_SERVICE_KEY:
            return dict(status="미확인", reason="기상청 키 없음")
        if offset <= 3:
            return _short(lat, lon, date, hours, now, fresh)
        return _mid(lat, lon, date, hours, now, address, fresh)
    except ForecastError as e:
        return dict(status="미확인", reason=str(e))
    except (KeyError, ValueError, TypeError, IndexError):
        return dict(status="미확인", reason="예보 날짜·필수 항목 미확인(미제공 값을 추정하지 않음)")
