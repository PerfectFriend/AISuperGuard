@echo off
:: SuperGuard Alarm - NSSM Service Installer
:: Run as Administrator

set "SERVICE_NAME=SuperGuardAlarm"
set "DISPLAY_NAME=SuperGuard Alarm - AI Video Surveillance"
set "DESCRIPTION=AI Video Surveillance with YOLO detection, Tuya plug control, Telegram bot"
set "PYTHON_EXE=C:\Users\tomas\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe"
set "SCRIPT_PATH=C:\SuperGuard\panic_mode.py"
set "WORK_DIR=C:\SuperGuard"
set "NSSM_PATH=C:\SuperGuard\nssm.exe"

:: Check if NSSM exists
if not exist "%NSSM_PATH%" (
    echo NSSM not found at %NSSM_PATH%
    echo Download from https://nssm.cc/download and place at %NSSM_PATH%
    pause
    exit /b 1
)

:: Stop and remove existing service if exists
sc query "%SERVICE_NAME%" >nul 2>&1
if %errorlevel% equ 0 (
    echo Stopping existing service...
    sc stop "%SERVICE_NAME%" >nul 2>&1
    timeout /t 3 /nobreak >nul
    echo Removing existing service...
    sc delete "%SERVICE_NAME%" >nul 2>&1
    timeout /t 2 /nobreak >nul
)

:: Install service
echo Installing service "%SERVICE_NAME%"...
"%NSSM_PATH%" install "%SERVICE_NAME%" "%PYTHON_EXE%" "%SCRIPT_PATH%"

:: Configure service
"%NSSM_PATH%" set "%SERVICE_NAME%" AppDirectory "%WORK_DIR%"
"%NSSM_PATH%" set "%SERVICE_NAME%" AppStdout "%WORK_DIR%\logs\superguard_stdout.log"
"%NSSM_PATH%" set "%SERVICE_NAME%" AppStderr "%WORK_DIR%\logs\superguard_stderr.log"
"%NSSM_PATH%" set "%SERVICE_NAME%" AppRotateFiles 1
"%NSSM_PATH%" set "%SERVICE_NAME%" AppRotateOnline 1
"%NSSM_PATH%" set "%SERVICE_NAME%" AppRotateSeconds 86400

:: Restart settings
"%NSSM_PATH%" set "%SERVICE_NAME%" AppRestartDelay 5000
"%NSSM_PATH%" set "%SERVICE_NAME%" AppExit Default Restart
"%NSSM_PATH%" set "%SERVICE_NAME%" AppThrottle 1500

:: Description
"%NSSM_PATH%" set "%SERVICE_NAME%" Description "%DESCRIPTION%"

:: Display name
"%NSSM_PATH%" set "%SERVICE_NAME%" DisplayName "%DISPLAY_NAME%"

:: Start type - Automatic (delayed start)
sc config "%SERVICE_NAME%" start= delayed-auto

:: Set recovery actions
sc failure "%SERVICE_NAME%" reset= 86400 actions= restart/5000/restart/10000/restart/60000

echo.
echo Service installed successfully!
echo.
echo To manage the service:
echo   Start:   net start "%SERVICE_NAME%"  OR  sc start "%SERVICE_NAME%"
echo   Stop:    net stop "%SERVICE_NAME%"   OR  sc stop "%SERVICE_NAME%"
echo   Status:  sc query "%SERVICE_NAME%"
echo   Logs:    %WORK_DIR%\logs\superguard_stdout.log
echo            %WORK_DIR%\logs\superguard_stderr.log
echo.
echo To remove service:
echo   sc stop "%SERVICE_NAME%"
echo   sc delete "%SERVICE_NAME%"
echo.
pause