<div align="center">

![SuperGuard Banner — cyberpunk × Van Gogh × Gaudí](assets/banner-header.png)

# 🛡️ SuperGuard Alarm

Vigilancia por vídeo con IA y respuesta mediante enchufes inteligentes, controlada desde Telegram.

**Detección YOLO → filtro de color HSV → filtro de zona → enchufe Tuya ON → alarma en Telegram**

[English](README.md) · [Русский](README.ru.md) · [Español](README.es.md) · [Guía de administrador](ADMIN_GUIDE.es.md) · [Desktop App](desktop/)

</div>

---

## ✨ Características

- **8+ cámaras** — flujos HLS, RTSP (cámaras PoE locales), capturas JPG por HTTP — monitorización simultánea
- **Detección IA** — YOLO11n (Ultralytics) con seguimiento; filtro por clase (coche, persona, autobús, camión…) y color (rojo, amarillo, azul… vía HSV)
- **Filtro de zona** — limitar la detección a una celda de la cuadrícula: `N3x4 C9` = cuadrícula 3×4, celda 9
- **Cámara activa** — los comandos (`/zone`, `/target`, `/plug`) siempre trabajan con la cámara activa. Una cámara se vuelve activa al disparar una alarma o vía `/cam`, y permanece activa hasta que otra la reemplace
- **Enchufes inteligentes** — Tuya, control local (tinytuya); se pueden vincular varios enchufes a una cámara: `/plug 1 2 3`
- **Protocolo de alarma** — fotograma de disparo (auditoría, nunca se borra) + fotograma en vivo **actualizado cada 2 s** desde la cámara de la alarma hasta la resolución
- **Auto-resolución** — en modo automático la alarma se cancela sola cuando el objetivo sale de la zona; en modo manual espera `/togglealarm`
- **Disparo manual** — `/togglealarm` para pruebas del administrador; duplica el comportamiento de la alarma automática (respeta modo auto/manual)
- **Bot de Telegram** — control total por comandos, botones inline, 3 idiomas (EN/ES/RU)
- **Resiliencia** — reconexión automática de cámaras y enchufes (`/plug test`), eliminador de procesos zombi, almacenamiento atómico, auto-descubrimiento de IP de enchufes vía Tuya Cloud
- **Vista en navegador** — servidor MJPEG integrado (`http://localhost:8081`)
- **26 comprobaciones automáticas** — sintaxis, configuración, modelos, cámaras, actuadores, protocolo de alarma, actualización del fotograma en vivo

---

## 🖥️ SuperGuard Desktop App (v1.0.0)

**Launcher y monitor autónomo para Windows** — un solo `.exe` (25 MB) que:

1. **Auto-reparación al inicio** — comprueba Python, venv, paquetes pip (numpy, opencv, ultralytics, torch, tinytuya, requests, psutil, pycryptodome, pyaes), modelo YOLO11n, `sguard.env`, rutas, repara lo que está roto
2. **UI completa de configuración** — 7 pestañas: General, Telegram, Cameras, Plugs, Paths, Advanced, About (tkinter, escritura atómica `.env`)
3. **Ejecuta SuperGuard core** como subproceso con health-monitoring (reinicio en crash, tail de logs)
4. **System tray icon** — ojo + rayo (cyberpunk × Van Gogh × Gaudí), menú: Show / Settings / Test alarm / Status / Exit
5. **Auto-expande a fullscreen en alarma** — borde rojo pulsante, live-frame (2 Hz), cámara/zona/objetivo/enchufes, cuenta atrás, botón "Dismiss"
6. **Desktop bridge** — sondea `desktop_state/status.json` + `alarm_live.jpg` escritos por SuperGuard core (sin sockets, cero deps)

### Instalación (un comando, Run as Administrator)

```powershell
irm https://raw.githubusercontent.com/PerfectFriend/AISuperGuard/main/install_desktop.ps1 | iex
```

