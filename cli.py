"""터미널에서 Agent 테스트.

사용 예:
  python cli.py "내일 오후 수동휠체어 장애인 화장실 필수 해안 산책로"
  python cli.py "유아차랑 서귀포 마을길" --json result.json
  python cli.py --check          # 설정·데이터 점검 (LLM·기상청 키 연결 확인 포함)
"""
from __future__ import annotations
from agent import parking

import argparse
import json
import sys

# Windows 터미널에서 한글이 깨지지 않도록
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from agent import cache, config, core, data, llm, weather  # noqa: E402


def check():
    print("[설정 점검]")
    print(f"- DB: {config.DB_PATH}")
    try:
        print(f"  장소 수: {data.place_counts()}")
    except data.DataError as e:
        print(f"  오류: {e}")
    print(f"- LLM: {config.LLM_PROVIDER} / {config.llm_model() or '-'} / 사용 가능={config.llm_enabled()}")
    if config.llm_enabled():
        ok, m = llm.test_connection(fresh=True)
        print(f"  연결 테스트: {'성공' if ok else '실패'} — {m}")
    print(f"- 하루 LLM 호출 제한: {config.LLM_DAILY_LIMIT if config.LLM_DAILY_LIMIT > 0 else '제한 없음'}")
    print('- ' + cache.usage_text())
    print(f'- 비용 기준: 가정 환율 1 USD={config.LLM_USD_KRW:g}원, 일반 토큰 단가. 할인·무료 구간·세금 미반영, 월 비용 차단 없음.')
    print(f"- 기상청 키: {'설정됨' if config.KMA_SERVICE_KEY else '없음(날씨는 미확인으로 표시)'}")
    if config.KMA_SERVICE_KEY:
        import datetime as dt
        today = weather.now_kst().date()
        for label, offset in [('단기', 1), ('중기', 4)]:
            w = weather.forecast(33.4996, 126.5312, (today + dt.timedelta(days=offset)).strftime('%Y%m%d'),
                                 address='제주시', fresh=True)
            print(f"  {label} 실제 호출 테스트: {w['status']} — {w.get('reason') or w.get('source')}")
            if w.get('base'):print('    발표: '+w['base']+' / 육상 '+str(w.get('reg_id','단기 격자'))+' / 기온 '+str(w.get('temp_reg_id','단기 격자'))+' / 날짜 칸 '+str(w.get('day_index','시간별')))
            if w.get('fallback_note'):print('    '+w['fallback_note'])
    else:
        print('  단기·중기 실제 호출 테스트 생략: 키 없음')


def show(res):
    print(f"\n목표: {res['goal']}   (모드: {res['mode']}, {res['elapsed_ms']}ms)")
    print("\n[요약]\n" + res["summary"])
    if res.get('day_recommendation'):
        advice = res['day_recommendation']
        print('\n[날짜별 강수확률] ' + (advice.get('reason') or ''))
        for row in advice.get('rows', []):
            print(f"{row['date']} | {str(row['pop'])+'%' if row['pop'] is not None else '미확인'} | {row['forecast_type']} | {row['precision']} | {row['reason']}")
    print("\n[순위]")
    for r in res["results"][:5]:
        if r.get('use_assessment'):
            print('이용 판단: ' + r['use_assessment']['text'])
            for proof in r['use_assessment']['evidence']: print('   근거: ' + proof)
        print(f"{r['rank']}. {r['place']['name']} — {r['grade']}  ({r['rank_reason']})")
        if res.get('missing_place'):
            from agent.missing_place import distance
            print('   '+distance(res['missing_place'],r))
        if r['place'].get('_distance_evidence'):
            for v in r['place']['_distance_evidence']:
                print(f"   거리 근거: {v['name']} ({v['lat']}, {v['lon']}) / {v['coord_source']} / {v['sources']}")
        if r['place'].get('_place_type'):
            print('   유형 근거: ' + str(r['place']['_place_type']))
        park=r['access'].get('parking')
        parking_display=parking.display_info(r['access'])
        for line in parking_display['lines']:
            print('   '+line['text']+(' (참고)' if line['reference'] else ''))
        if parking_display['notice']:print('   '+parking_display['notice'])
        if park:
            if park['general'].get('evidence'):print('     근거: '+park['general']['evidence'])
            if park['disabled']['supplement']:print('   '+park['disabled']['supplement']+' (장소 자체는 미확인)')
        for n in r["access"]["needs"]:
            print(f"   · {n['item']}: {n['effective']} (원본 {n['status']}) 근거: {n['evidence']}")
            if n["note"]:
                print(f"     ↳ {n['note']}")
        if r["route"]["max_slope"] is not None:
            print(f"   · 코스 최대 경사 {r['route']['max_slope']:g}° (경사 수치 {len(r['route']['course_slopes'])}개)")
        for c in r["caution_list"][:4]:
            print(f"   ! {c}")
        for proof in r.get("indoor_evidence", []):
            print("   + 실내 공간 포함(전체 실내 아님) 근거: " + proof["source"])
        for option in (r.get("indoor_alternative") or {}).get("options", []):
            slope = f"최대 {option['max_slope']:g}°" if option['max_slope'] is not None else "경사 측정값 없음(안전 확인 아님)"
            print(f"   + 실내 대안 {option['place']['name']} / {option['grade']} / {slope}")
            for proof in option["evidence"]:
                print("     근거: " + proof["source"])
        if "nearby" in r and r["nearby"]:
            from agent.tools import nearby_summary
            print("   + " + nearby_summary(r["nearby"]))
    if res.get('convenience_results'):
        print('\n[근처 식사·편의 장소] 관광지 대안과 구분, 이동 경로·운영 확인 필요')
        for r in res['convenience_results']:
            p=r['place'];kind=p['_place_type']
            print(f"- {p['name']} / {kind['label']} / {p['_distance_km']:.2f} km / {r['grade']} / {r['rank_reason']}")
            print('  유형 근거: ' + str(kind['evidence']))
            parking_display=parking.display_info(r['access'])
            for line in parking_display['lines']:print('  '+line['text']+(' (참고)' if line['reference'] else ''))
            if parking_display['notice']:print('  '+parking_display['notice'])
    print("\n[Agent 실행 과정]")
    for s in res["trace"]:
        print(f"{s['no']:>2}. {s['tool']:<34} {s['purpose']} | {s['input']} → {s['output']}"
              + ("" if s["ok"] else "  [실패]"))
    slow = res.get("slowest_step")
    if slow:
        print(f"가장 오래 걸린 단계: {slow['tool']} ({slow['ms']}ms)")
    print("\n[한계]")
    for l in res["limits"]:
        print(f"- {l}")


def _default(o):
    return str(o)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("text", nargs="?", default="")
    ap.add_argument("--json", help="결과를 JSON 파일로 저장")
    ap.add_argument("--no-llm", action="store_true", help="LLM을 쓰지 않고 규칙 모드로 실행")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    if a.check:
        check()
        return
    try:
        res = core.run(a.text, use_llm=not a.no_llm)
    except data.DataError as e:
        print(f"오류: {e}")
        sys.exit(1)
    show(res)
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=2, default=_default)
        print(f"\nJSON 저장: {a.json}")


if __name__ == "__main__":
    main()
