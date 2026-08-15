# SuperGuard Alarm — Evolution Plan to RC (Release Candidate)

**Версия:** 2.0  
**Дата:** 2025-08-14  
**Текущий статус:** Core функционал работает (85% готовности)  
**Цель:** Полноценный кросс-платформенный продукт с Server Backend + Flutter Client

---

## 1. Архитектурная الرؤية RC

```
��─────────────────────────────────────────────────────────────────────────────��
│                        SUPERGUARD RC ARCHITECTURE                           │
├─────────────────────────────────────────────────────────────────────────────��
│                                                                             │
│  ��──────────────��     ��──────────────────��     ��────────────────────────��  │
│  │  FLUTTER     │��───��│  SUPERGUARD      │��───��│  HARDWARE LAYER        │  │
│  │  CLIENT      │     │  SERVER BACKEND  │     │                        │  │
│  │  (iOS/Android/│     │  (Windows/Ubuntu)│     │  • Cameras (RTSP/HLS/  │  │
│  │   Web/Desk)  │     │                  │     │    JPG/ONVIF)          │  │
│  └──────────────��     └──────────────────��     │  • Smart Plugs (Tuya,  │  │
│        ▲                    ▲                  │    Sonoff, Shelly)     │  │
│        │                    │                  │  • Sensors (PIR, door, │  │
│        │         ��──────────��──────────��      │    smoke, water)       │  │
│        │         │   MESSAGE BUS       │      │  • Sirens/Relays       │  │
│        │         │   (Redis/RabbitMQ)  │      └────────────────────────��  │
│        │         └─────────────────────��                                  │
│        │                    │                  ��────────────────────────��  │
│        │         ��──────────��──────────��      │  EXTERNAL INTEGRATIONS │  │
│        └────────��│  TELEGRAM BOT       │      │  • Home Assistant (MQTT)│  │
│                  │  (Legacy/Backup)    │      │  • Pushover/Email/SMS   │  │
│                  └─────────────────────��      │  • Webhooks             │  │
│                                               └────────────────────────��  │
��─────────────────────────────────────────────────────────────────────────────��
```

### 1.1 Ключевые принципы RC
| Принцип | Описание |
|---------|----------|
| **Local-first** | Работает без интернета (LAN), облако — опционально |
| **Multi-tenant** | Один сервер = много объектов (дачи, офисы, склады) |
| **Zero-config discovery** | ONVIF/UPnP/mDNS автопоиск камер и устройств |
| **Offline-capable client** | Flutter кэширует состояние, синхронизируется при связи |
| **Plugin architecture** | Детекторы, актуаторы, уведомления — подключаемые модули |

---

## 2. Server Backend (SuperGuard Core v2)

### 2.1 Технологический стек
| Компонент | Выбор | Обоснование |
|-----------|-------|-------------|
| **Language** | Python 3.11+ | Текущая кодовая база, ML экосистема |
| **Async Framework** | FastAPI + Uvicorn | Высокая производительность, OpenAPI, WebSockets |
| **Message Bus** | Redis Streams | Простота, pub/sub, persistence, работает на Win/Linux |
| **Database** | SQLite (embedded) + SQLAlchemy 2.0 | Zero-config, ACID, легко бэкапить файл |
| **Auth** | JWT + bcrypt | Stateless, стандарт индустрии |
| **Video Proxy** | MediaMTX (Go) | RTSP→WebRTC/HLS, работает на Win/Linux, нет зависимостей |
| **ML Inference** | ONNX Runtime + YOLO11n | Кросс-платформенно, быстрее PyTorch, нет CUDA деплоя |
| **Config** | Pydantic Settings + YAML | Валидация, env override, типизация |
| **Logging** | structlog + OpenTelemetry | JSON logs, tracing, metrics |
| **Packaging** | PyInstaller (Win) / systemd (Ubuntu) | Нативные исполняемые файлы |

