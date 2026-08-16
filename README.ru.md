<div align="center">

![SuperGuard Banner — cyberpunk × Van Gogh × Gaudí](assets/banner-header.png)

# 🛡️ SuperGuard Alarm

AI-видеонаблюдение с управлением умными розетками и контролем через Telegram.

**YOLO-детекция → HSV-фильтр цвета → фильтр зоны → розетка Tuya ON → алерт в Telegram**

[English](README.md) · [Русский](README.ru.md) · [Español](README.es.md) · [Руководство админа](ADMIN_GUIDE.ru.md) · [Desktop App](desktop/)

</div>

---

## ✨ Возможности

- **8+ камер** — HLS-потоки, RTSP (локальные PoE-камеры), JPG-снимки по HTTP — все одновременно
- **AI-детекция** — YOLO11n (Ultralytics) с трекингом; фильтр по классу (авто, человек, автобус, грузовик…) и цвету (красный, жёлтый, синий… через HSV)
- **Фильтр зоны** — ограничить детекцию ячейкой сетки: `N3x4 C9` = сетка 3×4, ячейка 9
- **Активная камера** — команды (`/zone`, `/target`, `/plug`) всегда работают с активной камерой. Камера становится активной при тревоге или через `/cam`, и остаётся активной, пока другая не возьмёт контроль
- **Умные розетки** — Tuya розетки под управлением локально (tinytuya), привязка любое число розеток к камере: `/plug 1 2 3`
- **Протокол тревоги** — кадр-триггер (аудит, не удаляется) + live-кадр **обновляется каждые 2 с** с камеры тревоги до её снятия
- **Авто-снятие** — в авто-режиме тревога снимается сама, когда цель уходит из зоны; в ручном — ждёт `/togglealarm`
- **Ручной триггер** — `/togglealarm` для тестов админа; дублирует поведение авто-тревоги (с учётом auto/manual режима)
- **Telegram-бот** — полный контроль: команды, inline-кнопки, 3 языка (EN/ES/RU)
- **Устойчивость** — авто-переподключение камер, авто-переподключение розеток (`/plug test`), киллер зомби-процессов, атомарное хранение настроек, авто-обнаружение IP розеток через Tuya Cloud
- **Браузерный live-view** — встроенный MJPEG-сервер (`http://localhost:8081`)
- **26 автотестов** — синтаксис, конфиг, модели, камеры, актуаторы, протокол тревоги, live-frame

---

## 🖥️ SuperGuard Desktop App (v1.0.0)

**Автономный Windows-лаунчер и монитор** — один `.exe` (25 MB), который:

1. **Self-heal при старте** — проверяет Python, venv, pip-пакеты (numpy, opencv, ultralytics, torch, tinytuya, requests, psutil, pycryptodome, pyaes), модель YOLO11n, `sguard.env`, пути, чинит что сломано
2. **Полный UI конфигурации** — 7 вкладок: General, Telegram, Cameras, Plugs, Paths, Advanced, About (tkinter, атомарная запись `.env`)
3. **Запускает SuperGuard core** как подпроцесс с health-мониторингом (рестарт при краше, хвост логов)
4. **System tray** — иконка глаз+молния (cyberpunk × Van Gogh × Gaudí), меню: Show / Settings / Test alarm / Status / Exit
5. **Авто-разворачивается в fullscreen при тревоге** — красная пульсирующая рамка, live-кадр (2 Hz), камера/зона/цель/розетки, обратный отсчёт, кнопка "Dismiss"
6. **Desktop bridge** — опрашивает `desktop_state/status.json` + `alarm_live.jpg`, которые пишет SuperGuard core (нет сокетов, ноль зависимостей)

### Установка (одной командой, Run as Administrator)

```powershell
irm https://raw.githubusercontent.com/PerfectFriend/AISuperGuard/main/install_desktop.ps1 | iex
```

