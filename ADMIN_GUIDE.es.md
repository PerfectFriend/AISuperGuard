# 🛠️ SuperGuard Alarm — Guía de administrador

Configuración rápida: añadir cámaras y enchufes, vinculaciones, diagnóstico.

> **Importante:** **detenga** el bot antes de editar la configuración, de lo
> contrario la sobrescribirá desde memoria: `taskkill /F /IM python.exe`
> (o mediante el script de autoinicio). Siempre: **detener → editar → iniciar**.

---

## 1. Dónde está todo

| Archivo | Propósito |
|---|---|
| `sguard.env` | Configuración principal (token, cámaras, enchufes, parámetros) |
| `superguard\sguard_settings.json` | Ajustes cambiados por el bot (zona/objetivo/enchufes por cámara) |
| `saved_frames\` | Fotogramas de alarma |
| `superguard\tests\` | Pruebas |

---

## 2. Añadir una cámara

Las cámaras se definen en `sguard.env` mediante `SG_CAM{N}_URL` y `SG_CAM{N}_NAME`.

### Paso 1 — elija un número de cámara (2–32)
La cámara 1 se define con `SG_CAM_URL` (HLS). El resto: `SG_CAM2_URL` … `SG_CAM32_URL`.

### Paso 2 — añada líneas a `sguard.env`

```ini
# Flujo HLS
SG_CAM5_URL=https://example.com/live/stream.m3u8
SG_CAM5_NAME=5: Ejemplo HLS

# Cámara RTSP (PoE local)
SG_CAM6_URL=rtsp://admin:password@192.168.1.50:554/cam/realmonitor?channel=1&subtype=0
SG_CAM6_NAME=6: Cámara exterior

# Captura JPG (se actualiza periódicamente)
SG_CAM7_URL=https://example.com/camera/snapshot.jpg
SG_CAM7_NAME=7: Captura
```

### Paso 3 — reinicie el bot
El tipo de cámara se elige automáticamente por URL:
- `.jpg` / `.jpeg` / `.png` / `snapshot` / `image` → cámara JPG (captura HTTP)
- `.m3u8` / `rtsp://` → cámara de flujo (cv2.VideoCapture, reconexión automática)

### Paso 4 — verifique
En Telegram: `/cam` — la cámara debe aparecer en la lista; `/cam 6` — hacerla activa;
`/cam status` — estado (🟢 alive / 🔴 dead).

---

## 3. Añadir un enchufe Tuya (control local)

Los enchufes Tuya se controlan **localmente** mediante la biblioteca tinytuya (protocolo 3.4, puerto 6668).

### Paso 1 — obtenga los datos del enchufe
Los datos vienen de la app **Smart Life** o de la plataforma Tuya IoT:

| Campo | Qué es | Dónde obtenerlo |
|---|---|---|
| `device_id` | ID del dispositivo | Plataforma Tuya IoT → dispositivo |
| `local_key` | Clave local | Plataforma Tuya IoT → dispositivo |
| `ip` | IP del enchufe en la LAN | router / `nmap` / `ip auto` |
| `version` | Versión del protocolo (3.4 / 3.3 / 3.1) | Plataforma Tuya IoT |
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

- `"ip": "auto"` — la IP se descubre automáticamente vía Tuya Cloud (sección 4)
- `cameras` — vinculación inicial: qué cámaras controlan este enchufe

### Paso 3 — verifique
En Telegram: `/plug` — el enchufe debe estar 🟢 ONLINE; `/plug test` — prueba con reconexión automática.

---

## 4. Tuya Cloud (auto-descubrimiento de IP de enchufes)

Si la IP de un enchufe cambia (DHCP), proporcione las claves OpenAPI — la sincronización
cada 5 minutos encuentra el enchufe por `device_id` y actualiza la IP en la configuración y `.env`:

```ini
TUYA_ACCESS_ID=su_access_id
TUYA_ACCESS_SECRET=su_access_secret
TUYA_REGION=eu        # cn / us / eu / in
TUYA_SCHEMA=smartlife
```

Región — donde está registrada su cuenta Smart Life.

---

## 5. Vincular enchufes a una cámara vía Telegram

1. Cambie a la cámara: `/cam N`
2. Vincule enchufes por número: `/plug 1 2` (controlarán plug1 y plug2)
3. Compruebe: `/plug` — muestra las vinculaciones de la cámara activa

En alarma de esa cámara se encienden **todos** los enchufes vinculados; al resolverse, se apagan.
Las vinculaciones se guardan en `sguard_settings.json` y se restauran al iniciar.

---

## 6. Añadir otro tipo de enchufe (Sonoff, Shelly, ESPHome, Zigbee)

La arquitectura de actuadores es extensible: `BaseActuator` (interfaz) + `ActuatorRegistry`
(registro de tipos). El tipo `tuya` está implementado; los demás se añaden como subclase:

### Paso 1 — cree una clase en `superguard/actuators/__init__.py`

```python
class SonoffActuator(BaseActuator):
    """Sonoff / Tasmota vía API HTTP (http://<ip>/cm?cmnd=Power%20ON)."""
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

# Registrar el tipo
actuator_registry.register("sonoff", SonoffActuator)
```

Igualmente para Shelly (`http://<ip>/relay/0?turn=on`), ESPHome (REST/API),
Zigbee (vía zigbee2mqtt MQTT).

### Paso 2 — indique el tipo en `SG_ACTUATORS`

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

| Variable | Por defecto | Significado |
|---|---|---|
| `SG_UPDATE_EVERY` | 2.0 | Intervalo de fotogramas de cámara / periodo de actualización del fotograma en vivo |
| `SG_DETECT_EVERY` | 1.5 | Intervalo del bucle de detección |
| `SG_MIN_CONF` | 0.35 | Confianza mínima YOLO |
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
| `409 Conflict` Telegram | Proceso zombi con el mismo token → reiniciar, bot separado para SuperGuard |
| `404` de la API Telegram | Token incorrecto en `sguard.env` |
| El fotograma en vivo no se actualiza | Compruebe `SG_UPDATE_EVERY`, red hacia la cámara |
| Cambios de configuración no aplicados | Bot no reiniciado (ver advertencia al inicio) |

---

## 9. Pruebas tras la configuración

```bash
python superguard\tests\test_all.py              # 11 comprobaciones
python superguard\tests\test_live_update.py      # 7 comprobaciones protocolo fotograma en vivo
python superguard\tests\test_plug_active_cam.py  # 8 comprobaciones cámara activa y /plug
```
