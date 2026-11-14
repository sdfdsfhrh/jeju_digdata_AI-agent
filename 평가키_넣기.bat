@echo off
chcp 65001 >nul
cd /d "%~dp0"
python "%~dp0scripts\setup_eval_key.py"
echo 아무 키나 누르면 닫힙니다
pause >nul
