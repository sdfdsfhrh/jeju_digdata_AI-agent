"""실제 DB·HWP 대조 및 평가 입력 재현 결과. 외부 API는 호출하지 않는다."""
from pathlib import Path
import collections
import datetime as dt
import json
import sys
from unittest.mock import patch

from agent import config, core, data, tools
from agent.parser import Request

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
from hwp_reader import read_hwp

QUESTIONS = [
    "내일 오후 수동휠체어 장애인 화장실 필수 해안 산책로",
    "유아차 애월 마을길 주차 꼭 필요",
    "부모님 모시고 서귀포 걷기 편한 곳",
    "전동휠체어 구좌 화장실 주차 필수",
    "모레 오전 보행약자 조천 해안 화장실",
    "시각장애 제주시 역사 문화",
    "청각장애 성산 마을길",
    "시니어 남원 숲 자연 화장실",
    "수동휠체어 한림 화장실 필수",
    "",
    "한림공원 휠체어로 갈 수 있어?",
    "협재해수욕장 유아차로 갈 수 있어?",
    "섭지코지 휠체어로 갈 수 있어?",
    "성산일출봉 휠체어로 갈 수 있어?",
    "한라산 휠체어로 갈 수 있어?",
    "빛의 벙커 유아차로 갈 수 있어?",
    "제주 신라호텔 근처에 ６０대 어머니 모시고 산책할 만한 곳 추천해줘",
    "중문 근처 부모님이랑 걷기 좋은 곳",
    "성산일출봉 주변 유아차로 산책할 곳 내일 오후",
    "애월 근처 비 오면 갈 만한 실내",
    "없는장소123 근처 산책",
    "없는장소123",
    "휠체어가 갈 수 있는 곳 해안가 산책하고 싶어",
    "장애인 주차 필수 휠체어가 갈 수 있는 곳 해안가 산책하고 싶어",
    "유아차로 갈 만한 곳 렌트카로 가요",
    "휠체어로 주차 필요한 곳",
    "부모님이랑 차 가져가서 걷기 좋은 곳",
    "전동휠체어로 한림 근처 장애인 화장실 있는 곳",
    "다음 주 제주에서 휠체어로 갈 만한 실내 관광지",
    "주말에 부모님과 서귀포에서 바다 볼 수 있는 곳",
]


def main():
    out = ROOT / "output" / "validation"
    out.mkdir(parents=True, exist_ok=True)
    audit = []
    # DB의 화장실 상태를 추출기가 아닌 HWP 요약표의 셀 값과 직접 비교한다.
    for p in data.detailed_places():
        row = next((r for r in data.items(p["place_id"]) if r["item"] == "장애인화장실" and r.get('origin')=='제주데이터허브(필수)' and r.get('extract_method')=='template'), None)
        if row is None:
            continue
        grid = read_hwp(str(ROOT / "data" / "raw" / row["file_name"])).tables()[0]
        headers = [rc for rc, value in grid.items()
                   if "".join(value.split()) in ("장애인화장실", "추천장애인화장실")]
        assert len(headers) == 1, p["name"]
        rr, cc = headers[0]
        raw = grid.get((rr + 1, cc))
        assert row["value_raw"] == raw, p["name"]
        assert row["source_locator"] == f"T0 r{rr + 1} c{cc}", p["name"]
        if raw in ("있음", "유"):
            assert row["status"] == tools.YES, p["name"]
        elif raw == "없음":
            assert row["status"] == tools.NO, p["name"]
        elif raw in (None, "", "-") and row["status"] != tools.NO:
            assert row["status"] == tools.UNK, p["name"]
        audit.append(dict(name=p["name"], raw=raw, status=row["status"],
                          source=row["file_name"], locator=row["source_locator"]))
    results = []
    with (
        patch.dict(config._FILE_API_KEYS, {"VWORLD_API_KEY": ""}),
        patch.object(config, "KMA_SERVICE_KEY", ""),
        patch.object(config, "KTO_SERVICE_KEY", ""),
        patch("agent.llm.ask", side_effect=AssertionError("외부 호출 금지")),
    ):
        for i, q in enumerate(QUESTIONS, 1):
            res = core.run(q, use_llm=False)
            again = core.run(q, use_llm=False)
            signature = lambda x: [(r["place"]["place_id"], r["grade"]) for r in x["results"]]
            assert signature(res) == signature(again), q
            assert all(s["ok"] for s in res["trace"]), q
            (out / f"question_{i:02}.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
            results.append(dict(question=q or "(빈 문장)", count=len(res["results"]),
                                top=[f"{r['place']['name']} ({r['grade']})" for r in res["results"][:3]]))
    # 충돌 두 건이 양쪽 원본 근거와 함께 결과 주의사항에 나타나는지 확인한다.
    conflicts = []
    req = Request(user_type="수동휠체어", needs=["장애인주차장"])
    for p in data.detailed_places():
        cs = data.conflicts(p["place_id"])
        if cs:
            acc = tools.check_accessibility(p, req)
            cautions = core._collect_cautions(acc, tools.check_route(p, req), req)
            for c in cs:
                assert any(c["source_a"] in x and c["source_b"] in x for x in cautions)
            conflicts.extend(cs)
    counts = dict(collections.Counter(r["status"] for r in audit))
    payload = dict(checked_at=dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(),
                   counts=data.place_counts(), toilet_status=counts, toilet_audit=audit,
                   conflicts=conflicts, questions=results)
    (out / "audit.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# 실제 DB 검증 결과", "", f"화장실 원본 대조 {len(audit)}곳: {counts}", "",
             "| 질문 | 후보 수 | 상위 3곳 |", "|---|---:|---|"]
    lines += [f"| {r['question']} | {r['count']} | {' / '.join(r['top'])} |" for r in results]
    lines += ["", "키 없는 규칙 모드. 각 질문 2회 실행 시 순위·등급 동일. 실제 API 키 연동은 미검증.",
              "원본 데이터와 결과 JSON은 로컬 검증용이며 제출·공개 저장소에서 제외."]
    (out / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"검증 통과: HWP {len(audit)}곳, 질문 {len(results)}개, 충돌 {len(conflicts)}건. {out}")


if __name__ == "__main__":
    main()
