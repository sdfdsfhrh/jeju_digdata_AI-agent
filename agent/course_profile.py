"""지도와 추천 순위가 함께 사용하는 원문 구간 분류. 시설 상태/등급은 변경하지 않는다."""
import math
import re
from collections import defaultdict
from difflib import SequenceMatcher

GREEN=[35,155,92,240]; ORANGE=[240,146,28,255]; RED=[175,25,40,255]; BLUE=[30,105,220,255]
HARD=r'계단|단차|(?:접근|진입)\s*불가|턱'
ALT=r'휠체어\s*(?:길|접근\s*가능)|우회|경사로|엘리베이터|(?:계단|휠체어|경로|동선|코스|길).{0,15}분리|분리.{0,15}(?:길|동선|경로|계단|휠체어)'
NOTE='선은 조사 지점을 순서대로 이은 것으로 실제 길과 다를 수 있어요.'


def text(p):return ' '.join(str(p.get(k) or '') for k in ('label','description','detail_raw')).strip()
def valid(p):
    try:return math.isfinite(float(p['lat'])) and math.isfinite(float(p['lon'])) and -90<=float(p['lat'])<=90 and -180<=float(p['lon'])<=180
    except (KeyError,TypeError,ValueError):return False

def positive(raw,pattern):
    raw=re.sub(r'(?:계단|단차|턱|휠체어길|우회|경사로|엘리베이터)\s*(?:은|는|이|가)?\s*(?:없음|없는|없다|없습니다|없어)','',raw)
    raw=re.sub(r'턱\s*(?:높이)?\s*[:=]?\s*0\s*(?:cm|㎝|m)\b','',raw)
    return any(not re.match(r'\s*(?:길|장|시설)?\s*(?:은|는|이|가)?\s*(?:없|미설치|불가)',raw[m.end():]) for m in re.finditer(pattern,raw))

def proof(p):return f"{p.get('file_name') or '위치정보'} [{p.get('source_locator') or '지점 '+str(p.get('seq'))}]"


