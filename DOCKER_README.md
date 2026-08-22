# SuperGuard Docker Deployment

This directory contains Docker Compose configurations for deploying SuperGuard.

## Quick Start

### Development
```bash
# Start all services
make dev

# Or manually:
docker compose up -d postgres redis mediamtx
cd superguard-api && python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 3001 &
cd superguard-dashboard && npm run dev &
```

### Production
```bash
# Build images
make build

# Start with nginx reverse proxy
docker compose --profile production up -d

# Or just core services
docker compose up -d
```

## Services

| Service | Port | Description |
|---------|------|-------------|
| **API** | 3001 | FastAPI backend |
| **Dashboard** | 3000 | React frontend |
| **MediaMTX** | 8554/8888/8889/8890 | RTSP/HLS/WebRTC streaming |
| **PostgreSQL** | 5432 | Primary database |
| **Redis** | 6379 | Cache & WebSocket pub/sub |
| **Nginx** | 80/443 | Reverse proxy (production) |

## Configuration

1. Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

2. Edit `.env` with your values:
```bash
# Required
POSTGRES_PASSWORD=your_secure_password
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
SG_ENC_KEY=your_fernet_key  # Generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
JWT_SECRET_KEY=your_jwt_secret  # Generate: openssl rand -base64 32
```

## MediaMTX Streaming

MediaMTX handles all camera streaming:
- **RTSP**: `rtsp://localhost:8554/cam1`
- **HLS**: `http://localhost:8888/cam1/index.m3u8`
- **WebRTC (WHIP)**: `http://localhost:8889/cam1/whip`
- **WebRTC (WHEP)**: `http://localhost:8890/cam1/whep`

Add cameras by publishing to MediaMTX:
```bash
# FFmpeg example
ffmpeg -re -i rtsp://camera_ip:554/stream -c copy -f rtsp rtsp://localhost:8554/cam1
```

## Database Migrations

```bash
# Run migrations
docker compose exec api alembic upgrade head

# Create new migration
docker compose exec api alembic revision --autogenerate -m "description"
```

## Monitoring

```bash
# View logs
make logs

# API health
curl http://localhost:3001/health

# MediaMTX metrics
curl http://localhost:9997/metrics
```

## Backup & Restore

```bash
# Backup database
make backup

# Restore database
make restore  # Will prompt for backup file
```

## SSL Certificates

For production with Let's Encrypt:
```bash
# Generate certificates
make ssl-generate

# Renew certificates
make ssl-renew
```

Place certificates in `./ssl/` directory:
```
ssl/
├── cert.pem
└── key.pem
```

## Troubleshooting

```bash
# Check container status
docker compose ps

# View specific service logs
docker compose logs -f api
docker compose logs -f mediamtx

# Restart service
docker compose restart api

# Full reset
make reset
```

## CI/CD

GitHub Actions workflow in `.github/workflows/ci-cd.yml`:
- Lint & type check (ruff, mypy)
- Unit tests with PostgreSQL & Redis
- Docker image builds (API, Dashboard, Nginx)
- Deploy to staging (develop branch)
- Deploy to production (main branch)