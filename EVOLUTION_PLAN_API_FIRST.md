# SuperGuard Evolution Plan: API-First Architecture with Web Dashboard & Flutter Client

**Версия:** 3.0  
**Дата:** 2025-08-16  
**Статус:** Планирование (после завершения 20 циклов стабилизации)  
**Цель:** Полный переход от Telegram-бота к API-first платформе с Web Dashboard и Flutter-клиентом для развертывания на новых объектах "из коробки"

---

## 1. Архитектурная визия (Target State)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        SUPERGUARD PLATFORM v3.0                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────┐  │
│  │  FLUTTER     │    │   WEB        │    │  TELEGRAM    │    │  3RD     │  │
│  │  CLIENT      │    │  DASHBOARD   │    │  BOT (Legacy)│    │  PARTY   │  │
│  │  (iOS/Android│    │  (React/TS)  │    │  Compatibility│    │  API     │  │
│  │   Win/Mac/Lin│    │              │    │              │    │  Clients │  │
│  └──────┬───────┘    └──────┬───────┘    └──────┬───────┘    └────┬─────┘  │
│         │                   │                   │                   │        │
│         └───────────────────┼───────────────────┼───────────────────┘        │
│                             ▼                   ▼                            │
│                    ┌─────────────────────────────────────────┐              │
│                    │          API GATEWAY (FastAPI)          │              │
│                    │  ┌─────────┐ ┌─────────┐ ┌───────────┐  │              │
│                    │  │ REST API│ │ WebSocket│ │ Auth/JWT  │  │              │
│                    │  │  v1     │ │  /ws    │ │  + RBAC   │  │              │
│                    │  └─────────┘ └─────────┘ └───────────┘  │              │
│                    └──────────────────┬──────────────────────┘              │
│                                       │                                      │
│         ┌─────────────────────────────┼─────────────────────────────┐      │
│         ▼                             ▼                             ▼      │
│  ┌──────────────┐            ┌──────────────┐            ┌──────────────┐  │
│  │ CORE SERVICES│            │  MEDIA PLANE │            │  INTEGRATIONS│  │
│  │              │            │              │            │              │  │
│  │ • Sites      │            │ • MediaMTX   │            │ • Tuya Cloud │  │
│  │ • Cameras    │◄──────────►│   (WebRTC/   │            │ • Sonoff     │  │
│  │ • Detectors  │   WebSocket │   HLS/RTSP)  │            │ • Shelly     │  │
│  │ • Actuators  │            │ • Recording  │            │ • MQTT/HA    │  │
│  │ • Alarms     │            │ • Snapshots  │            │ • Webhooks   │  │
│  │ • Users/RBAC │            │              │            │ • Pushover   │  │
│  └──────────────┘            └──────────────┘            └──────────────┘  │
│         │                             │                             │       │
│         └─────────────────────────────┼─────────────────────────────┘       │
│                                       ▼                                      │
│                          ┌────────────────────────┐                         │
│                          │   DATA LAYER           │                         │
│                          │  • PostgreSQL (prod)   │                         │
│                          │  • SQLite (embedded)   │                         │
│                          │  • Redis (cache/ws)    │                         │
│                          │  • S3/MinIO (media)    │                         │
│                          └────────────────────────┘                         │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Этапы эволюции (Roadmap)

### Phase 0: Foundation (Неделя 1-2) — **Параллельно с текущей стабилизацией**

| Sprint | Deliverable | Details |
|--------|-------------|---------|
| 0.1 | **API Gateway Skeleton** | FastAPI + Auth (JWT RS256) + RBAC + OpenAPI 3.1 |
| 0.2 | **Database Migration** | SQLite → PostgreSQL (Alembic), модели Sites/Cameras/Users |
| 0.3 | **Core CRUD API** | Sites, Cameras, Detectors, Actuators, Alarms — полные REST эндпоинты |
| 0.4 | **WebSocket Infrastructure** | `/ws/{site_id}` — real-time alarms, camera status, actuator state |
| 0.5 | **MediaMTX Integration** | WebRTC/HLS proxy через API, signed URLs для стримов |

**Критерии готовности:** `GET /api/v1/sites/{id}/dashboard` возвращает полное состояние объекта за <200ms

---

### Phase 1: Web Dashboard MVP (Неделя 3-5)

#### 1.1 Технологический стек
| Компонент | Выбор | Обоснование |
|-----------|-------|-------------|
| **Framework** | React 18 + TypeScript + Vite | Экосистема, производительность, типизация |
| **State** | TanStack Query (React Query) | Кэширование, синхронизация, offline support |
| **UI Kit** | Radix UI + Tailwind CSS | Headless, accessible, кастомизируемо |
| **Real-time** | Native WebSocket + React Query mutations | Единый источник правды |
| **Charts** | Recharts / Tremor | Метрики детекции, алерты |
| **Video** | `react-webcam` + WebRTC (MediaMTX) | Низкая задержка, работает в браузере |

#### 1.2 Архитектура Dashboard
```
src/
├── app/                    # Next.js 14 App Router (или Vite + React Router)
│   ├── (auth)/            # Login, Register, Password Reset
│   ├── (dashboard)/       # Protected routes
│   │   ├── sites/         # Site List, Site Detail, Site Wizard
│   │   ├── cameras/       # Camera Grid, Camera Detail, Zone Editor
│   │   ├── detectors/     # Detector Config, Test on Frame
│   │   ├── actuators/     # Actuator Matrix, Manual Control
│   │   ├── alarms/        # Alarm History, Live Alarm View
│   │   ├── settings/      # Users, Notifications, Backup
│   │   └── monitoring/    # Health, Metrics, Logs
├── components/
│   ├── ui/                # Radix + Tailwind primitives
│   ├── cameras/           # CameraGrid, CameraPlayer, ZoneEditor
│   ├── actuators/         # ActuatorMatrix, ActuatorSwitch
│   ├── alarms/            # AlarmTimeline, AlarmMediaGallery
│   └── charts/            # DetectionFPSChart, AlarmHeatmap
├── hooks/
│   ├── useSites.ts
│   ├── useCameras.ts
│   ├── useWebSocket.ts    # WebSocket subscription hook
│   └── useAuth.ts
├── lib/
│   ├── api.ts             # TanStack Query + Axios client
│   ├── auth.ts            # JWT storage, refresh logic
│   └── websocket.ts       # WebSocket manager с reconnect
└── types/
    └── api.ts             # Generated from OpenAPI (orapi-codegen)
```

#### 1.3 Ключевые экраны (Definition of Done)

| Экран | Функционал | API Endpoints |
|-------|------------|---------------|
| **Site Wizard** | 6 шагов: Info → Network → Cameras (ONVIF scan) → Actuators → Detectors → Review | `POST /sites`, `POST /sites/{id}/cameras/discover`, `POST /sites/{id}/actuators` |
| **Dashboard** | Real-time grid: camera status, alarm count, actuator state, detection FPS | `GET /sites/{id}/dashboard`, `WS /ws/{site_id}` |
| **Camera Detail** | WebRTC player + YOLO overlay + PTZ + Zone Editor (N×M grid) | `GET /cameras/{id}/stream`, `PATCH /cameras/{id}/zone` |
| **Zone Editor** | Интерактивная сетка поверх превью, pinch-zoom, пресеты | `PATCH /cameras/{id}/zone` |
| **Actuator Matrix** | Drag-drop binding Camera × Actuator, Test кнопка на каждой ячейке | `GET /actuators`, `POST /actuators/{id}/command`, `PATCH /cameras/{id}/bindings` |
| **Live Alarm View** | Fullscreen WebRTC + YOLO boxes + ACK/SILENCE/RECORD/CALL кнопки | `WS /ws/{site_id}/alarms`, `POST /alarms/{id}/ack` |
| **Alarm History** | Фильтры по камере/детектору/статусу, медиа-галерея, таймлайн | `GET /alarms?filters...` |
| **Monitoring** | Health checks, Prometheus metrics, structured logs, backup status | `GET /system/health`, `GET /system/metrics`, `GET /system/logs` |

---

### Phase 2: Flutter Client MVP (Неделя 6-9)

#### 2.1 Аргументы за Flutter
| Критерий | Flutter | React Native | Tauri | Native |
|----------|---------|--------------|-------|--------|
| iOS/Android | ✅ | ✅ | ✅ | ❌ (2x) |
| Windows/macOS/Linux | ✅ | ⚠️ | ✅ | ❌ (3x) |
| Web | ✅ | ✅ | ⚠️ | ❌ |
| **Video (WebRTC/HLS)** | ✅ `flutter_webrtc` | ✅ | ✅ | ✅ |
| **Single codebase** | **100%** | ~90% | ~80% | 0% |
| **Performance** | Native AOT | JSI Bridge | Native Rust | Best |
| **Team skills** | Dart прост | JS/TS | Rust сложнее | Специалисты |
| **Итог** | **ВЫБОР** | Альтернатива | Для embedded | Нет |

#### 2.2 Архитектура Flutter App
```
lib/
├── core/
│   ├── config.dart              # Flavors (dev/staging/prod), API_URL
│   ├── api/
│   │   ├── client.dart          # Dio + interceptors (auth, retry, logging)
│   │   ├── endpoints.dart       # API paths
│   │   └── models/              # Freezed/JSON serializable
│   ├── auth/
│   │   ├── auth_service.dart    # JWT storage, auto-refresh, biometric
│   │   └── tokens.dart          # flutter_secure_storage
│   ├── database/
│   │   └── drift_db.dart        # Local cache (Drift/SQLite) для offline
│   ├── events/
│   │   └── event_bus.dart       # Stream-based local events
│   └── theme/
│       └── app_theme.dart       # Material 3, dark/light, brand colors
├── features/
│   ├── auth/
│   │   ├── login_screen.dart
│   │   ├── pin_biometric.dart
│   │   └── register_screen.dart (admin only)
│   ├── sites/
│   │   ├── site_list_screen.dart
│   │   ├── site_detail_screen.dart (Dashboard)
│   │   ├── site_setup_wizard.dart    # 6 шагов (NEW)
│   │   └── widgets/
│   │       ├── site_card.dart
│   │       └── site_status_chip.dart
│   ├── cameras/
│   │   ├── camera_list_screen.dart
│   │   ├── camera_detail_screen.dart
│   │   ├── camera_add_wizard.dart    # ONVIF scan + manual
│   │   ├── camera_test_screen.dart
│   │   ├── camera_zone_editor.dart   # Grid N×M editor
│   │   └── widgets/
│   │       ├── camera_preview.dart   # WebRTC/HLS player
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
│   │       └── actuator_binding_editor.dart # Camera ↔ Actuator matrix
│   ├── alarms/
│   │   ├── alarm_list_screen.dart     # History with filters
│   │   ├── alarm_detail_screen.dart   # Media gallery
│   │   ├── alarm_live_screen.dart     # Real-time alarm view
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
└── main.dart                    # Entry point, flavors, go_router
```

#### 2.3 Offline-First & Sync Strategy
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
    await _pushPendingChanges();      // POST/PATCH локальные изменения
    await _pullServerUpdates();       // GET обновления с сервера
    await _resolveConflicts();        // Last-write-wins + user prompt для критических
  }
}

