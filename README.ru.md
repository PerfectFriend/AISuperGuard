<div align="center">

![SuperGuard Banner — cyberpunk × Van Gogh × Gaudí](assets/banner-header.png)

# 🛡️ SuperGuard Alarm

ИИ-видеонаблюдение с реакцией через умные розетки и управлением из Telegram.

**YOLO-детекция → HSV-цветовой фильтр → фильтр зоны → розетка Tuya ON → тревога в Telegram**

[English](README.md) · [Русский](README.ru.md) · [Español](README.es.md) · [Руководство администратора](ADMIN_GUIDE.ru.md)

</div>

---

## ✨ Возможности

- **8+ камер** — HLS-потоки, RTSP (локальные PoE-камеры), HTTP JPG-снимки — мониторинг всех одновременно
- **ИИ-детекция** — YOLO11n (Ultralytics) с трекингом; фильтр по классу (авто, человек, автобус, грузовик…) и цвету (красный, жёлтый, синий… через HSV)
- **Фильтр зоны** — поиск только в ячейке сетки: `N3x4 C9` = сетка 3×4, ячейка 9
- **Активная камера** — команды (`/zone`, `/target`, `/plug`) всегда работают с активной камерой. Камера становится активной при тревоге или через `/cam` и остаётся активной, пока другая не станет активной
- **Умные розетки** — Tuya, локальное управление (tinytuya); к камере можно привязать любое число розеток: `/plug 1 2 3`
- **Протокол тревоги** — кадр срабатывания (аудит, не удаляется) + живой кадр, **обновляемый каждые 2 с** с камеры тревоги до снятия
- **Автоснятие** — в авторежиме тревога снимается сама, когда цель покидает зону; в ручном режиме ждёт `/togglealarm`
- **Ручной триггер** — `/togglealarm` для тестирования администратором; дублирует автоматическую тревогу (учитывает авто/ручной режим)
- **Telegram-бот** — полное управление командами, инлайн-кнопки, 3 языка (EN/ES/RU)
- **Отказоустойчивость** — авто-переподключение камер и розеток (`/plug test`), убийца зомби-процессов, атомарное хранение настроек, автообнаружение IP розеток через Tuya Cloud
- **Просмотр в браузере** — встроенный MJPEG-сервер (`http://localhost:8081`)
- **26 автоматических проверок** — синтаксис, конфиг, модели, камеры, актуаторы, протокол тревоги, обновление live-кадра

---

## 🏗️ Архитектура

```
C:\SuperGuard\
├── sguard.env                    # Вся конфигурация (токен, камеры, розетки)
├── sguard_settings.json          # Настройки (зона/цель/розетки по камерам)
├── saved_frames\                 # Архив кадров тревог
├── mjpeg_stream_server.py        # Просмотр в браузере (порт 8081)
├── requirements.txt
└── superguard\
    ├── main.py                   # Точка входа, SuperGuardApplication
    ├── config.py                 # Загрузка и валидация конфигурации
    ├── models\                   # Zone, Target, CameraSettings, Alarm (машина состояний)
    ├── detectors\                # Пайплайн: YOLO + HSV-цвет + зона
    ├── cameras\                  # Камеры JPG/HLS/RTSP, CameraManager
    ├── actuators\                # Абстракция розеток (Tuya…), реестр, ActuatorManager
    ├── telegram\                 # Telegram-клиент, роутер команд, бот
    ├── storage\                  # Атомарное JSON-хранилище, EnvWriter
    ├── tuya_cloud\               # Tuya Cloud синхронизация (авто-IP розеток)
    └── tests\                    # test_all.py, test_live_update.py, test_plug_active_cam.py
```

### Пайплайн детекции

```
Камера (JPG/HLS/RTSP) → кадр → YOLO11n → фильтр зоны → фильтр класса → HSV-цвет
   ↓ цель найдена N кадров подряд (require_frames)
ТРЕВОГА: розетка(и) ON → Telegram: кадр срабатывания (msg A)
   → через 1 с: живой кадр (msg B), обновляется каждые update_every с
   ↓ цель ушла (auto_resolve_frames чистых кадров + авторежим)
розетка(и) OFF → уведомление «Угроза устранена»
```

### Машина состояний тревоги

```
INACTIVE ──(цель N кадров)──▶ ACTIVE ──(авторежим + N чистых)──▶ AUTO_RESOLVING
   ▲                                │                                 │
   │                                │◀──(цель снова)───────────────────┘
   └────(/togglealarm или кнопка)───┘
```

---

## 🚀 Быстрый старт

```bash
git clone <repo-url> superguard
cd superguard
pip install -r requirements.txt

# 1. Создайте бота у @BotFather, укажите токен в sguard.env
# 2. Настройте камеры и розетки в sguard.env (см. Руководство администратора)
python superguard\main.py
```

---

