"""평가용 OpenAI 키 확인과 제출 ZIP 생성."""

import getpass
import re
import subprocess
import sys
import tempfile
import warnings
from pathlib import Path

import requests

from agent.config import DEFAULT_MODELS

ROOT = Path(__file__).resolve().parents[1]


def local_openai_key():
    path = ROOT / ".env"
    if not path.exists():
        return ""
    key = ""
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        name, separator, value = line.partition("=")
        if separator and name.strip() == "OPENAI_API_KEY":
            key = value.split(" #", 1)[0].strip().strip('"').strip("'")
    return key


def main():
    try:
        key = local_openai_key()
        if not key:
            with warnings.catch_warnings():
                warnings.simplefilter("error", getpass.GetPassWarning)
                key = getpass.getpass("키를 붙여 넣고 Enter: ").strip()
        if not re.fullmatch(r"sk-[A-Za-z0-9_-]+", key):
            print("키 오류: OpenAI 키 형식을 확인하세요.")
            return 1
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={
                "model": DEFAULT_MODELS["openai"],
                "messages": [{"role": "user", "content": "OK"}],
                "max_completion_tokens": 16,
                "reasoning_effort": "none",
            },
            timeout=20,
            allow_redirects=False,
        )
        if response.status_code != 200 or not response.json().get("choices"):
            print("키 오류: OpenAI 응답을 확인하세요.")
            return 1
    except (OSError, EOFError, ValueError, requests.RequestException, getpass.GetPassWarning, KeyboardInterrupt):
        print("키 오류: 키 입력 또는 OpenAI 연결을 확인하세요.")
        return 1
    print("키 확인 완료", flush=True)
    try:
        with tempfile.NamedTemporaryFile(dir=ROOT, prefix=".env.eval.", delete=False) as file:
            pending = Path(file.name)
            file.write(f"LLM_PROVIDER=openai\nOPENAI_API_KEY={key}\nLLM_DAILY_LIMIT=2000\n".encode())
        pending.replace(ROOT / ".env.eval")
    except OSError:
        if "pending" in locals():
            pending.unlink(missing_ok=True)
        print("평가용 설정 저장 실패")
        return 1
    print("제출 ZIP을 만들고 있습니다.", flush=True)
    result = subprocess.run(
        [sys.executable, "make_submission.py"], cwd=ROOT,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    if result.returncode:
        print("ZIP 생성 실패: 작업 폴더와 평가용 설정을 확인하세요.")
        return 1
    print("제출 ZIP:", ROOT / "dist" / "jeju_barrier_free_submission.zip")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