// Background sync каждые 30 сек + при reconnect
// Push notifications через FCM/APNs для alarms в background
```

---

### Phase 3: API Hardening & Production Readiness (Неделя 10-12)

| Sprint | Deliverable |
|--------|-------------|
| 3.1 | **Windows Installer** (Inno Setup) + **Ubuntu systemd** + **Docker Compose** |
| 3.2 | **OTA Updates** (signed, blue-green, rollback) |
| 3.3 | **Load Testing** (10 sites × 20 cameras × 5 fps) |
| 3.4 | **Security Audit** (pentest, dependency scan, secrets audit) |
| 3.5 | **Documentation** (User Guide, Admin Guide, API Reference, Plugin Dev Guide) |
| 3.6 | **RC Release** (GitHub Release + Changelog + Migration Guide v1→v2) |

---

## 3. API Contract (OpenAPI 3.1 — ключевые эндпоинты)

### Authentication
```
POST   /api/v1/auth/login           # email/password → {access_token, refresh_token}
POST   /api/v1/auth/refresh         # refresh_token → new access_token
GET    /api/v1/auth/me              # current user + permissions
POST   /api/v1/auth/biometric       # Включение/проверка биометрии (Flutter)
```

### Sites (Multi-tenancy)
```
GET    /api/v1/sites                        # List user's sites
POST   /api/v1/sites                        # Create site (Site Wizard step 1)
GET    /api/v1/sites/{id}                   # Site details
PATCH  /api/v1/sites/{id}                   # Update site
DELETE /api/v1/sites/{id}                   # Delete site
GET    /api/v1/sites/{id}/dashboard         # Aggregated status для UI
POST   /api/v1/sites/{id}/wizard/step2      # Network config
POST   /api/v1/sites/{id}/wizard/step3      # Cameras (ONVIF scan)
POST   /api/v1/sites/{id}/wizard/step4      # Actuators
POST   /api/v1/sites/{id}/wizard/step5      # Detectors & Rules
POST   /api/v1/sites/{id}/activate          # "Start Protection"
```

### Cameras
```
GET    /api/v1/sites/{site_id}/cameras
POST   /api/v1/sites/{site_id}/cameras              # Add camera (with ONVIF discovery)
GET    /api/v1/sites/{site_id}/cameras/{id}
PATCH  /api/v1/sites/{site_id}/cameras/{id}
DELETE /api/v1/sites/{site_id}/cameras/{id}
POST   /api/v1/sites/{site_id}/cameras/{id}/test    # Test connection
GET    /api/v1/sites/{site_id}/cameras/{id}/stream  # WebRTC/HLS stream URL (signed)
GET    /api/v1/sites/{site_id}/cameras/{id}/snapshot
POST   /api/v1/sites/{site_id}/cameras/discover     # ONVIF/UPnP scan
PATCH  /api/v1/sites/{site_id}/cameras/{id}/zone    # Zone grid update
```

### Detectors
```
GET    /api/v1/sites/{site_id}/detectors
POST   /api/v1/sites/{site_id}/detectors
GET    /api/v1/sites/{site_id}/detectors/{id}
PATCH  /api/v1/sites/{site_id}/detectors/{id}
DELETE /api/v1/sites/{site_id}/detectors/{id}
POST   /api/v1/sites/{site_id}/detectors/{id}/test  # Test on frame
```

### Actuators
```
GET    /api/v1/sites/{site_id}/actuators
POST   /api/v1/sites/{site_id}/actuators
GET    /api/v1/sites/{site_id}/actuators/{id}
PATCH  /api/v1/sites/{site_id}/actuators/{id}
DELETE /api/v1/sites/{site_id}/actuators/{id}
POST   /api/v1/sites/{site_id}/actuators/{id}/test
POST   /api/v1/sites/{site_id}/actuators/{id}/command  # {action: on/off/toggle}
PATCH  /api/v1/sites/{site_id}/cameras/{id}/bindings   # Camera ↔ Actuator matrix
```

### Alarms (Real-time via WebSocket)
```
GET    /api/v1/sites/{site_id}/alarms              # History with filters
GET    /api/v1/sites/{site_id}/alarms/{id}
GET    /api/v1/sites/{site_id}/alarms/{id}/media
WS     /api/v1/sites/{site_id}/alarms/ws           # Real-time alarm events
POST   /api/v1/sites/{site_id}/alarms/{id}/ack
POST   /api/v1/sites/{site_id}/alarms/{id}/silence
POST   /api/v1/sites/{site_id}/alarms/{id}/record
```

### System
```
GET    /api/v1/system/health
GET    /api/v1/system/metrics                      # Prometheus format
GET    /api/v1/system/logs
POST   /api/v1/system/backup                       # SQLite/PostgreSQL backup
POST   /api/v1/system/restore                      # Restore from backup
GET    /api/v1/system/plugins                      # Available plugins
GET    /api/v1/system/version
```

### WebSocket Events (Server → Client)
```typescript
type WSMessage =
  | { type: 'alarm.triggered', payload: AlarmEvent }
  | { type: 'alarm.acknowledged', payload: { alarmId, userId } }
  | { type: 'alarm.resolved', payload: { alarmId } }
  | { type: 'camera.status', payload: { cameraId, status: 'online'|'offline'|'error' } }
  | { type: 'actuator.status', payload: { actuatorId, state: boolean, power?: number } }
  | { type: 'detection.stats', payload: { cameraId, fps, detections: Detection[] } }
  | { type: 'system.health', payload: SystemHealth }
  | { type: 'site.updated', payload: Site };
