# 🛡️ CableGuard — AI Anti Cable-Theft Surveillance

**Detección de ladrones de cable en tiempo real.** Persona en la zona protegida con
**casco + chaleco reflectante + pértiga aislante (comprobación de tensión)** → foto
a Telegram → foco + sirena por WiFi (ESP32). Todo local, sin nube.

> 🇪🇸 Robo de cable = dolor de cabeza enorme para empresas de telecom, electricidad y obra.
> CableGuard detecta al ladrón en la **fase de comprobación de tensión** (antes de que corte),
> da la alarma y le asusta con luz + sirena. Sin falsas alarmas de "persona paseando".

---

## 🎯 Qué detecta

| Señal | Cómo |
|---|---|
| **Pértiga aislante (УКН)** | Análisis de FORMA: línea fina y vertical, extremo superior dentro de la zona del cable. No depende del color (funciona de noche/IR) |
| **Casco** | Color de alta visibilidad (amarillo/naranja) en el 25% superior del cuerpo |
| **Chaleco reflectante** | Color de alta visibilidad en el torso (40-70% del cuerpo) |
| **Persona** | YOLO11 (COCO) con confirmación en N fotogramas (anti-falsas) |

## 🏗️ Arquitectura

```
[Cámaras IP (RTSP)] → [YOLO + detector de pértiga] → [confirmación] → [Telegram] + [ESP32: foco + sirena]
```

## 📦 Instalación (un script)

**Windows (PowerShell):**
```powershell
curl.exe -L https://raw.githubusercontent.com/DarkPushkin/cableguard/main/install.ps1 -o install.ps1
powershell -ExecutionPolicy Bypass -File install.ps1
```

**Linux/macOS:**
```bash
curl -sSL https://raw.githubusercontent.com/DarkPushkin/cableguard/main/install.sh | bash
```

Después de instalar:
```bash
python scripts/scan_cameras.py                        # encontrar la cámara en la red
# editar config.yaml: RTSP url + Telegram chat_id
python demo_prototype.py --source rtsp://user:pass@IP:554/stream1
```

## 📁 Estructura

```
cableguard/
├── demo_prototype.py        # prototipo completo (cámara → alerta → Telegram → ESP32)
├── electrician_detector.py  # detector de "ladrón-electricista" (pértiga + casco + chaleco)
├── actuator.py              # actuador WiFi: ESP32 / webhook / simulación
├── surveillance.py          # núcleo multi-cámara (RTSP → YOLO → zonas → alertas)
├── config.example.yaml      # plantilla de configuración
├── install.sh / install.ps1 # instaladores
├── scripts/
│   └── scan_cameras.py      # escáner de cámaras IP en la red
├── tools/
│   └── rtsp_preview.py      # vista previa del stream
└── docs/
    ├── CAMERA-SETUP.md      # esquema de conexión (RU)
    └── esp32_alarm.ino      # firmware ESP32 (foco + sirena)
```

## 🔌 Actuador ESP32 (foco + sirena)

Protege el cable con luz y sonido:

```
GPIO2 → relé 1 → FOCO (proyector)
GPIO4 → relé 2 → SIRENA
```

Firmware: `docs/esp32_alarm.ino` (Arduino IDE). Tras flashear, el sistema llama a
`http://<ip-esp32>/on` y `/off`. Modo simulación disponible sin hardware.

## 📲 Telegram

1. Crea bot con @BotFather → token
2. Pon el token en `%LOCALAPPDATA%\hermes\.env` → `TELEGRAM_BOT_TOKEN=...`
3. Chat ID: `python -c "import requests; r=requests.get('https://api.telegram.org/bot<TOKEN>/getUpdates'); print(r.json())"` — el `chat.id` de tu mensaje
4. Pon el chat_id en `config.yaml` → `alert.telegram_channel`

## 🧪 Modo demo (sin cámara)

```bash
python demo_prototype.py --source synth --direct
```

Genera un fotograma sintético de un "ladrón-electricista" (casco + chaleco + pértiga
hacia el cable) y ejecuta el ciclo completo: detección → Telegram → actuador simulado.

## 📄 Licencia

MIT — libre para usar, modificar y vender. El código es tuyo.
