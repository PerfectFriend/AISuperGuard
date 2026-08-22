# 🛠️ SuperGuard Alarm — Руководство администратора

Быстрая настройка: добавление камер и розеток, привязки, диагностика.

> **Важно:** **остановите** бота перед редактированием конфига, иначе он перезапишет
> файлы из памяти: `taskkill /F /IM python.exe` (или через autostart-скрипт).
> Всегда: **стоп → правка → старт**.

---

## 1. Где что лежит

| Файл | Назначение |
|---|---|
| `sguard.env` | Главный конфиг (токен, камеры, розетки, параметры) |
| `superguard\sguard_settings.json` | Настройки, меняемые ботом (зона/цель/розетки по камерам) |
| `saved_frames\` | Кадры тревог |
| `desktop_state\` | Desktop bridge (status.json + alarm_live.jpg, создаётся при запуске) |
| `superguard\tests\` | Тесты |

---

## 2. Добавление камеры

Камеры задаются в `sguard.env` через `SG_CAM{N}_URL` и `SG_CAM{N}_NAME`.

### Шаг 1 — выберите номер камеры (2–32)
Камера 1 задаётся через `SG_CAM_URL` (HLS). Остальные: `SG_CAM2_URL` … `SG_CAM32_URL`.

### Шаг 2 — добавьте строки в `sguard.env`

```ini
# HLS-поток
SG_CAM5_URL=https://example.com/live/stream.m3u8
SG_CAM5_NAME=5: Example HLS

# RTSP-камера (локальная PoE)
SG_CAM6_URL=rtsp://admin:password@192.168.1.50:554/cam/realmonitor?channel=1&subtype=0
SG_CAM6_NAME=6: Outdoor camera

# JPG-снимок (периодически обновляется)
SG_CAM7_URL=https://example.com/camera/snapshot.jpg
SG_CAM7_NAME=7: Snapshot
```

### Шаг 3 — перезапустите бота
Тип камеры определяется автоматически по URL:
- `.jpg` / `.jpeg` / `.png` / `snapshot` / `image` → JPG-камера (HTTP-снимок)
- `.m3u8` / `rtsp://` → потоковая камера (cv2.VideoCapture, авто-переподключение)

### Шаг 4 — проверка
В Telegram: `/cam` — камера должна появиться в списке; `/cam 6` — сделать её активной;
`/cam status` — статус (🟢 alive / 🔴 dead).

---

## 3. Добавление розетки Tuya (локальный контроль)

Розетки Tuya управляются **локально** через библиотеку tinytuya (протокол 3.4, порт 6668).

### Шаг 1 — получите данные розетки
Данные берутся из приложения **Smart Life** или платформы Tuya IoT:

| Поле | Что это | Где взять |
|---|---|---|
| `device_id` | ID устройства | Tuya IoT Platform → device |
| `local_key` | Локальный ключ | Tuya IoT Platform → device |
| `ip` | IP розетки в локальной сети | роутер / `nmap` / `ip auto` |
| `version` | Версия протокола (3.4 / 3.3 / 3.1) | Tuya IoT Platform |
| `port` | Порт (обычно 6668) | стандартный |

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

- `"ip": "auto"` — IP обнаруживается автоматически через Tuya Cloud (см. раздел 4)
- `cameras` — начальная привязка: какие камеры управляют этой розеткой

### Шаг 3 — проверка
В Telegram: `/plug` — розетка должна быть 🟢 ONLINE; `/plug test` — тест с авто-переподключением.

---

## 4. Tuya Cloud (авто-обнаружение IP розеток)

Если IP розетки меняется (DHCP), укажите OpenAPI-ключи — синхронизация каждые 5 минут
найдёт розетку по `device_id` и обновит IP в конфиге и `.env`:

```ini
TUYA_ACCESS_ID=your_access_id
TUYA_ACCESS_SECRET=your_access_secret
TUYA_REGION=eu        # cn / us / eu / in
TUYA_SCHEMA=smartlife
```

Region — регион, где зарегистрирован аккаунт Smart Life.

---

## 5. Привязка розеток к камере через Telegram

1. Переключитесь на камеру: `/cam N`
2. Привяжите розетки по номеру: `/plug 1 2` (будут управлять plug1 и plug2)
3. Проверьте: `/plug` — показывает привязки активной камеры

При тревоге с этой камеры **все** привязанные розетки включаются; при снятии — выключаются.
Привязки сохраняются в `sguard_settings.json` и восстанавливаются при старте.

---

