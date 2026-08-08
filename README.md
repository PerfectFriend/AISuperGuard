<div align="center">

![SuperGuard Banner — cyberpunk × Van Gogh × Gaudí](assets/banner-header.png)

# 🛡️ SuperGuard Alarm

AI-powered video surveillance with smart-plug response and Telegram control.

**YOLO object detection → HSV color filter → zone filter → Tuya smart plug ON → Telegram alarm**

[English](README.md) · [Русский](README.ru.md) · [Español](README.es.md) · [Admin Guide (RU)](ADMIN_GUIDE.md)

</div>

---

## ✨ Features

- **8+ cameras** — HLS streams, RTSP (local PoE cameras), HTTP JPG snapshots — all monitored simultaneously
- **AI detection** — YOLO11n (Ultralytics) with object tracking; filter by class (car, person, bus, truck…) and color (red, yellow, blue… via HSV)
- **Zone filter** — limit detection to a grid cell: `N3x4 C9` = 3×4 grid, cell 9
- **Active camera** — commands (`/zone`, `/target`, `/plug`) always work with the active camera. A camera becomes active on alarm or via `/cam`, and stays active until another camera takes over
- **Smart plugs** — Tuya plugs controlled locally (tinytuya), bind any number of plugs to a camera: `/plug 1 2 3`
- **Alarm protocol** — trigger frame (audit, never deleted) + live frame **updated every 2 s** from the alarm camera until the alarm is resolved
- **Auto-resolve** — in auto mode the alarm cancels itself when the target leaves the zone; in manual mode it waits for `/togglealarm`
- **Manual trigger** — `/togglealarm` for admin testing; duplicates automatic alarm behavior (respects auto/manual mode)
- **Telegram bot** — full control via commands, inline buttons, 3 languages (EN/ES/RU)
- **Resilience** — camera auto-reconnect, plug auto-reconnect (`/plug test`), zombie-process killer, atomic settings storage, Tuya Cloud IP auto-discovery
- **Browser live view** — built-in MJPEG server (`http://localhost:8081`)
- **26 automated checks** — syntax, config, models, cameras, actuators, alarm protocol, live-frame updates

---

## 🏗️ Architecture

```
C:\SuperGuard\
├── sguard.env                    # All configuration (token, cameras, plugs)
├── sguard_settings.json          # Runtime settings (per-camera zone/target/plugs)
├── saved_frames\                 # Alarm frame archive
├── mjpeg_stream_server.py        # Browser live view (port 8081)
├── requirements.txt
└── superguard\
    ├── main.py                   # Entry point, SuperGuardApplication
    ├── config.py                 # Config loading & validation
    ├── models\                   # Zone, Target, CameraSettings, Alarm (state machine)
    ├── detectors\                # YOLO + HSV color + zone pipeline
    ├── cameras\                  # JPG/HLS/RTSP cameras, CameraManager
    ├── actuators\                # Plug abstraction (Tuya…), registry, ActuatorManager
    ├── telegram\                 # Telegram client, command router, bot
    ├── storage\                  # Atomic JSON settings, .env writer
    ├── tuya_cloud\               # Tuya Cloud sync (plug IP auto-discovery)
    └── tests\                    # test_all.py, test_live_update.py, test_plug_active_cam.py
```

### Detection pipeline

```
Camera (JPG/HLS/RTSP) → frame → YOLO11n → zone filter → class filter → HSV color filter
   ↓ target found N frames in a row (require_frames)
ALARM: plug(s) ON → Telegram: trigger frame (msg A)
   → 1 s later: live frame (msg B), updated every update_every s
   ↓ target gone (auto_resolve_frames clean frames + auto mode)
plug(s) OFF → "Threat resolved" notification
```

### Alarm state machine

```
INACTIVE ──(target N frames)──▶ ACTIVE ──(auto mode + N clean)──▶ AUTO_RESOLVING
   ▲                                │                                 │
   │                                │◀──(target re-detected)───────────┘
   └────(/togglealarm or button)────┘
```

---

## 🚀 Quick start

```bash
git clone <repo-url> superguard
cd superguard
pip install -r requirements.txt

# 1. Create bot with @BotFather, put token in sguard.env
# 2. Configure cameras & plugs in sguard.env (see Admin Guide)
python superguard\main.py
```

**Windows note:** run `python superguard\main.py`; the bot installs its command menu automatically.

---

## ⚙️ Configuration (`sguard.env`)