### 2.2 Архитектура модулей (Plugin System)
```
superguard-core/
├── core/
│   ├── config.py          # Pydantic Settings, YAML + env
│   ├── database.py        # SQLAlchemy models, migrations (Alembic)
│   ├── auth.py            # JWT, roles, permissions
│   ├── events.py          # Event bus (Redis Streams)
│   └── plugins.py         # Plugin loader, entry points
├── plugins/
│   ├── cameras/
│   │   ├── base.py        # CameraPlugin ABC
│   │   ├── rtsp.py        # RTSP/ONVIF
│   │   ├── hls.py         # HLS/DASH
│   │   ├── jpg.py         # JPEG snapshot
│   │   ├── onvif.py       # ONVIF Profile S/T/G
│   │   └── webcam.py      # Local USB/MIPI
│   ├── detectors/
│   │   ├── base.py        # DetectorPlugin ABC
│   │   ├── yolo_onnx.py   # YOLO11n ONNX Runtime
│   │   ├── yolo_trt.py    # TensorRT (optional, GPU)
│   │   ├── motion.py      # Classic motion detection
│   │   └── custom.py      # User Python scripts
│   ├── actuators/
│   │   ├── base.py        # ActuatorPlugin ABC
│   │   ├── tuya_local.py  # Tuya LAN protocol
│   │   ├── tuya_cloud.py  # Tuya IoT Cloud
│   │   ├── sonoff.py      # eWeLink API / MQTT
│   │   ├── shelly.py      # Shelly HTTP/CoAP/MQTT
│   │   ├── tasmota.py     # Tasmota HTTP/MQTT
│   │   └── gpio.py        # Local relays (RPi/OrangePi)
│   ├── notifiers/
│   │   ├── base.py        # NotifierPlugin ABC
│   │   ├── telegram.py    # Telegram Bot API
│   │   ├── push.py        # Pushover, Firebase FCM
│   │   ├── email.py       # SMTP
│   │   ├── webhook.py     # Generic HTTP webhooks
│   │   └── mqtt.py        # Home Assistant MQTT
│   └── storage/
│       ├── base.py        # StoragePlugin ABC
│       ├── local.py       # Local filesystem
│       ├── s3.py          # S3/MinIO
│       └── ftp.py         # FTP/SFTP
├── api/
│   ├── routes/
│   │   ├── auth.py        # /auth/*
│   │   ├── sites.py       # /sites/* (multi-tenant)
│   │   ├── cameras.py     # /cameras/*
│   │   ├── detectors.py   # /detectors/*
│   │   ├── actuators.py   # /actuators/*
│   │   ├── alarms.py      # /alarms/* (WebSocket)
│   │   ├── media.py       # /media/* (WebRTC/HLS proxy)
│   │   └── system.py      # /system/* (health, logs, backup)
│   └── websocket.py       # Real-time updates
├── services/
│   ├── camera_manager.py  # Lifecycle, reconnection, recording
│   ├── detection_engine.py # Pipeline orchestration
│   ├── alarm_engine.py    # Alarm logic, cooldowns, escalation
│   ├── actuator_engine.py # Command queue, retry, state sync
│   ├── recording_service.py # MP4 segments, retention
│   └── discovery_service.py # ONVIF/UPnP/mDNS scanning
��── main.py                # FastAPI app factory
```

### 2.3 База данных (SQLAlchemy Models)
```python
# core/models.py
class Site(Base):              # Объект охраны (дача, офис)
    id, name, timezone, lat, lon, created_at

class Camera(Base):            # Камера
    id, site_id, name, type, url, username, password,
    onvif_profile, zone_config, detector_id, enabled, position

class Detector(Base):          # Детектор
    id, site_id, name, plugin, config (JSON), classes, thresholds

class Actuator(Base):          # Исполнительный механизм
    id, site_id, name, plugin, config (JSON), camera_bindings (JSON)

class Alarm(Base):             # Тревога
    id, site_id, camera_id, detector_id, status, started_at,
    ended_at, acknowledged_at, acknowledged_by, media_refs (JSON)

class AlarmMedia(Base):        # Медиа тревоги
    id, alarm_id, type (frame/video), path, timestamp, metadata (JSON)

class User(Base):              # Пользователь
    id, email, password_hash, role (admin/operator/viewer), sites (M2M)

class NotificationRule(Base):  # Правила уведомлений
    id, site_id, trigger, notifier_plugin, config, schedule
```

### 2.4 API Contract (OpenAPI — ключевые эндпоинты)

#### Authentication
```
POST   /auth/login              # email/password → JWT
POST   /auth/refresh            # refresh token
GET    /auth/me                 # current user + permissions
```

