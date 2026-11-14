"""주차 CSV 통합·일반/장애인 조건·근처 보완 회귀 검증. 외부 호출 없음."""
import io,json,logging,sqlite3,sys,tempfile
from pathlib import Path
from unittest.mock import patch
import pandas as pd
sys.path.insert(0,str(Path(__file__).parent/'src'))
from parking_import import load,MAPPING
from db import connect
from agent import data,parking,tools,config,core
from agent.parser import Request,rule_parse,validate


def main():
    log=logging.getLogger('parking-test');log.addHandler(logging.NullHandler())
    with tempfile.TemporaryDirectory(dir=Path('output/validation').resolve(),prefix='parking-test-') as temp:
        root=Path(temp).resolve();assert root.is_relative_to(Path('output/validation').resolve())
        base={v:'' for v in MAPPING.values()};base.update(주차장명='모의주차장',위도='33.4',경도='126.5',주차구획수='12',데이터기준일자='2026-11-08')
        rows=[dict(base,장애인전용주차구역보유여부=v) for v in ('Y','N','')]+[dict(base,위도=''),dict(base,위도='33.8'),dict(base,경도='127.1')]
        pd.DataFrame(rows).to_csv(root/'parking_jeju.csv',index=False,encoding='utf-8-sig')
        pd.DataFrame([dict(base,주차장명='서귀포 모의')]).to_csv(root/'parking_seogwipo.csv',index=False,encoding='cp949')
        con=connect(':memory:');report=load(con,root,log)
        assert report['total']==4 and report['files'][0]['missing_coordinates']==1 and report['files'][0]['outside_jeju']==2
        assert report['files'][1]['encoding']=='cp949'
        assert con.execute('select disabled_status from parking_lot order by source_file,source_locator').fetchall()[:3]==[('있음',),('없음',),('미확인',)]
        assert con.execute('select count(*) from parking_lot where raw_json is not null and source_locator is not null').fetchone()[0]==4
        assert load(con,root,log)['total']==4 and con.execute('select count(*) from parking_lot').fetchone()[0]==4
        con.close()
    p=dict(place_id='mock-parking',name='모의장소',lat=33.4,lon=126.5)
    def item(status,raw=None):return dict(item='장애인주차장',status=status,status_reason='모의 원문',value_raw=raw or status,evidence=raw or status,file_name='place.hwp',source_locator='T0 r1',verify_status='모의')
    def lot(flag):return dict(parking_lot_id='test',name='근처 공영',lat=33.401,lon=126.5,spaces=10,fee_info='무료',fees_json='{}',disabled_status={'Y':'있음','N':'없음','':'미확인'}[flag],disabled_raw=flag,base_date='2026-11-08',source_file='parking.csv',source_locator='row 2')
    with patch.object(data,'points',return_value=[]),patch.object(data,'source_files',return_value=[]),patch.object(data,'parking_rows',return_value=[lot('')]),patch.object(data,'items',return_value=[item('미확인')]):
        a=tools.check_accessibility(p,Request(needs=['parking_general']))
        assert a['grade']==tools.G_COND and a['parking']['general']['display'].startswith('근처 있음')
        assert a['comfort']==1 and a['parking']['disabled']['original_status']=='미확인'
        b=tools.check_accessibility(p,Request(needs=['parking_disabled']))
        assert b['grade']==tools.G_CHECK and b['parking']['disabled']['supplement'] is None
    for flag in ('N',''):
        with patch.object(data,'points',return_value=[]),patch.object(data,'source_files',return_value=[]),patch.object(data,'parking_rows',return_value=[lot(flag)]),patch.object(data,'items',return_value=[item('미확인')]):
            a=tools.check_accessibility(p,Request(needs=['parking_disabled']))
            assert a['needs'][0]['status']=='미확인' and a['needs'][0]['effective']=='미확인'
    with patch.object(data,'points',return_value=[]),patch.object(data,'source_files',return_value=[]),patch.object(data,'parking_rows',return_value=[lot('Y')]),patch.object(data,'items',return_value=[item('미확인')]):
        a=tools.check_accessibility(p,Request(needs=['parking_disabled']))
        assert a['needs'][0]['status']=='미확인' and a['needs'][0]['effective']=='조건부' and a['grade']==tools.G_COND
        assert a['parking']['disabled']['supplement'].startswith('근처 장애인 주차 있음')
    with patch.object(data,'points',return_value=[]),patch.object(data,'parking_rows',return_value=[lot('Y')]),patch.object(data,'items',return_value=[item('없음')]):
        a=tools.check_accessibility(p,Request(needs=['parking_disabled']))
        assert a['grade']==tools.G_FAIL and not a['parking']['disabled']['supplement']
    with patch.object(data,'points',return_value=[]),patch.object(data,'parking_rows',return_value=[]),patch.object(data,'items',return_value=[item('있음')]):
        a=tools.check_accessibility(p,Request(needs=['parking_general']))
        assert a['grade']==tools.G_OK and '장애인 주차구역 근거' in a['parking']['general']['display']
    with patch.object(data,'points',return_value=[]),patch.object(data,'parking_rows',return_value=[]),patch.object(data,'items',return_value=[item('미확인')]):
        assert tools.check_accessibility(p,Request(needs=['parking_general']))['grade']==tools.G_CHECK
    assert rule_parse('휠체어 주차 필수',[]).needs==['parking_disabled']
    assert rule_parse('장애인 주차 필수',[]).needs==['parking_disabled']
    assert validate(dict(needs=['장애인주차장']),'일반 주차 필수',[]).needs==['parking_general']
    report=json.loads(Path('output/review/parking_import_report.json').read_text(encoding='utf-8'))
    assert report['total']==1557
    assert data._q('select count(*) n from parking_lot')[0]['n']==1557
    assert data._q("select count(*) n from parking_lot where disabled_status!='미확인'")[0]['n']==0
    with patch.object(config,'KMA_SERVICE_KEY',''),patch.object(config,'KTO_SERVICE_KEY',''):
        res=core.run('한림공원 일반 주차 꼭 필요',use_llm=False)
        assert res['results'][0]['place']['name']=='한림공원'
        assert any(t['tool']=='check_parking' for t in res['trace'])
        from cli import show
        from contextlib import redirect_stdout
        with redirect_stdout(io.StringIO()) as out:show(res)
        assert '일반 주차:' in out.getvalue()
    print('PASS 주차 통합/두 인코딩/좌표 제외/Y N 공란/일반·장애인 분리/근처 조건부1점/원본상태 보호/CLI·trace')

if __name__=='__main__':main()
