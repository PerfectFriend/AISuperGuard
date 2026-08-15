@echo off
:: SuperGuard Bot Keep-Alive Wrapper
:: Runs bot forever, restarts on crash/exit
:: Logs to C:\SuperGuard\bot_keepalive.log

set BOT_DIR=C:\SuperGuard
set PYTHON=python
set SCRIPT=run_bot.py
set LOG=C:\SuperGuard\bot_keepalive.log

cd /d %BOT_DIR%

echo [%DATE% %TIME%] === KEEP-ALIVE STARTED === >> %LOG%

:LOOP
echo [%DATE% %TIME%] Starting bot... >> %LOG%
%PYTHON% %SCRIPT% >> %LOG% 2>&1
set EXIT_CODE=%ERRORLEVEL%

echo [%DATE% %TIME%] Bot exited with code %EXIT_CODE%. Restarting in 5s... >> %LOG%
timeout /t 5 /nobreak >nul
goto LOOP