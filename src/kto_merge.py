"""관광공사 보조 출처 통합. 허브 원본·항목은 덮어쓰지 않는다."""
import csv
import datetime as dt
import html
import json
import re
from pathlib import Path

from common import stable_id, norm_name, file_sha256
from integrate import AUTO, judge
from db import write_rows

FIELDS = {'parking': ('주차','장애인주차장'), 'restroom': ('화장실','장애인화장실'),
          'exit': ('출입','출입구'), 'route': ('이동','접근로'), 'elevator': ('이동','엘리베이터'),
          'wheelchair': ('보조기기','휠체어대여'), 'stroller': ('보조기기','유아차대여'),
          'publictransport': ('교통','대중교통'), 'auditorium': ('관람','휠체어 관람석'),
          'ticketoffice': ('안내','매표소'), 'promotion': ('안내','홍보물'),
          'braileblock': ('시각','점자블록'), 'guidehuman': ('안내','안내요원'),
          'audioguide': ('시각','오디오가이드'), 'bigprint': ('시각','큰글자'),
          'brailepromotion': ('시각','점자홍보물'), 'guidesystem': ('안내','유도안내'),
          'signguide': ('청각','수어안내'), 'videoguide': ('청각','영상안내'),
          'hearingroom': ('청각','보청시설'), 'nursingroom': ('영유아','수유실'),
          'lactationroom': ('영유아','수유공간'), 'infantsfamilyetc': ('영유아','영유아 기타'),
          'handicapetc': ('기타','지체장애 기타'), 'blindhandicapetc': ('기타','시각장애 기타'),
          'hearinghandicapetc': ('기타','청각장애 기타'), 'room': ('숙박','객실')}
FIELDS.update({'babysparechair': ('영유아','유아용 보조의자'), 'helpdog': ('시각','안내견 동반')})


def classify(field, raw):
    t = re.sub('<[^>]+>', ' ', html.unescape(raw or '')).strip()
    if not t or t in ('-','해당없음','정보없음'):
        return '미확인', '공란·정보 미제공 (시설 없음과 구분)'
    if field in ('parking','restroom') and not re.search('장애인|장애우|장애자', t):
        return '미확인', '일반 시설 서술로 장애인 전용 여부를 확정할 수 없음'
    if re.search(r'대체|일부|동행|도움|보호자|제한|협소|문의|주의|경사|불편|신분증',t):
        return '조건부', '원문에 대체·제약·도움·경사 등 조건 명시'
    # 턱·단차·계단이 없다는 표현은 시설 부재가 아니다.
    clean=re.sub(r'(?:턱|단차|계단)\s*(?:이|가|은|는)?\s*(?:없음|없어|없다|없습니다)', '',t)
    if re.search(r'없음|없습니다|없다|미설치|불가|불가능|안\s*함|0\s*(?:대|면|개)', clean):
        return '없음', '원문에 시설 없음·이용 불가 명시'
    if re.search(r'있음|있습니다|있다|설치|가능|구비|보유|제공|대여|자동문|[1-9]\d*\s*(?:대|면|개)',t):
        return '있음', '원문에 있음·설치·가능·양수 수량 명시'
    return '미확인', '위치·설명만으로 시설 상태를 확정하지 않음'


def number(value):
    try: return float(value)
    except (ValueError,TypeError): return None


def base_date(value):
    digits=re.sub(r'\D','',value or '')
    if len(digits)>=8:
        try: return dt.datetime.strptime(digits[:8],'%Y%m%d').date().isoformat()
        except ValueError: pass
    return None


