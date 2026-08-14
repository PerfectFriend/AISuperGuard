# SuperGuard Alarm — Servicio Autónomo de Seguridad IA

**[English](README.md) | [Русский](README.ru.md) | [Español](README.es.md)**

**Videovigilancia IA → Detección de objetivo (YOLO11n + Color HSV + Zonas) → Enchufe Tuya ON → Telegram**

Servicio de seguridad autónomo para Windows. Despliegue en un comando en máquina limpia.

## Características

- 🎥 **Cámara RTSP/HLS** — Cualquier cámara streaming (test: Banjar ATCS Indonesia)
- 🤖 **Detección YOLO11n** — Coches, autobuses, camiones, personas (GPU: Radeon 780M / ROCm / DirectML)
- 🎨 **Filtro color HSV** — Objetivo en texto libre: `/target coche rojo`, `/target white truck`, `/target persona de pie`
- 📍 **Filtro zonal** — Cuadrícula N×M, celdas C01..C12: `/zone N3x4 C9`, `/zone off` (todo el frame)
- 🔌 **Tuya Smart Plug (local, tinytuya 3.4)** — Enchufe se activa al detectar
- 📱 **Bot Telegram (token separado)** — Menú comandos, foto disparo, live frame 2s, auto-apagado 5 frames limpios
- 🌍 **Multi-idioma** — RU/EN/ES via `/setlocal` (botones inline), menú sigue idioma elegido
- 💾 **Persistencia** — Ajustes en `sguard_settings.json` sobreviven reinicios
- 🛡 **Auto-protección zombis** — Al iniciar mata python.exe panic_mode viejos en mismo token
- 🪟 **Windows Service (NSSM)** — Auto-inicio, logs, reinicio en crash

## Comandos del bot (menú junto al clip)

| Comando | Descripción |
|---------|-------------|
| `/autoguard` | Activar/desactivar modo auto (enchufe OFF solo al irse objetivo) |
| `/togglealarm` | Alarma manual (enchufe ON, foto inmediata, sin YOLO) |
| `/zone` | Zona: `N3x4 C9`, `N9 C5`, `off`, `?` |
| `/target` | Objetivo: `coche rojo`, `white truck`, `persona de pie`, `?` |
| `/setlocal` | Idioma interfaz (RU/EN/ES) |

## Instalación rápida (Windows 10/11 limpio)

```powershell
# Como Administrador
irm https://raw.githubusercontent.com/DarkPushkin/superguard-alarm/main/install_superguard.ps1 | iex
```

O descargue y ejecute `install_superguard.ps1` con parámetros:
```powershell
.\install_superguard.ps1 -BotToken "123:ABC" -ChatId "143293811" -PlugIp "192.168.137.109" -PlugKey "abcdef123456..."
```

## Instalación manual

```powershell
# 1. Python 3.12
winget install Python.Python.3.12

# 2. Clonar
git clone https://github.com/DarkPushkin/superguard-alarm
cd superguard-alarm

# 3. Entorno virtual
python -m venv venv
venv\Scripts\pip install -r requirements.txt

# 4. Config
copy sguard.env.example sguard.env
# Edite sguard.env (token, chat_id, IP enchufe, local_key)

# 5. Ejecutar
venv\Scripts\python panic_mode.py
```

## Servicio Windows (auto-inicio)

```powershell
# Instale NSSM
# Cree servicio:
nssm install SuperGuardAlarm "C:\SuperGuard\venv\Scripts\python.exe" "C:\SuperGuard\panic_mode.py"
nssm set SuperGuardAlarm AppDirectory "C:\SuperGuard"
nssm set SuperGuardAlarm Start SERVICE_AUTO_START
Start-Service SuperGuardAlarm
```

## Requisitos

- Windows 10/11 (x64)
- Python 3.12
- GPU con soporte OpenCV (Radeon 780M / CUDA / DirectML) — **SIN fallback CPU**
- Bot Telegram (cree via @BotFather, **¡token SEPARADO!**)
- Tuya Smart Plug (flasheado local, tinytuya 3.4, puerto 6668)
- Cámara RTSP/HLS

## GPU en AMD Radeon 780M (Beelink SER9)

```bash
# Windows ROCm 7.2 — ÚNICO camino funcional
# WSL2 no funciona, DirectML — segfault
pip install torch torchvision --index-url https://download.pytorch.org/whl/rocm7.2
```

## Archivos de configuración

### `sguard.env` (¡NO COMITEAR!)
```
SG_TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
SG_CHAT_ID=143293811
SG_PLUG_IP=192.168.137.109
SG_PLUG_KEY=abcdef1234567890abcdef1234567890
```

### `sguard_settings.json` (auto-generado)
```json
{
  "zone": [3, 3, 5],
  "target": "white car",
  "lang": "es",
  "auto": true
}
```

## Arquitectura

```
panic_mode.py (archivo único, ~1000 líneas)
├── Telegram long-poll (async-safe, timeout 8s, aislamiento por update)
├── YOLO11n + ByteTrack (persist, conf=0.45, imgsz=640)
├── Filtro color HSV (11 colores, red=rango dual 0-10/170-180)
├── Cuadrícula zonas (N×M, overlay naranja en frame)
├── Tuya local (tinytuya 3.4, conexión fresca por comando)
├── Máquina estados alarma (AUTO/MANUAL, 5-frames auto-resolve)
├── i18n (RU/EN/ES, 48 claves, tr() en todo)
├── Auto-mata-zombis (PowerShell, psutil PID)
└── Persistencia (JSON, load_settings() PRIMERO en __main__)
```

## Mensajes del bot

**Alarma (msg A)** — frame disparo, bbox, **SIN botones**, queda para siempre (auditoría)  
**Live (msg B)** — frame vivo 2s, actualiza, **se borra al desactivar**  
**Auto-resolve (5 frames limpios)** — enchufe OFF + un mensaje:
```
✅ Amenaza eliminada: objetivo salió de zona búsqueda
🚨 Alarma desactivada.
📌 Modo actual: AUTO, zona=N3x3 C05, objetivo=white car
```

## Licencia

MIT — use, modifique, despliegue.

---

**Master Inquisitor (@RarioArmageddon) · The Grimoire · DarkPushkin/the-grimoire**