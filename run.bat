@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Установка зависимостей...
py -3.13 -m pip install -r requirements.txt -q
echo Запуск приложения...
py -3.13 app.py
pause