## ⚙️ Конфигурация (`sguard.env`)

| Переменная | Назначение |
|---|---|
| `SG_TELEGRAM_BOT_TOKEN` | Токен бота (**отдельный** бот, не gateway-бот!) |
| `SG_CHAT_ID` | ID чата Telegram для тревог |
| `SG_PLUG_KEY` | Локальный ключ Tuya (дефолтная розетка, обратная совместимость) |
| `SG_CAM_URL` | URL камеры 1 (HLS) |
| `SG_CAM2_URL` … `SG_CAM32_URL` | Камеры 2–32 (добавление/переопределение без правки кода) |
| `SG_CAM{N}_NAME` | Отображаемое имя камеры N |
| `SG_UPDATE_EVERY` | Интервал обновления кадров (с) — период обновления live-кадра |
| `SG_DETECT_EVERY` | Интервал цикла детекции (с) |
| `SG_MIN_CONF` | Порог уверенности YOLO |
| `SG_YELLOW_MIN_FRACTION` | Мин. доля пикселей цвета в боксе |
| `SG_MIN_YELLOW_VEHICLES` | Мин. число совпадений для «хита» |
| `SG_REQUIRE_FRAMES` | Кадров подряд для срабатывания тревоги |
| `SG_AUTO_RESOLVE_FRAMES` | Чистых кадров для автоснятия тревоги |
| `SG_ACTUATORS` | JSON-массив розеток (`name`, `type`, `cameras`, `ip`, `device_id`, `local_key`, `version`, `port`) |
| `TUYA_ACCESS_ID` / `TUYA_ACCESS_SECRET` | Ключи Tuya Cloud OpenAPI (автообнаружение IP розеток) |

Тип камеры выбирается автоматически по URL: `.jpg/.jpeg/.png` → JPG-камера; `.m3u8`/`rtsp://` → потоковая камера.

---

## 🤖 Команды Telegram

| Команда | Действие |
|---|---|
| `/autoguard` | Переключить авторежим вкл/выкл |
| `/togglealarm` | Ручная тревога вкл/выкл (тестовый триггер администратора) |
| `/zone` | `/zone N3x4 C9` — задать зону, `/zone off` — весь кадр, `/zone ?` — справка |
| `/target` | `/target red car` — задать цель, `/target ?` — справка |
| `/plug` | Показать розетки активной камеры |
| `/plug 1 2 3` | Привязать розетки plug1..plug3 к **активной** камере |
| `/plug test` | Тест розеток, авто-переподключение упавших |
| `/setlocal` | Язык EN/ES/RU (инлайн-кнопки) |
| `/cam` | Список/статус камер, переключение активной (`/cam 3`) |

### Формат зоны
- `N{rows}x{cols} C{cell}` — сетка rows×cols, номер ячейки (1 = верх-лево)
  `/zone N3x4 C9` → сетка 3×4, ячейка 9
- `N{total} C{cell}` — квадратная сетка: `/zone N9 C5` = 3×3, ячейка 5
- `off` / `всё` / `0` / `todo` / `nada` — весь кадр

### Формат цели
`/target <текст>` — слова-классы + слова-цвета:
- Классы: `person`, `car`, `bus`, `truck`, `bicycle`, `motorcycle`…
- Цвета: `red`, `blue`, `yellow`, `green`, `black`, `white`…
- Пример: `/target red car`

---

## 🔌 Привязка розеток

- Розетки задаются в `SG_ACTUATORS` (тип `tuya`, протокол 3.4, порт 6668)
- Привязка к камере: переключитесь на неё (`/cam N`), затем `/plug 1 2` (номера → `plug1`, `plug2`)
- При тревоге с этой камеры включаются **все привязанные розетки**; при снятии — выключаются
- Привязки хранятся в `sguard_settings.json` и восстанавливаются при старте
- `"ip": "auto"` + ключи Tuya Cloud → IP розетки обнаруживается автоматически (каждые 5 мин)

---

## 🖥️ Просмотр в браузере

```bash
python mjpeg_stream_server.py
```
- `http://localhost:8081/` — MJPEG-поток
- `http://localhost:8081/snapshot.jpg` — одиночный кадр

---

## 🧪 Тесты

```bash
python superguard\tests\test_all.py           # 11 проверок: синтаксис, конфиг, модели, камеры, актуаторы, приложение
python superguard\tests\test_live_update.py   # 7 проверок: протокол обновления live-кадра
python superguard\tests\test_plug_active_cam.py  # 8 проверок: активная камера, /plug, привязки тревоги
```

---

## 🛠️ Руководство администратора

Полная настройка — добавление камер, добавление розеток всех поддерживаемых типов — в [ADMIN_GUIDE.ru.md](ADMIN_GUIDE.ru.md) (также [EN](ADMIN_GUIDE.en.md), [ES](ADMIN_GUIDE.es.md)).

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
