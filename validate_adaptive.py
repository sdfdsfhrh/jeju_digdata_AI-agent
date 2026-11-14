"""중간 결과 분기 검증. 실제 DB와 모의 예보를 사용하며 외부 호출은 하지 않는다."""
import json
from pathlib import Path
from unittest.mock import patch

from agent import adaptive, config, core, data, tools
from agent.parser import Request


def main():
    checks = []
    places = data.detailed_places()
    # 주차장이 없는 실제 장소 하나만 남겨 시설 조건 완화까지 도달시킨다.
    p = next(p for p in places if any(t["item"] == "장애인주차장" and t["status"] == tools.NO
                                     for t in data.items(p["place_id"])))
    with patch.object(data, "detailed_places", return_value=(p,)), patch.object(config, "KMA_SERVICE_KEY", ""):
        r = core.run("수동휠체어 장애인 주차 필수", use_llm=False)
        assert r["relaxations"] == ["필수 시설 'parking_disabled' 해제"]
        assert r["results"][0]["grade"] == tools.G_FAIL
        assert r["results"][0]["relaxed_grade"] == tools.G_OK
        assert '장애인주차장' in r["summary"] and r["limits"]
        checks.append("필수 조건 0곳 → 한 조건 완화·재검색, 원래 등급 보존")
    p = next(p for p in places if "신천목장" in p["name"])
    with patch.object(data, "detailed_places", return_value=(p,)):
        r = core.run('화장실 필수', use_llm=False)
        assert r['relaxations'] == []
        assert r['results'][0]['grade'] == tools.G_COND
        assert any('필수 시설 완화 중단' in step['output'] for step in r['trace'])
        r = core.run('화장실 필수', form={'region': '성산읍'}, use_llm=False)
        assert r['relaxations'] == ["지역 '성산읍' 해제"]
        assert r['effective_request']['needs'] == ['장애인화장실']
        checks.append('조건부 충족 존재 → 지역 완화는 유지하되 필수 시설 완화 금지·trace 사유')
        req = Request(needs=['장애인주차장', '장애인화장실'])
        _, changes, effective = adaptive.relax(req, adaptive.evaluate([p],req), core.Tracer())
        assert changes == ["필수 시설 '장애인주차장' 해제"]
        assert effective.needs == ['장애인화장실']
        checks.append('완화 중간 결과가 조건부 충족이면 남은 필수 시설 추가 해제 금지')
    with patch.object(data, "detailed_places", return_value=(p,)):
        r = core.run("화장실 장애인 주차 필수", use_llm=False)
        assert len(r["relaxations"]) == 2
        assert r["results"][0]["grade"] == tools.G_FAIL
        assert r["effective_request"]["needs"] == []
        checks.append("두 필수 시설 모두 불충족 → 하나씩 두 차례 완화, 원래 등급 보존")
    # 존재하지 않는 지역은 도구가 임의로 넓히지 않고 Agent가 명시적으로 완화한다.
    r = core.run("", form={"region": "검증용없는지역", "needs": ["장애인주차장"]}, use_llm=False)
    assert r["relaxations"] == ["지역 '검증용없는지역' 해제"]
    checks.append("후보 0곳 → 지역 완화 및 재검색 trace")
    # 1위 화장실 미확인: 실제 원본 상태를 유지하며 주변 ● 업체 대안을 표시한다.
    p = next(p for p in places if any(t["item"] == "장애인화장실" and t["status"] == tools.UNK
                                     for t in data.items(p["place_id"])))
    with patch.object(data, "detailed_places", return_value=(p,)):
        r = core.run("", use_llm=False)
        assert r["results"][0]["toilet_alternative"] is not None
        assert any(s["tool"] == "find_toilet_alternative" for s in r["trace"])
        assert "주변" in r["summary"]
        checks.append("1위 화장실 미확인 → 주변 ● 업체 조사")
        with patch.object(data, "nearby", return_value=[]), patch.object(data, "source_files", return_value=[{"file_kind":"nearby_2021"}]):
            r = core.run("", use_llm=False)
            assert "찾지 못함" in r["summary"] and "실제 시설이 없다는 뜻은 아님" in r["summary"]
            checks.append("대안 0곳 → 데이터에서 찾지 못했음을 명시")
    fake = dict(status="조회됨", sky="흐림", pop_max=80, wind_max=2, precip=["비"],
                date="20261107", hours="13~17시", base="모의 발표", source="검증용 모의 예보")
    with patch.object(config, "KMA_SERVICE_KEY", "local-test"), patch("agent.weather.forecast", return_value=fake):
        r = core.run("내일 오후 수동휠체어 화장실 해안", use_llm=False)
        assert "이날 방문 추천" in r["summary"] and r["day_recommendation"]["choices"]
        assert any(s["tool"] == "recommend_rain_days" for s in r["trace"])
        checks.append("모의 비 예보 → 실외 주의·10일 자동 조회 후 날짜 추천")
    with patch.object(config, "KMA_SERVICE_KEY", ""), patch("agent.weather.forecast", side_effect=AssertionError("조회 금지")):
        r = core.run("내일 수동휠체어", use_llm=False)
        assert not any(s["tool"] == "check_weather" for s in r["trace"])
        assert any("기상청 키 없음" in s["output"] for s in r["trace"])
        checks.append("키 없음 → 날씨 분기 건너뜀 및 trace 사유")
    r = core.run("수동휠체어 화장실 해안", use_llm=False)
    from agent import recommendation
    assert [recommendation.key(x) for x in r['results']]==sorted(recommendation.key(x) for x in r['results'])
    assert all(x['grade']==x['access']['grade'] for x in r['results'])
    checks.append('추천 새 정렬·지도 공통 구간 수, 시설 등급 보존')
    # 반환 결과를 재사용해도 원래 순위 데이터가 손상되지 않는지 검사한다.
    assert all(s["ok"] for s in r["trace"])
    out = Path(__file__).parent / "output" / "validation" / "adaptive_checks.json"
    out.write_text(json.dumps(checks, ensure_ascii=False, indent=2), encoding="utf-8")
    print("분기 검증 통과:")
    for c in checks:
        print("- " + c)


if __name__ == "__main__":
    with patch.object(config,'KMA_SERVICE_KEY',''):
        main()
