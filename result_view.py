"""결과 표시 전용. 시설 상태·등급·순위를 계산하거나 변경하지 않는다."""
import datetime as dt
import html
import json
import re
import pandas as pd
import pydeck as pdk
import streamlit as st
import map_display
from agent import data, parking, tools

ICON={'있음':'✅','없음':'❌','조건부':'⚠️','미확인':'❔'}


def facility_text(result,only_parking=False):
    park=result['access'].get('parking') or {}
    general=(park.get('general') or {}).get('display','미확인')
    disabled=(park.get('disabled') or {}).get('original_status','미확인')
    supplement=(park.get('disabled') or {}).get('supplement')
    if supplement:disabled+=' · '+supplement+' (근처·장소 전용 여부 미확인)'
    if general.startswith('근처'):general+=' (근처·장소 전용 여부 미확인)'
    def token(label,value):
        status=next((s for s in ICON if value.startswith(s)),'조건부' if value.startswith('근처') else '미확인')
        return ICON[status]+' '+label+': '+value
    parts=[token('일반 주차',general),token('장애인 주차',disabled)]
    if not only_parking:
        toilet=next((t['status'] for t in result['access']['table'] if t['item']=='장애인화장실'),'미확인')
        parts.append(token('장애인 화장실',toilet))
    return ' · '.join(parts)


def facts(result):
    route=result['route'];slope=route.get('max_slope')
    slope_text=('❔ 경사 측정값 없음(안전 확인 아님)' if slope is None else ('⚠️ ' if route['over_ref'] else '✅ ')+f"최대 경사 {slope:g}°"+(' · 기준(약 4.8°)보다 가파름' if route['over_ref'] else ' · 기록된 값은 참고 기준 이하'))
    assessment=(result.get('use_assessment') or {}).get('text','')
    if '분리 지점' in assessment:barrier='⚠️ 계단길·휠체어길 분리 지점 있음'
    elif any('계단' in str(p.get('label',''))+str(p.get('description','')) for p in route['points']):barrier='⚠️ 계단 구간 있음 · 원문과 우회 정보 확인 필요'
    else:barrier='❔ 구간별 원문 확인 필요 · 특이 언급이 없다고 안전한 것은 아님'
    return [slope_text,barrier,facility_text(result)]


def conclusion(result):
    return (result.get('use_assessment') or {}).get('text','이용 판단: 확인 필요(상세 근거 확인)').split(' — ')[0]


def weather_line(res):
    if not res['results']:return '날씨: 판정 후보 없음'
    weather=res['results'][0].get('weather') or {}
    advice=res.get('day_recommendation') or {}
    if weather.get('status')=='조회됨':
        line=f"날씨: {weather.get('sky','')} · 강수 {weather.get('pop_max','미확인')}%"
        if weather.get('cautions'):line+=' · 실외 코스 주의'
    else:line='날씨: '+weather.get('reason','방문일 예보 미확인')
    if advice.get('choices') or advice.get('best'):
        choices=advice.get('choices') or [advice['best']]
        labels=[]
        for row in choices:
            d=dt.date.fromisoformat(row['date'])
            labels.append(f"{d.month}/{d.day}({'월화수목금토일'[d.weekday()]}) 강수 {row['pop']}% — 이날 방문 추천")
        line+=' / '+' · '.join(labels)+' (맑음·안전 보장 아님)'
    elif advice:line+=' / '+(advice.get('reason') or '비교 가능한 날짜 예보 없음')
    missing=sum(r.get('eligible',True) and (r.get('status')!='조회됨' or r.get('pop') is None) for r in advice.get('rows',[]))
    if missing:line+=f' · 예보 미확인 {missing}일은 비교 제외'
    return line


