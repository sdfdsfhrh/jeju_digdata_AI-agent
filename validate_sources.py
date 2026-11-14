"""실제 출처 집계와 독립 모의 DB의 통합·최신순·충돌·중복 실행을 검사한다."""
import csv
import json
import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

from agent import config, core, data, place_query, tools
from agent.parser import Request

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'src'))
from db import connect, write_rows
from kto_merge import classify, merge


def csv_file(path, rows):
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)


def main():
    # 실제 API 수집 CSV와 DB: 원문 누락·ID 누락·잘못된 상태값이 없어야 한다.
    c=sqlite3.connect(config.DB_PATH); c.row_factory=sqlite3.Row
    summary=json.loads(c.execute("select value from run_info where key='kto_integration'").fetchone()[0])
    assert summary['kto_list']==57 and summary['kto_detail']==57
    total=c.execute('select count(*) from place').fetchone()[0]
    eligible=c.execute("select count(*) from place where detail_level='상세파일있음'").fetchone()[0]
    hub=c.execute("select count(*) from place where place_id not like 'KTO-%'").fetchone()[0]
    assert total == hub + 57 - summary['matched_hub']
    assert eligible >= 107
    assert c.execute("select count(distinct place_id) from accessibility_item").fetchone()[0]==eligible
    assert c.execute("select count(*) from accessibility_item where status not in ('있음','없음','조건부','미확인')").fetchone()[0]==0
    original=list(csv.DictReader((ROOT/'data/extra/kto_detail.csv').open(encoding='utf-8-sig')))
    for row in original:
        for field in ('parking','restroom','wheelchair','stroller','exit','route','elevator'):
            saved=c.execute('select value_raw,verify_status,modifiedtime from accessibility_item where item_id=?',
                            ('KTO-ITEM-'+row['contentid']+'-'+field,)).fetchone()
            assert saved['value_raw']==row.get(field,'')
            assert saved['verify_status']=='검토필요(서술문)'
            assert saved['modifiedtime']==row['list_modifiedtime']
    distribution=[dict(r) for r in c.execute("select coalesce(source_label,'제주데이터허브(필수)') origin,status,count(*) n from accessibility_item group by origin,status")]
    report=dict(integration=summary,source_places=data.source_counts(),total=total,eligible=eligible,status_distribution=distribution)
    c.close()
    assert classify('restroom','-')[0]=='미확인'
    assert classify('parking','일반 주차장 있음')[0]=='미확인'
    assert classify('restroom','장애인 화장실 없음')[0]=='없음'
    assert classify('exit','턱이 없어 휠체어 접근 가능')[0]=='있음'
    assert classify('wheelchair','동행인 도움 필요, 일부 구간만 이용 가능')[0]=='조건부'
    # 별도 모의 DB에서도 양쪽 출처와 최신 판정을 독립적으로 검증한다.
    with tempfile.TemporaryDirectory(dir=ROOT/'output') as temp:
        folder=Path(temp); db=folder/'test.sqlite'; conn=connect(str(db))
        write_rows(conn,'source_file',[dict(source_file_id='HUB',file_name='hub.hwp',file_kind='general_2021',base_date='2021-12-17')])
        write_rows(conn,'place',[dict(place_id='HUB-1',name='검증 공원',address='제주시 구좌읍',lat=33.5,lon=126.7,
                                     detail_level='상세파일있음',bundle='2021')])
        write_rows(conn,'accessibility_item',[dict(item_id='HUB-TOILET',place_id='HUB-1',item='장애인화장실',category='화장실',status='있음',
                                                  value_raw='있음',evidence='있음',source_file_id='HUB',source_locator='T0 r7 c1')])
        csv_file(folder/'kto_list.csv',[dict(contentid='test',title='검증공원',addr1='제주시 구좌읍',mapy='33.5',mapx='126.7',modifiedtime='20251107090000')])
        csv_file(folder/'kto_detail.csv',[dict(contentid='test',restroom='장애인 화장실 없음',parking='장애인 주차장 있음')])
        first=merge(conn,folder); conn.commit()
        assert first['matched_hub']==1 and first['source_conflicts']==1
        assert conn.execute('select count(*) from place').fetchone()[0]==1
        assert conn.execute("select count(*) from accessibility_item where item='장애인화장실'").fetchone()[0]==2
        assert conn.execute("select count(*) from review_queue where review_type='출처간충돌'").fetchone()[0]==1
        before=conn.execute('select count(*) from accessibility_item').fetchone()[0]
        second=merge(conn,folder); conn.commit()
        assert second==first and conn.execute('select count(*) from accessibility_item').fetchone()[0]==before
        with patch.object(config,'DB_PATH',str(db)):
            data._con_path.cache_clear(); data.detailed_places.cache_clear()
            rows=data.items('HUB-1')
            toilets=[r for r in rows if r['item']=='장애인화장실']
            assert toilets[0]['status']=='없음' and toilets[0]['display_base_date']=='2025-11-07'
            access=tools.check_accessibility(dict(place_id='HUB-1'),Request(needs=['장애인화장실']))
            assert access['grade']==tools.G_FAIL
            assert any(t.get('source')=='제주데이터허브(필수)' for t in access['table'])
        data._con_path.cache_clear(); data.detailed_places.cache_clear(); conn.close()
    with patch.object(config,'KMA_SERVICE_KEY',''):
        p=next(p for p in data.detailed_places() if p['place_id'].startswith('KTO-'))
        result=core.run(p['name']+' 휠체어 화장실',use_llm=False)
        assert result['results'][0]['place']['place_id']==p['place_id']
        assert result['results'][0]['place']['lat'] is not None
    path=ROOT/'output/validation/source_report.json'
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print('통과: 수집57/상세57 원문 보존·출처/수정일·상태4종·허브 연결·모의 충돌·최신순·재실행·Agent 장소명/좌표')
    print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':
    main()
