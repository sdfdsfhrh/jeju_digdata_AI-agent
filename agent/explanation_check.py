"""설명문의 장소명·명시적 상태어를 대조하는 간단한 점검."""
import re
import json
from . import data


def issues(text, payload):
    """알려진 DB 장소명·명시적인 항목 상태 불일치를 찾는다(자유문장 전체 보증 아님)."""
    top = payload.get('top', [])
    allowed = {p['name'] for p in top}
    evidence_text = json.dumps(payload, ensure_ascii=False)
    found = []
    for p in data.all_places():
        name = p['name']
        if name in text and name not in evidence_text and not any(name in a for a in allowed):
            found.append('판정 JSON 밖 장소명: ' + name)
    current = top[0] if top else None
    for sentence in re.split(r'[。.!?\n]', text):
        mentioned = [p for p in top if p['name'] in sentence]
        if len(mentioned) == 1:
            current = mentioned[0]
        if current is None or len(mentioned) > 1:
            continue
        for n in current.get('needs', []):
            item = r'\s*'.join(map(re.escape, n['item']))
            match = re.search(item + r'\s*(?:은|는|이|가|:)?\s*(있음|없음|미확인|조건부|있습니다|없습니다)', sentence)
            if match:
                actual = {'있습니다': '있음', '없습니다': '없음'}.get(match[1], match[1])
                if actual not in {n['status'], n.get('original_status', n['status'])}:
                    found.append(f"{current['name']} {n['item']} 상태 불일치({actual}/{n['status']})")
    return found
