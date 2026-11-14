@echo off
chcp 65001 >nul
cd /d "%~dp0"
python -m scripts.setup_eval_key
echo 아무 키나 누르면 닫힙니다
pause >nul
