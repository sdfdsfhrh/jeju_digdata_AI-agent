"""2019~20 지점 CSV 원문에서 명시된 시설만 추출. 일반 시설을 장애인 시설로 추정하지 않는다."""
import re
from extract_hwp import Result
from common import YES, NO, COND, UNK


def extract_facilities(points, source_name=""):
    # 050 원문은 성산항→선박→우도 전체 여정. 섬의 시설을 성산항 시설로 오인하지 않음.
    if source_name=="050-2.csv":
        end=next((i for i,p in enumerate(points) if "선박 화장실" in (p.get("label") or "")),len(points))
        points=points[:end]
    result = Result('points_2019')
    for item, pattern in [('장애인화장실', r'장애(?:인|우)?\s*(?:전용|공용)?\s*화장실'),
                          ('장애인주차장', r'장애(?:인|우)?\s*(?:전용)?\s*주차'),
                          ('출입 경사로', r'경사로')]:
        matches=[]
        for p in points:
            text=' '.join(filter(None,[p.get('label'),p.get('description'),p.get('detail_raw')]))
            if not re.search(pattern,text): continue
            direct=' '.join(filter(None,[p.get('label'),p.get('description')]))
            if not re.search(pattern,direct) and 'etc 범례 row' in (p.get('detail_raw') or '') and (p.get('lat') is None or p.get('lon') is None):
                continue  # 범례 코드만 있고 실제 좌표 지점도 없으면 시설 존재를 확정하지 않는다.
            if item=='출입 경사로':
                if not re.search(r'입구|출입|진입',text) or re.search(r'화장실|전망대|이니스프리',text): continue
            elif item=='장애인화장실' and re.search(r'가는\s*길|방향|진입로|올라가는\s*길',p.get('label') or '') and not re.search(pattern,p.get('description') or ''):
                continue
            clean=re.sub(r'특이사항\s*없음','',text)
            negative=bool(re.search(pattern+r'(?:장|구역|공간)?\s*(?:은|는|이|가)?\s*(?:없음|없다|없습니다|미설치)',clean))
            conditional=bool(re.search(r'도움|동행|예약|주의|턱|단차|가파|불편|제한|계단|경사(?:로)?\s*[(]?\s*\d|\d+\s*도\s*경사로',text))
            matches.append((NO if negative else COND if conditional else YES,text,p['source_locator']))
        if matches:
            states={m[0] for m in matches}
            state=COND if COND in states or (NO in states and YES in states) else next(iter(states))
            raw='\n'.join(dict.fromkeys(m[1] for m in matches))
            loc='; '.join(dict.fromkeys(m[2] for m in matches))
            result.add_item('서술형 지점',item,raw,loc,'rule',evidence=raw,status=state,
                            reason='지점별 있음/없음 또는 계단·경사·단차 등 원문 접근 조건 확인 필요' if state==COND else '지점 CSV에 장애인 시설/출입 경사로 명시')
        else:
            result.add_item('서술형 지점',item,None,'전체','rule',status=UNK,
                            reason='지점 CSV에 해당 시설을 확정할 원문 없음(시설 없음 아님)')
            result.failures.append((item,'지점 CSV에 명시 근거 없음','전체'))
    return result
