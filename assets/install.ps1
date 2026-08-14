# ═══════════════════════════════════════════════════════════════════════════
#  CableGuard — Anti Cable-Theft AI Surveillance
#  Установщик для Windows (Linux/macOS — см. install.sh)
#
#  Запуск (PowerShell, от имени обычного пользователя):
#    curl.exe -L https://raw.githubusercontent.com/PerfectFriend/AISuperGuard/main/install.ps1 -o install.ps1
#    powershell -ExecutionPolicy Bypass -File install.ps1
# ═══════════════════════════════════════════════════════════════════════════
$ErrorActionPreference = "Stop"
$Green = "`e[32m"; $Yellow = "`e[33m"; $Red = "`e[31m"; $NC = "`e[0m"

function Info($m) { Write-Host "${Green}[+]${NC} $m" }
function Warn($m) { Write-Host "${Yellow}[!]${NC} $m" }
function Fail($m) { Write-Host "${Red}[x]${NC} $m"; exit 1 }

$InstallDir = if ($args.Count -gt 0) { $args[0] } else { Join-Path $HOME "cableguard" }
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
Set-Location $InstallDir
Info "Каталог: $InstallDir"

# ── Python ────────────────────────────────────────────────────────────────
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) {
    Warn "python не найден. Пробую winget..."
    try {
        winget install --id Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
    } catch { Fail "Не удалось поставить Python. Поставь вручную: python.org/downloads" }
}
$pyVer = python --version 2>&1
Info "Python: $pyVer"

# ── ffmpeg ────────────────────────────────────────────────────────────────
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    Warn "ffmpeg не найден — видео-клипы не будут работать (фото — будут)."
    Warn "Скачай Gyan build: https://www.gyan.dev/ffmpeg/builds/ и добавь в PATH"
}

# ── venv + зависимости ────────────────────────────────────────────────────
Info "Создаю виртуальное окружение..."
python -m venv .venv
$venvPy = Join-Path $InstallDir ".venv\Scripts\python.exe"
& $venvPy -m pip install --upgrade pip -q

Info "Ставлю зависимости (opencv, ultralytics, pyyaml, requests)..."
& $venvPy -m pip install -q opencv-python ultralytics pyyaml requests
Info "Зависимости установлены."

# ── YOLO веса ─────────────────────────────────────────────────────────────
if (-not (Test-Path "yolo11n.pt")) {
    Info "Скачиваю веса YOLO11n (~5.4 MB)..."
    & $venvPy -c "from ultralytics import YOLO; YOLO('yolo11n.pt')"
}

# ── Конфиг ────────────────────────────────────────────────────────────────
if (-not (Test-Path "config.yaml")) {
    Info "Создаю config.yaml из шаблона..."
    Copy-Item "config.example.yaml" "config.yaml"
    Warn "Отредактируй config.yaml: RTSP-URL камер и Telegram chat_id!"
}

# ── Проверка ──────────────────────────────────────────────────────────────
Info "Проверяю установку..."
& $venvPy -c "import cv2, ultralytics, yaml, requests; print('  opencv', cv2.__version__); print('  ultralytics', ultralytics.__version__)"

Info "Установка завершена! 🎉"
Write-Host ""
Write-Host "  Дальше:"
Write-Host "  1. .venv\Scripts\python.exe scripts\scan_cameras.py     # найти камеру"
Write-Host "  2. notepad config.yaml                                  # вписать RTSP + Telegram"
Write-Host "  3. .venv\Scripts\python.exe demo_prototype.py --source rtsp://user:pass@IP:554/stream1"
Write-Host ""
Write-Host "  Документация: docs\ (CAMERA-SETUP.md, ESP32 прошивка в docs\)"