Или скачайте с [Releases](https://github.com/PerfectFriend/AISuperGuard/releases/tag/v1.0.0): `SuperGuardDesktop-v1.0.0.exe`

### Архитектура Desktop

```
C:\SuperGuard\
├── sguard.env                    # Вся конфигурация (токен, камеры, розетки)
├── sguard_settings.json          # Runtime-настройки (зона/цель/розетки по камерам)
├── saved_frames\                 # Архив кадров тревог
├── desktop_state\                # Bridge: status.json + alarm_live.jpg (создаётся при запуске)
├── mjpeg_stream_server.py        # Браузерный live-view (порт 8081)
├── requirements.txt
├── superguard\                   # Core-пакет (модульный)
│   ├── main.py                   # Точка входа, SuperGuardApplication
│   ├── config.py                 # Загрузка и валидация конфига
│   ├── models\                   # Zone, Target, CameraSettings, Alarm (state machine)
│   ├── detectors\                # Pipeline: YOLO + HSV color + zone
│   ├── cameras\                  # JPG/HLS/RTSP камеры, CameraManager
│   ├── actuators\                # Абстракция розеток (Tuya…), реестр, ActuatorManager
│   ├── telegram\                 # Telegram-клиент, роутер команд, бот
│   ├── storage\                  # Атомарный JSON, EnvWriter
│   ├── tuya_cloud\               # Tuya Cloud sync (авто-обнаружение IP розеток)
│   └── tests\                    # test_all.py, test_live_update.py, test_plug_active_cam.py
├── desktop\                      # Исходники Desktop-приложения
│   ├── main.py                   # Оркестратор: self-heal → config → tray → monitor → SuperGuard
│   ├── self_heal.py              # Проверка и ремонт окружения
│   ├── config_ui.py              # tkinter 7-tab конфигурация
│   ├── tray.py                   # pystray system tray
│   ├── monitor.py                # 1s poll: on_status, on_alarm_on, on_alarm_off, on_new_frame
│   ├── bridge.py                 # Читает desktop_state/status.json + alarm_live.jpg
│   ├── alarm_window.py           # Fullscreen тревога: красная рамка, live-кадр, отсчёт, Dismiss
│   ├── icon.py                   # PIL-генератор: глаз + молния → 256² PNG + multi-res ICO
│   ├── build.ps1                 # PyInstaller build-скрипт
│   ├── install_desktop.ps1       # One-command installer
│   └── tests\                    # test_icon.py, test_self_heal.py, test_config_ui.py, test_monitor.py
└── install_desktop.ps1           # Root installer (копия из desktop/)
```

---

## 🏗️ Архитектура

```
C:\SuperGuard\
├── sguard.env                    # Вся конфигурация (токен, камеры, розетки)
├── sguard_settings.json          # Runtime-настройки (зона/цель/розетки по камерам)
├── saved_frames\                 # Архив кадров тревог
├── mjpeg_stream_server.py        # Браузерный live-view (порт 8081)
├── requirements.txt
└── superguard\
    ├── main.py                   # Точка входа, SuperGuardApplication
    ├── config.py                 # Загрузка и валидация конфига
    ├── models\                   # Zone, Target, CameraSettings, Alarm (state machine)
    ├── detectors\                # Pipeline: YOLO + HSV color + zone
    ├── cameras\                  # JPG/HLS/RTSP камеры, CameraManager
    ├── actuators\                # Абстракция розеток (Tuya…), реестр, ActuatorManager
    ├── telegram\                 # Telegram-клиент, роутер команд, бот
    ├── storage\                  # Атомарный JSON, EnvWriter
    ├── tuya_cloud\               # Tuya Cloud sync (авто-обнаружение IP розеток)
    └── tests\                    # test_all.py, test_live_update.py, test_plug_active_cam.py
```

### Pipeline детекции

```
Камера (JPG/HLS/RTSP) → кадр → YOLO11n → фильтр зоны → фильтр класса → HSV-цвет
   ↓ цель найдена N кадров подряд (require_frames)
ТРЕВОГА: розетка(и) ON → Telegram: кадр-триггер (msg A)
   → 1 с спустя: live-кадр (msg B), обновляется каждые update_every с
   ↓ цель ушла (auto_resolve_frames чистых кадров + авто-режим)
розетка(и) OFF → уведомление «Угроза устранена»
```

### State machine тревоги

```
INACTIVE ──(цель N кадров)──▶ ACTIVE ──(авто + N чистых)──▶ AUTO_RESOLVING
   ▲                                │                                 │
   │                                │◀──(цель снова найдена)───────────┘
   └────(/togglealarm или кнопка)────┘
```

---

## 🚀 Быстрый старт

```bash
git clone <repo-url> superguard
cd superguard
pip install -r requirements.txt

# 1. Создайте бота через @BotFather, положите токен в sguard.env
# 2. Настройте камеры и розетки в sguard.env (см. Руководство админа)
python superguard\main.py
```

**Windows:** запускайте `python superguard\main.py`; бот сам установит меню команд.

---

## ⚙️ Конфигурация (`sguard.env`)

| Переменная | Назначение |
|---|---|
| `SG_TELEGRAM_BOT_TOKEN` | Токен бота (**отдельный** бот, не gateway-бот) |
| `SG_CHAT_ID` | ID чата Telegram для тревог |
| `SG_PLUG_KEY` | Локальный ключ Tuya (розетка по умолчанию, совместимость) |
| `SG_CAM_URL` | URL камеры 1 (HLS) |
| `SG_CAM2_URL` … `SG_CAM32_URL` | Камеры 2–32 (добавить/переопределить без кода) |
| `SG_CAM{N}_NAME` | Отображаемое имя камеры N |
| `SG_UPDATE_EVERY` | Интервал обновления кадров (с) — период live-frame |
| `SG_DETECT_EVERY` | Интервал цикла детекции (с) |
| `SG_MIN_CONF` | Порог уверенности YOLO |
| `SG_YELLOW_MIN_FRACTION` | Мин. доля пикселей цвета в боксе |
| `SG_MIN_YELLOW_VEHICLES` | Мин. совпадений для «hit» |
| `SG_REQUIRE_FRAMES` | Кадров подряд для триггера тревоги |
| `SG_AUTO_RESOLVE_FRAMES` | Чистых кадров для авто-снятия |
| `SG_ACTUATORS` | JSON-массив розеток (`name`, `type`, `cameras`, `ip`, `device_id`, `local_key`, `version`, `port`) |
| `TUYA_ACCESS_ID` / `TUYA_ACCESS_SECRET` | Ключи Tuya Cloud OpenAPI (авто-обнаружение IP) |

Тип камеры выбирается автоматически по URL: `.jpg/.jpeg/.png` → JPG-камера; `.m3u8`/`rtsp://` → потоковая камера.

---

## 🤖 Команды Telegram

| Команда | Действие |
|---|---|
| `/autoguard` | Вкл/выкл авто-режим |
| `/togglealarm` | Ручная тревога on/off (тест админа) |
| `/zone` | `/zone N3x4 C9` задать зону, `/zone off` весь кадр, `/zone ?` помощь |
| `/target` | `/target red car` задать цель, `/target ?` помощь |
| `/plug` | Показать розетки активной камеры |
| `/plug 1 2 3` | Привязать розетки plug1..plug3 к **активной** камере |
| `/plug test` | Тест розеток, авто-переподключение упавших |
| `/setlocal` | Язык EN/ES/RU (inline-кнопки) |
| `/cam` | Список/статус камер, смена активной (`/cam 3`) |

### Формат зоны

- `N{rows}x{cols} C{cell}` — сетка rows×cols, номер ячейки (1 = верх-лево)
  `/zone N3x4 C9` → сетка 3×4, ячейка 9
- `N{total} C{cell}` — квадратная сетка: `/zone N9 C5` = 3×3, ячейка 5
- `off` / `всё` / `0` / `todo` / `nada` — весь кадр

### Формат цели

`/target <текст>` — слова класса + слова цвета:
- Классы: `person`, `car`, `bus`, `truck`, `bicycle`, `motorcycle`…
- Цвета: `red`, `blue`, `yellow`, `green`, `black`, `white`…
- Пример: `/target red car`

---

## 🔌 Привязка розеток

- Розетки задаются в `SG_ACTUATORS` (type `tuya`, протокол 3.4, порт 6668)
- Привязка к камере: переключитесь на неё (`/cam N`), затем `/plug 1 2` (числа → `plug1`, `plug2`)
- При тревоге с этой камеры **все** привязанные розетки включаются; при снятии — выключаются
- Привязки сохраняются в `sguard_settings.json` и восстанавливаются при старте
- `"ip": "auto"` + ключи Tuya Cloud → IP розетки обнаруживается автоматически (каждые 5 мин)

---

## 🖥️ Браузерный live-view

```bash
python mjpeg_stream_server.py
```

- `http://localhost:8081/` — MJPEG-поток
- `http://localhost:8081/snapshot.jpg` — одиночный кадр

---

## 🧪 Тесты

```bash
python superguard\tests\test_all.py           # 11 проверок: синтаксис, конфиг, модели, камеры, актуаторы, app
python superguard\tests\test_live_update.py   # 7 проверок: протокол live-frame
python superguard\tests\test_plug_active_cam.py  # 8 проверок: активная камера, /plug, привязки
```

Desktop app тесты:
```bash
python desktop\tests\test_icon.py             # 4 проверки
python desktop\tests\test_self_heal.py        # 5 проверок
python desktop\tests\test_config_ui.py        # 5 проверок
python desktop\tests\test_monitor.py          # 5 проверок
```

---

## 🛠️ Руководство админа

Полная настройка — добавление камер, добавление розеток всех поддерживаемых типов — см. [ADMIN_GUIDE.ru.md](ADMIN_GUIDE.ru.md) (также [EN](ADMIN_GUIDE.en.md), [ES](ADMIN_GUIDE.es.md)).

---

## 📄 Лицензия

MIT

---

**Master Inquisitor (@RarioArmageddon) · The Grimoire · DarkPushkin/the-grimoire**

---

<div align="center">

![SuperGuard Footer — cyberpunk × Van Gogh × Gaudí](assets/banner-footer.png)

**Protect your infrastructure. 24/7. Local. Intelligent.**

</div>