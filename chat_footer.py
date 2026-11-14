import streamlit as st
from agent import data,config,cache
SOURCE_CREDIT='출처: 제주특별자치도·제주데이터허브, 한국관광공사, 기상청(공공누리 제1유형), 공공데이터포털 주차장정보, 국토교통부 브이월드'

def render_footer():
    st.write("닿는제주")
    try:
        counts = data.place_counts()
        origins = data.source_counts()
        dates = data.source_date_ranges()
        st.write(f"판정 가능 장소: {counts.get('상세파일있음', 0)}곳")
        st.write(f"데이터 기준일: 제주데이터허브 {dates['hub']['lo']}~{dates['hub']['hi']} / 관광공사 최근 수정 {dates['kto']['hi']}")
        st.caption('출처별 콘텐츠 기준일이며 현장 조사일이 아닙니다.')
        st.write(f"핵심·필수 데이터: 제주데이터허브 {origins.get('제주데이터허브(필수)',0)}곳 / 보조 출처: 한국관광공사 {origins.get('한국관광공사(보조)',0)}곳(중복 포함)")
    except data.DataError as e:
        st.write(str(e))
    if st.session_state.get('res'):
        import result_view
        result_view.render_system(st.session_state.res)
    st.write('문장 이해: ' + ('LLM 모드' if config.llm_enabled() else '규칙 모드'))
    st.write('날씨: ' + ('기상청 연동' if config.KMA_SERVICE_KEY else '키 없음'))
    st.caption(cache.usage_text() + f" · 가정 환율 1 USD={config.LLM_USD_KRW:g}원. 캐시 재사용 제외·실패 요청 포함. 할인·무료 구간·세금 미반영. 월 비용 차단 없음.")
    st.caption(SOURCE_CREDIT)

    from map_display import NOTE
    st.caption(NOTE)
    st.markdown('**출처 상세**')
    for line in ['제주특별자치도·제주데이터허브: 무장애 시설·코스 위치·주변정보 원문(핵심 출처)', '한국관광공사: 무장애 여행 정보 원문·수정일(보조 출처)', '기상청: 단기·중기예보(공공누리 제1유형·출처표시)', '공공데이터포털 주차장정보: 제주시·서귀포시 주차장 CSV', '국토교통부 브이월드: 일반·위성 배경지도와 미리보기', '배경 대체 시 CARTO·OpenStreetMap 기여자: 지도 오른쪽 아래 실제 배경 출처 참조']:
        st.write(line)
    if config.llm_enabled():st.caption('AI 사용 시 질문과 공개 자료가 외부 API로 전송돼요.')

@st.dialog('자료 안내',width='large')
def show_information():
    render_footer()
