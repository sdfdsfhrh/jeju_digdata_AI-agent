"""Windows 실행 도우미: 사용할 포트를 확인한 뒤 Streamlit을 실행한다."""
import argparse
import socket
import subprocess
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=18766)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            sock.bind(("0.0.0.0", args.port))
    except (OSError, OverflowError) as e:
        print(f"포트 {args.port}를 사용할 수 없습니다(사용 중이거나 접근 불가).")
        print("기존 앱을 확인하거나 다음처럼 다른 포트로 실행하세요:")
        print(f"  python launch_app.py --port {args.port + 1}")
        print(f"오류 종류: {type(e).__name__}")
        return 1
    print(f"PC 접속: http://localhost:{args.port}", flush=True)
    print(f"같은 Wi-Fi 휴대폰: http://[PC IPv4 주소]:{args.port} (ipconfig로 확인)", flush=True)
    if args.check_only:
        return 0
    return subprocess.call([sys.executable, "-m", "streamlit", "run", "app.py",
                            "--server.port", str(args.port), "--server.address", "0.0.0.0"],
                           cwd=Path(__file__).resolve().parent)


if __name__ == "__main__":
    raise SystemExit(main())
