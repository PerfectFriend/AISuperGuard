# SuperGuard Project Audit Report
## Summary of Implemented Features (based on AUDIT_REPORT.md and current code)

### ✅ Implemented and Working
1. **Detection and Alarm Logic** (Section 2.1)
   - YOLO11n detector with conf=0.35, imgsz=640
   - HSV color filter (yellow by default, configurable)
   - Zone filter (N×M grid) with `Zone.contains_point()`
   - Detection pipeline (YOLO→Zone→Color) as clean functions
   - Per-camera settings via `CameraSettings`
   - 4K downscaling for Cam2 (Reotech)
   - Annotated frames stored for Telegram bot
   - Persistent tracking ID via `model.track(persist=True)`
   - Alarm protocol: single-message alarm with live updates, auto-resolve, manual toggle

2. **Actuators and Relays** (Section 2.2)
   - Local Tuya (tinytuya) support
   - ARP-based IP rediscovery (MAC-based)
   - Retry logic with re-discovery on socket error
   - MAC addresses stored in config
   - Cloud Tuya fallback (configured but not working due to platform config)
   - Actuator registry and manager
   - Many-to-many bindings between cameras and plugs
   - Persistence of bindings via `SettingsStore`
   - Alarm → actuator ON, cancel → actuator OFF flow

3. **Telegram Bot** (Section 2.3)
   - Full command set: `/autoguard`, `/togglealarm [cam_id]`, `/zone`, `/target`, `/cam`, `/plug`, `/setlocal`
   - Inline buttons for alarm cancel, auto-toggle, language change
   - Multi-language support (RU/EN/ES) via external JSON files
   - Rate limiting (20 req/s), retry with exponential backoff, 429 handling
   - Command router with prefix matching
   - `TelegramClient` wrapper with session reuse
   - `SuperGuardBot` wiring all components
   - Localization via `I18n` class
   - Desktop bridge via `status.json` and `alarm_live.jpg`

4. **Concurrent Alarms** (Section 2.4)
   - `AlarmManager` stores `Dict[int, CameraAlarmState]`
   - Independent alarms per camera
   - `active_camera_id` tracks last triggered camera
   - Per-camera auto-resolution (`clean_frames`)

5. **Persistence** (Section 2.5)
   - Atomic JSON storage (`write → tmp → os.replace`) with 500ms debounce
   - Atomic `.env` updates via `EnvWriter`
   - Atomic `desktop_state/status.json` for watchdog/desktop
   - Atomic `alarm_live.jpg` for desktop viewer
   - Settings schema includes version, language, auto mode, active camera, camera settings, actuator bindings

6. **Watchdog** (Section 2.6)
   - Monitors `desktop_state/status.json` every 10s
   - Startup grace period (60s)
   - Missed heartbeat tolerance (3 misses = 30s)
   - Kills duplicate bot processes by cmdline
   - Detached process launch
   - Logging to `watchdog.log`

### ⚠️ Partially Working / Needs Attention
1. **Tuya Cloud** (Section 3.1)
   - Configured in `sguard.env` but returns error 1108 (`uri path invalid`)
   - Root cause: Tuya IoT project misconfiguration (not code)
   - Requires proper setup on iot.tuya.com (schema, device IDs)

2. **RTSP Camera Credentials** (Section 3.1)
   - Default password `admin:123456` on Cam2 (Reotech)
   - Should be changed to strong password in camera web interface

3. **Telegram Rate Limit** (Section 5.2)
   - Occurs during aggressive testing
   - Already handled in `TelegramClient` (honors Retry-After)
   - Could be improved with caching of `getMe` and exponential backoff for 429

### ❌ Not Implemented / Missing
1. **User Authorization** (Section 3.2, Critical)
   - **Missing**: No check of `user_id` in Telegram updates
   - **Risk**: Anyone knowing `chat_id` (143293811) can control the bot
   - **Fix**: Add `ALLOWED_USER_IDS` to config and check in `handle_update`
   - **Status**: Partially addressed – we added `SG_ALLOWED_USER_IDS` to config and check in `telegram/__init__.py`, but need to set the ID in `sguard.env` (done: set to 143293811)

2. **End-to-End Tests** (Section 4.3)
   - Missing: Detection → alarm → actuator ON → Telegram photo → cancel → actuator OFF
   - Missing: ARP rediscovery test (plug IP change via DHCP)
   - Missing: Retry logic test for actuators
   - Missing: Concurrent alarms test (two cameras)
   - Missing: Watchdog restart cycle test
   - Missing: Telegram rate limit (429) handling test
   - Missing: Authorization test

3. **Performance / Optimization** (Section 5.3)
   - No GPU acceleration for YOLO (CPU only ~80-120ms/frame)
   - No metrics/health endpoint beyond existing `/api/v1/system/health`
   - No API documentation (OpenAPI/Swagger)

4. **Desktop Application** (Not in audit but mentioned in user request)
   - The audit does not cover a desktop client; only the web dashboard and Telegram bot.
   - The user referenced a desktop monitor (`node-monitor.py`) in the PXNode project, but for SuperGuard we have only the web dashboard and Telegram bot.

### 🔧 Integration Task: Useful Parts from Old Telegram Bot to New API
The "old Telegram bot" referenced by the user is likely the existing `superguard` directory (the bot we just audited). The "new API" is `superguard-api` (FastAPI). Useful parts to integrate:
- **Alarm and actuator logic**: Move core alarm triggering/actuator control from `SuperGuardBot` into API services so the dashboard can control via HTTP.
- **Detection engine**: The API already has a `DetectionEngine` service; we should ensure it uses the same YOLO/HSV/Zone logic as the bot.
- **Settings persistence**: API should read/write the same `sguard_settings.json` (or use a shared database) so settings changed via dashboard persist to the bot and vice versa.
- **WebSocket for live updates**: The API could provide WebSocket endpoint for live camera frames and alarm status to the dashboard.
- **Unified configuration**: Ensure both bot and API read from the same `sguard.env` and `SuperGuardConfig`.

Current state of `superguard-api`:
- Has basic CRUD endpoints for cameras, detectors, actuators, alarms, sites, notifiers, system.
- Uses SQLAlchemy with PostgreSQL/SQLite (likely SQLite in dev).
- Has WebSocket endpoint (`/api/v1/websocket`) for live updates.
- Has actuator health monitor and camera health monitor.
- Detection engine is initialized but may not be fully integrated with the bot's detection logic.

Thus, the integration work would involve:
1. Making the API's detection engine use the same `create_pipeline_from_config` and `ProcessedFrame` logic as the bot.
2. Ensuring the API's alarm endpoints trigger the same actuator logic as the bot (via shared service or direct calls to `ActuatorManager`).
3. Sharing the `SettingsStore` between bot and API (or using the database as source of truth).
4. Possibly refactoring to have a core `superguard-core` package shared by both.

Given the scope, we can note that the API already provides a foundation; further integration would require more detailed work.

## Recommended Next Steps for 70-Cycle Autonomous Evolution
1. **Set user ID for authorization** (already done).
2. **Fix Tuya Cloud** by configuring the IoT platform (outside code, but we can note).
3. **Change RTSP camera password** (manual step).
4. **Run the evolution script** (build/test/backup cycles) to ensure stability.
5. **Integrate core logic between bot and API** (shared configuration, settings, detection).
6. **Add missing e2e tests** to the test suite.
7. **Add OpenAPI docs** to the FastAPI app.
8. **Add GPU acceleration** for YOLO if possible (ONNX Runtime + DirectML).

We will now start the evolution script for 70 cycles (modified from 10000) in the background.