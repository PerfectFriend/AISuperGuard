@echo off
REM SuperGuard Alarm - NSSM Windows Service Installation Script
REM Run as Administrator

set SERVICE_NAME=SuperGuardAlarm
set DISPLAY_NAME=SuperGuard Alarm Core
set DESCRIPTION=SuperGuard Alarm Security Platform Core API
set PYTHON_EXE=C:\Python311\python.exe
set APP_DIR=C:\SuperGuard\superguard-core
set VENV_DIR=%APP_DIR%\venv
set UVICORN_EXE=%VENV_DIR%\Scripts\uvicorn.exe
set DATABASE_URL=postgresql+asyncpg://superguard:superguard123@localhost:5432/superguard
set REDIS_URL=redis://localhost:6379/0
set STORAGE_PATH=C:\SuperGuard\storage
set HOST=0.0.0.0
set PORT=8000
set DEBUG=false
set LOG_LEVEL=INFO
set SECRET_KEY=your-secret-key-here
set JWT_PRIVATE_KEY=C:\SuperGuard\keys\jwt_private.pem
set JWT_PUBLIC_KEY=C:\SuperGuard\keys\jwt_public.pem

REM Check if NSSM is available
where nssm >nul 2>&1
if %errorlevel% neq 0 (
    echo NSSM not found in PATH. Please install NSSM first.
    echo Download from: https://nssm.cc/download
    pause
    exit /b 1
)

echo Installing %SERVICE_NAME% service...

REM Install service
nssm install "%SERVICE_NAME%" "%UVICORN_EXE%" "superguard_core.main:app --host %HOST% --port %PORT% --workers 4"

if %errorlevel% neq 0 (
    echo Failed to install service.
    pause
    exit /b 1
)

REM Configure service
nssm set "%SERVICE_NAME%" DisplayName "%DISPLAY_NAME%"
nssm set "%SERVICE_NAME%" Description "%DESCRIPTION%"
nssm set "%SERVICE_NAME%" AppDirectory "%APP_DIR%"
nssm set "%SERVICE_NAME%" AppStdout "C:\SuperGuard\logs\superguard-out.log"
nssm set "%SERVICE_NAME%" AppStderr "C:\SuperGuard\logs\superguard-err.log"
nssm set "%SERVICE_NAME%" AppRotateFiles 1
nssm set "%SERVICE_NAME%" AppRotateBytes 10485760

REM Environment variables
nssm set "%SERVICE_NAME%" AppEnvironmentExtra SG_DATABASE_URL="%DATABASE_URL%"
nssm set "%SERVICE_NAME%" AppEnvironmentExtra SG_REDIS_URL="%REDIS_URL%"
nssm set "%SERVICE_NAME%" AppEnvironmentExtra SG_STORAGE_PATH="%STORAGE_PATH%"
nssm set "%SERVICE_NAME%" AppEnvironmentExtra SG_HOST="%HOST%"
nssm set "%SERVICE_NAME%" AppEnvironmentExtra SG_PORT="%PORT%"
nssm set "%SERVICE_NAME%" AppEnvironmentExtra SG_DEBUG="%DEBUG%"
nssm set "%SERVICE_NAME%" AppEnvironmentExtra SG_LOG_LEVEL="%LOG_LEVEL%"
nssm set "%SERVICE_NAME%" AppEnvironmentExtra SG_SECRET_KEY="%SECRET_KEY%"
nssm set "%SERVICE_NAME%" AppEnvironmentExtra SG_JWT_PRIVATE_KEY="%JWT_PRIVATE_KEY%"
nssm set "%SERVICE_NAME%" AppEnvironmentExtra SG_JWT_PUBLIC_KEY="%JWT_PUBLIC_KEY%"

REM Dependencies
nssm set "%SERVICE_NAME%" DependOnService postgresql-x64-16 redis

REM Restart settings
nssm set "%SERVICE_NAME%" Start SERVICE_AUTO_START
nssm set "%SERVICE_NAME%" RestartDelay 10000

echo Service installed successfully!
echo.
echo To start the service: net start "%SERVICE_NAME%"
echo To stop the service: net stop "%SERVICE_NAME%"
echo To view status: sc query "%SERVICE_NAME%"
echo.
echo Logs: C:\SuperGuard\logs\
pause