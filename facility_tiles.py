"""상세 시설 타일 표시만 담당. 기존 시설 상태와 예보 결과를 그대로 읽는다."""
import base64
import datetime as dt
import html
from functools import lru_cache
from pathlib import Path

ROOT=Path(__file__).resolve().parent/'static/icons'
GREEN='#085041'
STATES={'있음':('check',GREEN),'없음':('x','#ad3039'),'조건부':('exclamation-mark','#b65b19'),'미확인':('question-mark','#717b76')}
ICONS={'parking','wheelchair','sun','cloud','cloud-rain','cloud-storm','check','x','exclamation-mark','question-mark','chevron-down'}
CSS='''<style>
.facility-panel{margin:16px 0 20px}.facility-panel>summary.facility-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:6px;list-style:none;pointer-events:none}
.facility-panel>summary::-webkit-details-marker{display:none}.facility-panel>summary::marker{content:""}
.facility-box{box-sizing:border-box;min-width:0;background:#f4f6f1;border:1px solid #e4e9e1;border-radius:12px;padding:14px 6px;display:flex;align-items:center;flex-direction:column;text-align:center;gap:9px;overflow-wrap:anywhere;word-break:keep-all}
.facility-box img{display:inline-block;flex-shrink:0}.facility-label{font-size:12px;color:#64736a;line-height:1.5}.facility-state{font-size:17px;font-weight:700;line-height:1.6;display:inline-flex;justify-content:center;align-items:center;gap:3px;flex-wrap:wrap}
.facility-parking{display:flex;flex-direction:column;gap:5px;width:100%}.facility-parking-row{display:flex;justify-content:center;align-items:center;gap:5px;flex-wrap:wrap;line-height:1.6}.facility-kind{font-size:12px;color:#56675b}
.facility-weather{pointer-events:auto;cursor:pointer}.facility-weather:hover{border-color:#085041}.facility-panel>summary:focus-visible{outline:none}.facility-panel>summary:focus-visible .facility-weather{outline:2px solid #085041;outline-offset:2px}
.facility-recommend{font-size:11px;line-height:1.6;padding:3px 5px;background:#e1eddf;color:#28543d;border-radius:8px;max-width:100%;box-sizing:border-box}.facility-weather-note{font-size:11px;color:#b65b19;line-height:1.5}.facility-more{font-size:10px;color:#64736a;line-height:1.5;display:flex;gap:2px;align-items:center;justify-content:center;flex-wrap:wrap;margin-top:auto}
.facility-weather-table{margin-top:10px;border:1px solid #e0e6dc;border-radius:12px;padding:12px;font-size:13px;overflow-wrap:anywhere}.facility-weather-table table{width:100%;border-collapse:collapse;table-layout:fixed}.facility-weather-table th,.facility-weather-table td{padding:7px 3px;border-bottom:1px solid #e4e9e1;text-align:left;white-space:normal;overflow-wrap:anywhere}.facility-weather-table p{font-size:12px!important;color:#64736a}
@media(max-width:640px){.facility-box{padding:12px 4px;gap:8px}.facility-label,.facility-kind{font-size:11px}.facility-state{font-size:15px;gap:2px}.facility-parking-row{gap:3px}.facility-weather-table{padding:9px;font-size:12px}}
</style>'''

def esc(value):return html.escape(str(value),quote=True)

@lru_cache(maxsize=64)
def icon(name,color=GREEN,size=24):
    if name not in ICONS:raise ValueError('허용하지 않은 표시 아이콘')
    svg=(ROOT/(name+'.svg')).read_text(encoding='utf8').replace('currentColor',color)
    encoded=base64.b64encode(svg.encode()).decode()
    return f'<img src="data:image/svg+xml;base64,{encoded}" width="{size}" height="{size}" alt="" aria-hidden="true">'

def state(value,label=None):
    name,color=STATES.get(value,STATES['미확인'])
    return '<span class="facility-state" style="color:'+color+'">'+icon(name,color,16)+'<span>'+esc(label or value)+'</span></span>'