#### Sites (Multi-tenancy)
```
GET    /sites                   # List user's sites
POST   /sites                   # Create site
GET    /sites/{id}              # Site details
PATCH  /sites/{id}              # Update site
DELETE /sites/{id}              # Delete site
GET    /sites/{id}/dashboard    # Aggregated status for UI
```

#### Cameras
```
GET    /sites/{site_id}/cameras
POST   /sites/{site_id}/cameras              # Add camera (with ONVIF discovery)
GET    /sites/{site_id}/cameras/{id}
PATCH  /sites/{site_id}/cameras/{id}
DELETE /sites/{site_id}/cameras/{id}
POST   /sites/{site_id}/cameras/{id}/test    # Test connection
GET    /sites/{site_id}/cameras/{id}/stream  # WebRTC/HLS stream URL
GET    /sites/{site_id}/cameras/{id}/snapshot
POST   /sites/{site_id}/cameras/discover     # ONVIF/UPnP scan
```

#### Detectors
```
GET    /sites/{site_id}/detectors
POST   /sites/{site_id}/detectors
GET    /sites/{site_id}/detectors/{id}
PATCH  /sites/{site_id}/detectors/{id}
DELETE /sites/{site_id}/detectors/{id}
POST   /sites/{site_id}/detectors/{id}/test  # Test on frame
```

#### Actuators
```
GET    /sites/{site_id}/actuators
POST   /sites/{site_id}/actuators
GET    /sites/{site_id}/actuators/{id}
PATCH  /sites/{site_id}/actuators/{id}
DELETE /sites/{site_id}/actuators/{id}
POST   /sites/{site_id}/actuators/{id}/test
POST   /sites/{site_id}/actuators/{id}/command  # {action: on/off/toggle}
```

#### Alarms (Real-time via WebSocket)
```
GET    /sites/{site_id}/alarms              # History with filters
GET    /sites/{site_id}/alarms/{id}
GET    /sites/{site_id}/alarms/{id}/media
WS     /sites/{site_id}/alarms/ws           # Real-time alarm events
```

#### System
```
GET    /system/health
GET    /system/metrics                      # Prometheus format
GET    /system/logs
POST   /system/backup                       # SQLite backup
POST   /system/restore                      # Restore from backup
GET    /system/plugins                      # Available plugins
```

---

## 3. Flutter Client (SuperGuard Mobile/Desktop)

### 3.1 Выбор Flutter — обоснование
| Критерий | Flutter | React Native | Tauri | Native |
|----------|---------|--------------|-------|--------|
| **iOS/Android** | �� | �� | �� | ��� (2x) |
| **Windows/macOS/Linux** | �� | ������ | �� | ��� (3x) |
| **Web** | �� | �� | ������ | ��� |
| **Video (WebRTC/HLS)** | �� (flutter_webrtc) | �� | �� | �� |
| **Single codebase** | �� 100% | ~90% | ~80% | 0% |
| **Performance** | Native AOT | JSI Bridge | Native Rust | Best |
| **Team skills** | Dart прост | JS/TS | Rust сложнее | Специалисты |
| **Итог** | **В��БОР** | Альтернатива | Для embedded | Нет |

