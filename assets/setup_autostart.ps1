<# 
.SYNOPSIS
    SuperGuard Alarm - Setup Windows Service for Auto-Start
    Configures NSSM service to run panic_mode.py on system boot.

.DESCRIPTION
    Creates/updates Windows service (NSSM) for SuperGuard Alarm.
    Service runs as LocalSystem, auto-starts on boot, restarts on failure.
    Requires: Admin rights, NSSM installed, Python venv with dependencies.

.PARAMETER InstallDir
    SuperGuard install directory (default: C:\SuperGuard)
.PARAMETER ServiceName
    Windows service name (default: SuperGuardAlarm)
#>

param(
    [string]$InstallDir = "C:\SuperGuard",
    [string]$ServiceName = "SuperGuardAlarm"
)

$ErrorActionPreference = "Stop"

function Write-Log {
    param([string]$Msg, [string]$Level = "INFO")
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Write-Host "[$ts] [$Level] $Msg" -ForegroundColor Cyan
}

function Check-Admin {
    $id = [System.Security.Principal.WindowsIdentity]::GetCurrent()
    $p = New-Object System.Security.Principal.WindowsPrincipal($id)
    if (-not $p.IsInRole([System.Security.Principal.WindowsBuiltInRole]::Administrator)) {
        Write-Error "Run PowerShell as Administrator!"
        exit 1
    }
}

function Install-Nssm {
    Write-Log "Installing/verifying NSSM..."
    $nssmDir = "$env:ProgramFiles\NSSM"
    if (-not (Test-Path "$nssmDir\nssm.exe")) {
        $tmp = "$env:TEMP\nssm.zip"
        Write-Log "Downloading NSSM..."
        Invoke-WebRequest -Uri "https://nssm.cc/release/nssm-2.24.zip" -OutFile $tmp
        Expand-Archive -Path $tmp -DestinationPath "$env:TEMP\nssm" -Force
        New-Item -ItemType Directory -Force -Path $nssmDir | Out-Null
        Copy-Item "$env:TEMP\nssm\nssm-2.24\win64\nssm.exe" "$nssmDir\nssm.exe" -Force
        $env:Path += ";$nssmDir"
        [Environment]::SetEnvironmentVariable("Path", $env:Path, "Machine")
    }
    Write-Log "NSSM ready at $nssmDir\nssm.exe"
}

function Setup-Service {
    Write-Log "Setting up Windows service $ServiceName..."
    
    $pythonExe = "$InstallDir\venv\Scripts\python.exe"
    $scriptPath = "$InstallDir\panic_mode.py"
    $logPath = "$InstallDir\superguard.log"
    $errPath = "$InstallDir\superguard_err.log"
    
    if (-not (Test-Path $pythonExe)) {
        Write-Error "Python not found at $pythonExe. Run install_superguard.ps1 first."
        exit 1
    }
    if (-not (Test-Path $scriptPath)) {
        Write-Error "panic_mode.py not found at $scriptPath"
        exit 1
    }
    if (-not (Test-Path "$InstallDir\sguard.env")) {
        Write-Error "sguard.env not found at $InstallDir\sguard.env"
        exit 1
    }
    
    # Stop service if running
    $svc = Get-Service $ServiceName -ErrorAction SilentlyContinue
    if ($svc -and $svc.Status -ne 'Stopped') {
        Write-Log "Stopping existing service..."
        Stop-Service $ServiceName -Force
        Start-Sleep 2
    }
    
    # Remove old service if exists
    if ($svc) {
        Write-Log "Removing old service..."
        nssm remove $ServiceName confirm
        Start-Sleep 1
    }
    
    # Install service
    Write-Log "Installing service..."
    nssm install $ServiceName $pythonExe $scriptPath
    nssm set $ServiceName AppDirectory $InstallDir
    nssm set $ServiceName AppStdout $logPath
    nssm set $ServiceName AppStderr $errPath
    nssm set $ServiceName Start SERVICE_AUTO_START
    nssm set $ServiceName Description "SuperGuard Alarm - AI video surveillance + Telegram bot + Tuya plug"
    
    # Recovery: restart on failure
    nssm set $ServiceName AppExit Default Restart
    nssm set $ServiceName AppThrottle 10000
    nssm set $ServiceName AppRestartDelay 5000
    
    # Run as LocalSystem (has network access)
    nssm set $ServiceName ObjectName "LocalSystem"
    
    Write-Log "Service configured. Starting..."
    Start-Service $ServiceName
    Start-Sleep 3
    
    # Verify
    $svc = Get-Service $ServiceName
    if ($svc.Status -eq 'Running') {
        Write-Log "SUCCESS: Service $ServiceName is RUNNING" "OK"
    } else {
        Write-Log "Service status: $($svc.Status)" "WARN"
        Write-Log "Check logs: $logPath and $errPath" "WARN"
    }
}

function Add-FirewallRules {
    Write-Log "Adding firewall rules for Tuya plug (port 6668)..."
    New-NetFirewallRule -DisplayName "SuperGuard Tuya Plug Out" -Direction Outbound -Protocol TCP -LocalPort 6668 -Action Allow -ErrorAction SilentlyContinue
    New-NetFirewallRule -DisplayName "SuperGuard Tuya Plug In" -Direction Inbound -Protocol TCP -LocalPort 6668 -Action Allow -ErrorAction SilentlyContinue
}

# ---- MAIN ----
Check-Admin
Install-Nssm
Setup-Service
Add-FirewallRules
Write-Log 'Auto-start setup complete. Service will start on boot.'