def sources(res):
    labels=[]
    files=set()
    for r in res['results']+res.get('convenience_results',[]):
        for t in r['access']['table']:
            proof=str(t.get('evidence') or '')
            if t.get('source') and '허브' in t['source']:labels.append('제주특별자치도·제주데이터허브')
            if t.get('source') and '관광공사' in t['source']:labels.append('한국관광공사')
            files.update(re.findall(r'[^\s/“”]+\.(?:hwp|csv)',proof))
        for p in r['route']['points']:
            if p.get('file_name'):files.add(p['file_name']);labels.append('제주특별자치도·제주데이터허브 위치정보')
        for lot in (r['access'].get('parking') or {}).get('nearby',[]):
            files.add(lot['source_file']);labels.append('전국주차장정보표준데이터')
        address=r['place'].get('_address_evidence') or {}
        if address.get('evidence') and address.get('reason')!='장소 자체 주소':labels.append('제주데이터허브 색인(주소 보완)')
        nearby=r.get('nearby') or {}
        if nearby.get('rows'):labels.append('제주데이터허브 주변정보')
        if (r.get('weather') or {}).get('status')=='조회됨':labels.append('기상청(공공누리 제1유형)')
    if any(row.get('status')=='조회됨' for row in (res.get('day_recommendation') or {}).get('rows',[])):labels.append('기상청(공공누리 제1유형)')
    hub=[x for x in labels if '제주데이터허브' in x]
    summary=[]
    if hub:
        kinds=[]
        if '제주특별자치도·제주데이터허브' in hub:kinds.append('시설')
        for word in ('위치','색인','주변'):
            if any(word in x for x in hub):kinds.append(word)
        summary.append('제주특별자치도·제주데이터허브('+ '·'.join(kinds)+')')
    summary += [x for x in labels if '제주데이터허브' not in x]
    return '이 답에 쓰인 데이터: '+(' / '.join(dict.fromkeys(summary)) or '조회 가능한 출처 없음'),sorted(files)



def top_facts(res):
    lines=facts(res['results'][0])
    if res['results'][0]['route']['max_slope'] is None:
        measured=next((r for r in res['results'] if r['route']['max_slope'] is not None),None)
        lines[0]+=('; 측정값 있는 최상위: '+measured['place']['name']+f"(최대 {measured['route']['max_slope']:g}°)" if measured else '; 후보 중 측정값 있는 장소 없음')
    alternative=res['results'][0].get('toilet_alternative') or {}
    if alternative.get('message'):lines[2]+=' / 대안: '+alternative['message']
    return lines


def display_goal(res):
    if res.get('anchor') or any(r.get('requested_place') for r in res['results']):return res['goal']
    return res['request'].get('text') or res['goal']


def explanation_text(res):
    text=res.get('explanation') or '기록된 원문을 바탕으로 이용 조건을 확인했습니다. 전체 코스의 안전을 보장하지 않으므로 주의 구간을 확인하세요.'
    # 별도 한 줄로 표시하는 시설 상태의 반복만 덜고 위치·구간 설명은 남긴다.
    sentences=re.split(r'(?<=[.!?])\s+',text)
    out=[]
    for sentence in sentences:
        duplicate=re.search(r'화장실(?:과|이|은|는|·|,)|주차장(?:이|은|는|과|도)',sentence) and re.search(r'있(?:다|습|고)|없(?:다|습|고)|확인됐|확인되',sentence)
        location=re.search(r'오른쪽|왼쪽|위치|안쪽|바깥',sentence)
        if duplicate and not location:
            if res['results'] and res['results'][0]['place']['name'] in sentence:
                out.append(res['results'][0]['place']['name']+'의 일부 시설·구간 원문을 확인했습니다.')
        else:out.append(sentence)
    return ' '.join(out) or text


def copy_text(res):
    top=res['results'][0] if res['results'] else None
    lines=[display_goal(res)]
    if top:
        lines += [conclusion(top),explanation_text(res),*top_facts(res)]
    else:lines.append(res['summary'])
    lines += [weather_line(res),sources(res)[0]]
    return '\n\n'.join(lines)


def copy_button(text,key=""):
    button_id="result-copy-"+__import__("hashlib").sha256((key+text).encode()).hexdigest()[:16]
    safe=html.escape(text,quote=True)
    # 사용자 텍스트는 HTML 속성으로만 전달하고 실행 스크립트에 넣지 않는다.
    body=f'<button id="{button_id}" data-copy-text="{safe}" style="min-height:44px;padding:10px 18px;border-radius:8px;border:1px solid #888;background:white;cursor:pointer">결과 복사</button>'
    body+="""<script>
    (()=>{
      const button=document.getElementById('result-copy-button');
      if(!button)return;
      button.onclick=async()=>{
        const text=button.dataset.copyText;
        try { await navigator.clipboard.writeText(text); button.textContent='✅ 복사 완료'; }
        catch(error) {
          const field=document.createElement('textarea');field.value=text;
          field.style.position='fixed';field.style.left='-9999px';document.body.appendChild(field);
          field.select();const copied=document.execCommand('copy');field.remove();
          button.textContent=copied?'✅ 복사 완료':'복사 실패 — 텍스트 보기에서 복사';
        }
      };
    })();
    </script>"""
    body=body.replace("result-copy-button",button_id)
    st.html(body,unsafe_allow_javascript=True)


