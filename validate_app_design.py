"""새 추천 순위와 공통 지도 구간 분류·시설 판정 불변 검증."""
from copy import deepcopy
from unittest.mock import patch
from agent import core, config, recommendation, tools
import map_display

QUESTIONS=['휠체어가 갈 수 있는 곳 해안가 산책하고 싶어',
 '장애인 주차 필수 휠체어가 갈 수 있는 곳 해안가 산책하고 싶어']

def main():
    from agent.parser import Request
    with patch.object(config,'KMA_SERVICE_KEY',''),patch.object(config,'KTO_SERVICE_KEY',''):
        for q in QUESTIONS:
            res=core.run(q,use_llm=False)
            req=Request(**res['request'])
            keys=[recommendation.key(r) for r in res['results']]
            assert keys==sorted(keys)
            assert any(s['tool']=='rank_recommendations' for s in res['trace'])
            if q==QUESTIONS[1]:assert not any(recommendation.missing_required(r) for r in res['results'][:5])
            if q==QUESTIONS[0]:
                reds=[recommendation.red_band(r) for r in res['results']]
                assert reds==sorted(reds)
            for r in res['results']:
                profile=map_display.prepare(r)
                c=r['course_counts']
                assert c['red']==(sum(s['level']==2 for s in profile['segments']) if profile['segments'] else None)
                assert c['orange']==(sum(s['level']==1 for s in profile['segments']) if profile['segments'] else None)
                again=tools.check_accessibility(r['place'],req)
                assert again['grade']==r['grade']
                assert [(t['item'],t['status']) for t in again['table']]==[(t['item'],t['status']) for t in r['access']['table']]
        base=deepcopy(res['results'][0]);base['access']['needs']=[]
        samples=[]
        for label in ['가능','가능(일부 구간 주의)','확인 필요','어려움']:
            r=deepcopy(base);r['use_assessment']['text']='휠체어 이용: '+label
            r['course_counts']['red']=0;r['course_counts']['orange']=0;samples.append(r)
        assert sorted(reversed(samples),key=recommendation.key)==samples
        a=deepcopy(samples[1]);b=deepcopy(samples[1])
        a['course_counts']['red']=1;b['course_counts']['red']=2
        a['slope_unknown']=True;b['slope_unknown']=False
        assert recommendation.key(a)==recommendation.key(b)  # 빨강1~2는 같은 범주
        known=deepcopy(samples[2]);unknown=deepcopy(known)
        known['course_counts']=dict(red=0,orange=0,known=True)
        unknown['course_counts']=dict(red=None,orange=None,known=False)
        assert recommendation.key(known)<recommendation.key(unknown)
        yes=deepcopy(known);no=deepcopy(known)
        yes['access']['needs']=[dict(item='장애인주차장',effective='있음')];no['access']['needs']=[dict(item='장애인주차장',effective='없음')]
        assert recommendation.key(yes)<recommendation.key(no)
        near=deepcopy(yes);far=deepcopy(yes)
        near['place']['_distance_km']=1;far['place']['_distance_km']=2
        assert recommendation.key(near)<recommendation.key(far)
        buckets=[]
        for red in [0,None,1,2,3,10]:
            item=deepcopy(known);item['course_counts']['red']=red;buckets.append(item)
        assert sorted(reversed(buckets),key=recommendation.key)[:2]==buckets[:2]
        assert [recommendation.red_band(x) for x in sorted(buckets,key=recommendation.key)]==[0,1,2,2,3,3]
        failed=deepcopy(known);failed['access']['needs']=[dict(item='장애인주차장',condition_key='parking_disabled',effective='없음')]
        unknown['access']['needs']=[dict(item='장애인주차장',effective='미확인')]
        assert recommendation.key(unknown)<recommendation.key(failed)
        assert recommendation.missing_required(failed)==['장애인 주차 없음(필수 조건)']
        assert [{k:v for k,v in row.items() if k!='color'} for row in map_display.prepare(base)['segments']]==[{k:v for k,v in row.items() if k!='color'} for row in __import__('agent.course_profile',fromlist=['prepare']).prepare(base)['segments']]
    print('PASS: 필수 미충족 맨 뒤→빨강 범주→같은 범주 시설 상태→이용판단→주황→거리, 지도 공통 구간 수, 기존 시설 상태·등급 보존')

if __name__=='__main__':main()