```

---

## 4. Миграция от текущей версии (v1 → v2)

### Стратегия: Parallel Run + Gradual Cutover

```
CURRENT (v1)                          NEW (v2 API-First)
────────────────────────────────────────────────────────────
run_bot.py (monolith)          ──────►  superguard-api (FastAPI service)
watchdog.py                    ──────►  systemd/NSSM + health checks
Telegram Bot (polling)         ──────►  Notifier Plugin (Telegram) + Webhook
sguard.env                     ──────►  config.yaml + env override + Vault
sguard_settings.json           ──────►  PostgreSQL/SQLite (sites, cameras, actuators)
desktop_state/status.json      ──────►  Redis Streams + WebSocket
```

### Миграционный скрипт (`scripts/migrate_v1_to_v2.py`)
```python
async def migrate():
    # 1. Читаем sguard.env + sguard_settings.json
    # 2. Создаём Site "Main Site" с таймзоной/координатами
    # 3. Импортируем 8 камер → Camera records (с ONVIF профилями)
    # 4. Импортируем 2 розетки → Actuator records + bindings
    # 5. Создаём Detector "YOLO11n Default" с текущими порогами
    # 6. Создаём Notifier "Telegram Legacy" с текущим токеном
    # 7. Создаём Admin пользователя (email + сгенерированный пароль)
    # 8. Генерируем config.yaml для v2
    # 9. Запускаем v2 параллельно на порту 8081 для smoke-тестов