def prepare(result):
    groups=defaultdict(list)
    for p in result['route']['points']:
        if p.get('label')!='삭제':groups[p.get('file_name') or p.get('source_file_id') or '원본'].append(dict(p))
    # 2019 이동좌표(-1)와 조사지점(-2)을 번갈아 잇지 않는다. 서술이 있는 조사 파일이 있으면 그 파일들만 표시.
    described={k:v for k,v in groups.items() if any(text(p) for p in v)}
    chosen=described or groups
    segments=[];warnings=[];facilities=[];allvalid=[];seen_facilities=set()
    number=0
    for name,points in chosen.items():
        points.sort(key=lambda p:(int(p.get('seq') or 0),p.get('point_id','')))
        states=[]
        for i,p in enumerate(points):
            raw=text(p);hard=positive(raw,HARD)
            adjacent=[q for q in points[max(0,i-1):i+2] if positive(text(q),ALT)]
            slopes=[float(m['value']) for m in result['route']['course_slopes'] if str(m.get('point'))==str(p.get('seq')) and (name in m.get('evidence',''))]
            over=any(v>4.76 for v in slopes)
            level=2 if hard and not adjacent else 1 if over or hard else 0
            why=[]
            if hard:
                item='계단' if '계단' in raw else '접근불가' if re.search(r'(접근|진입)\s*불가',raw) else '단차·턱'
                if adjacent:
                    alternative=text(adjacent[0])
                    route='휠체어길로 우회' if re.search(r'휠체어\s*(?:길|접근\s*가능)',alternative) else '원문 대체 경로 확인 필요'
                    why.append(f'{item} 있음 → {route}')
                else:why.append(f'{item} 언급 · 우회 정보 없음')
            if over:why.append(f'경사 {max(slopes):g}° > 약 4.8°')
            state=dict(point=p,level=level,color=[GREEN,ORANGE,RED][level])
            states.append(state)
            if not valid(p):continue
            allvalid.append(p)
            if level:
                number+=1
                detail=' · '.join(why)
                warnings.append(dict(number=number,label=str(number),lat=p['lat'],lon=p['lon'],color=state['color'],level=level,course_order=number,raw_text=raw,slope=max(slopes) if slopes else None,
                    reason=detail,value=f"경사 {max(slopes):g}°" if slopes else '경사 측정값 미확인',quote=raw[:150],source=proof(p),
                    alternative=text(adjacent[0])[:150] if hard and adjacent else None,alternative_source=proof(adjacent[0]) if hard and adjacent else None,
                    info=f"지점 {number} · "+(f"경사 {max(slopes):g}° · " if slopes else '')+('내리막 주의' if '내리막' in raw else detail)[:50]))
            for label,pattern in [('화장실',r'장애인\s*화장실'),('주차',r'장애인\s*주차')]:
                if positive(raw,pattern):
                    key=(label,round(float(p['lat']),4),round(float(p['lon']),4))
                    if key not in seen_facilities:
                        seen_facilities.add(key);facilities.append(dict(label=label,lat=p['lat'],lon=p['lon'],info=f'{label} · {raw[:65]} · {proof(p)}'))
        for before,after in zip(states,states[1:]):
            if not (valid(before['point']) and valid(after['point'])):continue
            level=max(before['level'],after['level']);a,b=before['point'],after['point']
            segments.append(dict(path=[[a['lon'],a['lat']],[b['lon'],b['lat']]],color=[GREEN,ORANGE,RED][level],level=level,
                                 info=f"조사 지점 {a.get('seq')}–{b.get('seq')} · "+['특이 언급 없음(안전 확인 아님)','주의(경사·우회 필요)','어려움(우회 정보 없는 계단·단차)'][level]))
    # 동일 원문/0.9 유사도 및 모든 묶음 지점과30m 이내. 구간 색/등급은 손대지 않는다.
    grouped=[]
    def similar(a,b):return SequenceMatcher(None,re.sub(r'\s+','',a),re.sub(r'\s+','',b)).ratio()>=0.9
    def close(a,b):
        y1,y2=math.radians(float(a['lat'])),math.radians(float(b['lat']))
        dlon=math.radians(float(a['lon'])-float(b['lon']))
        h=math.sin((y2-y1)/2)**2+math.cos(y1)*math.cos(y2)*math.sin(dlon/2)**2
        return 6371000*2*math.asin(min(1,math.sqrt(h)))<=30
    for w in warnings:
        previous=next((v for v in reversed(grouped) if v['source'].split(' [')[0]==w['source'].split(' [')[0]
             and all(close(q,w) and similar(q['raw_text'],w['raw_text']) for q in v['_members'])),None)
        member=dict(w)
        if previous:
            previous['_members'].append(member)
            previous.setdefault('additional_sources',[]).append(w['source'])
            if previous['quote']!=w['quote']:previous.setdefault('additional_quotes',[]).append(w['quote'])
            if w['level']>previous['level']:previous.update(level=w['level'],color=w['color'],reason=w['reason'],alternative=w['alternative'],alternative_source=w['alternative_source'])
            if w['slope'] is not None:previous['slope']=max(previous['slope'] if previous['slope'] is not None else w['slope'],w['slope'])
        else:
            w['_members']=[member];grouped.append(w)
    warnings=sorted(grouped,key=lambda w:(-w['level'],w['course_order']))
    for i,w in enumerate(warnings,1):
        w['number']=i;w['label']=str(i);w['info']=re.sub(r'^지점 \d+',f'지점 {i}',w['info'])
        w['count']=len(w['_members']);w['sources']=[q['source'] for q in w['_members']]
        if '우회 정보 없음' in w['reason']:
            kind='계단' if '계단' in w['raw_text'] else '접근불가' if re.search(r'(접근|진입)\s*불가',w['raw_text']) else '단차·턱'
            w['title']=kind+' · 우회 정보 없음'
        elif w['alternative']:
            kind='계단' if '계단' in w['raw_text'] else '단차·턱'
            w['title']=kind+(' · 휠체어길로 우회 가능' if re.search(r'휠체어\s*(길|접근\s*가능)',w['alternative']) else ' · 경사로 등 대체 경로 확인 필요')
        elif w['slope'] is not None:w['title']=f"경사 {w['slope']:g}° · 기준(약 4.8°)보다 가파름"
        else:w['title']=w['reason']
        w['info']=f"지점 {i} · "+w['title']
    unique=[]
    for facility in facilities:
        if not any(v['label']==facility['label'] and math.hypot((float(v['lat'])-float(facility['lat']))*111000,(float(v['lon'])-float(facility['lon']))*93000)<20 for v in unique):
            unique.append(facility)
    facilities=unique
    entrance=next((p for pts in chosen.values() for p in sorted(pts,key=lambda x:int(x.get('seq') or 0)) if valid(p)),None)
    entrance=dict(label='입구',lat=entrance['lat'],lon=entrance['lon'],info='입구 표시: 첫 조사 지점(실제 출입구 확정 아님) · '+proof(entrance)) if entrance else None
    if not entrance and valid(result['place']):
        p=result['place'];entrance=dict(label='입구',lat=p['lat'],lon=p['lon'],info='입구 표시: 대표 위치(실제 출입구 미확인) · '+str(p.get('coord_source')));allvalid.append(p)
    whole=' '.join(str(result['place'].get(k) or '') for k in ('overview','mobility_note','recommended_course','full_course'))
    whole+=' '+' '.join(str(t.get('raw') or '') for t in result['access']['table'])
    whole_alt=positive(whole,r'휠체어\s*길')
    return dict(segments=segments,warnings=warnings,facilities=facilities,entrance=entrance,bounds=allvalid,
                count=sum(len(v) for v in chosen.values()),omitted=sum(len(v) for k,v in groups.items() if k not in chosen),whole_alt=whole_alt)


