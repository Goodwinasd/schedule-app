@echo off
chcp 65001 >nul
setlocal EnableExtensions EnableDelayedExpansion
set "APP_DIR=%~dp0.."
pushd "%APP_DIR%"
set "PIDFILE=%APP_DIR%\run\server.pid"
if not exist "%APP_DIR%\run" mkdir "%APP_DIR%\run"

rem --- уже запущен? ---
if exist "%PIDFILE%" (
    set /p OLD_PID=<"%PIDFILE%"
    tasklist /FI "PID eq !OLD_PID!" 2>nul | find "!OLD_PID!" >nul
    if not errorlevel 1 (
        echo Сайт уже запущен: PID !OLD_PID!
        start "" "http://127.0.0.1:5000"
        popd & exit /b 0
    )
    del /q "%PIDFILE%" >nul 2>&1
)

echo Запускаю сайт расписания...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$p = Start-Process -FilePath 'python' -ArgumentList @('-m','flask','--app','app','run','--host','127.0.0.1','--port','5000','--no-reload') -WorkingDirectory '%APP_DIR%' -WindowStyle Minimized -PassThru; if ($p) { $p.Id | Out-File -Encoding ascii -NoNewline '%PIDFILE%' }"
if not exist "%PIDFILE%" (
    echo ОШИБКА: не удалось запустить python.
    popd & pause & exit /b 1
)

echo Жду, пока сервер поднимется...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ok=$false; for($i=0;$i -lt 60;$i++){ try { $c=New-Object Net.Sockets.TcpClient; $c.Connect('127.0.0.1',5000); $c.Close(); $ok=$true; break } catch { Start-Sleep -Milliseconds 500 } }; if ($ok) { exit 0 } else { exit 1 }"
if errorlevel 1 (
    echo ОШИБКА: сервер не поднялся на порту 5000.
    popd & pause & exit /b 1
)

start "" "http://127.0.0.1:5000"
echo.
echo Сайт запущен: http://127.0.0.1:5000
echo Остановить: ярлык "Остановить расписание" на рабочем столе.
ping -n 4 127.0.0.1 >nul
popd & exit /b 0
