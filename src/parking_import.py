"""전국주차장정보표준데이터 로컬 CSV 통합. 원문·행·기준일 보존."""
import json
import math
from pathlib import Path
import pandas as pd
from common import stable_id
from db import write_rows

MAPPING={'name':'주차장명','division':'주차장구분','type':'주차장유형','address_road':'소재지도로명주소','address_jibun':'소재지지번주소',
 'lat':'위도','lon':'경도','spaces':'주차구획수','fee_info':'요금정보','disabled_raw':'장애인전용주차구역보유여부','base_date':'데이터기준일자','management_no':'주차장관리번호'}
HOURS=['운영요일','평일운영시작시각','평일운영종료시각','토요일운영시작시각','토요일운영종료시각','공휴일운영시작시각','공휴일운영종료시각']
FEES=['요금정보','주차기본시간','주차기본요금','추가단위시간','추가단위요금','1일주차권요금적용시간','1일주차권요금','월정기권요금','결제방법','특기사항']


def read(path):
    for enc in ('utf-8-sig','cp949'):
        try:return pd.read_csv(path,encoding=enc,dtype=str,keep_default_na=False),enc
        except UnicodeDecodeError:pass
    raise ValueError(f'{Path(path).name}: utf-8-sig/cp949 읽기 실패')


def load(con,extra_dir,log):
    con.execute('DELETE FROM parking_lot')
    reports=[];allrows=[]
    for filename in ('parking_jeju.csv','parking_seogwipo.csv'):
        path=Path(extra_dir)/filename
        if not path.exists():
            log.info('[주차장] %s 없음 → 보조 자료 생략',filename);continue
        df,encoding=read(path);df.columns=[str(c).strip() for c in df.columns]
        headers=list(df.columns)
        log.info('[주차장 헤더] %s (%s): %s',filename,encoding,json.dumps(headers,ensure_ascii=False))
        missing=[c for c in ('주차장명','위도','경도') if c not in headers]
        if missing:raise ValueError(filename+': 필수 헤더 누락 '+str(missing))
        rows=[];bad=outside=unexpected=0
        for i,r in enumerate(df.to_dict('records'),2):
            try:y,x=float(r['위도']),float(r['경도'])
            except (TypeError,ValueError):bad+=1;continue
            if not (math.isfinite(y) and math.isfinite(x)):bad+=1;continue
            if not (33.0<=y<=33.7 and 126.1<=x<=127.0):outside+=1;continue
            row={k:str(r.get(v,'')).strip() for k,v in MAPPING.items()};row.update(lat=y,lon=x)
            try:row['spaces']=int(float(row['spaces'])) if row['spaces'] else None
            except ValueError:row['spaces']=None
            flag=row['disabled_raw'].upper()
            row['disabled_status']={'Y':'있음','N':'없음','':'미확인'}.get(flag,'미확인')
            unexpected+=int(flag not in ('Y','N',''))
            row.update(parking_lot_id=stable_id('PARK',filename,i),address=row['address_road'] or row['address_jibun'],
                       hours_json=json.dumps({k:r.get(k,'') for k in HOURS},ensure_ascii=False),fees_json=json.dumps({k:r.get(k,'') for k in FEES},ensure_ascii=False),
                       source_file=filename,source_locator=f'row {i}',source_label='공공데이터포털 전국주차장정보표준데이터(15012896)',
                       raw_json=json.dumps(r,ensure_ascii=False))
            rows.append(row)
        allrows+=rows
        report=dict(file=filename,encoding=encoding,headers=headers,mapping=dict(MAPPING,hours_json=HOURS,fees_json=FEES,source_file='입력 파일명',source_locator='CSV 행'),input=len(df),kept=len(rows),missing_coordinates=bad,outside_jeju=outside,unexpected_disabled_flag=unexpected,
                    dates=sorted({r['base_date'] for r in rows}),disabled_status={s:sum(r['disabled_status']==s for r in rows) for s in ('있음','없음','미확인')})
        reports.append(report)
        log.info('[주차장 헤더 매핑] %s: %s',filename,json.dumps(report['mapping'],ensure_ascii=False))
        log.info('[주차장 통합] %s',json.dumps({k:v for k,v in report.items() if k not in ('headers','mapping')},ensure_ascii=False))
    write_rows(con,'parking_lot',allrows)
    return dict(total=len(allrows),files=reports)