### 3.2 Архитектура Flutter App
```
lib/
├── core/
│   ├── config.dart           # App config, flavors (dev/staging/prod)
│   ├── api/
│   │   ├── client.dart       # Dio + interceptors (auth, retry)
│   │   ├── endpoints.dart    # API paths
│   │   └── models/           # Freezed/JSON serializable models
│   ├── auth/
│   │   ├── auth_service.dart # JWT storage, refresh, biometric
│   │   └── tokens.dart       # Secure storage (flutter_secure_storage)
│   ├── database/
│   │   └── drift_db.dart     # Local cache (Drift/SQLite)
│   ├── events/
│   │   └── event_bus.dart    # Stream-based local events
│   └── theme/
│       └── app_theme.dart    # Material 3, dark/light, brand colors
├── features/
│   ├── auth/
│   │   ├── login_screen.dart
│   │   ├── register_screen.dart (admin only)
│   │   └── pin_biometric.dart
│   ├── sites/
│   │   ├── site_list_screen.dart
│   │   ├── site_detail_screen.dart (Dashboard)
│   │   ├── site_setup_wizard.dart  # ��� NEW: пошаговая настройка
│   │   └── widgets/
│   │       ├── site_card.dart
│   │       └── site_status_chip.dart
│   ├── cameras/
│   │   ├── camera_list_screen.dart
│   │   ├── camera_detail_screen.dart
│   │   ├── camera_add_wizard.dart     # ��� Discovery + manual
│   │   ├── camera_test_screen.dart
│   │   ├── camera_zone_editor.dart    # ��� Grid N×M editor
│   │   └── widgets/
│   │       ├── camera_preview.dart    # WebRTC/HLS player
│   │       ├── camera_grid.dart
│   │       └── ptz_controls.dart
│   ├── detectors/
│   │   ├── detector_list_screen.dart
│   │   ├── detector_config_screen.dart
│   │   ├── detector_test_screen.dart  # Test on live frame
│   │   └── widgets/
│   │       └── detection_overlay.dart # YOLO boxes overlay
│   ├── actuators/
│   │   ├── actuator_list_screen.dart
│   │   ├── actuator_add_wizard.dart   # Tuya/Sonoff/Shelly setup
│   │   ├── actuator_control_screen.dart
│   │   └── widgets/
│   │       ├── actuator_switch.dart
│   │       └── actuator_binding_editor.dart # Camera ↔ Actuator
│   ├── alarms/
│   │   ├── alarm_list_screen.dart     # History with filters
│   │   ├── alarm_detail_screen.dart   # Media gallery
│   │   ├── alarm_live_screen.dart     # ��� Real-time alarm view
│   │   └── widgets/
│   │       ├── alarm_card.dart
│   │       ├── alarm_media_gallery.dart
│   │       └── alarm_timeline.dart
│   ├── notifications/
│   │   ├── notification_settings_screen.dart
│   │   ├── notification_test_screen.dart
│   │   └── widgets/
│   │       └── notifier_config_form.dart
│   └── settings/
│       ├── general_settings_screen.dart
│       ├── appearance_screen.dart
│       ├── backup_restore_screen.dart
│       └── about_screen.dart
├── shared/
│   ├── widgets/
│   │   ├── app_scaffold.dart
│   │   ├── loading_overlay.dart
│   │   ├── error_banner.dart
│   │   ├── confirmation_dialog.dart
│   │   ├── pull_to_refresh.dart
│   │   └── empty_state.dart
│   ├── extensions/
│   └── utils/
��── main.dart                 # Entry point, flavors, routing (go_router)
```

### 3.3 Ключевые UI/UX решения

#### ��� Site Setup Wizard (Настройка нового объекта — 5 шагов)
```
Step 1: Basic Info          → Name, address, timezone, photo
Step 2: Network             → WiFi scan, hotspot config, test connectivity
Step 3: Cameras             → ONVIF scan → select → test → zone grid
Step 4: Actuators           → Tuya/Sonoff/Shelly discovery → bind to cameras
Step 5: Detectors & Rules   → Choose detector → test → notification rules
Step 6: Review & Activate   → Summary → "Start Protection"
```

#### ��� Camera Zone Editor (Grid N×M)
- Интерактивная сетка поверх live preview
- Tap ячейки = toggle active/inactive
- Pinch-to-zoom для точной настройки
- Пресеты: "Perimeter", "Entry Zone", "Parking", "Custom"

#### ��� Alarm Live View
- Fullscreen WebRTC с YOLO overlay (boxes + labels + confidence)
- Крупные кнопки: ��� ACKNOWLEDGE | ��� SILENCE | ��� RECORD | ��� CALL
- Swipe down = minimize to picture-in-picture
- Haptic feedback на критических действиях

#### ��� Actuator Binding Matrix
```
           Camera 1  Camera 2  Camera 3  Camera 4
Plug 1     �����        �����        ��         ��
Plug 2     ��         ��         �����        �����
Siren      �����        �����        �����        �����
```
- Drag-and-drop binding
- Test кнопка на каждой ячейке