## 6. Добавление другого типа розетки (Sonoff, Shelly, ESPHome, Zigbee)

Архитектура актуаторов расширяема: `BaseActuator` (интерфейс) + `ActuatorRegistry`
(реестр типов). Тип `tuya` реализован; остальные добавляются как подкласс:

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

`type` должен совпадать с именем в реестре (`register("sonoff", …)`).

### Шаг 3 — перезапустите и проверьте `/plug test`

---

## 7. Параметры детекции (тонкая настройка)

| Переменная | Default | Значение |
|---|---|---|
| `SG_UPDATE_EVERY` | 2.0 | Интервал кадров камеры / период live-frame в Telegram |
| `SG_DETECT_EVERY` | 1.5 | Интервал цикла детекции |
| `SG_MIN_CONF` | 0.35 | Мин. уверенность YOLO |
| `SG_YELLOW_MIN_FRACTION` | 0.15 | Мин. доля пикселей цвета в боксе |
| `SG_MIN_YELLOW_VEHICLES` | 1 | Мин. совпадений для «hit» |
| `SG_REQUIRE_FRAMES` | 2 | Кадров подряд для триггера |
| `SG_AUTO_RESOLVE_FRAMES` | 5 | Чистых кадров для авто-снятия |

---

## 8. Диагностика

| Симптом | Решение |
|---|---|
| Камера 🔴 dead | Проверьте URL, сеть, доступность. Для RTSP — камера в той же подсети |
| Розетка OFFLINE | IP сменился → Tuya Cloud (`ip: auto`) или `/plug test` |
| `409 Conflict` Telegram | Зомби-процесс с тем же токеном → рестарт, отдельный бот для SuperGuard |
| `404` от Telegram API | Неправильный токен в `sguard.env` |
| Live-frame не обновляется | Проверьте `SG_UPDATE_EVERY`, сеть до камеры |
| Изменения конфига не применяются | Бот не перезапущен (см. предупреждение вверху) |

---

## 9. SuperGuard Desktop App (v1.0.0)

### Что делает
Один `.exe` (25 MB), который:
- **Self-heal при старте** — проверяет Python, venv, pip-пакеты, модель YOLO11n, `sguard.env`, пути, чинит сломанное
- **Полный UI конфигурации** — 7 вкладок (General/Telegram/Cameras/Plugs/Paths/Advanced/About), атомарная запись `.env`
- **Запускает SuperGuard core** как подпроцесс с health-monitoring (авто-рестарт, хвост логов)
- **System tray** — иконка глаз+молния, меню: Show / Settings / Test alarm / Status / Exit
- **Fullscreen окно тревоги** — авто-разворачивается при тревоге, красная пульсирующая рамка, live-кадр (2 Hz), камера/зона/цель/розетки, обратный отсчёт, кнопка "Dismiss"
- **Desktop bridge** — опрашивает `desktop_state/status.json` + `alarm_live.jpg`, которые пишет SuperGuard core

### Установка
```powershell
# Run as Administrator
irm https://raw.githubusercontent.com/PerfectFriend/AISuperGuard/main/install_desktop.ps1 | iex
```

Или скачайте `SuperGuardDesktop-v1.0.0.exe` с [Releases](https://github.com/PerfectFriend/AISuperGuard/releases/tag/v1.0.0).

### Архитектура
```
desktop/
├── main.py           # Оркестратор
├── self_heal.py      # Проверка и ремонт окружения
├── config_ui.py      # tkinter 7-tab конфиг
├── tray.py           # pystray system tray
├── monitor.py        # 1s poll: события status/alarm/frame
├── bridge.py         # Читает desktop_state/status.json + alarm_live.jpg
├── alarm_window.py   # Fullscreen UI тревоги
├── icon.py           # PIL: глаз + молния → ICO
├── build.ps1         # PyInstaller build
└── tests/            # 19 тестов всего
```

### Сборка из исходников
```powershell
cd desktop
.\build.ps1
# Output: dist/SuperGuardDesktop.exe (25 MB)
```

---

## 10. Тесты после настройки

```bash
python superguard\tests\test_all.py              # 11 проверок
python superguard\tests\test_live_update.py      # 7 проверок live-frame протокол
python superguard\tests\test_plug_active_cam.py  # 8 проверок активная камера и /plug
```

Desktop app:
```bash
python desktop\tests\test_icon.py             # 4 проверки
python desktop\tests\test_self_heal.py        # 5 проверок
python desktop\tests\test_config_ui.py        # 5 проверок
python desktop\tests\test_monitor.py          # 5 проверок
```