# SuperGuard Desktop - build script (Windows)
# Usage: powershell -ExecutionPolicy Bypass -File build.ps1
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path   # desktop/
$Proj = Split-Path -Parent $Root                           # project root
$Venv = Join-Path $Proj "venv"

# Prefer project venv python; fallback to system
if (Test-Path "$Venv\Scripts\python.exe") {
    $Py = "$Venv\Scripts\python.exe"
} else {
    $Py = "python"
}

Write-Host "==> Python: $Py"
& $Py -m pip install --quiet pyinstaller pillow pystray requests

Write-Host "==> Building SuperGuardDesktop.exe..."
Push-Location $Root
& $Py -m PyInstaller --noconfirm --clean `
    --onefile --windowed `
    --name SuperGuardDesktop `
    --icon "$Root\assets\icon.ico" `
    --add-data "$Root\assets\icon.png;assets" `
    --add-data "$Root\assets\icon.ico;assets" `
    --exclude-module torch `
    --exclude-module ultralytics `
    --exclude-module cv2 `
    --exclude-module numpy `
    "$Root\main.py"
Pop-Location

$Exe = Join-Path $Root "dist\SuperGuardDesktop.exe"
if (Test-Path $Exe) {
    $Size = [math]::Round((Get-Item $Exe).Length / 1MB, 1)
    Write-Host "OK: $Exe ($Size MB)"
} else {
    Write-Host "BUILD FAILED"
    exit 1
}
