# 🛠️ SuperGuard Alarm — Руководство администратора

Краткое руководство по настройке: добавление камер и розеток, привязка, диагностика.

> **Важно:** перед правкой конфигурации **остановите** бота, иначе он перезапишет
> файлы из памяти: `taskkill /F /IM python.exe` (или через автозапуск-скрипт).
> Порядок всегда такой: **стоп → правим → старт**.

---

## 1. Где что лежит

| Файл | Назначение |
|---|---|
| `sguard.env` | Основная конфигурация (токен, камеры, розетки, параметры) |
| `superguard\sguard_settings.json` | Настройки, изменяемые через бота (зона/цель/розетки по камерам) |
| `saved_frames\` | Кадры тревог |
| `superguard\tests\` | Тесты |

---

## 2. Добавление камеры

Камеры задаются в `sguard.env` через переменные `SG_CAM{N}_URL` и `SG_CAM{N}_NAME`.

### Шаг 1 — выберите номер камеры (2–32)
Камера 1 задаётся переменной `SG_CAM_URL` (HLS). Остальные — `SG_CAM2_URL` … `SG_CAM32_URL`.

### Шаг 2 — добавьте строки в `sguard.env`

```ini
# HLS-поток
SG_CAM5_URL=https://example.com/live/stream.m3u8
SG_CAM5_NAME=5: Пример HLS

# RTSP-камера (локальная PoE)
SG_CAM6_URL=rtsp://admin:password@192.168.1.50:554/cam/realmonitor?channel=1&subtype=0
SG_CAM6_NAME=6: Уличная камера

# JPG-снимок (периодически обновляется)
SG_CAM7_URL=https://example.com/camera/snapshot.jpg
SG_CAM7_NAME=7: Снимок
```

### Шаг 3 — перезапустите бота
Тип камеры определяется автоматически по URL:
- `.jpg` / `.jpeg` / `.png` / `snapshot` / `image` → JPG-камера (HTTP-снимок)
- `.m3u8` / `rtsp://` → потоковая камера (cv2.VideoCapture, авто-переподключение)

### Шаг 4 — проверьте
В Telegram: `/cam` — камера должна появиться в списке, `/cam 6` — сделать активной,
`/cam status` — статус (🟢 alive / 🔴 dead).

---

## 3. Добавление розетки Tuya (локальное управление)

Розетки Tuya управляются **локально** через библиотеку tinytuya (протокол 3.4, порт 6668).

### Шаг 1 — получите данные розетки
Данные берутся из приложения **Smart Life** или панели Tuya IoT:

| Поле | Что это | Где взять |
|---|---|---|
| `device_id` | ID устройства | Туя IoT Platform → устройство |
| `local_key` | Локальный ключ | Туя IoT Platform → устройство |
| `ip` | IP розетки в локальной сети | роутер / `nmap` / `ip auto` |
| `version` | Версия протокола (3.4 / 3.3 / 3.1) | Туя IoT Platform |
| `port` | Порт (обычно 6668) | стандарт |

### Шаг 2 — добавьте розетку в `SG_ACTUATORS`

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

- `"ip": "auto"` — IP будет найден автоматически через Tuya Cloud (см. раздел 4)
- `cameras` — начальная привязка: какие камеры управляют этой розеткой

### Шаг 3 — проверьте
В Telegram: `/plug` — розетка должна быть 🟢 ONLINE; `/plug test` — тест с авто-переподключением.

---

## 4. Tuya Cloud (автообнаружение IP розеток)

Если IP розетки меняется (DHCP), укажите ключи OpenAPI — синхронизация каждые 5 минут
найдёт розетку по `device_id` и обновит IP в конфиге и `.env`:

```ini
TUYA_ACCESS_ID=ваш_access_id
TUYA_ACCESS_SECRET=ваш_access_secret
TUYA_REGION=eu        # cn / us / eu / in
TUYA_SCHEMA=smartlife
```

Регион — тот, в котором зарегистрирован аккаунт Smart Life.

---

## 5. Привязка розеток к камере через Telegram

1. Переключитесь на камеру: `/cam N`
2. Привяжите розетки по номерам: `/plug 1 2` (будут управлять plug1 и plug2)
3. Проверка: `/plug` — покажет привязки активной камеры

При тревоге с этой камеры включаются **все** привязанные розетки, при снятии — выключаются.
Привязки сохраняются в `sguard_settings.json` и восстанавливаются при старте.

---

## 6. Добавление розетки другого типа (Sonoff, Shelly, ESPHome, Zigbee)

Архитектура актуаторов расширяемая: `BaseActuator` (интерфейс) + `ActuatorRegistry`
(реестр типов). Сейчас реализован тип `tuya`; остальные добавляются классом-наследником:

### Шаг 1 — создайте класс в `superguard/actuators/__init__.py`

```python
class SonoffActuator(BaseActuator):
    """Sonoff / Tasmota через HTTP API (http://<ip>/cm?cmnd=Power%20ON)."""
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

# Регистрация типа
actuator_registry.register("sonoff", SonoffActuator)
```

Аналогично для Shelly (`http://<ip>/relay/0?turn=on`), ESPHome (REST/API),
Zigbee (через zigbee2mqtt MQTT).

### Шаг 2 — укажите тип в `SG_ACTUATORS`

```ini
SG_ACTUATORS=[
  {"name": "plug3", "type": "sonoff", "cameras": [3],
   "ip": "192.168.1.60", "device_id": "", "local_key": "", "version": 3.4, "port": 6668}
]
```

`type` должно совпадать с именем, зарегистрированным в реестре (`register("sonoff", …)`).

### Шаг 3 — перезапустите и проверьте `/plug test`

---

## 7. Параметры детекции (тонкая настройка)

| Переменная | По умолчанию | Смысл |
|---|---|---|
| `SG_UPDATE_EVERY` | 2.0 | Интервал кадров камер / обновления live-кадра в Telegram |
| `SG_DETECT_EVERY` | 1.5 | Интервал цикла детекции |
| `SG_MIN_CONF` | 0.35 | Мин. уверенность YOLO |
| `SG_YELLOW_MIN_FRACTION` | 0.15 | Мин. доля пикселей цвета в боксе |
| `SG_MIN_YELLOW_VEHICLES` | 1 | Мин. совпадений для «хита» |
| `SG_REQUIRE_FRAMES` | 2 | Кадров подряд для тревоги |
| `SG_AUTO_RESOLVE_FRAMES` | 5 | Чистых кадров для автоснятия |

---

## 8. Диагностика

| Симптом | Решение |
|---|---|
| Камера 🔴 dead | Проверьте URL, сеть, доступность. Для RTSP — камера в той же подсети |
| Розетка OFFLINE | IP изменился → Tuya Cloud (`ip: auto`) или `/plug test` |
| `409 Conflict` Telegram | Зомби-процесс с тем же токеном → перезапуск, отдельный бот для SuperGuard |
| `404` от Telegram API | Неверный токен в `sguard.env` |
| Live-кадр не обновляется | Проверьте `SG_UPDATE_EVERY`, сеть до камеры |
| Изменения конфига не применились | Не перезапустили бота (см. предупреждение в начале) |

---

## 9. Тесты после настройки

```bash
python superguard\tests\test_all.py              # 11 проверок
python superguard\tests\test_live_update.py      # 7 проверок протокола live-кадра
python superguard\tests\test_plug_active_cam.py  # 8 проверок активной камеры и /plug
```
