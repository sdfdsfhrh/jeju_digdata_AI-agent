"""평가용 설정 파일의 허용 항목만 읽는다."""
import re


def read_eval_env(path):
    values = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        name, separator, value = line.partition("=")
        name, value = name.strip(), value.strip()
        if not separator or name in values or name not in {
            "LLM_PROVIDER", "OPENAI_API_KEY", "LLM_DAILY_LIMIT"
        }:
            raise ValueError("평가용 설정에 허용되지 않은 항목 또는 중복 항목이 있습니다.")
        values[name] = value
    if (values.get("LLM_PROVIDER") != "openai"
            or not re.fullmatch(r"[0-9]{1,9}", values.get("LLM_DAILY_LIMIT", ""))
            or not re.fullmatch(r"(?:sk-[A-Za-z0-9_-]+)?", values.get("OPENAI_API_KEY", " "))
    ):
        raise ValueError("평가용 설정 형식이 올바르지 않습니다.")
    return values
