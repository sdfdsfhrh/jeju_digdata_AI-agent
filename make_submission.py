"""catalog 없는 DB를 새로 빌드하고 허용 목록으로 제출 ZIP을 만든다."""
from pathlib import Path
import hashlib
import json
import sqlite3
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parent
DOCS = ['DATA_SPEC.md', 'LIMITS.md', 'USER_MANUAL.md', 'API_KEY_GUIDE.md', 'data_sources.csv', 'SUBMISSION_AUDIT.md', 'REGRESSION_BASELINES.json','SUBMISSION_SIZE.md','API_DIAGNOSTICS_20261108.md']
EXTRA = ['kto_list.csv', 'kto_detail.csv', 'parking_jeju.csv', 'parking_seogwipo.csv']
APPENDIX_SCREENSHOTS = (
    *(f'anchor40_{scene}.jpg' for scene in ('aqua', 'seongsan', 'shilla', 'not_found')),
    *(f'caution39_{scene}_{size}.jpg' for scene in ('seopji', 'hanlim', 'hyeopjae') for size in ('pc', 'mobile')),
    *(f'tiles38_{scene}_{size}_20261111.jpg' for scene in ('hanlim', 'hyeopjae') for size in ('pc', 'mobile')),
    'tiles38_weather_table_pc_20261111.jpg',
)
# 별도 실험 스크립트: 인증정보가 들어 있어 앱 제출 대상에서 제외. 원본은 수정하지 않음.
EXCLUDED_ROOT = {'# 사회복지시설 목록 전체를 받아서 CSV로 저장하는 코드.py'}

def excluded_submission_name(name):
    path = Path(name)
    parts = tuple(part.lower() for part in path.parts)
    return (
        parts[:4] == ('data', 'raw', '2019', 'images')
        or any(part in {'_to_delete', '__pycache__', '.pytest_cache', '.git', '.venv', '.cache'} for part in parts)
        or any('catalog' in part for part in parts)
        or path.suffix.lower() in {'.pyc', '.zip', '.xlsx', '.xls', '.pdf'}
        or (path.name.lower().startswith('.env') and path.name.lower() != '.env.example')
    )


def check_db(path):
    with sqlite3.connect(path) as con:
        assert con.execute("SELECT value FROM run_info WHERE key='submission_no_catalog'").fetchone() == ('True',), '제출용 빌드 표식 없음'
        assert con.execute("SELECT value FROM run_info WHERE key='catalog'").fetchone() == ('False',), 'catalog 사용 DB'
        assert con.execute('SELECT count(*) FROM source_file WHERE catalog_period IS NOT NULL').fetchone()[0] == 0
        assert con.execute("SELECT count(*) FROM source_file WHERE base_date_source LIKE '%카탈로그%'").fetchone()[0] == 0
        assert con.execute('PRAGMA integrity_check').fetchone() == ('ok',)

def main():
    dest=ROOT/'dist';dest.mkdir(exist_ok=True)
    work=ROOT/'output';work.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='submission_build_',dir=work) as temporary:
        build=Path(temporary)
        subprocess.run([sys.executable,'build_db.py','--no-catalog','--out',str(build)],cwd=ROOT,check=True)
        check_db(build/'jeju_bf.sqlite')
        selected={}
        def add(path,arc=None):
            path=Path(path)
            if not path.is_file():return
            name=arc or path.relative_to(ROOT).as_posix()
            if excluded_submission_name(name):return
            selected[name]=path
        for path in ROOT.glob('*.py'):
            if path.name not in EXCLUDED_ROOT:add(path)
        for name in ['README.md','requirements.txt','run_app.bat','.env.example','.gitignore','AGENTS.md']:add(ROOT/name)
        for path in (ROOT/'static').rglob('*'):add(path)
        for folder in ['agent','src']:
            for path in (ROOT/folder).rglob('*.py'):add(path)
        for path in (ROOT/'map_component').rglob('*'):add(path)
        for name in DOCS:add(ROOT/'docs'/name)
        for name in APPENDIX_SCREENSHOTS:
            path = ROOT/'docs/screenshots'/name
            if not path.is_file():
                raise FileNotFoundError(f'기획서 부록 캡처 누락: {name}')
            add(path)
        add(ROOT/'.streamlit/config.toml')
        for name in ['result_mockup.png','app_style_mockup.png','home_mockup.png','chat_reference.png','chat_mockup.png']:add(ROOT/'docs/design'/name)
        for path in (ROOT/'docs/sample_results').glob('app_design_*_20261108.txt'):add(path)
        for path in (ROOT/'docs/sample_results').glob('fix27_*_20261108.txt'):add(path)
        for path in (ROOT/'data/raw').rglob('*'):add(path)
        for name in EXTRA:add(ROOT/'data/extra'/name)
        add(ROOT/'data/manifest_override.csv')
        add(ROOT/'data/manifest.generated.csv')
        for path in build.rglob('*'):
            if path.is_file():add(path,'output/'+path.relative_to(build).as_posix())
        secrets=[]
        env=ROOT/'.env'
        for line in (env.read_text(encoding='utf-8-sig').splitlines() if env.exists() else []):
            if '=' in line and not line.lstrip().startswith('#'):
                key,value=line.split('=',1);value=value.strip().strip(chr(34)).strip(chr(39))
                if 'KEY' in key.upper() and len(value)>12:secrets.append(value.encode())
        manifest=[]
        # ZIP을 쓰기 전 실키를 검사. 값은 출력하지 않고 발견 파일명만 남겨 생성 중단.
        for name,path in sorted(selected.items()):
            blob=path.read_bytes()
            if any(secret in blob for secret in secrets):
                raise RuntimeError('제출 제외 필요(인증정보 포함): '+name)
            manifest.append(dict(path=name,bytes=len(blob),sha256=hashlib.sha256(blob).hexdigest()))
        text='\n'.join(x['path'] for x in manifest)+'\n'
        (dest/'submission_files.txt').write_text(text,encoding='utf-8')
        (dest/'submission_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
        archive=dest/'jeju_barrier_free_submission.zip'
        with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
            for name,path in sorted(selected.items()):z.write(path,name)
            z.writestr('SUBMISSION_FILES.txt',text)
            z.writestr('SUBMISSION_MANIFEST.json',json.dumps(manifest,ensure_ascii=False,indent=2))
        with zipfile.ZipFile(archive) as z:
            assert z.testzip() is None
            assert 'output/jeju_bf.sqlite' in z.namelist()
            assert not any(excluded_submission_name(n) for n in z.namelist())
        print(text)
        print(f'제출 ZIP: {archive} / 파일 {len(manifest)+2}개 / {archive.stat().st_size:,} bytes')
        print('기존 DB·catalog 파생 보고서·실제 .env·캐시·개발 캡처 제외. 전체 목록: dist/submission_files.txt')

if __name__=='__main__':main()