### 3.4 Офлайн-режим и синхронизация
```dart
// Drift (SQLite) локальный кэш
@Table()
class CachedSite {
  IntColumn get id => integer().autoIncrement()();
  TextColumn get serverId => text()();
  TextColumn get name => text()();
  TextColumn get dataJson => text().map(jsonDecode)(); // Full site snapshot
  DateTimeColumn get lastSynced => dateTime()();
  BoolColumn get hasPendingChanges => boolean().withDefault(false)();
}

// Синхронизация при появлении сети
class SyncService {
  Future<void> sync() async {
    if (!await _connectivity.hasConnection) return;
    await _pushPendingChanges();
    await _pullServerUpdates();
    await _resolveConflicts(); // Last-write-wins + user prompt для критических
  }
}
```

---

## 4. Deployment Strategy (Windows + Ubuntu)

### 4.1 Windows (Production)
```yaml
# superguard-windows.yaml (NSSM + MediaMTX)
services:
  superguard-core:
    image: superguard/core:latest-windows
    # OR PyInstaller executable
    command: superguard-core.exe serve --config C:\SuperGuard\config.yaml
    restart: always
    volumes:
      - C:\SuperGuard\data:/data
      - C:\SuperGuard\config.yaml:/config.yaml
    ports:
      - "8080:8080"   # API
      - "8081:8081"   # MediaMTX HTTP
      - "8082:8082"   # MediaMTX WebRTC
    environment:
      - REDIS_URL=redis://localhost:6379
  
  redis:
    image: redis:7-alpine
    volumes:
      - C:\SuperGuard\redis:/data
  
  mediamtx:
    image: bluenviron/mediamtx:v1.8
    volumes:
      - C:\SuperGuard\mediamtx.yml:/mediamtx.yml
    ports:
      - "8554:8554"  # RTSP
      - "8888:8888"  # HLS
      - "8889:8889"  # WebRTC
```

**Installer:** Inno Setup / NSIS → `SuperGuard-Setup-x64.exe`
- Устанавливает: Python embedded, MediaMTX, Redis, SuperGuard Core
- Настраивает: NSSM сервисы, Firewall правила, автозапуск
- Создаёт: ярлыки, деинсталлятор

### 4.2 Ubuntu Server (Production)
```yaml
# docker-compose.yml
version: '3.8'
services:
  superguard-core:
    image: superguard/core:latest-linux
    command: superguard-core serve --config /etc/superguard/config.yaml
    restart: unless-stopped
    volumes:
      - /opt/superguard/data:/data
      - /etc/superguard/config.yaml:/config.yaml
    ports:
      - "8080:8080"
    environment:
      - REDIS_URL=redis://redis:6379
    depends_on:
      - redis
  
  redis:
    image: redis:7-alpine
    volumes:
      - /opt/superguard/redis:/data
  
  mediamtx:
    image: bluenviron/mediamtx:v1.8
    volumes:
      - /etc/superguard/mediamtx.yml:/mediamtx.yml
    ports:
      - "8554:8554"
      - "8888:8888"
      - "8889:8889"
  
  nginx:
    image: nginx:alpine
    volumes:
      - /etc/superguard/nginx.conf:/etc/nginx/nginx.conf
      - /etc/letsencrypt:/etc/letsencrypt:ro
    ports:
      - "80:80"
      - "443:443"
    depends_on:
      - superguard-core
      - mediamtx
```

**Systemd units:** `/etc/systemd/system/superguard-*.service`
- Автостарт, логи в journald, watchdog внутри контейнера

### 4.3 Обновления (OTA)
```python
# Core самопроверка обновлений
class UpdateService:
    async def check_update(self) -> UpdateInfo:
        # GitHub Releases API / приватный репозиторий
        # Подпись cosign/sigstore для верификации
    
    async def apply_update(self, info: UpdateInfo):
        # Blue-green: скачивает новую версию → health check → switch
        # Rollback на неудачу
```

---

## 5. План развития по фазам (Roadmap to RC)

### Phase 0: Foundation (Неделя 1-2) �� PARTIALLY DONE
- [x] Core detection + Telegram bot working
- [x] Actuators with ARP rediscovery
- [x] Watchdog + Windows Service
- [ ] **NEW:** Extract current logic into plugins (cameras, detectors, actuators)
- [ ] **NEW:** FastAPI skeleton with auth + SQLite + Redis
- [ ] **NEW:** MediaMTX integration for WebRTC/HLS
- [ ] **NEW:** OpenAPI spec generation

