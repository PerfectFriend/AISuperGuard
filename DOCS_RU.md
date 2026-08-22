# SuperGuard Dashboard — Руководство пользователя

## Обзор

SuperGuard — это система видеонаблюдения и безопасности с ИИ-детекцией объектов, управлением исполнителями (умные розетки, реле) и Telegram-уведомлениями.

**Доступ:**
- **Dashboard:** http://localhost:5173
- **API:** http://localhost:8080
- **API Docs:** http://localhost:8080/docs

**Демо-логин:** `test@superguard.com` / `testpass123`

---

## 1. Быстрый старт

### 1.1 Запуск всей системы

```bash
# 1. API Server (порт 8080)
cd /home/thomas/SuperGuard/superguard-api
python -m uvicorn app.main:app --host 0.0.0.0 --port 8080

# 2. Web Dashboard (порт 5173) — в другом терминале
cd /home/thomas/SuperGuard/web-dashboard
npm run dev -- --host 0.0.0.0 --port 5173

# 3. SuperGuard Bot (детекция + Telegram) — в третьем терминале
cd /home/thomas/SuperGuard
python -m superguard.main
```

### 1.2 Структура проекта

```
/home/thomas/SuperGuard/
├── superguard-api/       # FastAPI backend
├── web-dashboard/        # React + TypeScript + Vite frontend
├── superguard/           # Python bot (детекция, Telegram, Tuya)
├── secrets/
│   └── sguard.env.gpg    # Зашифрованные секреты (GPG)
└── sguard.env            # Расшифрованный конфиг для бота
```

---

## 2. Dashboard — Основные разделы

### 2.1 Dashboard (Главная)
Обзор системы: статистика по сайтам, камерам, тревогам, исполнителям и детекторам.

### 2.2 Sites (Объекты)
Управление физическими объектами наблюдения.

**Действия:**
- **Add Site** — создать новый объект
- **Edit** ✏️ — изменить название, описание, часовой пояс, координаты
- **Delete** 🗑️ — удалить объект (каскадно удаляет камеры, детекторы, исполнители)

**Поля:**
- Name — название (обязательно)
- Description — описание
- Timezone — часовой пояс (например: `Europe/Moscow`)
- Latitude / Longitude — координаты (опционально)
- Active — включить/выключить объект

### 2.3 Cameras (Камеры)
Добавление и настройка RTSP-камер для каждого сайта.

**Действия:**
- **Add Camera** — добавить камеру
- **Test** 🔌 — проверить подключение к RTSP-потоку
- **Edit** ✏️ — изменить настройки
- **Delete** 🗑️ — удалить

**Поля:**
- Name — название камеры
- RTSP URL — `rtsp://user:pass@ip:port/stream`
- Username / Password — для авторизации (опционально)
- Width / Height / FPS — разрешение и FPS (0 = авто)
- PTZ Enabled — поддержка PTZ
- Zone (Rows/Cols/Cell) — зона детекции (сетка 3×3, ячейка 5 = центр)

**Пример тестовой камеры (уже настроена):**
```
Name: Indonesian Test Cam
RTSP: rtsp://wowzaec2demo.streamlock.net/vod/mp4:BigBuckBunny_115k.mov
Zone: 3×3, cell 5 (центр)
```

### 2.4 Detectors (Детекторы)
Настройка ИИ-детекторов для камер.

**Действия:**
- **Add Detector** — создать детектор
- **Test** 🧪 — тестовый запуск детекции
- **Toggle** (переключатель) — включить/выключить
- **Edit** ✏️ / **Delete** 🗑️

**Поля:**
- Name — название
- Type: **YOLO** / Face Recognition / Color Detection
- Model Path — путь к ONNX модели (например: `models/yolo11n.onnx`)
- Classes (COCO IDs) — классы для детекции через запятую:
  - `0` — person
  - `2` — car
  - `5` — bus
  - `7` — truck
- Confidence Threshold — порог уверенности (0.0–1.0, рекомендуется 0.5)
- IoU Threshold — порог IoU для NMS (0.45)
- Require Frames — кадров подряд для срабатывания (3)
- Auto Resolve Frames — кадров без детекции для авто-сброса (10)

