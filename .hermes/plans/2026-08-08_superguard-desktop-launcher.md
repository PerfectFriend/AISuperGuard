# SuperGuard Desktop — Autonomous Launcher & Monitor

**Goal:** Автономное десктоп-приложение (Windows): проверка окружения → авторемонт → полная конфигурация → запуск SuperGuard → трей + fullscreen-тревога.

**Architecture:** Приложение — **лаунчер/монитор**, а не перепись SuperGuard. Оно находит Python-окружение, проверяет/ставит зависимости и модель, настраивает `sguard.env` через GUI, запускает `superguard/main.py` как дочерний процесс и мониторит его события (status.json + alarm-файлы) для трея и fullscreen-окна тревоги. Тяжёлые библиотеки (torch, ultralytics) живут в venv, exe остаётся лёгким.

**Tech Stack:** Python 3.12, tkinter (GUI), pystray (трей), Pillow (иконка), pyinstaller (сборка exe), subprocess (запуск/ремонт), venv (изоляция зависимостей).

---

## Текущее состояние / допущения

- SuperGuard работает: `C:\SuperGuard\superguard\main.py`, конфиг `C:\SuperGuard\sguard.env`
- Рабочее Python-окружение: `C:\Users\tomas\AppData\Local\hermes\hermes-agent\venv` (все deps есть)
- Модель: `C:\SuperGuard\yolo11n.pt` (есть; ultralytics скачает при отсутствии)
- Desktop не тащит torch в свой exe — только проверяет/чинит venv SuperGuard
- Windows 10/11, иконка глаза с молнией (PIL-генератор), трей через pystray, fullscreen через tkinter

## Целевая структура

```
C:\SuperGuard\desktop\
├── main.py               # Точка входа: self-heal → GUI → запуск SuperGuard → трей
├── self_heal.py          # Проверка/ремонт: python, pip, deps, модель, конфиг, PATH
├── config_ui.py          # Окно конфигурации: токен, chat_id, папки, камеры, розетки, параметры
├── tray.py               # Трей: pystray (показать/настройки/тест-тревога/статус/выход)
├── alarm_window.py       # Fullscreen окно тревоги: фото, статус, зона/цель, кнопка снятия
├── monitor.py            # Поллинг status.json/alarm-файлов, диспетчер событий
├── bridge.py             # Чтение status.json, обнаружение новых кадров тревоги
├── icon.py               # Генерация иконки (глаз + молния) PNG/ICO
├── build.ps1             # Сборка exe (pyinstaller)
└── tests/
    ├── test_self_heal.py
    ├── test_icon.py
    └── test_monitor.py
```

## Изменения в SuperGuard (интеграция)

- `superguard/telegram/__init__.py`: при тревоге писать `desktop_state/status.json` + копию live-кадра в `desktop_state/alarm_live.jpg`; при снятии — обновлять status.json
- status.json: `{active_camera, zone, target, auto_mode, alarm_active, alarm_camera, plugs, timestamp}`
- Писать в `C:\SuperGuard\desktop_state\` (single source of truth для desktop)

---

## Этапы

### Этап 0: Инфраструктура
- `desktop/` + `desktop/tests/`, git
- pyinstaller в рабочем окружении

### Этап 1: Иконка «глаз + молния»
- `icon.py`: PIL — глаз (овал/миндалина + зрачок), внутри зрачка жёлтая молния; размеры 256/64/32/16, экспорт PNG + ICO
- Тест: файлы создаются, размеры корректны, PNG не пустой

### Этап 2: self_heal.py
- Проверки (каждая возвращает (ok, message)):
  1. python.exe существует/найден (venv или системный)
  2. pip доступен
  3. зависимости: numpy, opencv-python-headless, ultralytics, torch, tinytuya, requests, psutil, pycryptodome/pyaes — через importlib
  4. модель yolo11n.pt существует (если нет — инструкция/скачивание через ultralytics)
  5. sguard.env существует, токен непустой и не `***`
  6. пути в PATH: python, pip
- Ремонт: `pip install -r requirements.txt` для отсутствующих; создание sguard.env из шаблона; скачивание модели
- Отчёт: список (✅/❌/🔧) → GUI
- Тест: мок subprocess/pip, проверка веток

### Этап 3: config_ui.py (tkinter)
- Вкладки: Telegram (токен, chat_id), Пути (домашняя папка, папка проекта), Камеры (динамические SG_CAM{N}_URL/NAME), Розетки (SG_ACTUATORS JSON с подсветкой), Детекция (7 параметров)
- Кнопки: Сохранить (пишет sguard.env атомарно), Проверить, Сброс
- Тест: генерация/валидация env-строк, атомарная запись

### Этап 4: tray.py (pystray)
- Иконка в трее, меню: Показать, Настройки, Тест-тревога, Статус, Выход
- Сворачивание главного окна в трей (protocol WM_DELETE_WINDOW → hide)
- Тест: создание иконки, пункты меню (без показа на CI — smoke)

### Этап 5: monitor.py + bridge.py
- Чтение `desktop_state/status.json` каждые 1–2 с
- Обнаружение новых `alarm_live.jpg` (по hash/mtime) → событие ALARM
- События: status_changed, alarm_on, alarm_off
- Тест: создание/изменение status.json, фейковый alarm-файл

### Этап 6: alarm_window.py (tkinter fullscreen)
- Полноэкранное окно: фото камеры (из alarm_live.jpg), крупный текст ТРЕВОГА, камера/зона/цель/розетки, кнопки (Снять тревогу через superguard API/файл-команду, Свернуть)
- `attributes('-fullscreen', True)`, Esc — свернуть в трей
- Тест: окно создаётся, fullscreen-флаг, обработка команд

### Этап 7: main.py — оркестрация
- Старт: self-heal (отчёт в окне) → если проблемы требующие решения — показать config_ui → запуск superguard (subprocess, venv python) → трей + monitor → alarm_window при тревоге
- Кнопки: Запустить/Остановить сервис, Автозапуск при старте Windows
- Тест: smoke-запуск, фейковый superguard

### Этап 8: Сборка и релиз
- build.ps1: `pyinstaller --onefile --windowed --icon=assets/icon.ico desktop/main.py --name SuperGuardDesktop`
- Проверка exe: запуск, self-heal, трей
- Загрузка в GitHub Releases (gh release create)
- Коммит/пуш кода

### Этап 9: Интеграция событий в SuperGuard
- Патч `telegram/__init__.py`: запись status.json + alarm_live.jpg при тревоге/снятии
- Обновление тестов супергарда, прогон 26 проверок

---

## Тесты/валидация

- desktop: pytest (self_heal, icon, monitor, config_ui-логика)
- superguard: существующие 3 сьюта (26 проверок) после патча интеграции
- e2e: запуск desktop → self-heal зелёный → запуск superguard → имитация тревоги → fullscreen окно → снятие

## Риски

| Риск | Митигация |
|---|---|
| tkinter-окна на headless | Windows-хосты, smoke-тесты без показа |
| pyinstaller большой из-за torch | torch НЕ в exe — desktop только лаунчер, deps в venv |
| pystray + tkinter thread | pystray в отдельном потоке, коммуникация через queue |
| sguard.env перезаписан | Атомарная запись + бэкап .bak |
| Тревога пропущена поллингом | Интервал 1 с + mtime/hash-детект + чтение status.json |

## Открытые вопросы

- Автозапуск: планировщик задач (schtasks) — да
- Обновление: самодесктоп проверяет новую версию GitHub Releases — в v2
