@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 배리어프리 제주 여정 검증 Agent - 기본 포트 18766
python launch_app.py %*
if errorlevel 1 echo 실행에 실패했습니다. 위 안내를 확인하세요.
pause