### Phase 1: Server Core MVP (Неделя 3-5)
| Sprint | Deliverable |
|--------|-------------|
| 1 | FastAPI + Auth (JWT) + Sites CRUD + Camera CRUD + ONVIF discovery |
| 2 | Detector plugins (YOLO ONNX) + Detection engine + Alarm engine |
| 3 | Actuator plugins (Tuya local/cloud, Sonoff, Shelly) + Binding matrix |
| 4 | Notifier plugins (Telegram, Push, Email, Webhook, MQTT) |
| 5 | Recording service (MP4 segments) + MediaMTX WebRTC proxy |
| 6 | WebSocket real-time alarms + API docs + Integration tests |

### Phase 2: Flutter Client MVP (Неделя 6-9)
| Sprint | Deliverable |
|--------|-------------|
| 1 | Project setup: flavors, routing, theme, API client, auth flow, secure storage |
| 2 | Site List + Site Setup Wizard (6 steps) + Dashboard |
| 3 | Camera management: list, add wizard (ONVIF scan), test, zone editor |
| 4 | Detector config + test on live frame |
| 5 | Actuator management: add wizard, binding matrix, manual control |
| 6 | Alarm history + Live alarm view (WebRTC + YOLO overlay) + ACK/SILENCE |
| 7 | Notifications settings + Test notifications |
| 8 | Offline cache (Drift) + Sync service + Settings/Backup/Restore |
| 9 | Polish: animations, haptics, PiP, accessibility, iOS/Android build |

### Phase 3: Hardening & RC (Неделя 10-12)
| Sprint | Deliverable |
|--------|-------------|
| 1 | Windows Installer (Inno Setup) + Ubuntu systemd + Docker Compose |
| 2 | OTA updates (signed) + Rollback + Health checks |
| 3 | Load testing (10 sites × 20 cameras) + Stress tests |
| 4 | Security audit: pentest, dependency scan, secrets audit |
| 5 | Documentation: User Guide, Admin Guide, API Reference, Plugin Dev Guide |
| 6 | **RC Release**: GitHub Release + Changelog + Migration guide from v1 |

---

## 6. Миграция от текущей версии (v1 → v2)

### 6.1 Стратегия: Parallel Run
```
CURRENT (v1)                    NEW (v2 RC)
────────────────────────────────────────────────
run_bot.py          ──────────��  superguard-core (FastAPI)
watchdog.py         ──────────��  systemd/NSSM + health checks
Telegram Bot        ──────────��  Notifier Plugin (Telegram)
sguard.env          ──────────��  config.yaml + env override
sguard_settings.json─────────��  SQLite (sites, cameras, actuators)
desktop_state/      ──────────��  Redis Streams + WebSocket
```

### 6.2 Миграционный скрипт
```python
# scripts/migrate_v1_to_v2.py
async def migrate():
    # 1. Читаем sguard.env + sguard_settings.json
    # 2. Создаём Site "Main Site"
    # 3. Импортируем 8 камер → Camera records
    # 4. Импортируем 2 розетки → Actuator records + bindings
    # 5. Создаём Detector "YOLO11n Default" с текущими порогами
    # 6. Создаём Notifier "Telegram Legacy" с текущим токеном
    # 7. Создаём Admin пользователя
    # 8. Генерируем config.yaml для v2
```

### 6.3 Обратная совместимость
- v2 API включает `/legacy/*` эндпоинты для старого бота
- Telegram бот продолжает работать как Notifier Plugin
- Watchdog v1 может мониторить v2 через `/system/health`

---

## 7. Plugin Development Guide (для расширяемости)

### 7.1 Пример Camera Plugin
```python
# plugins/cameras/my_camera.py
from superguard.core.plugins import CameraPlugin, CameraFrame

class MyCameraPlugin(CameraPlugin):
    name = "my_camera"
    version = "1.0.0"
    config_schema = MyCameraConfig  # Pydantic model
    
    async def connect(self, config: MyCameraConfig) -> None:
        self._cap = cv2.VideoCapture(config.rtsp_url)
    
    async def read_frame(self) -> CameraFrame:
        ret, frame = self._cap.read()
        return CameraFrame(image=frame, timestamp=time.time())
    
    async def disconnect(self) -> None:
        self._cap.release()
    
    @classmethod
    def discover(cls) -> list[DiscoveredCamera]:
        # ONVIF/UPnP/mDNS сканирование
        return [...]

# Регистрация через entry_points в pyproject.toml:
# [project.entry-points."superguard.cameras"]
# my_camera = "plugins.cameras.my_camera:MyCameraPlugin"
```

