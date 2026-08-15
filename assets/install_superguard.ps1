<# 
.SYNOPSIS
    SuperGuard Alarm — Autonomous AI Security Service Installer
    Deploys panic_mode.py (AI video surveillance + Telegram bot + Tuya smart plug)
    from GitHub to a fresh Windows machine.

.DESCRIPTION
    Installs: Python 3.12, OpenCV, YOLO11n, tinytuya, requests, psutil
    Configures: Windows service (NSSM) for auto-start, firewall rules
    Requires: Admin rights, internet, GitHub repo with panic_mode.py + sguard.env template

.PARAMETER RepoUrl
    GitHub repo URL (default: https://github.com/DarkPushkin/superguard-alarm)
.PARAMETER InstallDir
    Target directory (default: C:\SuperGuard)
.PARAMETER ServiceName
    Windows service name (default: SuperGuardAlarm)
.PARAMETER BotToken
    Telegram bot token (optional, will prompt if omitted)
.PARAMETER ChatId
    Telegram chat ID (optional, will prompt if omitted)
.PARAMETER PlugIp
    Tuya plug IP (optional, will prompt if omitted)
.PARAMETER PlugKey
    Tuya plug local_key (optional, will prompt if omitted)
#>

param(
    [string]$RepoUrl = "https://github.com/DarkPushkin/superguard-alarm",
    [string]$InstallDir = "C:\SuperGuard",
    [string]$ServiceName = "SuperGuardAlarm",
    [string]$BotToken = "",
    [string]$ChatId = "",
    [string]$PlugIp = "",
    [string]$PlugKey = ""
)

$ErrorActionPreference = "Stop"

function Write-Log {
    param([string]$Msg, [string]$Level = "INFO")
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Write-Host "[$ts] [$Level] $Msg" -ForegroundColor ([System.ConsoleColor]::Cyan)
}

function Check-Admin {
    $id = [System.Security.Principal.WindowsIdentity]::GetCurrent()
    $p = New-Object System.Security.Principal.WindowsPrincipal($id)
    if (-not $p.IsInRole([System.Security.Principal.WindowsBuiltInRole]::Administrator)) {
        Write-Error "Run PowerShell as Administrator!"
        exit 1
    }
}

function Install-Python {
    Write-Log "Installing Python 3.12 via winget..."
    winget install --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements --silent
    $pythonPath = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
    if (-not (Test-Path $pythonPath)) {
        $pythonPath = "C:\Python312\python.exe"
    }
    if (-not (Test-Path $pythonPath)) {
        Write-Error "Python not found after install"
        exit 1
    }
    Write-Log "Python at $pythonPath"
    return $pythonPath
}

function Install-Nssm {
    Write-Log "Installing NSSM (service wrapper)..."
    $nssmDir = "$env:ProgramFiles\NSSM"
    if (-not (Test-Path "$nssmDir\nssm.exe")) {
        $tmp = "$env:TEMP\nssm.zip"
        Invoke-WebRequest -Uri "https://nssm.cc/release/nssm-2.24.zip" -OutFile $tmp
        Expand-Archive -Path $tmp -DestinationPath "$env:TEMP\nssm" -Force
        New-Item -ItemType Directory -Force -Path $nssmDir | Out-Null
        Copy-Item "$env:TEMP\nssm\nssm-2.24\win64\nssm.exe" "$nssmDir\nssm.exe" -Force
        $env:Path += ";$nssmDir"
        [Environment]::SetEnvironmentVariable("Path", $env:Path, "Machine")
    }
    Write-Log "NSSM ready"
}

function Setup-Directory {
    Write-Log "Creating install directory $InstallDir..."
    New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
    Set-Location $InstallDir
}

function Clone-Repo {
    Write-Log "Cloning repo $RepoUrl..."
    git clone $RepoUrl .
}

function Create-Venv {
    param($PythonPath)
    Write-Log "Creating virtual environment..."
    & $PythonPath -m venv venv
    $pip = "venv\Scripts\pip.exe"
    & $pip install --upgrade pip
    Write-Log "Installing dependencies..."
    & $pip install opencv-python ultralytics tinytuya requests psutil numpy
}

function Create-EnvFile {
    Write-Log "Creating sguard.env..."
    if (-not $BotToken) { $BotToken = Read-Host "Enter Telegram Bot Token (SuperGuard Alarm bot)" }
    if (-not $ChatId) { $ChatId = Read-Host "Enter Telegram Chat ID (your user/group ID)" }
    if (-not $PlugIp) { $PlugIp = Read-Host "Enter Tuya Smart Plug IP (e.g. 192.168.137.109)" }
    if (-not $PlugKey) { $PlugKey = Read-Host "Enter Tuya Plug Local Key (32 hex chars)" -AsSecureString | ConvertFrom-SecureString }

    @"
SG_TELEGRAM_BOT_TOKEN=$BotToken
SG_CHAT_ID=$ChatId
SG_PLUG_IP=$PlugIp
SG_PLUG_KEY=$PlugKey
"@ | Set-Content -Path "sguard.env" -Encoding UTF8
    Write-Log "sguard.env created (keep it secret!)"
}

function Create-Service {
    param($PythonPath)
    Write-Log "Creating Windows service $ServiceName..."
    $pythonExe = "$InstallDir\venv\Scripts\python.exe"
    $scriptPath = "$InstallDir\panic_mode.py"
    nssm install $ServiceName $pythonExe $scriptPath
    nssm set $ServiceName AppDirectory $InstallDir
    nssm set $ServiceName AppStdout "$InstallDir\superguard.log"
    nssm set $ServiceName AppStderr "$InstallDir\superguard_err.log"
    nssm set $ServiceName Start SERVICE_AUTO_START
    nssm set $ServiceName Description "SuperGuard Alarm — AI video surveillance + Telegram bot + Tuya plug"
    Write-Log "Service created. Starting..."
    Start-Service $ServiceName -ErrorAction SilentlyContinue
}

function Add-FirewallRules {
    Write-Log "Adding firewall rules for Tuya plug (port 6668)..."
    New-NetFirewallRule -DisplayName "SuperGuard Tuya Plug" -Direction Outbound -Protocol TCP -LocalPort 6668 -Action Allow -ErrorAction SilentlyContinue
    New-NetFirewallRule -DisplayName "SuperGuard Tuya Plug In" -Direction Inbound -Protocol TCP -LocalPort 6668 -Action Allow -ErrorAction SilentlyContinue
}

function Verify-Install {
    Write-Log "Verifying installation..."
    $svc = Get-Service $ServiceName -ErrorAction SilentlyContinue
    if ($svc -and $svc.Status -eq 'Running') {
        Write-Log "SUCCESS: Service $ServiceName is RUNNING" "OK"
    } else {
        Write-Log "Service status: $($svc.Status)" "WARN"
    }
    if (Test-Path "$InstallDir\panic_mode.py" -and Test-Path "$InstallDir\sguard.env") {
        Write-Log "Files in place" "OK"
    }
    Write-Log "Install complete. Check logs: $InstallDir\superguard.log"
}

# ---- MAIN ----
Check-Admin
$python = Install-Python
Install-Nssm
Setup-Directory
Clone-Repo
Create-Venv -PythonPath $python
Create-EnvFile
Create-Service -PythonPath $python
Add-FirewallRules
Verify-Install