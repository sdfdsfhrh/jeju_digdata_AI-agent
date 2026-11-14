"""18곳 전체 수동 원문 대조 기준과 추출값·연결·실내 대안 검증. 외부 호출 없음."""
import json
import sys
from pathlib import Path
from unittest.mock import patch
from agent import config, core, data, indoor, tools
from agent.parser import Request

sys.path.insert(0,str(Path(__file__).parent/'src'))
from common import read_csv_auto
from extract_hwp import extract_narrative_2019
from hwp_reader import read_hwp
from legacy_points import extract_facilities
from prep_csv import parse_points_2019

# 순서: 장애인 화장실 / 장애인 주차 / 출입 경사로. 공란은 없음이 아닌 미확인.
EXPECTED={
 '한림공원':('있음','있음','조건부'), '천지연폭포':('조건부','미확인','미확인'),
 '섭지코지(휘닉스아일랜드&섭지코지주차장)':('있음','있음','미확인'),
 '주상절리(산책로)':('있음','미확인','미확인'), '비자림':('조건부','미확인','미확인'),
 '카멜리아힐':('조건부','미확인','미확인'), '오설록':('미확인','미확인','조건부'),
 '절물휴양림':('있음','있음','조건부'), '협재해수욕장':('있음','있음','조건부'),
 '성읍민속마을':('조건부','있음','미확인'), '우도성산항여객터미널':('있음','있음','미확인'),
 '제주국립박물관':('있음','미확인','있음'), '빛의 벙커':('있음','미확인','미확인'),
 '해녀박물관':('있음','있음','미확인'), '서귀포매일올레시장':('있음','미확인','미확인'),
 '함덕서우봉해변':('조건부','미확인','미확인'), '산굼부리':('조건부','있음','미확인'),
 '삼양해수욕장':('조건부','미확인','미확인'),
}
ITEMS=['장애인화장실','장애인주차장','출입 경사로']


def main():
    audit=[]
    for name,expected in EXPECTED.items():
        places=[p for p in data.detailed_places() if p['name']==name]
        assert len(places)==1,(name,places)
        p=places[0]
        source_items=[a for a in data.items(p['place_id']) if a.get('origin')=='제주데이터허브(필수)' and a['extract_method']=='rule']
        for item,status in zip(ITEMS,expected):
            matches=[a for a in source_items if a['item']==item]
            assert matches and all(a['status']==status for a in matches),(name,item,status,[(a['status'],a['value_raw']) for a in matches])
            for a in matches:
                if a['value_raw']:
                    assert a['evidence'] and a['source_locator'] and a['file_name']
                assert a['verify_status']=='검토필요(서술문)'
            audit.append(dict(name=name,place_id=p['place_id'],item=item,expected=status,actual=matches[0]['status'],sources=matches))
    # 중립 표현·다른 장소·사진 없는 추정·백사장 접근 조건 회귀.
    simple=lambda text: extract_facilities([dict(label=text,description='',detail_raw='',source_locator='row 2')])
    assert next(a for a in simple('장애인 주차구역 특이사항없음').items if a['item']=='장애인주차장')['status']=='있음'
    assert next(a for a in simple('장애인 화장실 없음').items if a['item']=='장애인화장실')['status']=='없음'
    assert next(a for a in simple('일반 화장실').items if a['item']=='장애인화장실')['status']=='미확인'
    light=extract_narrative_2019(read_hwp('data/raw/제주특별자치도_무장애여행정보_빛의벙커.hwp'),expected_name='빛의벙커')
    assert not any(m['value']==7 for m in light.measures),'바움커피박물관 경사를 본 장소에 혼합 금지'
    terminal=next(p for p in data.detailed_places() if p['name']=='우도성산항여객터미널')
    assert all('하우목동항' not in (a['value_raw'] or '') for a in data.items(terminal['place_id']))
    assert indoor.evidence(terminal)
    for name in ['오설록','제주국립박물관','해녀박물관','빛의 벙커']:
        assert indoor.evidence(next(p for p in data.detailed_places() if p['name']==name)),name
    # 비 예보·같은 구좌읍·화장실 필수: 해녀박물관 등 근거 있는 대안만.
    coast=next(p for p in data.detailed_places() if '행원리' in p['name'])
    alternative=indoor.alternatives(coast,Request(user_type='수동휠체어',needs=['장애인화장실']))
    assert alternative['options']
    assert all(data.region_of(o['place']['address'])==data.region_of(coast['address']) for o in alternative['options'])
    assert all(o['evidence'] and o['grade'] in (tools.G_OK,tools.G_COND) for o in alternative['options'])
    rain={'status':'조회됨','sky':'흐림','wind_max':2,'forecast_type':'단기','precision':'모의 시간별','pop_max':80,'precip':['비'],'cautions':[]}
    with patch.object(config,'KMA_SERVICE_KEY','mock'),patch.object(tools,'check_weather',return_value=rain):
        r=core.run('행원리 풍차마을 내일 휠체어 화장실',use_llm=False)
        assert any(s['tool']=='find_indoor_alternative' for s in r['trace'])
        assert any(s['tool']=='find_indoor_alternative' and s['ok'] for s in r['trace'])
    with patch.object(config,'KMA_SERVICE_KEY',''):
        r=core.run('행원리 풍차마을 내일 휠체어 화장실',use_llm=False)
        assert not any(s['tool']=='find_indoor_alternative' for s in r['trace'])
    Path('output/validation/narrative18/audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
    print('통과: 18곳×3항목 수동 대조·전체 근거 보존·중립 표현·다른 장소 분리·실내 5곳·동일지역/시설/비 분기')


if __name__=='__main__': main()
