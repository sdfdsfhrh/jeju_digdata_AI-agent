"""KorWithService2 제주 목록·상세 수집. 키·요청 URL·응답 원문은 로그에 출력하지 않는다."""
import argparse
import csv
import datetime as dt
import json
import math
import time
from pathlib import Path
from urllib.parse import unquote
from xml.etree import ElementTree as ET

import requests
from agent import config

BASE = 'https://apis.data.go.kr/B551011/KorWithService2/'
ROOT = Path(__file__).resolve().parent


class ApiError(Exception):
    def __init__(self, code, reason):
        self.code, self.reason = str(code), reason
        super().__init__(f'{self.code}: {reason}')


def error_reason(code):
    return {'30':'등록되지 않은 키 또는 해당 서비스 미신청·승인 미반영',
            '31':'만료된 키', '20':'서비스 접근 거부(활용신청·승인 상태 확인)',
            '22':'호출 한도 초과', '10':'필수 요청변수 누락', '12':'요청 서비스 없음'}.get(str(code),
            '제공기관 응답 오류(포털 신청·승인 상태 및 서비스 점검 확인)')


def call(endpoint, **params):
    if not config.KTO_SERVICE_KEY:
        raise ApiError('KEY_MISSING','KTO_SERVICE_KEY 미설정')
    try:
        resp = requests.get(BASE + endpoint, params=dict(serviceKey=unquote(config.KTO_SERVICE_KEY),
                            MobileOS='ETC', MobileApp='JejuBarrierFree', _type='json', **params), timeout=25)
    except requests.RequestException:
        raise ApiError('NETWORK','외부 연결 실패 또는 응답 시간 초과') from None
    try:
        payload = resp.json()['response']
    except (ValueError, KeyError, TypeError):
        code = 'HTTP_' + str(resp.status_code)
        try:
            code = ET.fromstring(resp.text).findtext('.//returnReasonCode') or code
        except ET.ParseError:
            pass
        raise ApiError(code,error_reason(code)) from None
    code = str(payload.get('header',{}).get('resultCode','UNKNOWN'))
    if code not in ('0000','00','0'):
        raise ApiError(code,error_reason(code))
    body = payload.get('body',{})
    entries = (body.get('items') or {}).get('item',[]) if isinstance(body.get('items'),dict) else []
    if isinstance(entries,dict): entries = [entries]
    return entries, int(body.get('totalCount',len(entries)))


def write_csv(path, rows):
    if not rows: return
    cols = sorted({k for row in rows for k in row})
    tmp = path.with_suffix('.tmp')
    with tmp.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=cols); w.writeheader(); w.writerows(rows)
    tmp.replace(path)


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--check',action='store_true')
    parser.add_argument('--interval',type=float,default=0.35)
    args=parser.parse_args()
    dest=ROOT/'data'/'extra'; dest.mkdir(parents=True,exist_ok=True)
    try:
        first,total=call('areaBasedList2',areaCode=39,numOfRows=100,pageNo=1,arrange='A')
    except ApiError as e:
        print(f'관광공사: 실패 코드={e.code}, 원인={e.reason}',flush=True)
        return 1
    print(f'관광공사: 정상 응답 / 제주 totalCount={total}',flush=True)
    if args.check:
        write_csv(dest/'kto_list_probe.csv',first)
        (ROOT/'output'/'kto_probe.json').write_text(json.dumps(dict(totalCount=total),ensure_ascii=False),encoding='utf-8')
        # 기상청 단기예보 1회만 직접 호출하여 상태 확인 (키·URL은 출력하지 않음).
        from agent import weather
        if not config.KMA_SERVICE_KEY:
            print('기상청: KMA_SERVICE_KEY 미설정'); return 1
        now=weather.now_kst(); bd,bt=weather._base_time(now)
        try:
            weather._items(weather.URL,dict(base_date=bd,base_time=bt,nx=52,ny=38),'kma_short',fresh=True)
            print('기상청 단기예보: 정상 응답',flush=True)
        except weather.ForecastError as e:
            print('기상청 단기예보: '+str(e),flush=True)
        return 0
    rows=list(first); failures=[]
    for page in range(2,math.ceil(total/100)+1):
        time.sleep(args.interval)
        try:
            batch,_=call('areaBasedList2',areaCode=39,numOfRows=100,pageNo=page,arrange='A'); rows.extend(batch)
        except ApiError as e:
            failures.append(dict(stage='list',id=str(page),code=e.code,reason=e.reason))
        print(f'목록 페이지 {page}: 누적 {len(rows)}/{total}',flush=True)
    rows=list({str(r['contentid']):r for r in rows}.values())
    write_csv(dest/'kto_list.csv',rows)
    existing={}
    detail_path=dest/'kto_detail.csv'
    if detail_path.exists():
        with detail_path.open(encoding='utf-8-sig',newline='') as f:
            existing={r['contentid']:r for r in csv.DictReader(f)}
    for i,r in enumerate(rows,1):
        cid=str(r['contentid'])
        if cid in existing and existing[cid].get('list_modifiedtime')==r.get('modifiedtime'):
            continue
        time.sleep(args.interval)
        try:
            batch,_=call('detailWithTour2',contentId=cid,numOfRows=10,pageNo=1)
            if not batch: raise ApiError('EMPTY','무장애 상세 응답 없음')
            existing[cid]=dict(batch[0],contentid=cid,list_modifiedtime=r.get('modifiedtime',''),
                               collected_at=dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat())
        except ApiError as e:
            failures.append(dict(stage='detail',id=cid,code=e.code,reason=e.reason))
        if i%25==0 or i==len(rows):
            write_csv(detail_path,list(existing.values()))
            write_csv(dest/'kto_failures.csv',failures)
            print(f'상세 진행 {i}/{len(rows)} / 성공 {len(existing)} / 실패 {len(failures)}',flush=True)
    report=dict(totalCount=total,list_count=len(rows),detail_count=len(existing),failures=failures,
                collected_at=dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat())
    (ROOT/'output'/'kto_collection_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='failures'},ensure_ascii=False),flush=True)
    return 0


if __name__=='__main__':
    raise SystemExit(main())