def weather_icon(weather):
    if weather.get('status')!='조회됨':return 'question-mark'
    sky=str(weather.get('sky') or '')
    if any(x in sky for x in ('천둥','번개','뇌우')):return 'cloud-storm'
    if weather.get('precip') is True or any(x in sky for x in ('비','소나기','눈')):return 'cloud-rain'
    return 'sun' if '맑' in sky else 'cloud'

def date_label(value):
    try:
        date=dt.date.fromisoformat(value)
        return f"{date.month}/{date.day}({'월화수목금토일'[date.weekday()]})"
    except (ValueError,TypeError):return str(value or '날짜 미확인')

def forecast_table(weather,advice,visit_date=None):
    rows=advice.get('rows') or []
    if not rows and visit_date and weather.get('status')=='조회됨':
        rows=[dict(date=visit_date,pop=weather.get('pop_max'),forecast_type=weather.get('forecast_type'))]
    content='<strong>날짜별 강수확률</strong>'
    if rows:
        content+='<table><thead><tr><th>날짜</th><th>강수확률</th><th>예보</th></tr></thead><tbody>'
        for row in rows:
            pop=str(row['pop'])+'%' if row.get('pop') is not None else '미확인'
            kind=row.get('forecast_type') or '미확인'
            if row.get('eligible') is False:kind+=' · 비교 제외'
            content+='<tr>'+''.join('<td>'+esc(x)+'</td>' for x in (date_label(row.get('date')),pop,kind))+'</tr>'
        content+='</tbody></table>'
    else:content+='<p>날짜별 예보 비교 자료가 없어요.</p>'
    for text in [weather.get('reason'),weather.get('fallback_note'),advice.get('reason')]:
        if text:content+='<p>'+esc(text)+'</p>'
    return content+'<p>예보는 바뀔 수 있으며 맑음과 안전을 보장하지 않습니다. 출처: 기상청(공공누리 제1유형)</p>'

def markup(result,advice=None,visit_date=None):
    advice=advice or {};access=result['access'];weather=result.get('weather') or {}
    general=(access.get('parking') or {}).get('general') or {}
    lookup={t['item']:t['status'] for t in access['table']}
    general_state=general.get('status','미확인')
    general_label='근처 있음' if general.get('options') and general_state=='조건부' else general_state
    parking=''.join('<div class="facility-parking-row"><span class="facility-kind">'+name+'</span>'+state(value,label)+'</div>' for name,value,label in [('일반',general_state,general_label),('장애인',lookup.get('장애인주차장','미확인'),None)])
    first='<div class="facility-box">'+icon('parking')+'<div class="facility-label">주차</div><div class="facility-parking">'+parking+'</div></div>'
    second='<div class="facility-box">'+icon('wheelchair')+'<div class="facility-label">장애인 화장실</div>'+state(lookup.get('장애인화장실','미확인'))+'</div>'
    pop=weather.get('pop_max')
    value=f'강수 {pop}%' if weather.get('status')=='조회됨' and pop is not None else '미확인'
    weather_value='<span class="facility-state" style="color:'+GREEN+'">'+esc(value)+'</span>' if value!='미확인' else '<span class="facility-state" style="color:#717b76">예보 없음</span>'
    recommended=(advice.get('choices') or ([advice['best']] if advice.get('best') else []))
    chip='<span class="facility-recommend">'+esc(date_label(recommended[0].get('date'))+' 방문 추천')+'</span>' if recommended else ''
    caution='<span class="facility-weather-note">실외 코스 주의</span>' if weather.get('cautions') else ''
    credit = '<span class="facility-more">기상청 · 공공누리 제1유형</span>' if weather.get('status') == '조회됨' or recommended else ''
    third='<div class="facility-box facility-weather">'+(icon(weather_icon(weather)) if value!='미확인' else '')+'<div class="facility-label">날씨</div>'+weather_value+chip+caution+credit+'<span class="facility-more">날짜별 예보 보기'+icon('chevron-down','#64736a',13)+'</span></div>'
    return CSS+'<details class="facility-panel"><summary class="facility-grid" aria-label="날씨 · 날짜별 강수확률 펼치기">'+first+second+third+'</summary><div class="facility-weather-table">'+forecast_table(weather,advice,visit_date)+'</div></details>'
