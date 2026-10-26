@echo off
chcp 65001 >nul
setlocal EnableExtensions EnableDelayedExpansion
set "APP_DIR=%~dp0.."
set "PIDFILE=%APP_DIR%\run\server.pid"

if not exist "%PIDFILE%" (
    echo Сайт не запущен: PID-файл не найден.
    echo Если сервер запущен вручную из консоли — закройте его там.
    ping -n 5 127.0.0.1 >nul
    exit /b 0
)

set /p PID=<"%PIDFILE%"
echo Останавливаю сайт ^(PID !PID!^)...
taskkill /PID !PID! /T /F >nul 2>&1
if errorlevel 1 (
    echo Процесс !PID! уже завершён.
) else (
    echo Сайт остановлен.
)
del /q "%PIDFILE%" >nul 2>&1

rem Если порт 5000 всё ещё занят — это чужой процесс, его НЕ трогаем.
powershell -NoProfile -ExecutionPolicy Bypass -Command "$busy=$false; try { $c=New-Object Net.Sockets.TcpClient; $c.Connect('127.0.0.1',5000); $c.Close(); $busy=$true } catch {}; if ($busy) { exit 1 } else { exit 0 }"
if errorlevel 1 echo ВНИМАНИЕ: порт 5000 занят другим процессом — проверьте вручную.
ping -n 4 127.0.0.1 >nul
exit /b 0
