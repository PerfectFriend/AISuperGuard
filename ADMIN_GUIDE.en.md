# 🛠️ SuperGuard Alarm — Administrator Guide

Quick setup: adding cameras and plugs, bindings, diagnostics.

> **Important:** **stop** the bot before editing config, otherwise it will overwrite
> files from memory: `taskkill /F /IM python.exe` (or via autostart script).
> Always: **stop → edit → start**.

---

## 1. Where everything lives

| File | Purpose |
|---|---|
| `sguard.env` | Main config (token, cameras, plugs, parameters) |
| `superguard\sguard_settings.json` | Bot-changed settings (zone/target/plugs per camera) |
| `saved_frames\` | Alarm frames |
| `desktop_state\` | Desktop bridge (status.json + alarm_live.jpg, created at runtime) |
| `superguard\tests\` | Tests |

---

## 2. Adding a camera

Cameras are defined in `sguard.env` via `SG_CAM{N}_URL` and `SG_CAM{N}_NAME`.

### Step 1 — choose a camera number (2–32)
Camera 1 is set by `SG_CAM_URL` (HLS). The rest: `SG_CAM2_URL` … `SG_CAM32_URL`.

### Step 2 — add lines to `sguard.env`

```ini
# HLS stream
SG_CAM5_URL=https://example.com/live/stream.m3u8
SG_CAM5_NAME=5: Example HLS

# RTSP camera (local PoE)
SG_CAM6_URL=rtsp://admin:password@192.168.1.50:554/cam/realmonitor?channel=1&subtype=0
SG_CAM6_NAME=6: Outdoor camera

# JPG snapshot (periodically refreshed)
SG_CAM7_URL=https://example.com/camera/snapshot.jpg
SG_CAM7_NAME=7: Snapshot
```

### Step 3 — restart the bot
Camera type is chosen automatically by URL:
- `.jpg` / `.jpeg` / `.png` / `snapshot` / `image` → JPG camera (HTTP snapshot)
- `.m3u8` / `rtsp://` → stream camera (cv2.VideoCapture, auto-reconnect)

### Step 4 — verify
In Telegram: `/cam` — camera must appear in the list; `/cam 6` — make it active;
`/cam status` — status (🟢 alive / 🔴 dead).

---

## 3. Adding a Tuya plug (local control)

Tuya plugs are controlled **locally** via the tinytuya library (protocol 3.4, port 6668).

### Step 1 — get the plug data
Data comes from the **Smart Life** app or the Tuya IoT platform:

| Field | What it is | Where to get |
|---|---|---|
| `device_id` | Device ID | Tuya IoT Platform → device |
| `local_key` | Local key | Tuya IoT Platform → device |
| `ip` | Plug IP on the LAN | router / `nmap` / `ip auto` |
| `version` | Protocol version (3.4 / 3.3 / 3.1) | Tuya IoT Platform |
| `port` | Port (usually 6668) | standard |

### Step 2 — add the plug to `SG_ACTUATORS`

```ini
SG_ACTUATORS=[
  {"name": "plug1", "type": "tuya", "cameras": [1, 2, 3, 4],
   "ip": "192.168.137.197", "device_id": "bfd23bfc...", "local_key": "3MTI4(N~...",
   "version": 3.4, "port": 6668},
  {"name": "plug2", "type": "tuya", "cameras": [5, 6, 7, 8],
   "ip": "auto", "device_id": "sesjdvq...", "local_key": "sesjdvq...",
   "version": 3.4, "port": 6668}
]
```

- `"ip": "auto"` — the IP is discovered automatically via Tuya Cloud (see section 4)
- `cameras` — initial binding: which cameras drive this plug

### Step 3 — verify
In Telegram: `/plug` — the plug must be 🟢 ONLINE; `/plug test` — test with auto-reconnect.

---

## 4. Tuya Cloud (plug IP auto-discovery)

If a plug's IP changes (DHCP), provide OpenAPI keys — sync every 5 minutes finds
the plug by `device_id` and updates the IP in config and `.env`:

```ini
TUYA_ACCESS_ID=your_access_id
TUYA_ACCESS_SECRET=your_access_secret
TUYA_REGION=eu        # cn / us / eu / in
TUYA_SCHEMA=smartlife
```

Region — where your Smart Life account is registered.

---

## 5. Binding plugs to a camera via Telegram

1. Switch to the camera: `/cam N`
2. Bind plugs by number: `/plug 1 2` (will drive plug1 and plug2)
3. Check: `/plug` — shows the active camera's bindings

On alarm from that camera, **all** bound plugs turn ON; on resolve, they turn OFF.
Bindings persist in `sguard_settings.json` and are restored on start.

---

## 6. Adding another plug type (Sonoff, Shelly, ESPHome, Zigbee)

The actuator architecture is extensible: `BaseActuator` (interface) + `ActuatorRegistry`
(type registry). Type `tuya` is implemented; others are added as a subclass:

### Step 1 — create a class in `superguard/actuators/__init__.py`

