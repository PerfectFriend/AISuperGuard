# SuperGuard Desktop - one-command install (Windows)
# Usage (Run as Administrator in PowerShell):
#   irm https://raw.githubusercontent.com/PerfectFriend/AISuperGuard/main/install_desktop.ps1 | iex
$ErrorActionPreference = "Stop"

$Version  = "v1.0.0"
$Repo     = "https://github.com/PerfectFriend/AISuperGuard"
$DestDir  = "C:\SuperGuard"
$ExeUrl   = "$Repo/releases/download/$Version/SuperGuardDesktop.exe"
$ExePath  = Join-Path $DestDir "SuperGuardDesktop.exe"

Write-Host "==> SuperGuard Desktop installer ($Version)" -ForegroundColor Cyan
Write-Host "    Dir: $DestDir"

# 1. destination dir
New-Item -ItemType Directory -Force -Path $DestDir | Out-Null

# 2. download exe
Write-Host "==> Downloading SuperGuardDesktop.exe..."
Invoke-WebRequest -Uri $ExeUrl -OutFile $ExePath -UseBasicParsing
$Size = [math]::Round((Get-Item $ExePath).Length / 1MB, 1)
Write-Host "    OK: $ExePath ($Size MB)"

# 3. shortcut in Startup for autostart (optional: comment to disable)
$Startup = [Environment]::GetFolderPath("Startup")
$Lnk = Join-Path $Startup "SuperGuardDesktop.lnk"
$ws = New-Object -ComObject WScript.Shell
$sc = $ws.CreateShortcut($Lnk)
$sc.TargetPath = $ExePath
$sc.WorkingDirectory = $DestDir
$sc.Description = "SuperGuard Desktop - AI video surveillance monitor"
$sc.Save()
Write-Host "==> Автозапуск: ярлык создан ($Lnk)"

# 4. launch
Write-Host "==> Запуск..."
Start-Process $ExePath
Write-Host "Готово! SuperGuard Desktop установлен и запущен." -ForegroundColor Green
Write-Host "В первом окне укажите токен Telegram-бота (или нажмите Настройки)."
