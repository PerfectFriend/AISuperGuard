"""
SuperGuard API - FastAPI Application Factory
"""
import time
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.database import get_db
from app.services.telegram_bot import start_telegram_bot, stop_telegram_bot

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    app.state.start_time = time.time()
    Path("logs").mkdir(exist_ok=True)
    Path("backups").mkdir(exist_ok=True)

    # Create tables (dev mode — use Alembic for prod migrations)
    from app.models.models import Base
    from app.core.database import engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Start actuator health monitor
    from app.services.actuator_health import ActuatorHealthMonitor
    actuator_monitor = ActuatorHealthMonitor(get_db)
    app.state.actuator_monitor = actuator_monitor
    await actuator_monitor.start(interval=60)  # Check every 60 seconds

    # Start camera health monitor
    from app.services.camera_health import CameraHealthMonitor
    camera_monitor = CameraHealthMonitor(get_db)
    app.state.camera_monitor = camera_monitor
    await camera_monitor.start(interval=60)  # Check every 60 seconds

    # Start detection engine with WS manager
    from app.services.detection_engine import DetectionEngine
    from app.api.v1.endpoints.websocket import manager as ws_manager
    detection_engine = DetectionEngine(ws_manager=ws_manager)
    app.state.detection_engine = detection_engine
    app.state.ws_manager = ws_manager  # Expose for other services
    await detection_engine.initialize()
    detection_engine.start()

    # Start Telegram bot
    telegram_bot = await start_telegram_bot()
    app.state.telegram_bot = telegram_bot
    if telegram_bot:
        logger.info("Telegram bot started successfully")
    else:
        logger.warning("Telegram bot not started (token not configured or initialization failed)")

    yield
    
    # Shutdown
    await actuator_monitor.stop()
    await camera_monitor.stop()
    app.state.detection_engine.stop()
    await stop_telegram_bot()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="SuperGuard Alarm API - Multi-site security platform",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # Middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(GZipMiddleware, minimum_size=1024)

    # Request timing middleware
    @app.middleware("http")
    async def add_process_time(request: Request, call_next):
        start = time.time()
        response = await call_next(request)
        elapsed = time.time() - start
        response.headers["X-Process-Time"] = f"{elapsed:.4f}s"
        return response

    # Include routers
    from app.api.v1 import api_router
    app.include_router(api_router, prefix=settings.api_prefix)

    # Root health (outside /api/v1)
    @app.get("/health")
    async def health():
        return {"status": "ok", "version": settings.app_version}

    return app


app = create_app()