def warning_card(warning):
    with st.container(border=True):
        st.markdown(f"**{'❌' if warning['level']==2 else '⚠️'} {warning['number']}. {warning['title']}**")
        if warning['count']>1:st.caption(f"같은 내용 지점 {warning['count']}곳")
        st.write('원문: “'+warning['quote']+'”')
        for quote in warning.get('additional_quotes',[]):st.caption('함께 묶은 원문: '+quote)
        # 모든 출처 행은 생략하지 않는다.
        rows={}
        for source in warning['sources']:
            name=source.split(' [')[0];row=re.search(r'row (\d+)',source)
            rows.setdefault(name,[]).append(row.group(1) if row else source)
        for name,values in rows.items():st.caption('출처: '+name+' · row '+', '.join(values))
        if warning['alternative']:
            st.write('대체 경로 원문: “'+warning['alternative']+'”')
            st.caption(warning['alternative_source'])


def course_map(result):
    model=map_display.prepare(result)
    st.markdown('### '+result['place']['name']+' 코스')
    st.caption(f"조사 지점 {model['count']}곳 · 주의 {len(model['warnings'])}곳 · 출처: 제주데이터허브 위치정보"+(' · 휠체어길 별도 운영(원문)' if model['whole_alt'] else ''))
    st.markdown(':green[● 편한 구간]　:orange[● 주의(경사·우회 필요)]　:red[● 어려움(우회 정보 없는 계단·단차)]')
    st.caption('구간 색은 원문 기준이며 안전 판정이 아닙니다. 우회 가능 여부는 현장에서 확인하세요.')
    st.pydeck_chart(map_display.deck(model),use_container_width=True,height=480,key='course_'+result['place']['place_id'])
    st.caption(map_display.NOTE)
    for warning in model['warnings'][:5]:warning_card(warning)
    if len(model['warnings'])>5:
        with st.expander(f"주의 지점 더 보기({len(model['warnings'])-5}곳)"):
            for warning in model['warnings'][5:]:warning_card(warning)


def detail(result,primary=False):
    p=result['place'];acc=result['access'];route=result['route']
    with st.container(border=True):
        st.subheader(p['name']+(' 상세' if primary else ''))
        if not primary:
            st.write(conclusion(result))
            st.write(facility_text(result))
        if p.get('address'):st.caption(p['address'])
        else:st.caption('주소 미확인')
        if p.get('_distance_km') is not None:st.caption(f"직선거리 {p['_distance_km']:.2f} km")
        weather=result.get('weather') or {}
        if weather.get('status')=='조회됨':st.caption(f"날씨 · 강수 {weather.get('pop_max','미확인')}%")
        with st.expander('근거·시설 판정'):
            st.write('시설 조건 등급: '+result['grade'])
            if result.get('use_assessment'):
                for proof in result['use_assessment']['evidence']:st.caption(proof)
            if p.get('_address_evidence'):st.json(p['_address_evidence'])
            st.dataframe(pd.DataFrame([dict(항목=t['item'],상태=ICON.get(t['status'],'❔')+' '+t['status'],원문=t.get('raw'),출처=t.get('source'),근거=t.get('evidence'),기준일=t.get('base_date')) for t in acc['table']]),hide_index=True,use_container_width=True)
            for c in acc.get('conflicts',[]):st.write('⚠️ 출처 간 차이: '+str(c))
            for lot in (acc.get('parking') or {}).get('nearby',[]):
                st.write(f"근처 주차장: {lot['name']} · {lot['distance_m']}m · {lot['spaces']}면 · {lot.get('fee_summary','요금 미확인')}")
                st.caption(lot['evidence'])
        with st.expander('코스·주변 시설·날씨 상세'):
            if route['course_slopes']:st.dataframe(pd.DataFrame(route['course_slopes']),hide_index=True,use_container_width=True)
            if route['cautions']:st.dataframe(pd.DataFrame(route['cautions']),hide_index=True,use_container_width=True)
            nearby=result.get('nearby')
            if nearby:st.caption(tools.nearby_summary(nearby))
            if nearby and nearby.get('rows'):st.dataframe(pd.DataFrame(nearby['rows']),hide_index=True,use_container_width=True)
            if weather:st.json({k:v for k,v in weather.items() if k!='cautions'})
            indoor=result.get('indoor_alternative')
            if indoor:
                st.write(indoor['message'])
                for option in indoor['options']:
                    for proof in option['evidence']:st.caption(proof['source'])
            day=result.get('rain_days')
            if day and day.get('rows'):st.dataframe(pd.DataFrame(day['rows']),hide_index=True,use_container_width=True)


