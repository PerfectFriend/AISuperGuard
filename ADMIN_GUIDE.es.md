# 🛠️ SuperGuard Alarm — Guía de administrador

Configuración rápida: añadir cámaras y enchufes, vinculaciones, diagnóstico.

> **Importante:** **pare** el bot antes de editar el config, de lo contrario sobrescribirá
> los archivos desde la memoria: `taskkill /F /IM python.exe` (o vía script de autostart).
> Siempre: **stop → edit → start**.

---

## 1. Dónde está todo

| Archivo | Propósito |
|---|---|
| `sguard.env` | Config principal (token, cámaras, enchufes, parámetros) |
| `superguard\sguard_settings.json` | Ajustes cambiados por el bot (zona/objetivo/enchufes por cámara) |
| `saved_frames\` | Fotogramas de alarma |
| `desktop_state\` | Desktop bridge (status.json + alarm_live.jpg, creado en runtime) |
| `superguard\tests\` | Tests |

---

## 2. Añadir una cámara

Las cámaras se definen en `sguard.env` vía `SG_CAM{N}_URL` y `SG_CAM{N}_NAME`.

### Paso 1 — elija un número de cámara (2–32)
La cámara 1 la define `SG_CAM_URL` (HLS). El resto: `SG_CAM2_URL` … `SG_CAM32_URL`.

### Paso 2 — añada líneas a `sguard.env`

```ini
# Flujo HLS
SG_CAM5_URL=https://example.com/live/stream.m3u8
SG_CAM5_NAME=5: Example HLS

# Cámara RTSP (PoE local)
SG_CAM6_URL=rtsp://admin:password@192.168.1.50:554/cam/realmonitor?channel=1&subtype=0
SG_CAM6_NAME=6: Outdoor camera

# Captura JPG (actualizada periódicamente)
SG_CAM7_URL=https://example.com/camera/snapshot.jpg
SG_CAM7_NAME=7: Snapshot
```

### Paso 3 — reinicie el bot
El tipo de cámara se elige automáticamente por URL:
- `.jpg` / `.jpeg` / `.png` / `snapshot` / `image` → cámara JPG (snapshot HTTP)
- `.m3u8` / `rtsp://` → cámara de flujo (cv2.VideoCapture, auto-reconexión)

### Paso 4 — verifique
En Telegram: `/cam` — la cámara debe aparecer en la lista; `/cam 6` — hacerla activa;
`/cam status` — estado (🟢 alive / 🔴 dead).

---

## 3. Añadir un enchufe Tuya (control local)

Los enchufes Tuya se controlan **localmente** vía la librería tinytuya (protocolo 3.4, puerto 6668).

### Paso 1 — obtenga los datos del enchufe
Los datos vienen de la app **Smart Life** o la plataforma Tuya IoT:

| Campo | Qué es | Dónde conseguir |
|---|---|---|
| `device_id` | ID del dispositivo | Tuya IoT Platform → device |
| `local_key` | Clave local | Tuya IoT Platform → device |
| `ip` | IP del enchufe en la LAN | router / `nmap` / `ip auto` |
| `version` | Versión del protocolo (3.4 / 3.3 / 3.1) | Tuya IoT Platform |
| `port` | Puerto (normalmente 6668) | estándar |

### Paso 2 — añada el enchufe a `SG_ACTUATORS`

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

- `"ip": "auto"` — la IP se descubre automáticamente vía Tuya Cloud (ver sección 4)
- `cameras` — vinculación inicial: qué cámaras mueven este enchufe

### Paso 3 — verifique
En Telegram: `/plug` — el enchufe debe ser 🟢 ONLINE; `/plug test` — test con auto-reconexión.

---

## 4. Tuya Cloud (auto-descubrimiento de IP de enchufes)

Si la IP del enchufe cambia (DHCP), proporcione claves OpenAPI — la sincronización cada 5 minutos
encontrará el enchufe por `device_id` y actualizará la IP en el config y `.env`:

```ini
TUYA_ACCESS_ID=your_access_id
TUYA_ACCESS_SECRET=your_access_secret
TUYA_REGION=eu        # cn / us / eu / in
TUYA_SCHEMA=smartlife
```

Region — donde está registrada la cuenta Smart Life.

---

## 5. Vincular enchufes a una cámara vía Telegram

1. Cambie a la cámara: `/cam N`
2. Vincule enchufes por número: `/plug 1 2` (moverán plug1 y plug2)
3. Compruebe: `/plug` — muestra las vinculaciones de la cámara activa

En alarma de esa cámara, **todos** los enchufes vinculados se encienden; al resolverse, se apagan.
Las vinculaciones persisten en `sguard_settings.json` y se restauran al iniciar.

---

## 6. Añadir otro tipo de enchufe (Sonoff, Shelly, ESPHome, Zigbee)

La arquitectura de actuadores es extensible: `BaseActuator` (interfaz) + `ActuatorRegistry`
(registro de tipos). Tipo `tuya` implementado; los demás se añaden como subclase:

### Paso 1 — cree una clase en `superguard/actuators/__init__.py`