O descargue desde [Releases](https://github.com/PerfectFriend/AISuperGuard/releases/tag/v1.0.0): `SuperGuardDesktop-v1.0.0.exe`

### Arquitectura Desktop

```
C:\SuperGuard\
├── sguard.env                    # Toda la configuración (token, cámaras, enchufes)
├── sguard_settings.json          # Ajustes runtime (zona/objetivo/enchufes por cámara)
├── saved_frames\                 # Archivo de fotogramas de alarma
├── desktop_state\                # Bridge: status.json + alarm_live.jpg (creado en runtime)
├── mjpeg_stream_server.py        # Vista en navegador (puerto 8081)
├── requirements.txt
├── superguard\                   # Core package (modular)
│   ├── main.py                   # Punto de entrada, SuperGuardApplication
│   ├── config.py                 # Carga y validación de config
│   ├── models\                   # Zone, Target, CameraSettings, Alarm (state machine)
│   ├── detectors\                # Pipeline: YOLO + HSV color + zone
│   ├── cameras\                  # Cámaras JPG/HLS/RTSP, CameraManager
│   ├── actuators\                # Abstracción enchufes (Tuya…), registro, ActuatorManager
│   ├── telegram\                 # Cliente Telegram, router comandos, bot
│   ├── storage\                  # JSON atómico, EnvWriter
│   ├── tuya_cloud\               # Tuya Cloud sync (auto-descubrimiento IP enchufes)
│   └── tests\                    # test_all.py, test_live_update.py, test_plug_active_cam.py
├── desktop\                      # Fuente Desktop app
│   ├── main.py                   # Orquestador: self-heal → config → tray → monitor → SuperGuard
│   ├── self_heal.py              # Comprobación y reparación del entorno
│   ├── config_ui.py              # tkinter 7-tab configuración
│   ├── tray.py                   # pystray system tray
│   ├── monitor.py                # 1s poll: on_status, on_alarm_on, on_alarm_off, on_new_frame
│   ├── bridge.py                 # Lee desktop_state/status.json + alarm_live.jpg
│   ├── alarm_window.py           # Fullscreen alarma: borde rojo, live-frame, cuenta atrás, Dismiss
│   ├── icon.py                   # PIL generador: ojo + rayo → 256² PNG + multi-res ICO
│   ├── build.ps1                 # PyInstaller build script
│   ├── install_desktop.ps1       # One-command installer
│   └── tests\                    # test_icon.py, test_self_heal.py, test_config_ui.py, test_monitor.py
└── install_desktop.ps1           # Root installer (copia de desktop/)
```

---

## 🏗️ Arquitectura

```
C:\SuperGuard\
├── sguard.env                    # Toda la configuración (token, cámaras, enchufes)
├── sguard_settings.json          # Ajustes runtime (zona/objetivo/enchufes por cámara)
├── saved_frames\                 # Archivo de fotogramas de alarma
├── mjpeg_stream_server.py        # Vista en navegador (puerto 8081)
├── requirements.txt
└── superguard\
    ├── main.py                   # Punto de entrada, SuperGuardApplication
    ├── config.py                 # Carga y validación de config
    ├── models\                   # Zone, Target, CameraSettings, Alarm (state machine)
    ├── detectors\                # Pipeline: YOLO + HSV color + zone
    ├── cameras\                  # Cámaras JPG/HLS/RTSP, CameraManager
    ├── actuators\                # Abstracción enchufes (Tuya…), registro, ActuatorManager
    ├── telegram\                 # Cliente Telegram, router comandos, bot
    ├── storage\                  # JSON atómico, EnvWriter
    ├── tuya_cloud\               # Tuya Cloud sync (auto-descubrimiento IP enchufes)
    └── tests\                    # test_all.py, test_live_update.py, test_plug_active_cam.py
```

### Pipeline de detección

```
Cámara (JPG/HLS/RTSP) → fotograma → YOLO11n → filtro de zona → filtro de clase → color HSV
   ↓ objetivo encontrado N fotogramas seguidos (require_frames)
ALARMA: enchufe(s) ON → Telegram: fotograma de disparo (msg A)
   → 1 s después: fotograma en vivo (msg B), actualizado cada update_every s
   ↓ objetivo se fue (auto_resolve_frames fotogramas limpios + modo auto)
enchufe(s) OFF → notificación «Amenaza resuelta»
```

### Máquina de estados de alarma

```
INACTIVE ──(objetivo N fotogramas)──▶ ACTIVE ──(modo auto + N limpios)──▶ AUTO_RESOLVING
   ▲                                      │                                   │
   │                                      │◀──(objetivo reaparece)────────────┘
   └────(/togglealarm o botón)────────────┘
```

---

## 🚀 Inicio rápido

```bash
git clone <repo-url> superguard
cd superguard
pip install -r requirements.txt

# 1. Crea un bot con @BotFather, pon el token en sguard.env
# 2. Configura cámaras y enchufes en sguard.env (ver Guía de administrador)
python superguard\main.py
```

---

## ⚙️ Configuración (`sguard.env`)

| Variable | Propósito |
|---|---|
| `SG_TELEGRAM_BOT_TOKEN` | Token del bot (**bot separado**, no el bot gateway) |
| `SG_CHAT_ID` | ID del chat de Telegram para alarmas |
| `SG_PLUG_KEY` | Clave local Tuya (enchufe por defecto, compatibilidad) |
| `SG_CAM_URL` | URL de la cámara 1 (HLS) |
| `SG_CAM2_URL` … `SG_CAM32_URL` | Cámaras 2–32 (añadir/sobrescribir sin tocar código) |
| `SG_CAM{N}_NAME` | Nombre visible de la cámara N |
| `SG_UPDATE_EVERY` | Intervalo de refresco de fotogramas (s) — periodo del fotograma en vivo |
| `SG_DETECT_EVERY` | Intervalo del bucle de detección (s) |
| `SG_MIN_CONF` | Umbral de confianza YOLO |
| `SG_YELLOW_MIN_FRACTION` | Fracción mínima de píxeles de color en la caja |
| `SG_MIN_YELLOW_VEHICLES` | Coincidencias mínimas para un «hit» |
| `SG_REQUIRE_FRAMES` | Fotogramas seguidos para disparar la alarma |
| `SG_AUTO_RESOLVE_FRAMES` | Fotogramas limpios para auto-cancelar |
| `SG_ACTUATORS` | Array JSON de enchufes (`name`, `type`, `cameras`, `ip`, `device_id`, `local_key`, `version`, `port`) |
| `TUYA_ACCESS_ID` / `TUYA_ACCESS_SECRET` | Claves Tuya Cloud OpenAPI (auto-descubrimiento de IP) |

El tipo de cámara se elige automáticamente por URL: `.jpg/.jpeg/.png` → cámara JPG; `.m3u8`/`rtsp://` → cámara de flujo.

---

## 🤖 Comandos de Telegram

| Comando | Acción |
|---|---|
| `/autoguard` | Alternar modo automático |
| `/togglealarm` | Alarma manual on/off (disparo de prueba del administrador) |
| `/zone` | `/zone N3x4 C9` definir zona, `/zone off` todo el cuadro, `/zone ?` ayuda |
| `/target` | `/target red car` definir objetivo, `/target ?` ayuda |
| `/plug` | Mostrar enchufes de la cámara activa |
| `/plug 1 2 3` | Vincular enchufes plug1..plug3 a la **cámara activa** |
| `/plug test` | Probar enchufes, reconectar fallidos |
| `/setlocal` | Idioma EN/ES/RU (botones inline) |
| `/cam` | Lista/estado de cámaras, cambiar cámara activa (`/cam 3`) |

### Formato de zona

- `N{rows}x{cols} C{cell}` — cuadrícula rows×cols, número de celda (1 = arriba-izquierda)
  `/zone N3x4 C9` → cuadrícula 3×4, celda 9
- `N{total} C{cell}` — cuadrícula cuadrada: `/zone N9 C5` = 3×3, celda 5
- `off` / `всё` / `0` / `todo` / `nada` — todo el cuadro

### Formato de objetivo

`/target <texto>` — palabras de clase + palabras de color:
- Clases: `person`, `car`, `bus`, `truck`, `bicycle`, `motorcycle`…
- Colores: `red`, `blue`, `yellow`, `green`, `black`, `white`…
- Ejemplo: `/target red car`

---

## 🔌 Vinculación de enchufes

- Los enchufes se definen en `SG_ACTUATORS` (tipo `tuya`, protocolo 3.4, puerto 6668)
- Vincular a una cámara: cámbiala (`/cam N`), luego `/plug 1 2` (números → `plug1`, `plug2`)
- En alarma de esa cámara se encienden **todos los enchufes vinculados**; al resolverse, se apagan
- Las vinculaciones se guardan en `sguard_settings.json` y se restauran al iniciar
- `"ip": "auto"` + claves Tuya Cloud → IP del enchufe descubierta automáticamente (cada 5 min)

---

## 🖥️ Vista en navegador

```bash
python mjpeg_stream_server.py
```

- `http://localhost:8081/` — flujo MJPEG
- `http://localhost:8081/snapshot.jpg` — fotograma único

---

## 🧪 Pruebas

```bash
python superguard\tests\test_all.py           # 11 comprobaciones: sintaxis, config, modelos, cámaras, actuadores, app
python superguard\tests\test_live_update.py   # 7 comprobaciones: protocolo de fotograma en vivo
python superguard\tests\test_plug_active_cam.py  # 8 comprobaciones: cámara activa, /plug, vinculaciones
```

Desktop app tests:
```bash
python desktop\tests\test_icon.py             # 4 comprobaciones
python desktop\tests\test_self_heal.py        # 5 comprobaciones
python desktop\tests\test_config_ui.py        # 5 comprobaciones
python desktop\tests\test_monitor.py          # 5 comprobaciones
```

---

## 🛠️ Guía de administrador

Configuración completa — añadir cámaras, añadir enchufes de todos los tipos soportados — en [ADMIN_GUIDE.es.md](ADMIN_GUIDE.es.md) (también [EN](ADMIN_GUIDE.en.md), [RU](ADMIN_GUIDE.ru.md)).

---

## 📄 Licencia

MIT

---

**Master Inquisitor (@RarioArmageddon) · The Grimoire · DarkPushkin/the-grimoire**

---

<div align="center">

![SuperGuard Footer — cyberpunk × Van Gogh × Gaudí](assets/banner-footer.png)

**Protect your infrastructure. 24/7. Local. Intelligent.**

</div>