**Настроенный детектор (уже есть):**
```
Name: YOLO Vehicle Detector
Type: YOLO
Model: models/yolo11n.onnx
Classes: 2, 5, 7 (car, bus, truck)
Target: red car (class 2)
Config: {"target": "red car", "target_class": 2}
```

### 2.5 Actuators (Исполнители)
Управление умными розетками, реле и выключателями.

**Действия:**
- **Add Actuator** — добавить исполнитель
- **Turn ON** ⏻ / **Turn OFF** ⏹ — ручное управление
- **Test** 🧪 — проверить связь
- **Toggle** — включить/выключить мониторинг
- **Edit** ✏️ / **Delete** 🗑️

**Типы:**
- **Tuya Smart Plug** — умные розетки Tuya (локальное управление + облако)
- **Relay** — реле
- **Switch** — выключатель

**Config (JSON) для Tuya:**
```json
{
  "ip": "192.168.1.129",
  "device_id": "bfd23bfc0bdd93b6904c3s",
  "local_key": "m+<ri=H[/r9./v;w",
  "version": 3.4,
  "port": 6668,
  "mac": "d8:c8:0c:d6:45:6c"
}
```

**Настроенные розетки (уже есть):**
- **plug1** — IP: 192.168.1.129, MAC: d8:c8:0c:d6:45:6c
- **plug2** — IP: 192.168.1.142, MAC: d8:c8:0c:d6:63:51

> **Важно:** IP могут меняться при DHCP. Бот использует MAC-адреса для автопоиска IP через ARP.

### 2.6 Alarms (Тревоги)
Просмотр и управление тревогами.

**Фильтры:** All / Unacknowledged / Acknowledged

**Действия:**
- **Acknowledge** ✓ — подтвердить тревогу
- **Silence** 🔇 — заглушить уведомления

**Статусы:** Active (активна) / Resolved (разрешена)

### 2.7 Notifiers (Уведомления)
Настройка каналов уведомлений.

**Действия:**
- **Add Notifier** — добавить канал
- **Test** 📤 — тестовое уведомление
- **Delete** 🗑️

**Типы:**
- **Telegram** — бот в Telegram
- **Email** — электронная почта
- **Webhook** — HTTP webhook

**Config для Telegram:**
```json
{
  "bot_token": "8711875181:AAEXplOLwvsxMRV1iSR7i7f5Wygf-JK5Av8",
  "chat_id": "143293811"
}
```

**Триггеры:**
- On Trigger — при срабатывании детектора
- On Ack — при подтверждении тревоги
- On Resolve — при разрешении тревоги

**Настроенный уведомитель (уже есть):**
- **Telegram Bot** — отправляет в чат 143293811 при срабатывании

### 2.8 System (Система)
Мониторинг здоровья API, БД, Redis, камер и бэкапы.

---

## 3. SuperGuard Bot (Python)

### 3.1 Конфигурация

Конфиг хранится в зашифрованном виде: `secrets/sguard.env.gpg`

**Расшифровка:**
```bash
gpg --decrypt /home/thomas/SuperGuard/secrets/sguard.env.gpg > /home/thomas/SuperGuard/sguard.env
```