```python
class SonoffActuator(BaseActuator):
    """Sonoff / Tasmota via HTTP API (http://<ip>/cm?cmnd=Power%20ON)."""
    def __init__(self, config):
        super().__init__(config)
        self.ip = config.get("ip")
        self._base = f"http://{self.ip}/cm"
   
    def _cmd(self, cmd: str) -> bool:
        import requests
        try:
            r = requests.get(f"{self._base}?cmnd={cmd}", timeout=5)
            return r.status_code == 200 and "POWER" in r.text
        except Exception:
            return False
   
    def turn_on(self) -> bool:
        return self._cmd("Power%20ON")
   
    def turn_off(self) -> bool:
        return self._cmd("Power%20OFF")
   
    def get_status(self) -> bool:
        import requests
        try:
            r = requests.get(f"{self._base}?cmnd=Power", timeout=5)
            return '"ON"' in r.text
        except Exception:
            return False

# Register the type
actuator_registry.register("sonoff", SonoffActuator)
```

Likewise for Shelly (`http://<ip>/relay/0?turn=on`), ESPHome (REST/API),
Zigbee (via zigbee2mqtt MQTT).

### Step 2 — set the type in `SG_ACTUATORS`

```ini
SG_ACTUATORS=[
  {"name": "plug3", "type": "sonoff", "cameras": [3],
   "ip": "192.168.1.60", "device_id": "", "local_key": "", "version": 3.4, "port": 6668}
]
```

`type` must match the name registered in the registry (`register("sonoff", …)`).

### Step 3 — restart and check with `/plug test`

---

## 7. Detection parameters (fine-tuning)

| Variable | Default | Meaning |
|---|---|---|
| `SG_UPDATE_EVERY` | 2.0 | Camera frame interval / live-frame update period in Telegram |
| `SG_DETECT_EVERY` | 1.5 | Detection loop interval |
| `SG_MIN_CONF` | 0.35 | Min YOLO confidence |
| `SG_YELLOW_MIN_FRACTION` | 0.15 | Min color-pixel fraction in a box |
| `SG_MIN_YELLOW_VEHICLES` | 1 | Min matches for a "hit" |
| `SG_REQUIRE_FRAMES` | 2 | Consecutive hit frames to trigger |
| `SG_AUTO_RESOLVE_FRAMES` | 5 | Clean frames to auto-cancel |

---

## 8. Diagnostics

| Symptom | Solution |
|---|---|
| Camera 🔴 dead | Check URL, network, reachability. For RTSP — camera on the same subnet |
| Plug OFFLINE | IP changed → Tuya Cloud (`ip: auto`) or `/plug test` |
| `409 Conflict` Telegram | Zombie process with the same token → restart, separate bot for SuperGuard |
| `404` from Telegram API | Wrong token in `sguard.env` |
| Live frame not updating | Check `SG_UPDATE_EVERY`, network to the camera |
| Config changes not applied | Bot not restarted (see warning at top) |

---

## 9. SuperGuard Desktop App (v1.0.0)

### What it does
Single `.exe` (25 MB) that:
- **Self-heals on startup** — checks Python, venv, pip packages, YOLO11n model, `sguard.env`, paths, repairs what's broken
- **Full config UI** — 7 tabs (General/Telegram/Cameras/Plugs/Paths/Advanced/About), atomic `.env` writes
- **Runs SuperGuard core** as subprocess with health monitoring (auto-restart, log tail)
- **System tray** — eye + lightning icon, menu: Show / Settings / Test alarm / Status / Exit
- **Fullscreen alarm window** — auto-expands on alarm, red pulse border, live frame (2 Hz), camera/zone/target/plugs, countdown, "Dismiss"
- **Desktop bridge** — polls `desktop_state/status.json` + `alarm_live.jpg` written by SuperGuard core

### Installation
```powershell
# Run as Administrator
irm https://raw.githubusercontent.com/PerfectFriend/AISuperGuard/main/install_desktop.ps1 | iex
```

Or download `SuperGuardDesktop-v1.0.0.exe` from [Releases](https://github.com/PerfectFriend/AISuperGuard/releases/tag/v1.0.0).

### Architecture
```
desktop/
├── main.py           # Orchestrator
├── self_heal.py      # Environment check & repair
├── config_ui.py      # tkinter 7-tab config
├── tray.py           # pystray system tray
├── monitor.py        # 1s poll: status/alarm/frame events
├── bridge.py         # Reads desktop_state/status.json + alarm_live.jpg
├── alarm_window.py   # Fullscreen alarm UI
├── icon.py           # PIL: eye + lightning → ICO
├── build.ps1         # PyInstaller build
└── tests/            # 19 tests total
```

### Build from source
```powershell
cd desktop
.\build.ps1
# Output: dist/SuperGuardDesktop.exe (25 MB)
```

---

## 10. Tests after setup

```bash
python superguard\tests\test_all.py              # 11 checks
python superguard\tests\test_live_update.py      # 7 checks live-frame protocol
python superguard\tests\test_plug_active_cam.py  # 8 checks active camera and /plug
```

Desktop app:
```bash
python desktop\tests\test_icon.py             # 4 checks
python desktop\tests\test_self_heal.py        # 5 checks
python desktop\tests\test_config_ui.py        # 5 checks
python desktop\tests\test_monitor.py          # 5 checks
```