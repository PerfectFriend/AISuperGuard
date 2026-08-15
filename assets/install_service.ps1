<#
.SYNOPSIS
    SuperGuard Alarm - NSSM Service Installer
    Installs SuperGuard as a Windows Service via NSSM.
    Service runs Watchdog which manages SuperGuard process with health checks.

.DESCRIPTION
    Architecture:
      NSSM Service "SuperGuardAlarm" (SYSTEM, auto-start delayed)
            |
            v
      superguard_watchdog.py (health-check, rate-limited restarts, kills stale on START only)
            |
            v
      run_bot.py -> superguard.main (core: YOLO detection, Telegram bot, Tuya control)
            |
            v
      Writes desktop_state/status.json + alarm_live.jpg (read by Desktop Admin Panel)

    Desktop App (manual launch) = Admin Panel:
      - Reads status.json, shows live alarm frame
      - Full config UI (zones, targets, camera-plug bindings, etc.)
      - Start/Stop/Restart Service buttons
      - Log viewer (tail of bot.log + service logs)
      - NO auto-restart, NO autostart

.PARAMETER ServiceName
    Windows service name (default: SuperGuardAlarm)

.PARAMETER DisplayName
    Display name in services.msc

.PARAMETER Description
    Service description

.PARAMETER InstallDir
    SuperGuard project directory (default: C:\SuperGuard)

.PARAMETER PythonExe
    Python interpreter to use (default: Hermes venv python)