**Основные параметры (sguard.env):**
```env
# Telegram
SG_TELEGRAM_BOT_TOKEN=8711875181:AAEXplOLwvsxMRV1iSR7i7f5Wygf-JK5Av8
SG_CHAT_ID=143293811

# Камеры (JSON)
SG_CAMERAS=[{"name":"cam1","type":"rtsp","stream_url":"rtsp://...","zone":{"rows":3,"cols":3,"cell":5},"target":"red car"}]

# Детекция
SG_UPDATE_EVERY=2.0
SG_DETECT_EVERY=1.5
SG_YELLOW_MIN_FRACTION=0.15
SG_MIN_CONF=0.35
SG_MIN_YELLOW_VEHICLES=1
SG_REQUIRE_FRAMES=2
SG_AUTO_RESOLVE_FRAMES=5

# Tuya Cloud
TUYA_ACCESS_ID=sesjdvqsts3d9kh4rpef
TUYA_ACCESS_SECRET=4f979a4f42e04431baf98ef6fbd448dd
TUYA_REGION=eu
TUYA_SCHEMA=smartlife

# Actuators (JSON) — локальные Tuya
SG_ACTUATORS=[{"name":"plug1","type":"tuya","cameras":[1,2,3,4],"ip":"192.168.1.129","device_id":"bfd23bfc0bdd93b6904c3s","local_key":"m+<ri=H[/r9./v;w","version":3.4,"port":6668,"mac":"d8:c8:0c:d6:45:6c"},{"name":"plug2","type":"tuya","cameras":[5,6,7,8],"ip":"192.168.1.142","device_id":"bfbb8aef4f24f1e958yzxr","local_key":"v[M.[|`MXci/^R6}","version":3.4,"port":6668,"mac":"d8:c8:0c:d6:63:51"}]
```

### 3.2 Запуск бота

```bash
cd /home/thomas/SuperGuard
# Сначала расшифровать конфиг если нужно
gpg --decrypt secrets/sguard.env.gpg > sguard.env
# Запуск
python -m superguard.main
```

### 3.3 Команды Telegram-бота

Бот работает в чате `143293811` (topic 252).

| Команда | Описание |
|---------|----------|
| `/start` | Приветствие и меню |
| `/status` | Статус системы |
| `/cameras` | Список камер |
| `/actuators` | Список исполнителей |
| `/alarm_on` | Включить охрану |
| `/alarm_off` | Выключить охрану |
| `/plug1_on` / `/plug1_off` | Управление розеткой 1 |
| `/plug2_on` / `/plug2_off` | Управление розеткой 2 |
| `/test` | Тест уведомления |

---

## 4. API (FastAPI)

### 4.1 Аутентификация

```bash
# Login
curl -X POST http://localhost:8080/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@superguard.com","password":"testpass123"}'

# Response: { "access_token": "...", "refresh_token": "...", "token_type": "bearer" }

# Использование токена
curl -H "Authorization: Bearer <access_token>" http://localhost:8080/api/v1/auth/me
```

### 4.2 Основные эндпоинты

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/health` | Health check |
| GET | `/api/v1/sites` | Список сайтов |
| POST | `/api/v1/sites` | Создать сайт |
| GET | `/api/v1/sites/{id}` | Получить сайт |
| PATCH | `/api/v1/sites/{id}` | Обновить сайт |
| DELETE | `/api/v1/sites/{id}` | Удалить сайт |
| GET | `/api/v1/sites/{id}/cameras` | Камеры сайта |
| POST | `/api/v1/sites/{id}/cameras` | Добавить камеру |
| GET | `/api/v1/sites/{id}/detectors` | Детекторы сайта |
| POST | `/api/v1/sites/{id}/detectors` | Добавить детектор |
| GET | `/api/v1/sites/{id}/actuators` | Исполнители сайта |
| POST | `/api/v1/sites/{id}/actuators` | Добавить исполнитель |
| POST | `/api/v1/sites/{id}/actuators/{aid}/command` | Команда исполнителю |
| GET | `/api/v1/sites/{id}/alarms` | Тревоги сайта |
| POST | `/api/v1/sites/{id}/alarms/{aid}/ack` | Подтвердить тревогу |
| GET | `/api/v1/sites/{id}/notifiers` | Уведомители сайта |
| POST | `/api/v1/sites/{id}/notifiers` | Добавить уведомитель |
| GET | `/api/v1/system/health` | Статус системы |

### 4.3 Примеры

**Создать сайт:**
```bash
curl -X POST http://localhost:8080/api/v1/sites \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"Office","description":"Main office","timezone":"Europe/Moscow"}'
```

**Добавить камеру:**
```bash
curl -X POST http://localhost:8080/api/v1/sites/<site_id>/cameras \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"Cam1","type":"rtsp","stream_url":"rtsp://192.168.1.100:554/stream","zone":{"rows":3,"cols":3,"cell":5}}'
```

**Включить розетку:**
```bash
curl -X POST http://localhost:8080/api/v1/sites/<site_id>/actuators/<actuator_id>/command \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"action":"on"}'
```

---

## 5. Локализация

Dashboard поддерживает 3 языка:
- **English** 🇺🇸 (по умолчанию)
- **Русский** 🇷🇺
- **Español** 🇪🇸

