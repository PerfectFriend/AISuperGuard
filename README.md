# SuperGuard Alarm — Autonomous AI Security Service

**[English](README.md) | [Русский](README.ru.md) | [Español](README.es.md)**

**AI Video Surveillance → Target Detection (YOLO11n + HSV Color + Zones) → Tuya Smart Plug ON → Telegram**

Autonomous security service for Windows. Deploys in one command on a fresh machine.

## Features

- 🎥 **RTSP/HLS Camera** — Any streaming camera (tested: Banjar ATCS Indonesia)
- 🤖 **YOLO11n Detection** — Cars, buses, trucks, people (GPU: Radeon 780M / ROCm / DirectML)
- 🎨 **HSV Color Filter** — Target set in free text: `/target red car`, `/target white truck`, `/target person standing`
- 📍 **Zone Filter** — N×M grid, cells C01..C12: `/zone N3x4 C9`, `/zone off` (whole frame)
- 🔌 **Tuya Smart Plug (local, tinytuya 3.4)** — Plug activates on trigger
- 📱 **Telegram Bot (separate token)** — Command menu, trigger photo, live frame 2s, auto-off after 5 clean frames
- 🌍 **Multi-language** — RU/EN/ES via `/setlocal` (inline buttons), menu follows selected language
- 💾 **Persistence** — Settings in `sguard_settings.json` survive restarts
- 🛡 **Self Zombie-Killer** — On start kills stale python.exe panic_mode on same token
- 🪟 **Windows Service (NSSM)** — Auto-start, logs, restart on crash

## Bot Commands (menu next to paperclip)

| Command | Description |
|---------|-------------|
| `/autoguard` | Toggle auto mode (plug OFF automatically when target leaves) |
| `/togglealarm` | Manual alarm (plug ON, photo immediately, no YOLO) |
| `/zone` | Zone: `N3x4 C9`, `N9 C5`, `off`, `?` |
| `/target` | Target: `red car`, `white truck`, `person standing`, `?` |
| `/setlocal` | Interface language (RU/EN/ES) |

## Quick Install (on clean Windows 10/11)

```powershell
# Run as Administrator
irm https://raw.githubusercontent.com/DarkPushkin/superguard-alarm/main/install_superguard.ps1 | iex
```

Or download and run `install_superguard.ps1` with parameters:
```powershell
.\install_superguard.ps1 -BotToken "123:ABC" -ChatId "143293811" -PlugIp "192.168.137.109" -PlugKey "abcdef123456..."
```

## Manual Install

```powershell
# 1. Python 3.12
winget install Python.Python.3.12

# 2. Clone
git clone https://github.com/DarkPushkin/superguard-alarm
cd superguard-alarm

# 3. Virtual environment
python -m venv venv
venv\Scripts\pip install -r requirements.txt

# 4. Config
copy sguard.env.example sguard.env
# Edit sguard.env (token, chat_id, plug IP, local_key)

# 5. Run
venv\Scripts\python panic_mode.py
```

## Windows Service (Auto-start)

```powershell
# Install NSSM
# Create service:
nssm install SuperGuardAlarm "C:\SuperGuard\venv\Scripts\python.exe" "C:\SuperGuard\panic_mode.py"
nssm set SuperGuardAlarm AppDirectory "C:\SuperGuard"
nssm set SuperGuardAlarm Start SERVICE_AUTO_START
Start-Service SuperGuardAlarm
```

## Requirements

- Windows 10/11 (x64)
- Python 3.12
- GPU with OpenCV support (Radeon 780M / CUDA / DirectML) — **NO CPU fallback**
- Telegram Bot (create via @BotFather, **SEPARATE token!**)
- Tuya Smart Plug (flashed locally, tinytuya 3.4, port 6668)
- RTSP/HLS Camera

## GPU on AMD Radeon 780M (Beelink SER9)

```bash
# Windows ROCm 7.2 — ONLY WORKING PATH
# WSL2 doesn't work, DirectML segfaults
pip install torch torchvision --index-url https://download.pytorch.org/whl/rocm7.2
```

## Config Files

### `sguard.env` (DO NOT COMMIT!)
```
SG_TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
SG_CHAT_ID=143293811
SG_PLUG_IP=192.168.137.109
SG_PLUG_KEY=abcdef1234567890abcdef1234567890
```

### `sguard_settings.json` (auto-generated)
```json
{
  "zone": [3, 3, 5],
  "target": "white car",
  "lang": "es",
  "auto": true
}
```

## Architecture

```
panic_mode.py (single file, ~1000 lines)
├── Telegram long-poll (async-safe, 8s timeout, per-update isolation)
├── YOLO11n + ByteTrack (persist, conf=0.45, imgsz=640)
├── HSV color filter (11 colors, red=dual range 0-10/170-180)
├── Zone grid (N×M, orange overlay on frame)
├── Tuya local (tinytuya 3.4, fresh conn per command)
├── Alarm state machine (AUTO/MANUAL, 5-frame auto-resolve)
├── i18n (RU/EN/ES, 48 keys, tr() everywhere)
├── Self-zombie-killer (PowerShell, psutil PID)
└── Persistence (JSON, load_settings() FIRST in __main__)
```

## Bot Messages

**Alarm (msg A)** — trigger frame, bounding box, **NO buttons**, stays forever (audit)  
**Live (msg B)** — live frame 2s, updates, **deleted on disarm**  
**Auto-resolve (5 clean frames)** — plug OFF + single message:
```
✅ Threat cleared: target left search zone
🚨 Alarm disarmed.
📌 Current mode: AUTO, zone=N3x3 C05, target=white car
```

## License

MIT — use, modify, deploy.

---

**Master Inquisitor (@RarioArmageddon) · The Grimoire · DarkPushkin/the-grimoire**