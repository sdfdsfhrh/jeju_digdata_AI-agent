from difflib import SequenceMatcher
from html import escape
import re
import map_display
from agent.recommendation import assessment_order

WORDS=('휠체어로 갈 수 있어요','갈 수 있지만 주의할 곳이 있어요','미리 확인이 필요해요','휠체어로는 어려워요')
COLORS=('#085041','#085041','#92510c','#ad3039')
KINDS=('계단·단차·진입 불가','가파른 길','확인 필요')


def warning_priority(warning):
    """지도 번호와 색은 유지하고, 화면에 표시할 순서만 정한다."""
    slope = warning.get('slope') or 0
    number = warning['number']
    if warning['level'] == 2:
        return (0, 0, number)
    if warning['level'] == 1 and slope > 4.76:
        return (1, -slope, number)
    return (2, 0, number)

def numbers(values):
    runs=[]
    for n in sorted(set(values)):
        if runs and n==runs[-1][-1]+1: runs[-1].append(n)
        else: runs.append([n])
    return ', '.join(str(r[0]) if len(r)==1 else f'{r[0]}–{r[-1]}' for r in runs)

def groups(result, model=None):
    model=map_display.prepare(result) if model is None else model
    out={k:[] for k in KINDS}
    for warning in sorted(model['warnings'], key=warning_priority):
        out[KINDS[warning_priority(warning)[0]]].append(warning)
    return {k:v for k,v in out.items() if v}

def reason(grouped):
    return ', '.join(f'{k} {len(v)}곳' for k,v in grouped.items()) or '주의 구간 기록 없음'

def short(w):
    raw=' '.join((w.get('quote') or '').split())
    return (raw[:65]+'…' if len(raw)>65 else raw) or '조사 지점 원문을 확인해 주세요'

def explanation(grouped):
    rows=[warning for group in grouped.values() for warning in group][:2]
    if not rows:return '구간별 주의 기록이 없어 방문 전 현장 상황을 확인해 주세요.'
    return '지도 '+', '.join(f"{w['number']}번의 ‘{short(w)}’" for w in rows)+'을 미리 확인해 주세요.'

def quotes(rows):
    buckets=[]
    for w in rows:
        for raw in dict.fromkeys([w['quote'],*w.get('additional_quotes',[])]):
            key=re.sub(r'\s+','',raw)
            match=next((b for b in buckets if SequenceMatcher(None,b[0],key).ratio()>=0.8),None)
            if match is None:buckets.append((key,{w['number']},[raw]))
            else:
                match[1].add(w['number'])
                if raw not in match[2]:match[2].append(raw)
    return buckets

CSS='''<style>
.simple-cautions{border:1px solid #e1e6de;border-radius:16px;padding:0 12px;background:white}
.simple-cautions details+details{border-top:1px solid #e1e6de}
.simple-cautions summary{display:grid;grid-template-columns:30px minmax(0,1fr) auto;align-items:center;gap:8px;padding:14px 0;cursor:pointer;list-style:none}
.simple-cautions summary::-webkit-details-marker{display:none}
.caution-icon{border-radius:50%;background:#fae7dd;color:#92510c;text-align:center;padding:4px}.caution-icon.hard{background:#f8dddd;color:#ad3039}
.caution-short,.caution-numbers,.caution-quote{font-size:12px;color:#59685e;overflow-wrap:anywhere}.caution-numbers{text-align:right;max-width:85px}.caution-quote{padding:6px 0}
.simple-decision{border-radius:14px;padding:15px;margin:12px 0;overflow-wrap:anywhere}.simple-decision div{margin-top:5px}
.simple-chip{display:inline-block;border-radius:20px;padding:4px 9px;background:#eef1ee;color:#58635c;font-size:12px}.simple-chip.yes{background:#dceedd;color:#085041}.simple-chip.partial{background:#fff0d8;color:#92510c}
</style>'''

def markup(grouped):
    parts=[]
    for k,rows in grouped.items():
        slopes=[w['slope'] for w in rows if w.get('slope') is not None] if k==KINDS[1] else []
        span=f' · {min(slopes):g}°~{max(slopes):g}°' if slopes and min(slopes)!=max(slopes) else f' · {max(slopes):g}°' if slopes else ''
        worst=rows[0]
        body=''.join(f'<div class="caution-quote"><strong>지도 {numbers(ids)}</strong> · {escape(" / ".join(raws))}</div>' for _,ids,raws in quotes(rows))
        if slopes:body+='<div class="caution-quote">기준: 건축물 경사로 1/12(약 4.8°)</div>'
        icon='<span class="caution-icon hard" aria-hidden="true">▥</span>' if k==KINDS[0] else '<span class="caution-icon" aria-hidden="true">↗</span>' if slopes else '<span class="caution-icon" aria-hidden="true">!</span>'
        parts.append(f'<details><summary>{icon}<span><strong>{k} {len(rows)}곳{span}</strong><br><span class="caution-short">{escape((f"{worst['slope']:g}° · " if slopes else "")+short(worst))}</span></span><span class="caution-numbers">지도 {numbers(w["number"] for w in rows)} ▾</span></summary>{body}</details>')
    return '<div class="simple-cautions">'+''.join(parts)+'</div>' if parts else '<div class="caution-short">주의 구간 기록 없음</div>'