**Переключение:** селектор языка в левом сайдбаре (под email пользователя). Выбор сохраняется в `localStorage`.

---

## 6. Безопасность секретов

Все секреды (токены ботов, ключи Tuya, пароли) хранятся **только в зашифрованном виде**:

```bash
# Зашифровать
gpg --batch --yes --encrypt --recipient "thomas@localhost" \
  --output /home/thomas/SuperGuard/secrets/sguard.env.gpg \
  /home/thomas/SuperGuard/sguard.env

# Расшифровать (для бота)
gpg --decrypt /home/thomas/SuperGuard/secrets/sguard.env.gpg > /home/thomas/SuperGuard/sguard.env
```

**GPG ключ:** создан локально для `thomas@localhost` (RSA 4096). Никакие секреты **не** лежат в открытом виде в репозитории или конфигах.

---

## 7. Troubleshooting

### Dashboard не открывается
```bash
# Проверь API
curl http://localhost:8080/health
# Должен вернуть: {"status":"ok","version":"0.1.0"}

# Проверь CORS
curl -H "Origin: http://localhost:5173" -X OPTIONS http://localhost:8080/api/v1/auth/login -v
# Должен вернуть 200 с access-control-allow-origin: http://localhost:5173
```

### Логин не работает
1. Проверь, что API запущен на порту 8080
2. Проверь CORS (см. выше)
3. Открой DevTools (F12) → Console / Network — посмотри ошибку

### Бот не отвечает в Telegram
1. Проверь, что `sguard.env` расшифрован и токен верный
2. Проверь логи бота в терминале
3. Убедись, что чат `143293811` добавлен в бота

### Камеры оффлайн
1. Проверь RTSP URL в браузере (VLC: Media → Open Network Stream)
2. Проверь `Test` кнопку в Dashboard → Cameras
3. Проверь логи бота — есть ли ошибки подключения

### Розетки не управляются
1. Проверь, что IP в конфиге актуальны (DHCP может менять IP)
2. Бот использует MAC для автопоиска — проверь MAC в конфиге
3. Проверь `local_key` — он уникален для каждого устройства
4. Тест: кнопка `Test` в Dashboard → Actuators

---

## 8. Полезные команды

```bash
# Проверить процессы
ps aux | grep -E "(uvicorn|vite|superguard)"

# Логи API
cd /home/thomas/SuperGuard/superguard-api && tail -f logs/superguard-api.log

# Перезапуск всего
pkill -f "uvicorn.*8080"
pkill -f "vite.*5173"
pkill -f "superguard.main"
# Затем запусти заново (см. п. 1.1)

# Бэкап БД
cp /home/thomas/SuperGuard/superguard-api/superguard.db /home/thomas/SuperGuard/backups/superguard_$(date +%F).db
```

---

## 9. Архитектура

```
┌─────────────────┐     HTTP/WS      ┌──────────────────┐
│  Web Dashboard  │◄────────────────►│   FastAPI API    │
│  (React/Vite)   │   REST + WebSocket│   (port 8080)   │
└─────────────────┘                  └────────┬─────────┘
                                              │
                    ┌─────────────────────────┼─────────────────────────┐
                    ▼                         ▼                         ▼
            ┌───────────────┐        ┌───────────────┐        ┌───────────────┐
            │   SQLite DB   │        │  Redis (pub/sub)  │        │  MediaMTX     │
            │  (superguard.db)       │  (port 6379)   │        │  (RTSP→WebRTC)│
            └───────────────┘        └───────────────┘        └───────────────┘
                                              ▲
                                              │
                                    ┌─────────┴─────────┐
                                    ▼                   ▼
                          ┌───────────────┐      ┌───────────────┐
                          │ SuperGuard Bot │      │  Tuya Cloud   │
                          │ (YOLO detect)  │      │  (remote ctrl)│
                          └───────┬─────────┘      └───────────────┘
                                  │
                          ┌───────┴───────┐
                          ▼               ▼
                    ┌──────────┐    ┌──────────┐
                    │ Telegram │    │  Tuya    │
                    │   Bot    │    │  Local   │
                    └──────────┘    └──────────┘
```

---

*Документация актуальна на 2026-08-19. Версия системы: 0.1.0*