.PARAMETER NssmPath
    Path to nssm.exe (download from https://nssm.cc/download if missing)

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File install_service.ps1

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File install_service.ps1 -ServiceName "MySuperGuard" -InstallDir "D:\SuperGuard"
#>

param(
    [string]$ServiceName = "SuperGuardAlarm",
    [string]$DisplayName = "SuperGuard Alarm - AI Video Surveillance",
    [string]$Description = "AI Video Surveillance with YOLO detection, Tuya plug control, Telegram bot. Managed by watchdog with health checks.",
    [string]$InstallDir = "C:\SuperGuard",
    [string]$PythonExe = "C:\Users\tomas\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe",
    [string]$NssmPath = "C:\SuperGuard\nssm.exe"
)

$ErrorActionPreference = "Stop"

function Write-Log {
    param([string]$Message, [string]$Level = "INFO")
    $timestamp = Get-Date -Format "HH:mm:ss"
    Write-Host "[$timestamp] [$Level] $Message" -ForegroundColor $(if ($Level -eq "ERROR") { "Red" } elseif ($Level -eq "WARN") { "Yellow" } else { "Cyan" })
}

# 1. Check Admin
if (-NOT ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Log "This script requires Administrator privileges. Re-run as Admin." "ERROR"
    exit 1
}

# 2. Check NSSM
if (-not (Test-Path $NssmPath)) {
    Write-Log "NSSM not found at $NssmPath" "ERROR"
    Write-Log "Download from https://nssm.cc/download (nssm-2.24.zip) and extract nssm.exe to $NssmPath" "ERROR"
    exit 1
}

# 3. Check Python
if (-not (Test-Path $PythonExe)) {
    Write-Log "Python not found at $PythonExe" "ERROR"
    Write-Log "Expected: Hermes venv python or specify -PythonExe" "ERROR"
    exit 1
}

# 4. Check project dir and watchdog script
$WatchdogScript = Join-Path $InstallDir "superguard_watchdog.py"
if (-not (Test-Path $WatchdogScript)) {
    Write-Log "Watchdog script not found at $WatchdogScript" "ERROR"
    exit 1
}

$RunBotScript = Join-Path $InstallDir "run_bot.py"
if (-not (Test-Path $RunBotScript)) {
    Write-Log "run_bot.py not found at $RunBotScript" "ERROR"
    exit 1
}

$LogsDir = Join-Path $InstallDir "logs"
New-Item -ItemType Directory -Force -Path $LogsDir | Out-Null

# 5. Stop and remove existing service
Write-Log "Checking for existing service..."
$existingService = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($existingService) {
    Write-Log "Stopping existing service..."
    try { Stop-Service -Name $ServiceName -Force -ErrorAction Stop } catch { Write-Log "Stop failed: $_" "WARN" }
    Start-Sleep -Seconds 3
    Write-Log "Removing existing service..."
    try { sc.exe delete $ServiceName | Out-Null } catch { Write-Log "Delete failed: $_" "WARN" }
    Start-Sleep -Seconds 2
}

# 6. Install service via NSSM
Write-Log "Installing service '$ServiceName'..."
$installCmd = & $NssmPath install $ServiceName "`"$PythonExe`"" "`"$WatchdogScript`""
if ($LASTEXITCODE -ne 0) {
    Write-Log "NSSM install failed with exit code $LASTEXITCODE" "ERROR"
    exit 1
}

# 7. Configure service
Write-Log "Configuring service..."

# Working directory
& $NssmPath set $ServiceName AppDirectory "`"$InstallDir`""
# Stdout/Stderr logs with rotation
& $NssmPath set $ServiceName AppStdout "`"$LogsDir\superguard_stdout.log`""
& $NssmPath set $ServiceName AppStderr "`"$LogsDir\superguard_stderr.log`""
& $NssmPath set $ServiceName AppRotateFiles 1
& $NssmPath set $ServiceName AppRotateOnline 1
& $NssmPath set $ServiceName AppRotateSeconds 86400  # daily rotation

# Restart settings - LET WATCHDOG HANDLE RESTARTS, not NSSM
# NSSM should NOT restart on exit - watchdog manages lifecycle
& $NssmPath set $ServiceName AppExit Default Exit  # Important: Exit (not Restart) so watchdog controls it
& $NssmPath set $ServiceName AppRestartDelay 0
& $NssmPath set $ServiceName AppThrottle 5000  # Min 5s between starts if watchdog exits

# Description and display name
& $NssmPath set $ServiceName Description "$Description"
& $NssmPath set $ServiceName DisplayName "$DisplayName"

# Start type: Automatic (Delayed Start) - survives reboot, starts after boot
sc.exe config $ServiceName start= delayed-auto

# Recovery actions - NSSM recovery (only if watchdog itself crashes)
# First failure: restart after 10s, second: 30s, subsequent: 60s
sc.exe failure $ServiceName reset= 86400 actions= restart/10000/restart/30000/restart/60000

Write-Log "Service installed successfully!"

# 8. Show management commands
Write-Log ""
Write-Log "=== Service Management ==="
Write-Log "Start:   net start `"$ServiceName`"   OR   sc start `"$ServiceName`""
Write-Log "Stop:    net stop `"$ServiceName`"    OR   sc stop `"$ServiceName`""
Write-Log "Status:  sc query `"$ServiceName`""
Write-Log "Logs:    $LogsDir\superguard_stdout.log"
Write-Log "         $LogsDir\superguard_stderr.log"
Write-Log ""
Write-Log "=== Desktop Admin Panel ==="
Write-Log "Run manually: python desktop.bak/main.py"
Write-Log "  - Reads desktop_state/status.json"
Write-Log("  - Shows live alarm frame from desktop_state/alarm_live.jpg")
Write-Log("  - Full config UI (zones, targets, camera-plug bindings)")
Write-Log("  - Start/Stop/Restart Service buttons")
Write-Log("  - Log viewer")
Write-Log ""
Write-Log "=== Architecture ==="
Write-Log "NSSM Service (SYSTEM) -> Watchdog -> run_bot.py -> superguard.main"
Write-Log "Watchdog: health-check 5s, rate-limit 10 restarts/5min, kills stale ON START ONLY"
Write-Log "Desktop App: MANUAL launch only, read-only status + service control + config UI"