### 7.2 Пример Detector Plugin
```python
# plugins/detectors/my_detector.py
from superguard.core.plugins import DetectorPlugin, Detection, ProcessedFrame

class MyDetectorPlugin(DetectorPlugin):
    name = "my_detector"
    config_schema = MyDetectorConfig
    
    async def initialize(self, config: MyDetectorConfig) -> None:
        self.model = load_model(config.model_path)
    
    async def process(self, frame: np.ndarray) -> ProcessedFrame:
        detections = self.model.infer(frame)
        return ProcessedFrame(
            frame=frame,
            annotated=draw_boxes(frame, detections),
            matches=[d for d in detections if d.confidence > self.config.threshold],
            timestamp=time.time()
        )
```

---

## 8. Безопасность (Security Hardening)

| Мера | Реализация |
|------|------------|
| **Auth** | JWT (RS256), access 15m, refresh 7d, rotation |
| **Roles** | Admin (full), Operator (control), Viewer (read) |
| **API** | Rate limiting (100 req/min), CORS, Helmet headers |
| **Secrets** | HashiCorp Vault / SOPS / age encryption для config |
| **TLS** | Let's Encrypt (prod) / self-signed (dev) через nginx |
| **Video** | WebRTC DTLS-SRTP, HLS с подписанными URL |
| **Audit Log** | Все действия в БД + Structured logs |
| **Supply Chain** | Sigstore cosign для подписи релизов, SBOM (Syft) |

---

## 9. Мониторинг и Observability

### 9.1 Metrics (Prometheus + Grafana)
```yaml
# Ключевые метрики
- superguard_cameras_total{site,status}
- superguard_detection_fps{site,camera,detector}
- superguard_alarm_total{site,status,detector}
- superguard_actuator_commands_total{site,actuator,action,result}
- superguard_api_request_duration_seconds{endpoint,method}
- superguard_websocket_connections{site}
- superguard_recording_disk_usage_bytes{site}
```

### 9.2 Alerts (Alertmanager → Telegram/Email/PagerDuty)
- Camera offline > 60s
- Detection FPS < 1 for 5min
- Disk usage > 80%
- Memory > 90%
- Failed actuator commands > 3 in row

### 9.3 Distributed Tracing (OpenTelemetry → Jaeger)
- Trace: HTTP request → Detection → Alarm → Notification
- Latency percentiles per component

---

## 10. Тестирование (Quality Gates)

| Уровень | Инструменты | Цель |
|---------|-------------|------|
| **Unit** | pytest, pytest-asyncio, hypothesis | >90% coverage core logic |
| **Integration** | testcontainers (Redis, PostgreSQL), httpx | API contracts, plugin lifecycle |
| **Contract** | schemathesis (OpenAPI) | API backward compatibility |
| **E2E** | Flutter integration_test + patrol | User flows: setup, alarm, control |
| **Load** | k6 / Locust | 10 sites × 20 cams × 5 fps |
| **Chaos** | chaos-mesh (k8s) / manual | Network partition, process kill |
| **Security** | bandit, safety, trivy, OWASP ZAP | 0 critical/high vulnerabilities |

---

## 11. Риски и митигация

| Риск | Вероятность | Влияние | Митигация |
|------|-------------|---------|-----------|
| Flutter WebRTC нестабилен на iOS | Medium | High | Fallback на HLS, нативный модуль при необходимости |
| MediaMTX не тянет 20+ камер | Low | Medium | Горизонтальное масштабирование (multiple instances) |
| ONVIF discovery не находит все камеры | Medium | Low | Ручной ввод + профили вендоров |
| YOLO ONNX медленнее PyTorch | Low | Medium | TensorRT плагин для GPU, батчинг |
| Windows installer антивирусы блокируют | Medium | Low | Code signing (EV сертификат), SmartScreen reputation |
| Миграция v1→v2 ломает настройки | Low | High | Автотест миграции на реальных конфигах, rollback |

---

## 12. Команда и ресурсы (для одного разработчика)

