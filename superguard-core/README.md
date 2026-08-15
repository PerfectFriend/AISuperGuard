# SuperGuard Core

Cross-platform Security Platform Core API with plugin architecture.

## Architecture

```
��─────────────────────────────────────────────────────────────────��
│                        SuperGuard Core                           │
├─────────────────────────────────────────────────────────────────��
│  FastAPI + Plugin System + Event Bus (Redis Streams)            │
├─────────────��─────────────��─────────────��─────────────��─────────��
│   Cameras   │  Detectors  │  Actuators  │  Notifiers  │ Storage │
│  (plugins)  │  (plugins)  │  (plugins)  │  (plugins)  │(plugins)│
├─────────────��─────────────��─────────────��─────────────��─────────��
│                    Core Services                                 │
│  Camera Manager │ Detection Engine │ Alarm Engine │ Actuator    │
│  Recording Svc  │ Plugin Manager   │ Event Bus    │ Auth        │
├─────────────────────────────────────────────────────────────────��
│              PostgreSQL + Redis + MediaMTX                       │
��─────────────────────────────────────────────────────────────────��
```

## Plugin Types

### Cameras
- **rtsp** - RTSP streams via OpenCV
- **hls** - HLS/DASH streams
- **jpg** - HTTP JPEG snapshots
- **onvif** - ONVIF Profile S/T/G with PTZ
- **webcam** - Local USB/MIPI cameras

### Detectors
- **yolo_onnx** - YOLO11n via ONNX Runtime (CUDA/CPU)
- **motion** - Classic frame differencing

### Actuators
- **tuya_local** - Tuya LAN protocol with ARP rediscovery
- **tuya_cloud** - Tuya Cloud API fallback
- **mqtt** - Generic MQTT actuators

### Notifiers
- **telegram** - Rich Telegram bot with inline keyboards
- **webhook** - Generic webhook integration

### Storage
- **sqlite** - Local filesystem + SQLite metadata

## Quick Start (Docker)

```bash
# Clone and configure
git clone <repo>
cd superguard-core

# Create .env file
cp .env.example .env
# Edit .env with your secrets

# Start stack
docker-compose up -d

# Check health
curl http://localhost:8000/system/health

# Access API docs
open http://localhost:8000/docs
```

## Quick Start (Bare Metal - Ubuntu)

```bash
# Install dependencies
sudo apt update && sudo apt install -y python3.11 python3.11-venv postgresql redis nginx

# Create user
sudo useradd -r -s /bin/bash -d /opt/superguard superguard

# Setup project
sudo mkdir -p /opt/superguard
sudo chown superguard:superguard /opt/superguard
cd /opt/superguard

# Clone and setup venv
git clone <repo> .
python3.11 -m venv venv
source venv/bin/activate
pip install -e ".[all]"

# Configure
cp .env.example .env
# Edit .env

# Run migrations
alembic upgrade head

# Install service
sudo cp superguard.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now superguard
```

## Quick Start (Bare Metal - Windows)

```powershell
# Install Python 3.11, PostgreSQL, Redis, NSSM

# Setup project
git clone <repo> C:\SuperGuard\superguard-core
cd C:\SuperGuard\superguard-core

# Create venv
python -m venv venv
.\venv\Scripts\activate
pip install -e ".[all]"

# Configure
copy .env.example .env
# Edit .env

# Run migrations
alembic upgrade head

# Install service (Run as Administrator)
.\install_service.bat
```

## Configuration

All configuration via environment variables or `.env` file:

```env
# Database
SG_DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/superguard

# Redis
SG_REDIS_URL=redis://localhost:6379/0

# Storage
SG_STORAGE_PATH=/var/lib/superguard/storage

# Server
SG_HOST=0.0.0.0
SG_PORT=8000
SG_WORKERS=4

# Security
SG_SECRET_KEY=your-secret-key
SG_JWT_PRIVATE_KEY=/path/to/private.pem
SG_JWT_PUBLIC_KEY=/path/to/public.pem

# Logging
SG_LOG_LEVEL=INFO
```

## API Endpoints

| Category | Endpoints |
|----------|-----------|
| Auth | `POST /api/auth/login`, `POST /api/auth/refresh`, `GET /api/auth/me` |
| Sites | `GET/POST /api/sites`, `GET/PUT/DELETE /api/sites/{id}` |
| Cameras | `GET/POST /api/sites/{id}/cameras`, `GET/PUT/DELETE /api/cameras/{id}`, `POST /api/cameras/{id}/test`, `GET /api/cameras/{id}/snapshot`, `GET /api/cameras/{id}/stream` |
| Detectors | `GET/POST /api/sites/{id}/detectors`, `GET/PUT/DELETE /api/detectors/{id}`, `POST /api/detectors/{id}/test` |
| Actuators | `GET/POST /api/sites/{id}/actuators`, `GET/PUT/DELETE /api/actuators/{id}`, `POST /api/actuators/{id}/on`, `POST /api/actuators/{id}/off`, `POST /api/actuators/{id}/toggle`, `GET /api/actuators/{id}/state` |
| Alarms | `GET /api/sites/{id}/alarms`, `GET /api/alarms/{id}`, `POST /api/alarms/{id}/acknowledge`, `POST /api/alarms/{id}/resolve` |
| Media | `GET /api/media/alarm/{alarm_id}`, `GET /api/media/camera/{camera_id}`, `GET /api/media/{media_id}/download`, `GET /api/media/{media_id}/thumbnail` |
| System | `GET /system/health`, `GET /system/metrics`, `GET /system/status` |
| WebSocket | `WS /ws/{site_id}` |

## Plugin Development

```python
from superguard_core.core.plugins import CameraPlugin, PluginConfig

class MyCameraPlugin(CameraPlugin):
    name = "my_camera"
    plugin_type = "camera"
    
    async def initialize(self):
        await self._set_status(self.PluginStatus.LOADED)
    
    async def connect(self, camera):
        # Connect to camera
        pass
    
    async def read_frame(self) -> CameraFrame:
        # Return frame
        pass
    
    # ... other methods

# Register in superguard_core/plugins/cameras/__init__.py
```

## Migration from v1

```bash
# Run migration script
python -m superguard_core.scripts.migrate \
    --config /path/to/sguard.env \
    --settings /path/to/sguard_settings.json \
    --site-name "Main Site"
```

## License

MIT