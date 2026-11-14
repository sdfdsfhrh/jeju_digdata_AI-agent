"""제출 ZIP·catalog 분리 및 실제 제출 DB의 회귀를 검증한다."""
from pathlib import Path
import json,sqlite3,zipfile
from make_submission import APPENDIX_SCREENSHOTS, check_db

def main():
 root=Path(__file__).resolve().parent
 archive=root/'dist/jeju_barrier_free_submission.zip'
 with zipfile.ZipFile(archive) as z:
  names=z.namelist()
  assert z.testzip() is None
  assert not any('catalog' in Path(n).name.lower() for n in names)
  assert not any('/__pycache__/' in n or any(part in ('cache', '.cache') for part in Path(n).parts) or n.endswith('.pyc') for n in names)
  assert '.env' not in names and '.env.example' in names
  assert 'HANDOFF.md' not in names
  for filename in ['leaflet_map.py','leaflet_tiles.py','static/leaflet_map.html','static/vendor/leaflet.js','static/vendor/leaflet.css','static/vendor/LICENSE.leaflet','static/preview_normal.png','static/preview_satellite.png','app.py','chat_view.py','chat_footer.py','result_view.py','ui_controls.py','.streamlit/config.toml','map_background.py','map_display.py','map_icons.py','app_results.py','map_component/index.html','map_component/deck.gl-9.2.6.js','map_component/maplibre-gl-4.7.1.js','map_component/maplibre-gl-4.7.1.css','map_component/LICENSE.deck.gl','map_component/LICENSE.maplibre']:
   assert filename in names, '지도 실행 파일 누락: '+filename
   assert z.read(filename)==(root/filename).read_bytes(), '지도 실행 파일이 최신 아님: '+filename
  assert {n for n in names if n.startswith('docs/screenshots/')} == {
      f'docs/screenshots/{name}' for name in APPENDIX_SCREENSHOTS
  }
  assert all('docs/design/'+name in names for name in ['chat_reference.png','chat_mockup.png'])
  assert all('data/extra/'+n in names for n in ['kto_list.csv','kto_detail.csv','parking_jeju.csv','parking_seogwipo.csv'])
  # 실제 키를 출력하지 않고 ZIP 안 포함 여부만 검사한다.
  secrets=[]
  for line in ((root/'.env').read_text(encoding='utf-8-sig').splitlines() if (root/'.env').exists() else []):
   if '=' in line and not line.lstrip().startswith('#'):
    k,v=line.split('=',1);v=v.strip().strip('\"').strip("'")
    if 'KEY' in k and len(v)>12:secrets.append(v.encode())
  for name in names:
   blob=z.read(name)
   assert not any(value in blob for value in secrets), '인증정보가 포함된 파일 발견'
   if name.startswith('output/'):
    target=root/'output/submission'/name[len('output/'):]
    target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(blob)
 check_db(root/'output/submission/jeju_bf.sqlite')
 con=sqlite3.connect(root/'output/submission/jeju_bf.sqlite')
 import csv
 public_rows=list(csv.DictReader((root/'docs/data_sources.csv').open(encoding='utf-8-sig')))
 if not any(row.get('데이터번호') for row in public_rows):
  assert con.execute('select count(*) from source_file where hub_dataset_no is not null or hub_dataset_name is not null').fetchone()[0]==0, '현재 빈 출처표 기준 메타데이터 없어야 함'
 assert con.execute("select count(*) from place where coord_source like '%498%'").fetchone()[0]==0
 assert con.execute('select count(*) from place').fetchone()[0]==221
 con.close()
 print('PASS: ZIP 무결성·제외 목록·키 미포함·catalog 없는 실제 제출 DB')

if __name__=='__main__':main()
