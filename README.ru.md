# SuperGuard Alarm — Автономный ИИ-сервис охраны

**[English](README.md) | [Русский](README.ru.md) | [Español](README.es.md)**

**ИИ-видеонаблюдение → Детекция цели (YOLO11n + HSV-цвет + зоны) → Розетка Tuya ON → Telegram**

Автономная служба охраны для Windows. Развёртывается одной командой на чистую машину.

## Возможности

- 🎥 **RTSP/HLS камера** — Любая потоковая камера (тест: Banjar ATCS Indonesia)
- 🤖 **YOLO11n детекция** — Машины, автобусы, грузовики, люди (GPU: Radeon 780M / ROCm / DirectML)
- 🎨 **Цветовой фильтр HSV** — Цель задаётся свободным текстом: `/target красная машина`, `/target white truck`, `/target persona de pie`
- 📍 **Зонный фильтр** — Сетка N×M, ячейки C01..C12: `/zone N3x4 C9`, `/zone off` (весь кадр)
- 🔌 **Tuya Smart Plug (локально, tinytuya 3.4)** — Розетка включается при срабатывании
- 📱 **Telegram-бот (отдельный токен)** — Меню команд, фото срабатывания, live-кадр 2с, авто-выкл по 5 чистым кадрам
- 🌍 **Мультиязык** — RU/EN/ES через `/setlocal` (inline-кнопки), меню следует за выбранным языком
- 💾 **Персистентность** — Настройки в `sguard_settings.json` переживают рестарты
- 🛡 **Самозащита от зомби** — При старте убивает старые python.exe panic_mode на этом токене
- 🪟 **Windows Service (NSSM)** — Автозапуск, логи, рестарт при падении

## Команды бота (меню справа от скрепки)

| Команда | Описание |
|---------|----------|
| `/autoguard` | Вкл/выкл авторежим (розетка OFF сама при уходе цели) |
| `/togglealarm` | Ручная тревога (розетка ON, фото сразу, без YOLO) |
| `/zone` | Зона: `N3x4 C9`, `N9 C5`, `off`, `?` |
| `/target` | Цель: `красная машина`, `white truck`, `persona de pie`, `?` |
| `/setlocal` | Язык интерфейса (RU/EN/ES) |

## Быстрая установка (на чистом Windows 10/11)

```powershell
# От администратора
irm https://raw.githubusercontent.com/DarkPushkin/superguard-alarm/main/install_superguard.ps1 | iex
```

Или скачайте и запустите `install_superguard.ps1` с параметрами:
```powershell
.\install_superguard.ps1 -BotToken "123:ABC" -ChatId "143293811" -PlugIp "192.168.137.109" -PlugKey "abcdef123456..."
```

## Ручная установка

```powershell
# 1. Python 3.12
winget install Python.Python.3.12

# 2. Клонирование
git clone https://github.com/DarkPushkin/superguard-alarm
cd superguard-alarm

# 3. Виртуальное окружение
python -m venv venv
venv\Scripts\pip install -r requirements.txt

# 4. Конфиг
copy sguard.env.example sguard.env
# Отредактируйте sguard.env (токен, chat_id, IP розетки, local_key)

# 5. Запуск
venv\Scripts\python panic_mode.py
```

## Windows-сервис (автозапуск)

```powershell
# Установите NSSM
# Создайте сервис:
nssm install SuperGuardAlarm "C:\SuperGuard\venv\Scripts\python.exe" "C:\SuperGuard\panic_mode.py"
nssm set SuperGuardAlarm AppDirectory "C:\SuperGuard"
nssm set SuperGuardAlarm Start SERVICE_AUTO_START
Start-Service SuperGuardAlarm
```

## Требования

- Windows 10/11 (x64)
- Python 3.12
- GPU с поддержкой OpenCV (Radeon 780M / CUDA / DirectML) — **CPU fallback НЕТ**
- Telegram-бот (создайте через @BotFather, **отдельный токен!**)
- Tuya Smart Plug (прошит локально, tinytuya 3.4, порт 6668)
- RTSP/HLS камера

## GPU на AMD Radeon 780M (Beelink SER9)

```bash
# Windows ROCm 7.2 — ЕДИНСТВЕННЫЙ рабочий путь
# WSL2 не работает, DirectML — segfault
pip install torch torchvision --index-url https://download.pytorch.org/whl/rocm7.2
```

## Файлы конфигурации

### `sguard.env` (НЕ КОММИТИТЬ!)
```
SG_TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
SG_CHAT_ID=143293811
SG_PLUG_IP=192.168.137.109
SG_PLUG_KEY=abcdef1234567890abcdef1234567890
```

### `sguard_settings.json` (автогенерируется)
```json
{
  "zone": [3, 3, 5],
  "target": "white car",
  "lang": "es",
  "auto": true
}
```

## Архитектура

```
panic_mode.py (один файл, ~1000 строк)
├── Telegram long-poll (async-safe, 8s timeout, изоляция апдейтов)
├── YOLO11n + ByteTrack (persist, conf=0.45, imgsz=640)
├── HSV цветовой фильтр (11 цветов, red=дуальный диапазон 0-10/170-180)
├── Зонная сетка (N×M, оранжевая рамка на кадре)
├── Tuya local (tinytuya 3.4, свежее соединение на команду)
├── Машина состояний тревоги (AUTO/MANUAL, 5-кадровый авто-resolve)
├── i18n (RU/EN/ES, 48 ключей, tr() везде)
├── Самозащита от зомби (PowerShell, psutil PID)
└── Персистентность (JSON, load_settings() ПЕРВЫМ в __main__)
```

## Сообщения бота

**Тревога (msg A)** — кадр срабатывания, рамка, **БЕЗ кнопок**, остаётся навсегда (аудит)  
**Live (msg B)** — живой кадр 2с, обновляется, **удаляется при отключении**  
**Авто-resolve (5 чистых кадров)** — розетка OFF + одно сообщение:
```
✅ Угроза устранена: цель покинула зону поиска
🚨 Сигнализация отключена.
📌 Текущий режим: АВТО, зона=N3x3 C05, цель=white car
```

## Лицензия

MIT — используйте, меняйте, деплойте.

---

**Master Inquisitor (@RarioArmageddon) · The Grimoire · DarkPushkin/the-grimoire**