"""18개 장소 폴더·동일 파일명/동일 내용·공통 가이드·범례 처리 회귀(외부 호출 없음)."""
import csv
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'src'))
from raw_scan import scan
from prep_csv import parse_points_2019
from legacy_points import extract_facilities
import pandas as pd


def main():
    guide=ROOT/'data/raw/2019/제주무장애여행 데이터셋 가이드문서.hwp'
    if not guide.exists(): guide=ROOT/'output/validation/narrative18/common_dataset_guide.hwp'
    doc=guide.read_bytes()
    base=[dict(ID='1',lat='33.5',lon='126.5',Title='',Description='',info='',A='',B='',etc='장애인화장실:2')]
    parsed,_=parse_points_2019(pd.DataFrame(base))
    assert next(a for a in extract_facilities(parsed).items if a['item']=='장애인화장실')['status']=='미확인'
    linked=[dict(base[0],info='2')]
    parsed,_=parse_points_2019(pd.DataFrame(linked))
    item=next(a for a in extract_facilities(parsed).items if a['item']=='장애인화장실')
    assert item['status']=='있음' and 'legend row 2 etc' in item['source_locator'] and 'info=2' in item['value_raw']
    parsed,_=parse_points_2019(pd.DataFrame([dict(linked[0],lat='',lon='')]))
    assert next(a for a in extract_facilities(parsed).items if a['item']=='장애인화장실')['status']=='미확인'
    with tempfile.TemporaryDirectory(dir=ROOT/'output') as temp:
        temp=Path(temp); raw=temp/'raw'; out=temp/'out'
        for i in range(18):
            folder=raw/'2019'/f'모의장소{i:02d}';folder.mkdir(parents=True)
            (folder/'제주무장애여행 데이터셋 가이드문서.hwp').write_bytes(doc)
            with (folder/'014-2.csv').open('w',encoding='utf-8-sig',newline='') as f:
                w=csv.DictWriter(f,fieldnames=list(base[0]));w.writeheader();w.writerows(linked)
            images=folder/'images'; images.mkdir();(images/'same.jpg').write_bytes(b'count-only-no-decode')
        files,report=scan(raw)
        assert len(files)==18 and report['image_count']==18 and len(report['place_folders'])==18
        excluded=[r for r in report['files'] if r['action']=='제외']
        assert len(excluded)==18 and len({r['sha256'] for r in excluded})==1 and len({r['text_sha256'] for r in excluded})==1
        manifest=ROOT/'data/manifest.generated.csv'
        previous=manifest.read_bytes() if manifest.exists() else None
        try:
            built=subprocess.run([sys.executable,str(ROOT/'build_db.py'),'--raw',str(raw),'--out',str(out),
                              '--override',str(temp/'absent.csv')],cwd=ROOT,capture_output=True,timeout=90)
        finally:
            if previous is not None: manifest.write_bytes(previous)
        assert built.returncode==0,built.stderr.decode('utf-8',errors='replace')[-600:]
        c=sqlite3.connect(out/'jeju_bf.sqlite')
        sources=c.execute("select file_name,place_name_declared,place_name_source from source_file where file_kind='points_2019'").fetchall()
        assert len(sources)==18 and all(row[2]=='folder' and row[1] in row[0] for row in sources)
        assert c.execute("select count(distinct source_file_id) from source_file where file_kind='points_2019'").fetchone()[0]==18
        assert c.execute("select count(*) from source_file where file_name like '%가이드%'").fetchone()[0]==0
        c.close()
        # 임시 원본은 삭제되므로 실행 산출물의 경로를 실제 목록으로 덮어쓰지 않게 한다.
    print('통과: 18폴더·동일 파일명/동일 SHA 분리·folder 출처·가이드 SHA/내용 제외·이미지 개수·범례만/코드연결/좌표없음')


if __name__=='__main__': main()