| Variable | Purpose |
|---|---|
| `SG_TELEGRAM_BOT_TOKEN` | Bot token (must be a **separate** bot from your gateway bot) |
| `SG_CHAT_ID` | Telegram chat ID for alarms |
| `SG_PLUG_KEY` | Tuya local key (backward-compat default plug) |
| `SG_CAM_URL` | Camera 1 URL (HLS) |
| `SG_CAM2_URL` … `SG_CAM32_URL` | Cameras 2–32 (add/override without code changes) |
| `SG_CAM{N}_NAME` | Optional display name for camera N |
| `SG_UPDATE_EVERY` | Frame refresh interval (s) — live frame update period |
| `SG_DETECT_EVERY` | Detection loop interval (s) |
| `SG_MIN_CONF` | YOLO confidence threshold |
| `SG_YELLOW_MIN_FRACTION` | Min color-pixel fraction in a box |
| `SG_MIN_YELLOW_VEHICLES` | Min matches to count a "hit" |
| `SG_REQUIRE_FRAMES` | Consecutive hit frames to trigger alarm |
| `SG_AUTO_RESOLVE_FRAMES` | Clean frames to auto-cancel alarm |
| `SG_ACTUATORS` | JSON array of plugs (`name`, `type`, `cameras`, `ip`, `device_id`, `local_key`, `version`, `port`) |
| `TUYA_ACCESS_ID` / `TUYA_ACCESS_SECRET` | Tuya Cloud OpenAPI keys (plug IP auto-discovery) |

Camera types are chosen automatically by URL: `.jpg/.jpeg/.png` → JPG camera; `.m3u8`/`rtsp://` → stream camera.

---

## 🤖 Telegram commands

| Command | Action |
|---|---|
| `/autoguard` | Toggle auto mode on/off |
| `/togglealarm` | Manual alarm on/off (admin test trigger) |
| `/zone` | `/zone N3x4 C9` set zone, `/zone off` whole frame, `/zone ?` help |
| `/target` | `/target red car` set target, `/target ?` help |
| `/plug` | Show plugs of the active camera |
| `/plug 1 2 3` | Bind plugs plug1..plug3 to the **active** camera |
| `/plug test` | Test plugs, auto-reconnect failed |
| `/setlocal` | Language EN/ES/RU (inline buttons) |
| `/cam` | Camera list/status, switch active camera (`/cam 3`) |

### Zone format
- `N{rows}x{cols} C{cell}` — grid rows×cols, cell number (1 = top-left)
  `/zone N3x4 C9` → 3×4 grid, cell 9
- `N{total} C{cell}` — square grid: `/zone N9 C5` = 3×3, cell 5
- `off` / `всё` / `0` / `todo` / `nada` — whole frame

### Target format
`/target <text>` — class words + color words:
- Classes: `person`, `car`, `bus`, `truck`, `bicycle`, `motorcycle`…
- Colors: `red`, `blue`, `yellow`, `green`, `black`, `white`…
- Example: `/target red car`

---

## 🔌 Plug bindings

- Plugs are configured in `SG_ACTUATORS` (type `tuya`, protocol 3.4, port 6668)
- Bind plugs to a camera: switch to it (`/cam N`), then `/plug 1 2` (numbers → `plug1`, `plug2`)
- On alarm from that camera, **all bound plugs** turn ON; on resolve, they turn OFF
- Bindings persist in `sguard_settings.json` and are restored on start
- `"ip": "auto"` + Tuya Cloud keys → plug IP discovered automatically (every 5 min)

---

## 🖥️ Browser live view

```bash
python mjpeg_stream_server.py
```
- `http://localhost:8081/` — MJPEG stream
- `http://localhost:8081/snapshot.jpg` — single frame

---

## 🧪 Tests

```bash
python superguard\tests\test_all.py           # 11 checks: syntax, config, models, cameras, actuators, app
python superguard\tests\test_live_update.py   # 7 checks: live-frame update protocol
python superguard\tests\test_plug_active_cam.py  # 8 checks: active camera, /plug, alarm bindings
```

---

## 🛠️ Admin Guide

Full setup — adding cameras, adding plugs of all supported types — see [ADMIN_GUIDE.md](ADMIN_GUIDE.md) (Russian).

---

## 📄 License

MIT

---

**Master Inquisitor (@RarioArmageddon) · The Grimoire · DarkPushkin/the-grimoire**

---

<div align="center">

![SuperGuard Footer — cyberpunk × Van Gogh × Gaudí](assets/banner-footer.png)

**Protect your infrastructure. 24/7. Local. Intelligent.**

</div>