| Роль | Недели | Комментарий |
|------|--------|-------------|
| Backend Developer (Python) | 12 | Основная нагрузка |
| Flutter Developer | 9 | Может начать с Phase 1 Sprint 3 |
| DevOps/Platform | 3 (part-time) | Installers, CI/CD, серверная инфра |
| QA/Testing | 2 (part-time) | E2E тесты, нагрузочное тестирование |
| Technical Writer | 1 (part-time) | Документация к RC |

**Итого: ~12 недель (3 месяца) до RC** при фуллтайме бэкенда + параллельный Flutter.

---

## 13. Definition of Done (RC Criteria)

### Functional
- [ ] Site Setup Wizard: новый объект за 5 минут без CLI
- [ ] Camera: ONVIF discovery + manual + zone editor + PTZ
- [ ] Detector: YOLO ONNX + custom classes + test on frame
- [ ] Actuator: Tuya/Sonoff/Shelly + binding matrix + manual control
- [ ] Alarm: Real-time WebSocket + WebRTC live + ACK/SILENCE + media gallery
- [ ] Notifications: Telegram/Push/Email/Webhook/MQTT + test button
- [ ] Recording: MP4 segments + retention + download
- [ ] Offline: Flutter works offline, syncs on reconnect
- [ ] Multi-tenant: изоляция сайтов, роли пользователей

### Technical
- [ ] Windows Installer (x64) + Ubuntu systemd + Docker Compose
- [ ] OTA updates с подписью и rollback
- [ ] OpenAPI 3.1 spec + Swagger UI
- [ ] Prometheus metrics + Grafana dashboards
- [ ] Structured JSON logs + OpenTelemetry tracing
- [ ] 0 critical vulns (trivy, bandit, safety)
- [ ] Unit coverage > 80%, Integration tests all green

### Documentation
- [ ] User Guide (PDF + Web)
- [ ] Admin Guide (deployment, config, backup)
- [ ] API Reference (auto-generated)
- [ ] Plugin Development Guide
- [ ] Migration Guide v1 → v2
- [ ] Changelog + Upgrade Notes

---

## 14. Следующие шаги (Immediate Action Items)

### На этой неделе:
1. **Создать репозиторий `superguard-core`** с FastAPI skeleton
2. **Вынести текущие модули в плагины** (cameras, detectors, actuators, notifiers)
3. **Настроить CI/CD** (GitHub Actions: lint, test, build, docker push)
4. **Написать OpenAPI spec** для всех эндпоинтов
5. **Настроить MediaMTX** + WebRTC тест

### Flutter (можно начать параллельно):
1. `flutter create superguard_client --platforms=ios,android,windows,linux,macos,web`
2. Настроить: go_router, dio, freezed, drift, flutter_secure_storage, flutter_webrtc
3. Реализовать Auth flow + Site List + Dashboard skeleton

---

## 15. Заключение

Этот план трансформирует SuperGuard из **"работающего скрипта для одной дачи"** в **"продуктовый Security Platform"**:

| Аспект | Текущее (v1) | RC (v2) |
|--------|--------------|---------|
| **Архитектура** | Монолитный скрипт | Plugin-based microservices |
| **Платформы** | Windows only | Windows + Ubuntu + ARM |
| **UI** | Telegram Bot | Flutter (Mobile/Desktop/Web) |
| **Мультитенантность** | Нет | Полная (sites, users, roles) |
| **Камеры** | 8 hardcoded | Unlimited + ONVIF discovery |
| **Детекторы** | YOLO only | Plugin system (YOOL, Motion, Custom) |
| **Актуаторы** | Tuya only | Tuya/Sonoff/Shelly/Tasmota/GPIO |
| **Уведомления** | Telegram only | 5+ каналов + Webhook/MQTT |
| **Видео** | MJPEG snapshots | WebRTC/HLS/MP4 recording |
| **Офлайн** | Нет | Full offline + sync |
| **Деплой** | NSSM руками | Installer + Docker + systemd |
| **Обновления** | Git pull | OTA signed + rollback |
| **Мониторинг** | status.json | Prometheus + Grafana + Alerting |

**Готовность к старту Phase 1: 90%** — база есть, плагины выделены, схема БД готова.

---

*План создан на основе аудита текущего кодовой базы и архитектурного видения RC (2025-08-14)*