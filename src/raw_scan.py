"""원본 하위 폴더 조사. images는 개수만 기록하고 공통 가이드는 장소에서 제외."""
import hashlib
import os
from pathlib import Path
from common import file_sha256
from hwp_reader import read_hwp


def folder_place(path, root):
    relative=Path(path).relative_to(root)
    parents=relative.parts[:-1]
    if not parents or parents[-1].lower() in ('2019','2020','2019-2020','images'):
        return None
    return parents[-1]


def scan(root):
    root=Path(root)
    records=[]; files=[]; images={}
    for directory,dirs,names in os.walk(root):
        # 이미지 하위는 목록만 세며 내용·해시·OCR을 읽지 않는다.
        for image in [d for d in dirs if d.lower()=='images']:
            target=Path(directory)/image
            images[target.relative_to(root).as_posix()]=sum(len(ns) for _,_,ns in os.walk(target))
        dirs[:]=[d for d in dirs if d.lower()!='images']
        for name in sorted(names):
            p=Path(directory)/name
            if p.suffix.lower() not in ('.csv','.hwp','.zip'): continue
            rel=p.relative_to(root).as_posix()
            rec=dict(path=rel,folder=folder_place(p,root),bytes=p.stat().st_size,sha256=file_sha256(p))
            if p.suffix.lower()=='.zip':
                rec.update(action='제외',reason='zip은 직접 읽지 않음. 장소별 폴더에 압축 해제 필요')
            elif p.suffix.lower()=='.hwp':
                try:
                    text=read_hwp(str(p)).plain_text()
                    rec['text_sha256']=hashlib.sha256(text.encode('utf-8')).hexdigest()
                    if '가이드' in name and '데이터셋' in text and ('아이디' in text or '공통사항' in text):
                        rec.update(action='제외',reason='공통 데이터셋 구조·관광지 ID 가이드. 장소별 시설 문서가 아님',text_preview=text[:300])
                except Exception:
                    pass  # 실제 파서는 실패 사유를 source_file에 기록한다.
            if 'action' not in rec:
                rec['action']='입력'
                files.append(dict(path=str(p),relative=rel,folder=rec['folder']))
            records.append(rec)
    files.sort(key=lambda f:(not bool(f['folder']),f['relative']))
    return files,dict(files=records,images=images,image_count=sum(images.values()),
                      place_folders=sorted({f['folder'] for f in files if f['folder']}))