```python
class SonoffActuator(BaseActuator):
    """Sonoff / Tasmota vía HTTP API (http://<ip>/cm?cmnd=Power%20ON)."""
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

# Registro del tipo
actuator_registry.register("sonoff", SonoffActuator)
```

Igual para Shelly (`http://<ip>/relay/0?turn=on`), ESPHome (REST/API),
Zigbee (vía zigbee2mqtt MQTT).

### Paso 2 — establezca el tipo en `SG_ACTUATORS`

```ini
SG_ACTUATORS=[
  {"name": "plug3", "type": "sonoff", "cameras": [3],
   "ip": "192.168.1.60", "device_id": "", "local_key": "", "version": 3.4, "port": 6668}
]
```

`type` debe coincidir con el nombre registrado en el registro (`register("sonoff", …)`).

### Paso 3 — reinicie y compruebe con `/plug test`

---

## 7. Parámetros de detección (ajuste fino)

| Variable | Default | Significado |
|---|---|---|
| `SG_UPDATE_EVERY` | 2.0 | Intervalo de fotogramas cámara / periodo live-frame en Telegram |
| `SG_DETECT_EVERY` | 1.5 | Intervalo del bucle de detección |
| `SG_MIN_CONF` | 0.35 | Min. confianza YOLO |
| `SG_YELLOW_MIN_FRACTION` | 0.15 | Fracción mínima de píxeles de color en la caja |
| `SG_MIN_YELLOW_VEHICLES` | 1 | Coincidencias mínimas para un «hit» |
| `SG_REQUIRE_FRAMES` | 2 | Fotogramas seguidos para disparar |
| `SG_AUTO_RESOLVE_FRAMES` | 5 | Fotogramas limpios para auto-cancelar |

---

## 8. Diagnóstico

| Síntoma | Solución |
|---|---|
| Cámara 🔴 dead | Compruebe URL, red, accesibilidad. Para RTSP — cámara en la misma subred |
| Enchufe OFFLINE | IP cambiada → Tuya Cloud (`ip: auto`) o `/plug test` |
| `409 Conflict` Telegram | Proceso zombi con mismo token → reinicio, bot separado para SuperGuard |
| `404` de Telegram API | Token incorrecto en `sguard.env` |
| Live-frame no se actualiza | Compruebe `SG_UPDATE_EVERY`, red a la cámara |
| Cambios de config no aplican | Bot no reiniciado (ver aviso arriba) |

---

## 9. SuperGuard Desktop App (v1.0.0)

### Qué hace
Un solo `.exe` (25 MB) que:
- **Auto-reparación al inicio** — comprueba Python, venv, paquetes pip, modelo YOLO11n, `sguard.env`, rutas, repara lo roto
- **UI completa de config** — 7 pestañas (General/Telegram/Cameras/Plugs/Paths/Advanced/About), escritura atómica `.env`
- **Ejecuta SuperGuard core** como subproceso con health-monitoring (auto-reinicio, tail de logs)
- **System tray** — icono ojo+rayo, menú: Show / Settings / Test alarm / Status / Exit
- **Ventana fullscreen de alarma** — auto-expande en alarma, borde rojo pulsante, live-frame (2 Hz), cámara/zona/objetivo/enchufes, cuenta atrás, "Dismiss"
- **Desktop bridge** — sondea `desktop_state/status.json` + `alarm_live.jpg` escritos por SuperGuard core

### Instalación
```powershell
# Run as Administrator
irm https://raw.githubusercontent.com/PerfectFriend/AISuperGuard/main/install_desktop.ps1 | iex
```

O descargue `SuperGuardDesktop-v1.0.0.exe` desde [Releases](https://github.com/PerfectFriend/AISuperGuard/releases/tag/v1.0.0).

### Arquitectura
```
desktop/
├── main.py           # Orquestador
├── self_heal.py      # Comprobación y reparación del entorno
├── config_ui.py      # tkinter 7-tab config
├── tray.py           # pystray system tray
├── monitor.py        # 1s poll: eventos status/alarm/frame
├── bridge.py         # Lee desktop_state/status.json + alarm_live.jpg
├── alarm_window.py   # Fullscreen UI alarma
├── icon.py           # PIL: ojo + rayo → ICO
├── build.ps1         # PyInstaller build
└── tests/            # 19 tests total
```

### Compilar desde fuentes
```powershell
cd desktop
.\build.ps1
# Output: dist/SuperGuardDesktop.exe (25 MB)
```

---

## 10. Tests tras la configuración

```bash
python superguard\tests\test_all.py              # 11 comprobaciones
python superguard\tests\test_live_update.py      # 7 comprobaciones live-frame protocolo
python superguard\tests\test_plug_active_cam.py  # 8 comprobaciones cámara activa y /plug
```

Desktop app:
```bash
python desktop\tests\test_icon.py             # 4 comprobaciones
python desktop\tests\test_self_heal.py        # 5 comprobaciones
python desktop\tests\test_config_ui.py        # 5 comprobaciones
python desktop\tests\test_monitor.py          # 5 comprobaciones
```