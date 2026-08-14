#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
#  CableGuard — Anti Cable-Theft AI Surveillance
#  Установщик для Linux/macOS (Windows — см. install.ps1)
#
#  Разворачивает систему одним скриптом:
#    git clone → venv → зависимости → yolo веса → конфиг → тест
#
#  Запуск:
#    curl -sSL https://raw.githubusercontent.com/PerfectFriend/AISuperGuard/main/install.sh | bash
#    или
#    git clone https://github.com/PerfectFriend/AISuperGuard.git && cd cableguard && bash install.sh
# ═══════════════════════════════════════════════════════════════════════════
set -euo pipefail

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()  { echo -e "${GREEN}[✓]${NC} $1"; }
warn()  { echo -e "${YELLOW}[!]${NC} $1"; }
fail()  { echo -e "${RED}[✗]${NC} $1"; exit 1; }

# ── 1. Каталог ────────────────────────────────────────────────────────────
INSTALL_DIR="${1:-$HOME/cableguard}"
mkdir -p "$INSTALL_DIR"
cd "$INSTALL_DIR"
info "Каталог: $INSTALL_DIR"

# ── 2. Python ──────────────────────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
  warn "python3 не найден — ставлю..."
  if command -v apt-get &>/dev/null; then sudo apt-get update && sudo apt-get install -y python3 python3-venv python3-pip ffmpeg
  elif command -v brew &>/dev/null; then brew install python ffmpeg
  else fail "Не могу установить python3 — поставь вручную и повтори."
  fi
fi
info "Python: $(python3 --version)"

# ── 3. ffmpeg (для клипов) ────────────────────────────────────────────────
if ! command -v ffmpeg &>/dev/null; then
  warn "ffmpeg не найден — ставлю..."
  if command -v apt-get &>/dev/null; then sudo apt-get install -y ffmpeg
  elif command -v brew &>/dev/null; then brew install ffmpeg
  else warn "ffmpeg не установлен — видео-клипы не будут работать (фото — будут)."
  fi
fi

# ── 4. venv + зависимости ─────────────────────────────────────────────────
info "Создаю виртуальное окружение..."
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip -q

info "Ставлю зависимости (opencv, ultralytics, pyyaml, requests)..."
pip install -q opencv-python ultralytics pyyaml requests
info "Зависимости установлены."

# ── 5. Веса YOLO ──────────────────────────────────────────────────────────
if [ ! -f "yolo11n.pt" ]; then
  info "Скачиваю веса YOLO11n (~5.4 MB)..."
  python -c "from ultralytics import YOLO; YOLO('yolo11n.pt')"
fi

# ── 6. Конфиг ─────────────────────────────────────────────────────────────
if [ ! -f "config.yaml" ]; then
  info "Создаю config.yaml из шаблона..."
  cp config.example.yaml config.yaml
  warn "Отредактируй config.yaml: впиши RTSP-URL камер и Telegram chat_id!"
fi

# ── 7. Проверка ───────────────────────────────────────────────────────────
info "Проверяю установку..."
python - <<'EOF'
import cv2, ultralytics, yaml, requests
print(f"  opencv     {cv2.__version__}")
print(f"  ultralytics {ultralytics.__version__}")
from pathlib import Path
assert Path("yolo11n.pt").exists(), "нет yolo11n.pt"
print("  yolo11n.pt OK")
EOF

# ── 8. Финальный тест ─────────────────────────────────────────────────────
if [ -f "test-person.jpg" ]; then
  info "Тест детекции на тестовом кадре..."
  python - <<'EOF'
import cv2
from ultralytics import YOLO
from electrician_detector import analyze_frame, draw_alerts
model = YOLO("yolo11n.pt")
frame = cv2.imread("test-person.jpg")
results = model.predict(frame, conf=0.4, verbose=False)
dets = []
for r in results:
    for b in r.boxes:
        x1,y1,x2,y2 = b.xyxy[0].tolist()
        dets.append((x1,y1,x2,y2, r.names[int(b.cls[0])], float(b.conf[0])))
persons = [d for d in dets if d[4]=="person"]
print(f"  YOLO: {len(persons)} person, {len(dets)} всего")
EOF
fi

info "Установка завершена! 🎉"
echo ""
echo "  Дальше:"
echo "  1. python scripts/scan_cameras.py            # найти камеру"
echo "  2. nano config.yaml                          # вписать RTSP + Telegram"
echo "  3. python demo_prototype.py --source rtsp://user:pass@IP:554/stream1"
echo ""
echo "  Документация: docs/ (CAMERA-SETUP.md, ESP32 прошивка в docs/)"