def merge(con, extra_dir):
    directory=Path(extra_dir)
    with (directory/'kto_list.csv').open(encoding='utf-8-sig',newline='') as f: lists=list(csv.DictReader(f))
    with (directory/'kto_detail.csv').open(encoding='utf-8-sig',newline='') as f: details=list(csv.DictReader(f))
    det={r['contentid']:r for r in details}
    con.row_factory=__import__('sqlite3').Row
    con.execute("""UPDATE place SET detail_level='색인만(상세파일 미수집)' WHERE place_id NOT LIKE 'KTO-%'
                   AND NOT EXISTS (SELECT 1 FROM accessibility_item a WHERE a.place_id=place.place_id AND a.item_id NOT LIKE 'KTO-%')""")
    hubs=[dict(r) for r in con.execute("SELECT * FROM place WHERE place_id NOT LIKE 'KTO-%'")]
    # 재실행 때 같은 ID를 사용하며 기존 관광공사 파생 행만 재작성한다.
    for table,column in [('accessibility_item','item_id'),('place_source_link','link_id'),
                         ('review_queue','review_id'),('conflict','conflict_id')]:
        con.execute(f"DELETE FROM {table} WHERE {column} LIKE 'KTO-%'")
    con.execute("DELETE FROM place WHERE place_id LIKE 'KTO-%'")
    for table in ('kto_place','kto_accessibility','kto_hub_comparison'):
        con.execute(f'DELETE FROM {table}')
    sources=[]
    for fn,kind in [('kto_list.csv','kto_list'),('kto_detail.csv','kto_detail')]:
        sid='KTO-SOURCE-'+kind
        con.execute('DELETE FROM source_file WHERE source_file_id=?',(sid,))
        sources.append(dict(source_file_id=sid,file_name=fn,file_ext='.csv',file_kind=kind,
                            base_date=max((base_date(r.get('modifiedtime')) or '' for r in lists),default=''),
                            base_date_source='목록 modifiedtime(콘텐츠 수정일)', sha256=file_sha256(str(directory/fn)),
                            parse_status='성공',encoding='utf-8-sig',parse_message='한국관광공사 보조 출처'))
    write_rows(con,'source_file',sources)
    matched=0; matched_detail=0; new=0; failure_detail=0; reviews=[]; conflicts=[]
    for idx,r in enumerate(lists,2):
        cid=r['contentid']; lat,lon=number(r.get('mapy')),number(r.get('mapx'))
        candidates=[]
        for p in hubs:
            aliases=[r.get('title') or '']+[a.strip() for a in re.findall(r'[(]([^()]+)[)]',r.get('title') or '') if len(a.strip())>=4]
            judged=[(*judge(alias,r.get('addr1'),lat,lon,p['name'],p.get('address'),p.get('lat'),p.get('lon')),alias) for alias in aliases]
            judged.sort(key=lambda x:(x[0]!=AUTO, -x[1]))
            status,sim,distance,am,why,alias=judged[0]
            if status:
                if alias!=r.get('title'): why+='; 관광공사 제목 괄호 별칭: '+alias
                candidates.append((status,sim,distance,why,p))
        autos=[c for c in candidates if c[0]==AUTO]
        d=det.get(cid)
        if len(autos)==1:
            p=autos[0][4]; pid=p['place_id']; matched+=1
            matched_detail+=p['detail_level']=='상세파일있음'
            if d:
                con.execute("UPDATE place SET detail_level='상세파일있음' WHERE place_id=?",(pid,))
        else:
            pid='KTO-'+cid; new+=1
            write_rows(con,'place',[dict(place_id=pid,name=r.get('title'),name_norm=norm_name(r.get('title')),
                       address=r.get('addr1'),lat=lat,lon=lon,coord_source='한국관광공사(보조)',bundle='KTO(보조)',
                       detail_level='상세파일있음' if d else '색인만(상세파일 미수집)',base_date=base_date(r.get('modifiedtime')))])
            if candidates:
                reviews.append(dict(review_id='KTO-MATCH-'+cid,review_type='장소매칭',place_id=pid,
                           source_file_id='KTO-SOURCE-kto_list',detail='자동 후보 0개 또는 2개 이상 → 허브와 자동 결합하지 않음',
                           candidates=json.dumps([dict(name=c[4]['name'],place_id=c[4]['place_id'],status=c[0],why=c[3]) for c in candidates],ensure_ascii=False),status='미검토'))
        write_rows(con,'place_source_link',[dict(link_id='KTO-LINK-'+cid,place_id=pid,source_file_id='KTO-SOURCE-kto_list',
                   source_locator=f'row {idx}; contentid={cid}',raw_name=r.get('title'),raw_address=r.get('addr1'),
                   raw_lat=lat,raw_lon=lon,link_method='integrate.judge 유일 자동 후보' if len(autos)==1 else '보조 출처 신규·검토 후보',
                   link_status=AUTO if len(autos)==1 else '신규장소')])
        write_rows(con,'kto_place',[dict(kto_id=cid,title=r.get('title'),addr=r.get('addr1'),lat=lat,lon=lon,
                   contenttypeid=r.get('contenttypeid'),modifiedtime=r.get('modifiedtime'),matched_place_id=pid if len(autos)==1 else None,
                   match_status=AUTO if len(autos)==1 else '신규장소',data_status='보조 출처(서술문 검토필요)',source_file_id='KTO-SOURCE-kto_list')])
        if not d:
            failure_detail+=1; continue
        write_rows(con,'place_source_link',[dict(link_id='KTO-LINK-DETAIL-'+cid,place_id=pid,source_file_id='KTO-SOURCE-kto_detail',
                   source_locator=f'contentid={cid}',raw_name=r.get('title'),link_method='contentid 일치',link_status=AUTO)])
        for field,(category,item) in FIELDS.items():
            raw=d.get(field,''); status,reason=classify(field,raw)
            locator=f"contentid={cid}; field={field}"
            hubrows=[dict(x) for x in con.execute("SELECT a.*,s.file_name FROM accessibility_item a JOIN source_file s USING(source_file_id) WHERE a.place_id=? AND a.item=? AND a.item_id NOT LIKE 'KTO-%'",(pid,item))]
            for hub in hubrows:
                if hub['status']!=status:
                    conflicts.append(dict(conflict_id='KTO-CONFLICT-'+cid+'-'+hub['item_id']+'-'+field,place_id=pid,
                        topic='출처간충돌: '+item,value_a=f"{hub['status']}: {hub['value_raw']}",
                        source_a=f"{hub['file_name']} {hub['source_locator']}",value_b=f'{status}: {raw}',
                        source_b=f'kto_detail.csv {locator}',note='허브(필수)와 관광공사(보조)의 상태·정보량 차이. 미확인은 시설 부재가 아님. 수정일이 현장 조사일을 뜻하지 않음'))
            write_rows(con,'accessibility_item',[dict(item_id='KTO-ITEM-'+cid+'-'+field,place_id=pid,category=category,item=item,
                       status=status,status_reason=reason,value_raw=raw,evidence=raw,applies_to='대상 장소',
                       source_file_id='KTO-SOURCE-kto_detail',source_locator=locator,extract_method='rule',
                       verify_status='검토필요(서술문)',source_label='한국관광공사(보조)',base_date=base_date(r.get('modifiedtime')),
                       modifiedtime=r.get('modifiedtime'))])
            write_rows(con,'kto_accessibility',[dict(kto_id=cid,field=field,value_raw=raw,source_file_id='KTO-SOURCE-kto_detail')])
    write_rows(con,'review_queue',reviews); write_rows(con,'conflict',conflicts)
    for c in conflicts:
        write_rows(con,'review_queue',[dict(review_id=c['conflict_id'],review_type='출처간충돌',place_id=c['place_id'],
                   source_file_id='KTO-SOURCE-kto_detail',detail=c['topic']+' / '+c['note'],status='미검토')])
    result=dict(kto_list=len(lists),kto_detail=len(details),matched_hub=matched,matched_hub_detail=matched_detail,
                new_places=new,unmatched_detail=failure_detail,source_conflicts=len(conflicts),match_review=len(reviews))
    con.execute("INSERT OR REPLACE INTO run_info VALUES('kto_integration',?)",(json.dumps(result,ensure_ascii=False),))
    return result
