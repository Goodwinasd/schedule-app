@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Killing existing Python processes...
taskkill /f /im python.exe >nul 2>&1
timeout /t 2 /nobreak >nul
if exist venv\Scripts\activate.bat (
    call venv\Scripts\activate.bat
) else if exist .venv\Scripts\activate.bat (
    call .venv\Scripts\activate.bat
)
echo Starting schedule-app server...
start "Schedule App" python app.py
echo Server started on http://127.0.0.1:5000