ACTIONS={
 'list_regions':'지역 이름을 준비했습니다','parse_request':'질문에서 이용 조건을 읽었습니다',
 'lookup_named_place':'질문에 적힌 장소를 찾았습니다','search_places':'보유 장소에서 후보를 찾았습니다',
 'check_accessibility + check_route':'필수 시설과 코스 경사를 확인했습니다','assess_named_visit':'지정 장소의 이용 범위를 원문과 대조했습니다',
 'find_named_nearby_alternatives':'지정 장소 가까이에 있는 대안을 찾았습니다','rank_slope':'같은 등급 안에서 경사 정보를 비교했습니다',
 'check_weather':'방문 날짜의 날씨를 확인했습니다','recommend_rain_days':'날씨 나쁨 → 다른 날짜 자동 조회',
 'recommend_visit_day':'방문하기 좋은 날짜를 비교했습니다','find_indoor_alternative':'같은 지역의 실내 대안을 조사했습니다',
 'find_nearby':'주변 시설의 보유 정보를 확인했습니다','explain':'원문 근거로 답변을 정리했습니다',
 'resolve_anchor':'기준 위치를 찾았습니다','filter_anchor_distance':'기준 위치와 후보의 거리를 확인했습니다',
 'rank_walking_conditions':'원문에 있는 보행 조건을 비교했습니다'}


def render(res):
    from app_results import render as render_app
    render_app(res)


def render_system(res):
    from app_results import render_system as render_info
    render_info(res)


def full_text(res):
    """현재 표시 구조와 펼친 근거/작업 과정을 포함한 전체 텍스트 저장."""
    lines=[copy_text(res),'날짜별 예보 비교']
    lines += [json.dumps(row,ensure_ascii=False) for row in (res.get('day_recommendation') or {}).get('rows',[])]
    lines += ['지도·주의 지점',map_display.NOTE]
    for result in res['results']:
        lines.append('\n'+result['place']['name']+' 코스')
        for w in map_display.prepare(result)['warnings']:
            lines += [f"{w['number']}. {w['title']} · 같은 내용 지점 {w['count']}곳",w['quote'],*w['sources']]
            if w['alternative']:lines += [w['alternative'],w['alternative_source']]
        lines += ['장소 상세: '+result['place']['name'],conclusion(result),result['place'].get('address') or '주소 미확인',facility_text(result),'근거: 시설 조건 등급 '+result['grade']]
        lines += [json.dumps(t,ensure_ascii=False) for t in result['access']['table']]
        if result['place'].get('_address_evidence'):
            lines += ['주소 선택 근거',json.dumps(result['place']['_address_evidence'],ensure_ascii=False)]
    if res.get('convenience_results'):
        lines.append('근처 식사·편의 장소')
        for r in res['convenience_results']:
            p=r['place'];lines += [p['name']+' · '+p.get('_place_type',{}).get('label','유형 미확인')+f" · {p.get('_distance_km',0):.2f} km",facility_text(r,only_parking=True)]
    lines += ['Agent 작업 과정']+[f"{s['no']}. 무엇을: {ACTIONS.get(s['tool'],s['purpose'])} / 왜: {s['purpose']} / 결과: {s['output']} / {s['ms']}ms" for s in res['trace']]
    lines += ['데이터 한계',*res['limits'],sources(res)[0]]
    return '\n'.join(lines)