```

### Обратная совместимость
- v2 API включает `/legacy/*` эндпоинты для старого бота
- Telegram бот продолжает работать как Notifier Plugin
- Watchdog v1 может мониторить v2 через `/system/health`

---

## 5. Deployment Strategy

### 5.1 Development
```yaml
# docker-compose.dev.yml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: superguard
      POSTGRES_USER: sg
      POSTGRES_PASSWORD: dev
    ports: ["5432:5432"]
    volumes: [pgdata:/var/lib/postgresql/data]

  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]

  mediamtx:
    image: bluenviron/mediamtx:v1.8
    ports: ["8554:8554", "8888:8888", "8889:8889"]
    volumes: [./mediamtx.dev.yml:/mediamtx.yml]

  api:
    build: 
      context: ./superguard-core
      target: development
    volumes: [./superguard-core:/app]
    ports: ["8080:8080"]
    environment:
      - DATABASE_URL=postgresql://sg:dev@postgres:5432/superguard
      - REDIS_URL=redis://redis:6379/0
      - MEDIAMTX_API_URL=http://mediamtx:9997
    depends_on: [postgres, redis, mediamtx]

  web:
    build: 
      context: ./web-dashboard
      target: development
    volumes: [./web-dashboard:/app, /app/node_modules]
    ports: ["3000:3000"]
    environment:
      - VITE_API_URL=http://localhost:8080
    depends_on: [api]
```

### 5.2 Production (Ubuntu Server)
```yaml
# docker-compose.prod.yml
version: '3.8'
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_DB: superguard
      POSTGRES_USER: ${DB_USER}
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./backups:/backups
    deploy:
      resources:
        limits:
          memory: 1G

  redis:
    image: redis:7-alpine
    volumes: [redisdata:/data]
    command: redis-server --appendonly yes --maxmemory 256mb --maxmemory-policy allkeys-lru

  mediamtx:
    image: bluenviron/mediamtx:v1.8
    volumes:
      - ./mediamtx.prod.yml:/mediamtx.yml
      - /etc/letsencrypt:/etc/letsencrypt:ro
    ports: ["8554:8554", "8888:8888", "8889:8889"]
    deploy:
      resources:
        limits:
          memory: 2G

  api:
    image: superguard/api:latest
    environment:
      - DATABASE_URL=postgresql://${DB_USER}:${DB_PASSWORD}@postgres:5432/superguard
      - REDIS_URL=redis://redis:6379/0
      - MEDIAMTX_API_URL=http://mediamtx:9997
      - JWT_SECRET_KEY=${JWT_SECRET_KEY}
      - OTEL_ENDPOINT=http://jaeger:4317
    deploy:
      replicas: 2
      resources:
        limits:
          memory: 1G
          cpus: '1.0'
    depends_on: [postgres, redis, mediamtx]

  web:
    image: superguard/web:latest
    ports: ["80:80", "443:443"]
    volumes:
      - /etc/letsencrypt:/etc/letsencrypt:ro
      - ./nginx.prod.conf:/etc/nginx/nginx.conf:ro
    depends_on: [api]

  jaeger:
    image: jaegertracing/all-in-one:1.50
    ports: ["16686:16686", "4317:4317"]

volumes:
  pgdata:
  redisdata:
```

### 5.3 Windows (NSSM + Embedded Python)
- PyInstaller сборка `superguard-api.exe` + `superguard-agent.exe`
- MediaMTX как отдельный сервис
- Redis как отдельный сервис (memurai или WSL2)
- Inno Setup инсталлятор: `SuperGuard-Setup-x64.exe`

---

## 6. Plugin Architecture (для расширяемости)

```python
# superguard-core/plugins/__init__.py
from abc import ABC, abstractmethod
from typing import List, Dict, Any

class CameraPlugin(ABC):
    name: str
    version: str
    config_schema: type[BaseModel]  # Pydantic
    
    @abstractmethod
    async def connect(self, config: BaseModel) -> None: ...
    
    @abstractmethod
    async def read_frame(self) -> CameraFrame: ...
    
    @abstractmethod
    async def disconnect(self) -> None: ...
    
    @classmethod
    @abstractmethod
    def discover(cls) -> List[DiscoveredCamera]: ...

class DetectorPlugin(ABC):
    name: str
    config_schema: type[BaseModel]
    
    @abstractmethod
    async def initialize(self, config: BaseModel) -> None: ...
    
    @abstractmethod
    async def process(self, frame: np.ndarray) -> ProcessedFrame: ...

class ActuatorPlugin(ABC):
    name: str
    config_schema: type[BaseModel]
    
    @abstractmethod
    async def turn_on(self) -> bool: ...
    @abstractmethod
    async def turn_off(self) -> bool: ...
    @abstractmethod
    async def get_status(self) -> bool: ...

# Регистрация через entry_points в pyproject.toml:
# [project.entry-points."superguard.cameras"]
# rtsp = "plugins.cameras.rtsp:RTSPCameraPlugin"
# onvif = "plugins.cameras.onvif:ONVIFCameraPlugin"
```

---

## 7. Monitoring & Observability

### 7.1 Key Metrics (Prometheus)
```prometheus
# Camera health
superguard_cameras_total{site,status}          # online/offline/error
superguard_camera_fps{site,camera}             # Actual FPS

# Detection pipeline
superguard_detection_fps{site,camera,detector} # Processing FPS
superguard_detection_latency_ms{site,camera}   # P50/P95/P99
superguard_detections_total{site,camera,class} # Per-class counter

# Alarms
superguard_alarm_total{site,status,detector}   # triggered/acknowledged/resolved
superguard_alarm_duration_seconds{site}        # Time to acknowledge/resolve

# Actuators
superguard_actuator_commands_total{site,actuator,action,result} # on/off/toggle success/fail
superguard_actuator_status{site,actuator}      # Current state

# API
superguard_api_request_duration_seconds{endpoint,method} # P50/P95/P99
superguard_websocket_connections{site}          # Active WS connections

# Storage
superguard_recording_disk_usage_bytes{site}     # Media storage
superguard_database_size_bytes                  # DB size
```

### 7.2 Alerts (Alertmanager → Telegram/Email/PagerDuty)
- Camera offline > 60s
- Detection FPS < 1 for 5min
- Disk usage > 80%
- Memory > 90%
- Failed actuator commands > 3 in row
- API error rate > 5%

### 7.3 Distributed Tracing (OpenTelemetry → Jaeger)
- Trace: HTTP request → Detection → Alarm → Notification
- Latency percentiles per component

---

## 8. Security Hardening

| Layer | Implementation |
|-------|----------------|
| **Auth** | JWT RS256, access 15min, refresh 7d, rotation |
| **Roles** | Admin (full), Operator (control), Viewer (read) |
| **API** | Rate limiting (100 req/min), CORS, Security headers |
| **Secrets** | HashiCorp Vault / SOPS / age encryption для config |
| **TLS** | Let's Encrypt (prod) / self-signed (dev) через nginx |
| **Video** | WebRTC DTLS-SRTP, HLS с подписанными URL (TTL 5min) |
| **Audit Log** | Все действия в БД + Structured logs |
| **Supply Chain** | Sigstore cosign для подписи релизов, SBOM (Syft) |

---

## 9. Timeline Summary

| Phase | Weeks | Focus | Parallelizable |
|-------|-------|-------|----------------|
| 0. Foundation | 1-2 | API Gateway, DB, Core CRUD, WS, MediaMTX | — |
| 1. Web Dashboard | 3-5 | React/TS Dashboard, все экраны | Flutter team может начать с недели 3 |
| 2. Flutter Client | 6-9 | Flutter App (Mobile/Desktop/Web) | Backend стабилен с недели 2 |
| 3. Hardening & RC | 10-12 | Installers, OTA, Load test, Security, Docs | — |

**Итого: ~12 недель (3 месяца) до RC** при фуллтайме бэкенда + параллельный Flutter.

---

## 10. Definition of Done (RC Criteria)

### Functional
- [ ] Site Setup Wizard: новый объект за 5 минут без CLI
- [ ] Camera: ONVIF discovery + manual + zone editor + PTZ
- [ ] Detector: YOLO ONNX + custom classes + test on frame
- [ ] Actuator: Tuya/Sonoff/Shelly + binding matrix + manual control
- [ ] Alarm: Real-time WS + WebRTC live + ACK/SILENCE + media gallery
- [ ] Notifications: Telegram/Push/Email/Webhook/MQTT + test button
- [ ] Recording: MP4 segments + retention + download
- [ ] Offline: Flutter работает офлайн, синхронизируется при reconnect
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

## 11. Next Actions (Immediate)

1. **Создать репозиторий `superguard-api`** с FastAPI skeleton (Phase 0.1)
2. **Вынести текущие модули в плагины** (cameras, detectors, actuators, notifiers)
3. **Настроить CI/CD** (GitHub Actions: lint, test, build, docker push)
4. **Написать OpenAPI spec** для всех эндпоинтов
5. **Настроить MediaMTX** + WebRTC тест

### Flutter (можно начать параллельно с Phase 0.3):
1. `flutter create superguard_client --platforms=ios,android,windows,linux,macos,web`
2. Настроить: go_router, dio, freezed, drift, flutter_secure_storage, flutter_webrtc
3. Реализовать Auth flow + Site List + Dashboard skeleton

---

## 12. Заключение

Этот план трансформирует SuperGuard из **"работающего скрипта для одной дачи"** в **"продуктовую Security Platform"**:

| Аспект | Текущее (v1) | RC (v2) |
|--------|--------------|---------|
| **Архитектура** | Монолитный бот | API-first + Plugin-based |
| **Платформы** | Windows only | Windows + Ubuntu + ARM + Web |
| **UI** | Telegram Bot | Flutter (Mobile/Desktop/Web) + Web Dashboard |
| **Мультитенантность** | Нет | Полная (sites, users, roles) |
| **Камеры** | 8 hardcoded | Unlimited + ONVIF discovery |
| **Детекторы** | YOLO only | Plugin system (YOLO, Motion, Custom) |
| **Актуаторы** | Tuya only | Tuya/Sonoff/Shelly/Tasmota/GPIO |
| **Уведомления** | Telegram only | 5+ каналов + Webhook/MQTT |
| **Видео** | MJPEG snapshots | WebRTC/HLS/MP4 recording |
| **Офлайн** | Нет | Full offline + sync |
| **Деплой** | NSSM руками | Installer + Docker + systemd |
| **Обновления** | Git pull | OTA signed + rollback |
| **Мониторинг** | status.json | Prometheus + Grafana + Alerting |

**Готовность к старту Phase 0: 90%** — база есть, плагины выделены, схема БД готова.

---

*План создан на основе аудита текущего кодовой базы (20 циклов эволюции) и архитектурного видения RC v3.0*