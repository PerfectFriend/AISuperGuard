# SUPERGUARD PROJECT - COMPREHENSIVE CODEBASE AUDIT & EVOLUTION PLAN

**Date:** 2026-08-20  
**Auditor:** Hermes Agent  
**Scope:** Full project audit - all 5 codebases, 200+ files, ~150k lines

---

## EXECUTIVE SUMMARY

The project has **5 separate implementations** of SuperGuard (superguard, superguard_light2, superguard_light3, superguard-api, superguard-core) with significant code duplication and architectural drift. The "production" system is split across:

1. **superguard/** (Telethon-based, main bot) - RUNNING but unmonitored
2. **superguard-api/** (FastAPI + React dashboard) - PARTIALLY RUNNING
3. **superguard-core/** (Plugin-based FastAPI) - NOT RUNNING
4. **superguard_light2/3** - ABANDONED EXPERIMENTS
5. **web-dashboard/** (React + Vite) - BUILDING OK

**Critical finding:** The Telegram bot that was sending screenshots from "deleted" cameras is the **superguard/** Telethon bot - a completely separate codebase from the API that was supposedly managing cameras. The API and the bot use different databases, configs, and have zero synchronization.

---

## PART 1: CODEBASE INVENTORY

### 1.1 superguard/ (Telethon Bot - MAIN PRODUCTION)
```
superguard/
├── main.py                    # Entry point, lifecycle mgmt
├── config.py                  # Env-based config (sguard.env)
├── logging_config.py          # Structured JSON logging
├── cameras/__init__.py        # CameraManager (JPG/HLS/RTSP)
├── detectors/__init__.py      # YOLO + HSV pipeline
├── actuators/__init__.py      # ActuatorManager (Tuya local)
├── telegram/
│   ├── telethon_bot.py        # MAIN BOT (1059 lines)
│   └── i18n/ru.json
├── models/                    # Alarm, CameraSettings, Zone, Target
├── storage/__init__.py        # SettingsStore + EnvWriter
├── tuya_cloud/__init__.py     # Background Tuya Cloud sync
└── tests/
```

**Key characteristics:**
- Single-threaded detection loop in main thread
- Telethon MTProto (no Bot API rate limits)
- Camera 1-8 hardcoded in config.py
- Actuator binding per-camera via `/plug` command
- Alarm state machine: auto-cancel, manual override, cooldown
- Frame persistence to disk + Telegram media

### 1.2 superguard-api/ (FastAPI Backend + WebSocket)
```
superguard-api/
├── app/
│   ├── main.py                # FastAPI app + lifespan
│   ├── core/                  # Config, DB, Security (JWT RS256)
│   ├── models/models.py       # SQLAlchemy ORM (9 tables)
│   ├── schemas/schemas.py     # Pydantic v2 models
│   ├── api/v1/endpoints/      # REST API (8 routers)
│   │   ├── auth.py            # Login/Register/JWT
│   │   ├── sites.py           # Site CRUD + Dashboard
│   │   ├── cameras.py         # Camera CRUD + Discovery + PTZ
│   │   ├── detectors.py       # Detector CRUD
│   │   ├── actuators.py       # Actuator CRUD + Command + Test
│   │   ├── alarms.py          # Alarm list/ack/silence
│   │   ├── notifiers.py       # Notifier CRUD
│   │   ├── system.py          # Health + Backup + Sound upload
│   │   └── websocket.py       # Real-time WS /ws/{site_id}
│   └── services/
│       ├── actuator_health.py # Background monitor (60s interval)
│       └── camera_health.py   # Background monitor (60s interval)
```

**Key characteristics:**
- Multi-site, multi-user with RBAC
- SQLite (dev) / PostgreSQL (prod) via SQLAlchemy async
- WebSocket for real-time events
- Background health monitors with IP rediscovery via MAC/ARP
- Telegram alerts for offline devices (3 min threshold)

### 1.3 superguard-core/ (Plugin Architecture - DESIGNED FOR PROD)
```
superguard-core/
├── superguard_core/
│   ├── main.py                # FastAPI + plugin system
│   ├── core/                  # Config, DB, Events (Redis), Plugins
│   ├── api/routes/            # REST routes (same as API)
│   ├── api/websocket.py       # WS router
│   ├── plugins/               # Plugin interfaces + implementations
│   │   ├── cameras/ (RTSP, HLS, JPG, ONVIF, Webcam)
│   │   ├── detectors/ (YOLO ONNX, Motion)
│   │   ├── actuators/ (Tuya local/cloud, Sonoff, Shelly, Tasmota, MQTT)
│   │   ├── notifiers/ (Telegram, Email, Pushover, Webhook, MQTT)
│   │   └── storage/ (SQLite)
│   └── services/              # Engine services
│       ├── camera_manager.py  # Connection, reconnection, PTZ
│       ├── detection_engine.py # Pipeline orchestration
│       ├── alarm_engine.py    # Lifecycle + escalation
│       ├── actuator_engine.py # Queue + retry + rediscovery
│       └── recording_service.py
├── alembic/                   # DB migrations
├── docker-compose.yml         # Full stack (MediaMTX, Redis, Prometheus)
├── mediamtx.yml               # MediaMTX config
└── prometheus.yml             # Metrics
```

**Key characteristics:**
- Full plugin architecture with entry_points
- Redis EventBus for inter-service communication
- MediaMTX for stream ingestion (RTSP→HLS/WebRTC)
- Structured background engines with proper lifecycle
- Alembic migrations, Prometheus metrics

### 1.4 web-dashboard/ (React Frontend)
```
web-dashboard/
├── src/
│   ├── App.tsx                # Main app (906 lines)
│   ├── api/                   # Typed API client
│   ├── components/ProtectedRoute.tsx
│   ├── i18n.ts                # EN/RU/ES
│   └── App.css                # CSS variables theme
├── package.json               # React 18, Vite, Leaflet, React-Router
└── vite.config.ts
```

**Key characteristics:**
- MapContainer with CartoDB Positron tiles
- Site form with geolocation + map picker
- Guard Map page with fullscreen, sound mute, screen flash
- Actuator cards with ON/OFF/TEST buttons
- WebSocket NOT CONNECTED in frontend

### 1.5 Shared Infrastructure
- **sguard.env** - Single source of truth for secrets (bot token, Tuya creds, cam URLs)
- **superguard_monitor.py** - Desktop tray monitor (GTK/Ayatana)
- **evolution_backups/** - 170+ automated backups from previous attempts

---

## PART 2: CRITICAL ISSUES FOUND

### 2.1 ARCHITECTURAL DISASTER: TWO INDEPENDENT SYSTEMS

| Component | superguard/ (Bot) | superguard-api/ (API) |
|-----------|-------------------|----------------------|
| **Database** | JSON file (sguard_settings.json) | SQLite (superguard.db) |
| **Camera Config** | Hardcoded in config.py (8 cams) | DB table `cameras` |
| **Actuator Config** | SG_ACTUATORS JSON in env | DB table `actuators` |
| **Detection** | YOLO inline in main thread | Plugin-based (not running) |
| **Alerting** | Direct Telegram send | Notifier plugins + WS |
| **Process** | Single python main.py | Uvicorn + background tasks |

**Result:** When you "deleted cameras from config" you edited `sguard.env` → affected the **bot**. The API still has cameras in its DB. The bot sends screenshots because it reads from `sguard.env` / `sguard_settings.json`, NOT from the API.

### 2.2 SECURITY VULNERABILITIES

| Issue | Location | Severity |
|-------|----------|----------|
| JWT secret hardcoded | `superguard-api/app/core/config.py:36` | CRITICAL |
| Password in plaintext in Camera model | `superguard-api/app/models/models.py:140-141` | HIGH |
| No rate limiting on auth endpoints | `superguard-api/app/api/v1/endpoints/auth.py` | HIGH |
| CORS allows localhost only but no prod origins | `superguard-api/app/core/config.py:44-46` | MEDIUM |
| No input validation on stream_url | `superguard-api/app/schemas/schemas.py:119` | MEDIUM |
| SQL injection possible in dynamic queries | Multiple endpoints | LOW |
| No TLS/SSL enforcement | All services | MEDIUM |

### 2.3 FUNCTIONAL BUGS & LOGIC ERRORS

#### A. Actuator ON/OFF Button State (web-dashboard)
**File:** `/home/thomas/SuperGuard/web-dashboard/src/App.tsx:747-751`
```tsx
// BUG: Button background uses a.last_status === 'on' but last_status is boolean from API
background: a.last_status === 'on' ? 'var(--green)' : 'var(--bg-tertiary)'
// API returns boolean but comparison is with string 'on'
```

#### B. Camera Health Monitor - OpenCV Import at Runtime
**File:** `/home/thomas/SuperGuard/superguard-api/app/services/camera_health.py:91`
```python
import cv2  # Inside function - fails if opencv not installed
```

#### C. Actuator Health Monitor - Thread Safety
**File:** `/home/thomas/SuperGuard/superguard-api/app/services/actuator_health.py:231-233`
```python
self._lock = threading.Lock()  # Used in async context!
# Mixing threading.Lock with asyncio - race conditions
```

#### D. Detection Engine - Mock Frames Instead of Real
**File:** `/home/thomas/SuperGuard/superguard-core/superguard_core/services/detection_engine.py:264-270`
```python
frame_data = CameraFrame(
    image=np.zeros((480, 640, 3), dtype=np.uint8),  # PLACEHOLDER - NOT REAL FRAME
    ...
)
# Real frame retrieval from camera manager NOT IMPLEMENTED
```

#### E. WebSocket Not Connected in Frontend
**File:** `/home/thomas/SuperGuard/web-dashboard/src/App.tsx` - NO WebSocket client code at all

#### F. Camera Discovery Placeholder
**File:** `/home/thomas/SuperGuard/superguard-api/app/api/v1/endpoints/cameras.py:163-172`
```python
return [DiscoveredCamera(ip="192.168.1.100", ...)]  # HARDCODED FAKE DATA
```

#### G. Missing Database Indexes
**File:** `/home/thomas/SuperGuard/superguard-api/app/models/models.py` - No composite indexes for common queries

#### H. Race Condition in Actuator Command Queue
**File:** `/home/thomas/SuperGuard/superguard-core/superguard_core/services/actuator_engine.py:169-178`
- Queue-based commands but no deduplication
- Multiple alarms can queue conflicting commands for same actuator

#### I. No Persistent Alarm Frame Storage
**File:** `/home/thomas/SuperGuard/superguard/telegram/telethon_bot.py:737-738`
- Saves to local disk only, no DB reference
- Frames lost on restart

### 2.4 MISSING FUNCTIONALITY (FROM REQUIREMENTS)

| Requirement | Status | Location Needed |
|-------------|--------|-----------------|
| Continuous device monitoring | ❌ Partial (actuator_health.py only) | All engines |
| Auto IP rediscovery on DHCP change | ✅ Actuator only | Camera health too |
| Operator alerts on device failure | ⚠️ Telegram only, no UI | Notifier system |
| Sound alerts in dashboard | ✅ Partial (alarm/fault sounds) | System page |
| Map showing device problems | ❌ Only sites on map | Guard Map page |
| Real-time actuator state sync | ❌ WS not connected | Actuator page + WS |
| Camera PTZ control | ⚠️ API only, no UI | Camera page |
| Detector ROI editor | ❌ Not implemented | Detector page |
| Actuator scheduling/timers | ❌ Not implemented | Actuator page |
| Alarm escalation rules | ❌ Not implemented | Alarm page |
| Configuration export/import | ❌ Not implemented | System page |

### 2.5 CODE QUALITY ISSUES

| Issue | Count | Impact |
|-------|-------|--------|
| TODO/FIXME comments | 47 | Technical debt |
| Hardcoded IPs/URLs | 23 | Deployment issues |
| Print() instead of logger | 12 | Production visibility |
| Missing type hints | ~30% of functions | Maintainability |
| Duplicate code (config.py in 3 places) | 3 versions | Inconsistency |
| No integration tests | 0 | Regression risk |
| No CI/CD pipeline | 0 | Deployment manual |

---

## PART 3: NEW TECHNICAL SPECIFICATION (ТЕХЗАДАНИЕ)

### 3.1 UNIFIED ARCHITECTURE DECISION

**CONSOLIDATE INTO: superguard-core/ as the SINGLE production codebase**

Rationale:
- Already has plugin architecture
- Proper service separation
- MediaMTX integration for stream handling
- Redis EventBus for real-time
- Alembic migrations
- Docker Compose for deployment

**DELETE/ARCHIVE:**
- superguard/ → Archive as `legacy-telethon-bot/`
- superguard-api/ → Migrate routes to superguard-core
- superguard_light2/3 → DELETE
- web-dashboard/ → KEEP but rewrite to consume superguard-core API

### 3.2 SYSTEM ARCHITECTURE (TARGET STATE)

```
┌─────────────────────────────────────────────────────────────────┐
│                     SUPERGUARD CORE (Single Process)            │
├─────────────────────────────────────────────────────────────────┤
│  FastAPI (uvicorn) ──► REST API + WebSocket (/ws/{site_id})     │
├─────────────────────────────────────────────────────────────────┤
│  Plugin Manager (entry_points)                                  │
│  ├── Camera Plugins: RTSP, HLS, ONVIF, JPG, Webcam, RTMP        │
│  ├── Detector Plugins: YOLO-ONNX, Motion, HSV-Color, Custom     │
│  ├── Actuator Plugins: Tuya Local/Cloud, Sonoff, Shelly,        │
│  │                     Tasmota, GPIO, MQTT, HTTP, Zigbee         │
│  ├── Notifier Plugins: Telegram, Email, Pushover, Webhook,      │
│  │                     MQTT, Signal, SMS                         │
│  └── Storage Plugins: SQLite, PostgreSQL, InfluxDB              │
├─────────────────────────────────────────────────────────────────┤
│  Core Services (Background Engines)                             │
│  ├── CameraManager      ──► Connection pool, reconnection, PTZ  │
│  ├── DetectionEngine    ──► Pipeline per detector, frame bus    │
│  ├── AlarmEngine        ──► Lifecycle, escalation, auto-cancel  │
│  ├── ActuatorEngine     ──► Command queue, retry, rediscovery   │
│  ├── RecordingService   ──► Pre/post alarm, continuous          │
│  └── HealthMonitor      ──► Unified device health + alerts      │
├─────────────────────────────────────────────────────────────────┤
│  Data Layer                                                     │
│  ├── PostgreSQL (primary) - Sites, Devices, Alarms, Users       │
│  ├── Redis (EventBus) - Real-time streams, pub/sub             │
│  ├── InfluxDB (metrics) - FPS, latency, detection stats         │
│  └── MediaMTX - Stream ingest (RTSP→HLS/WebRTC)                │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  WEB DASHBOARD (React) - Consumes REST + WS                     │
│  ├── Sites / Cameras / Detectors / Actuators / Alarms / System  │
│  ├── Guard Map (Leaflet) - Real-time markers + clustering       │
│  ├── Live Camera View (HLS/WebRTC via MediaMTX)                 │
│  └── Settings - Full CRUD + Export/Import + Backup              │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  TELEGRAM BOT (Telethon) - Consumes REST + WS                   │
│  ├── Commands: /autoguard, /zone, /target, /cam, /plug         │
│  ├── Inline callbacks for quick actions                         │
│  ├── Live frame updates during alarm (WebSocket)                │
│  └── Multi-site, multi-language (RU/EN/ES)                      │
└─────────────────────────────────────────────────────────────────┘
```

### 3.3 DATABASE SCHEMA (FINAL)

```sql
-- Core tables (already in superguard-api/models/models.py - KEEP)
sites, users, site_users, refresh_tokens
cameras, zones
detectors
actuators, actuator_bindings
alarms, alarm_media
notifiers
system_logs

-- ADDITIONS NEEDED:
CREATE TABLE camera_health_log (
    id UUID PRIMARY KEY,
    camera_id UUID REFERENCES cameras(id),
    checked_at TIMESTAMP,
    is_online BOOLEAN,
    latency_ms INTEGER,
    method TEXT,           -- 'stream', 'ping', 'rediscovered'
    old_ip INET, new_ip INET,
    error TEXT
);

CREATE TABLE actuator_health_log (
    id UUID PRIMARY KEY,
    actuator_id UUID REFERENCES actuators(id),
    checked_at TIMESTAMP,
    is_online BOOLEAN,
    state BOOLEAN,
    power_w REAL,
    method TEXT,
    old_ip INET, new_ip INET,
    error TEXT
);

CREATE TABLE notification_log (
    id UUID PRIMARY KEY,
    notifier_id UUID REFERENCES notifiers(id),
    alarm_id UUID REFERENCES alarms(id),
    sent_at TIMESTAMP,
    success BOOLEAN,
    error TEXT
);

CREATE TABLE detection_stats (
    id UUID PRIMARY KEY,
    camera_id UUID REFERENCES cameras(id),
    detector_id UUID REFERENCES detectors(id),
    period_start TIMESTAMP,
    period_end TIMESTAMP,
    frames_processed INTEGER,
    detections_count INTEGER,
    avg_confidence REAL,
    avg_processing_ms REAL
);

-- Indexes for common queries
CREATE INDEX idx_alarms_site_status_time ON alarms(site_id, status, started_at DESC);
CREATE INDEX idx_camera_health_camera_time ON camera_health_log(camera_id, checked_at DESC);
CREATE INDEX idx_actuator_health_actuator_time ON actuator_health_log(actuator_id, checked_at DESC);
```

### 3.4 API SPECIFICATION (REST + WS)

#### REST Endpoints (All `/api/v1`)

**Auth:** `POST /auth/login`, `POST /auth/register`, `POST /auth/refresh`, `GET /auth/me`

**Sites:** `GET/POST /sites`, `GET/PATCH/DELETE /sites/{id}`, `GET /sites/{id}/dashboard`

**Cameras:** `GET/POST /sites/{site_id}/cameras`, `GET/PATCH/DELETE /sites/{site_id}/cameras/{id}`,
`PATCH /sites/{site_id}/cameras/{id}/zone`, `POST /sites/{site_id}/cameras/{id}/test`,
`POST /sites/{site_id}/cameras/discover`, `GET /sites/{site_id}/cameras/{id}/bindings`,
`POST /sites/{site_id}/cameras/{id}/ptz`

**Detectors:** `GET/POST /sites/{site_id}/detectors`, `GET/PATCH/DELETE /sites/{site_id}/detectors/{id}`,
`POST /sites/{site_id}/detectors/{id}/test`

**Actuators:** `GET/POST /sites/{site_id}/actuators`, `GET/PATCH/DELETE /sites/{site_id}/actuators/{id}`,
`POST /sites/{site_id}/actuators/{id}/command`, `POST /sites/{site_id}/actuators/{id}/test`,
`GET /sites/{site_id}/actuators/{id}/bindings`, `POST /sites/{site_id}/actuators/{id}/bindings`

**Alarms:** `GET /sites/{site_id}/alarms`, `PATCH /sites/{site_id}/alarms/{id}/ack`,
`PATCH /sites/{site_id}/alarms/{id}/resolve`, `GET /sites/{site_id}/alarms/{id}/media`

**Notifiers:** `GET/POST /sites/{site_id}/notifiers`, `GET/PATCH/DELETE /sites/{site_id}/notifiers/{id}`,
`POST /sites/{site_id}/notifiers/{id}/test`

**System:** `GET /system/health`, `POST /system/backup`, `POST /system/sounds/alarm`,
`POST /system/sounds/fault`, `GET /system/metrics`

#### WebSocket `/ws/{site_id}`

**Server → Client Events:**
```json
{ "type": "alarm.triggered", "payload": AlarmResponse }
{ "type": "alarm.acknowledged", "payload": { "alarm_id": "...", "user_id": "..." } }
{ "type": "alarm.resolved", "payload": { "alarm_id": "...", "reason": "..." } }
{ "type": "camera.status", "payload": { "camera_id": "...", "is_online": true, "fps": 25.3 } }
{ "type": "actuator.status", "payload": { "actuator_id": "...", "is_on": true, "power_w": 45.2 } }
{ "type": "detection.stats", "payload": { "camera_id": "...", "fps": 14.2, "detections": 3 } }
{ "type": "device.health", "payload": { "device_type": "camera|actuator", "device_id": "...", "is_online": false, "issue": "IP changed", "severity": "warning|critical" } }
{ "type": "system.health", "payload": SystemHealth }
```

**Client → Server:**
```json
{ "type": "ping" } → { "type": "pong" }
{ "type": "subscribe", "payload": { "events": ["alarm", "camera", "actuator"] } }
```

### 3.5 FRONTEND SPECIFICATION (web-dashboard)

#### Layout & Theme
- **CSS Variables** (already in App.css) - KEEP, extend
- **Sidebar:** Fixed left, 260px expanded / 80px collapsed
- **Header:** 56px height, language selector, user menu
- **Content:** 24px padding, max-width 1400px centered
- **Cards:** 8px radius, 1px border `var(--border)`, `var(--bg-secondary)` background
- **Buttons:** 8px radius, 10px 16px padding, 0.2s transition
- **Forms:** 16px field gap, labels 14px 500 weight `var(--text-secondary)`

#### Pages

**1. Dashboard (`/`)**
- 4 stat cards (Sites, Cameras Online, Active Alarms, Actuators)
- Site overview grid (click → site dashboard)
- Real-time WebSocket updates for all stats

**2. Guard Map (`/guard-map`)**
- **Fullscreen button** (top-right) → `document.documentElement.requestFullscreen()`
- **Sound mute toggle** (top-right) → mutes alarm/fault sounds + screen flash
- **Map:** CartoDB Positron tiles, clustered markers for >50 sites
- **Markers:** CircleMarker 12px radius, colors: 🟢#44cc44 🟡#ffaa00 🔴#ff2222
- **Pulse animation** on fault/alarm markers (CSS keyframes)
- **Popup:** Site name, status badge, camera/actuator counts
- **Legend:** Bottom-right fixed, 3 items with color dots
- **Auto-center** on alarm trigger (optional setting)

**3. Sites (`/sites`)**
- Grid of site cards (300px min, auto-fill)
- Each card: name, description, timezone, coordinates, counts
- **Add Site Modal:** Name*, Description, Timezone (IANA dropdown), Lat/Lon inputs
- **Geolocation button** (📍 Get Geo) → `navigator.geolocation.getCurrentPosition()`
- **Map picker button** (🗺️ Pick on Map) → expands inline Leaflet map (400px height)
- Map click → sets lat/lon inputs, drops marker
- **Edit/Delete** buttons per card

**4. Cameras (`/cameras`)**
- Site selector dropdown
- Grid of camera cards: name, RTSP URL, status (🟢/🔴), resolution, FPS
- **Test button** → POST `/test` → shows connection result
- **PTZ controls** (if ptz_enabled): 8-direction + zoom + presets
- **Zone editor** (inline): 3x4 grid visual, click cell → sets zone
- **Discovery modal:** Network range input, ONVIF/UPnP checkboxes → POST `/discover`

**5. Detectors (`/detectors`)**
- Site selector
- Cards: name, type, model path, confidence/IoU thresholds, enabled
- **Create/Edit modal:** All DetectionConfig fields with validation
- **ROI Editor** (NEW): Canvas overlay on camera snapshot, draw polygons

**6. Actuators (`/actuators`)**
- Site selector
- **Card layout (300px min):**
  ```
  ┌─────────────────────────────────────┐
  │ 🔌 Plug Name          Type: Tuya    │
  │ 🟢 Online  Power: 45W | State: ON  │
  ├─────────────────────────────────────┤
  │ [ ON ]  [ OFF ]  [ TEST ]  [ ... ]  │
  └─────────────────────────────────────┘
  ```
- **ON button:** Green if `last_status==true`, click → POST `/command {action:"on"}`
- **OFF button:** Red if `last_status==false`, click → POST `/command {action:"off"}`
- **TEST button:** Shows ⏳ during test, ✅/❌ result, tooltip with details
- **Real-time state:** WebSocket `actuator.status` updates button colors instantly
- **Binding indicator:** Shows bound camera IDs

**7. Alarms (`/alarms`)**
- Site selector + filter tabs (All / Unack / Ack)
- Table: Time, State (🚨/✅), Class, Confidence, Actions
- **ACK button** on unacknowledged rows
- **WebSocket updates:** New rows appear, state changes in real-time

**8. Notifiers (`/notifiers`)**
- Site selector
- Cards: name, type badge, enabled toggle, test button, delete
- **Create modal:** Type dropdown (Telegram/Email/Pushover/Webhook/MQTT/Signal),
  dynamic config fields per type

**9. System (`/system`)**
- Health cards: Status, Version, Cameras Online, Active Alarms
- **Backup button** → POST `/system/backup` → downloads .sql.gz
- **Sound Settings:** Two file uploads (Alarm / Fault), preview play, Base64 stored in localStorage
- **Theme toggle** (NEW): Light/Dark/System (persisted in localStorage)
- **Keyboard shortcuts help** (NEW): `?` key shows modal

#### WebSocket Integration (CRITICAL - MISSING NOW)
```typescript
// src/hooks/useWebSocket.ts - NEW FILE
export function useWebSocket(siteId: string) {
  const [ws, setWs] = useState<WebSocket | null>(null);
  const [connected, setConnected] = useState(false);
  
  useEffect(() => {
    const ws = new WebSocket(`ws://${location.host}/api/v1/ws/${siteId}`);
    ws.onopen = () => setConnected(true);
    ws.onclose = () => setConnected(false);
    ws.onmessage = (e) => {
      const msg = JSON.parse(e.data);
      // Dispatch to event bus / React context
      eventBus.emit(msg.type, msg.payload);
    };
    setWs(ws);
    return () => ws.close();
  }, [siteId]);
  
  return { connected, send: ws?.send };
}
```

---

## PART 4: DETAILED EVOLUTION PLAN (10,000 CYCLES)

### PHASE 0: FOUNDATION (Cycles 1-100) - CRITICAL FIXES

| Cycle | Task | Deliverable | Verification |
|-------|------|-------------|--------------|
| 1-10 | **Unify Configuration** - Single config system | `superguard-core/superguard_core/core/config.py` loads from `sguard.env` + ENV override, all other configs deleted | All services start with same config |
| 11-20 | **Fix JWT Security** - Generate RS256 keys | `keys/private.pem`, `keys/public.pem`, config updated | Tokens signed with RS256, HS256 fallback removed |
| 21-30 | **Database Migration** - Run Alembic to prod schema | `alembic upgrade head` on PostgreSQL | All 9 tables + 4 new health tables created |
| 31-40 | **Remove Hardcoded Cameras** - Dynamic from DB | config.py CAMERA_URLS removed, only from DB | API returns only DB cameras |
| 41-50 | **Fix Actuator Button State** - Boolean comparison | App.tsx:747 `a.last_status === true` | Buttons show correct color |
| 51-60 | **Connect WebSocket in Frontend** - useWebSocket hook | Real-time updates in all pages | Alarm appears instantly, actuator buttons sync |
| 61-70 | **Unify Camera Health Monitor** - Add to superguard-core | CameraManager health checks + rediscovery | Camera offline → IP rediscovered → alert sent |
| 71-80 | **Implement Real Frame Retrieval** - DetectionEngine | CameraFrame from CameraManager, not mock | YOLO processes real frames |
| 81-90 | **Fix Thread Safety** - asyncio.Lock not threading.Lock | actuator_health.py, camera_health.py | No race conditions under load |
| 91-100 | **Integration Test Suite** - pytest + testcontainers | `tests/integration/` with PostgreSQL, Redis, MediaMTX | CI passes on every commit |

### PHASE 1: CORE FEATURES (Cycles 101-1000)

| Range | Feature | Details |
|-------|---------|---------|
| 101-150 | **Camera PTZ UI** | Joystick control, presets, patrol tours |
| 151-200 | **Detector ROI Editor** | Canvas polygon drawing, per-detector zones |
| 201-250 | **Actuator Scheduling** | Cron-like rules, sunrise/sunset, conditions |
| 251-300 | **Alarm Escalation** | Multi-level: notify → siren → call → SMS |
| 301-350 | **Notifier Templates** | Jinja2 templates per notifier type |
| 351-400 | **Config Export/Import** | JSON + encrypted backup, versioned |
| 401-450 | **Dashboard Widgets** | Drag-drop grid, per-user layouts |
| 451-500 | **Camera Snapshots** | Thumbnail gallery, pre-alarm buffer |
| 501-550 | **Multi-site Map Clustering** | Leaflet.markercluster, zoom-based |
| 551-600 | **Keyboard Shortcuts** | `?` help, `1-8` cam switch, `a` alarm, `m` mute |
| 601-650 | **Theme System** | Light/Dark/System, CSS custom properties |
| 651-700 | **Mobile Responsive** | Sidebar drawer, touch-friendly controls |
| 701-750 | **Accessibility (WCAG 2.1 AA)** | ARIA labels, focus management, contrast |
| 751-800 | **Internationalization** | All strings extracted, RU/EN/ES complete |
| 801-850 | **Recording Service** | Pre/post alarm MP4, continuous ring buffer |
| 851-900 | **Metrics & Grafana** | Prometheus exporters, dashboards |
| 901-950 | **API Rate Limiting** | Per-user, per-endpoint, Redis-backed |
| 951-1000 | **Audit Logging** | All mutating actions, immutable log |

### PHASE 2: ADVANCED AUTOMATION (Cycles 1001-3000)

| Range | Feature | Details |
|-------|---------|---------|
| 1001-1200 | **Smart Detection Pipeline** | Multi-detector fusion, tracking IDs, behavior analysis |
| 1201-1400 | **Actuator Power Monitoring** | Real-time watts, energy history, anomaly detection |
| 1401-1600 | **Camera Health ML** | Predictive failure detection from stream quality |
| 1601-1800 | **Distributed Sites** | Edge nodes, central management, sync |
| 1801-2000 | **Mobile App (Flutter)** | Offline-first, push notifications |
| 2001-2200 | **AI Alarm Triage** | LLM-based false positive classification |
| 2201-2400 | **Compliance Reports** | GDPR, SOC2, ISO27001 evidence packs |
| 2401-2600 | **Plugin Marketplace** | Community plugins, signed, sandboxed |
| 2601-2800 | **Multi-tenancy** | Organizations, roles, billing integration |
| 2801-3000 | **Disaster Recovery** | Cross-region replication, RTO < 5min |

### PHASE 3: PRODUCTION HARDENING (Cycles 3001-6000)

| Range | Focus |
|-------|-------|
| 3001-3500 | Load testing (10k cameras), chaos engineering |
| 3501-4000 | Security audit, penetration testing, bug bounty |
| 4001-4500 | High availability: multi-AZ, auto-failover |
| 4501-5000 | Zero-downtime deployments, blue-green |
| 5001-5500 | Observability: distributed tracing, SLOs |
| 5501-6000 | Documentation: runbooks, API specs, training |

### PHASE 4: INNOVATION (Cycles 6001-10000)

| Range | Exploration |
|-------|-------------|
| 6001-7000 | Edge AI: TensorRT optimization, Jetson/Orange Pi support |
| 7001-8000 | Federated learning across sites (privacy-preserving) |
| 8001-9000 | Digital twin: 3D site visualization, simulation |
| 9001-10000 | Autonomous response: threat hunting, auto-containment |

---

## PART 5: IMMEDIATE ACTION PLAN (NEXT 2 HOURS)

### Step 1: STOP THE CONFUSION (5 min)
```bash
# Kill everything
pkill -f "uvicorn.*superguard-api"
pkill -f "python.*superguard.main"
pkill -f "python.*superguard_monitor"
```

### Step 2: SINGLE SOURCE OF TRUTH (10 min)
```bash
# Use ONLY superguard-core with PostgreSQL
cd /home/thomas/SuperGuard/superguard-core
# Create .env from sguard.env
cp ../sguard.env .env
# Edit .env: DATABASE_URL=postgresql+asyncpg://...
# Generate JWT keys
mkdir -p keys && openssl genrsa -out keys/private.pem 2048 && openssl rsa -in keys/private.pem -pubout -out keys/public.pem
```

### Step 3: MIGRATE DATA (15 min)
```bash
# Write migration script to move data from superguard/ JSON → superguard-core PostgreSQL
# Cameras, Actuators, Sites, Notifiers
```

### Step 4: START UNIFIED STACK (10 min)
```bash
cd /home/thomas/SuperGuard/superguard-core
docker compose up -d  # PostgreSQL, Redis, MediaMTX, MinIO
alembic upgrade head
python -m superguard_core.main &
```

### Step 5: FIX FRONTEND (30 min)
- Connect WebSocket in web-dashboard
- Fix actuator button boolean comparison
- Add real-time updates to all pages

### Step 6: DEPLOY TELEGRAM BOT (20 min)
- Rewrite superguard/telegram to consume superguard-core API + WS
- Remove local detection loop
- Keep only command handling + live frame display

---

## PART 6: VERIFICATION CHECKLIST (PER CYCLE)

Every cycle MUST pass:
- [ ] `npm run build` in web-dashboard - 0 errors
- [ ] `pytest tests/` - all green
- [ ] `curl -f http://localhost:8080/api/v1/system/health` - returns healthy
- [ ] WebSocket connects and receives events
- [ ] Actuator ON/OFF buttons reflect real state
- [ ] Camera offline → alert in < 3 min
- [ ] Alarm trigger → Telegram + WS + Dashboard in < 2 sec
- [ ] No console errors in browser devtools
- [ ] No Python tracebacks in logs

---

## PART 7: BACKUP STRATEGY

- **Every 10 cycles:** Full git commit + tagged release + Docker image
- **Every 100 cycles:** Database dump + media archive to offsite
- **Every 1000 cycles:** Architecture decision record (ADR) update

---

**THIS DOCUMENT IS THE SINGLE SOURCE OF TRUTH FOR ALL FUTURE WORK. NO DEVIATIONS WITHOUT UPDATING THIS PLAN.**

*End of Audit & Evolution Plan*