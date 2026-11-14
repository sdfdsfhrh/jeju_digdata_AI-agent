"""제출ZIP 용량 읽기 전용 집계. 압축 방법·포함 파일을 바꾸지 않는다."""
from pathlib import Path
from collections import defaultdict
import zipfile

ROOT=Path(__file__).resolve().parent

def main():
    archive=ROOT/'dist/jeju_barrier_free_submission.zip'
    with zipfile.ZipFile(archive) as z:rows=[r for r in z.infolist() if not r.is_dir()]
    def aggregate(key):
        values=defaultdict(lambda:[0,0,0])
        for r in rows:
            v=values[key(r.filename)];v[0]+=r.file_size;v[1]+=r.compress_size;v[2]+=1
        return sorted(values.items(),key=lambda x:-x[1][1])
    def section(title,values):
        out=['\n## '+title,'','|구분|파일 수|원본 MiB|ZIP 내부 압축 MiB|','|---|---:|---:|---:|']
        for name,(original,compressed,count) in values[:15]:out.append(f'|{name}|{count}|{original/1048576:,.2f}|{compressed/1048576:,.2f}|')
        return out
    lines=['# 제출 ZIP 용량 분석(재생성 전 스냅샷)','',f'분석 대상: `{archive.name}`',f'실제 ZIP 크기: {archive.stat().st_size:,} bytes ({archive.stat().st_size/1048576:,.2f} MiB)',f'파일 수: {len(rows)}',
        '','원본·이미지 등을 삭제하거나 압축 수준을 바꾸지 않은 읽기 전용 분석입니다. ZIP 파일 자체의 헤더 크기는 항목별 압축 크기 합계와 다릅니다.']
    lines+=section('파일 종류별',aggregate(lambda n:Path(n).suffix.lower() or '(확장자 없음)'))
    lines+=section('폴더별(상위2단계)',aggregate(lambda n:'/'.join(Path(n).parts[:2]) if len(Path(n).parts)>2 else Path(n).parent.as_posix()))
    lines+=section('폴더별(상위4단계)',aggregate(lambda n:'/'.join(Path(n).parts[:4]) if len(Path(n).parts)>4 else Path(n).parent.as_posix()))
    lines+=section('압축 용량이 큰 파일',[(r.filename,[r.file_size,r.compress_size,1]) for r in sorted(rows,key=lambda r:-r.compress_size)[:15]])
    report='\n'.join(lines)+'\n';(ROOT/'docs/SUBMISSION_SIZE.md').write_text(report,encoding='utf-8')
    print(report)

if __name__=='__main__':main()
