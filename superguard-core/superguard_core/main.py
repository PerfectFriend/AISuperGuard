"""
SuperGuard Core - Main Entry Point

FastAPI application factory with plugin system, authentication,
and all API routes.
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from superguard_core.core.config import Settings, get_settings
from superguard_core.core.database import init_db, close_db
from superguard_core.core.plugins import PluginManager
from superguard_core.core.events import EventBus, get_event_bus
from superguard_core.api.routes import auth, sites, cameras, detectors, actuators, alarms, media, system
from superguard_core.api.websocket import router as ws_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    settings = get_settings()
    
    # Initialize database
    await init_db(settings.database_url)
    
    # Get site ID for services that require it
    from superguard_core.core.database import get_session_factory, Site
    from sqlalchemy import select
    site_id = 1  # default fallback
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(select(Site).where(Site.is_active == True).limit(1))
        site = result.scalar_one_or_none()
        if site:
            site_id = site.id
    
    # Initialize Redis event bus
    event_bus = await EventBus.create(settings.redis_url)
    app.state.event_bus = event_bus
    
    # Initialize plugin manager
    plugin_manager = PluginManager()
    await plugin_manager.discover_plugins()
    app.state.plugin_manager = plugin_manager
    
    # Start background services
    from superguard_core.services.camera_manager import CameraManager
    from superguard_core.services.detection_engine import DetectionEngine
    from superguard_core.services.alarm_engine import AlarmEngine
    from superguard_core.services.actuator_engine import ActuatorEngine
    from superguard_core.services.recording_service import RecordingService
    
    camera_manager = CameraManager(plugin_manager, event_bus, site_id)
    detection_engine = DetectionEngine(plugin_manager, event_bus, site_id)
    # For AlarmEngine we need actuator_engine instance, but we haven't created it yet.
    # We'll create actuator_engine first, then alarm_engine.
    actuator_engine = ActuatorEngine(plugin_manager, event_bus, site_id)
    alarm_engine = AlarmEngine(event_bus, site_id, actuator_engine)
    recording_service = RecordingService(event_bus, settings.storage_path)
    
    app.state.camera_manager = camera_manager
    app.state.detection_engine = detection_engine
    app.state.alarm_engine = alarm_engine
    app.state.actuator_engine = actuator_engine
    app.state.recording_service = recording_service
    
    # Start services
    await camera_manager.start()
    await detection_engine.start()
    await alarm_engine.start()
    await actuator_engine.start()
    await recording_service.start()
    
    yield
    
    # Shutdown
    await recording_service.stop()
    await actuator_engine.stop()
    await alarm_engine.stop()
    await detection_engine.stop()
    await camera_manager.stop()
    await plugin_manager.shutdown()
    await event_bus.close()
    await close_db()
def create_app() -> FastAPI:
    """Create FastAPI application."""
    settings = get_settings()
    
    app = FastAPI(
        title="SuperGuard Core API",
        version="2.0.0-dev",
        description="Cross-platform Security Platform API",
        lifespan=lifespan,
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
    )
    
    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Include API routes
    app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
    app.include_router(sites.router, prefix="/sites", tags=["Sites"])
    app.include_router(cameras.router, prefix="/sites/{site_id}/cameras", tags=["Cameras"])
    app.include_router(detectors.router, prefix="/sites/{site_id}/detectors", tags=["Detectors"])
    app.include_router(actuators.router, prefix="/sites/{site_id}/actuators", tags=["Actuators"])
    app.include_router(alarms.router, prefix="/sites/{site_id}/alarms", tags=["Alarms"])
    app.include_router(media.router, prefix="/sites/{site_id}/media", tags=["Media"])
    app.include_router(system.router, prefix="/system", tags=["System"])
    app.include_router(ws_router, prefix="/ws", tags=["WebSocket"])
    
    # Static files for media
    media_path = Path(settings.storage_path) / "media"
    media_path.mkdir(parents=True, exist_ok=True)
    app.mount("/media", StaticFiles(directory=str(media_path)), name="media")\n# Static files for dashboard
dashboard_path = Path(__file__).parent.parent / "dashboard"
dashboard_path.mkdir(parents=True, exist_ok=True)
app.mount("/dashboard", StaticFiles(directory=str(dashboard_path)), name="dashboard")


    
    @app.get("/health")
    async def health_check():
        return {
            "status": "healthy",
            "version": "2.0.0-dev",
            "services": {
                "database": "ok",
                "redis": "ok",
                "plugins": len(app.state.plugin_manager.plugins) if hasattr(app.state, "plugin_manager") else 0,
            }
        }
    
    return app


app = create_app()


def main():
    """Entry point for console script."""
    import uvicorn
    settings = get_settings()
    uvicorn.run(
        "superguard_core.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        workers=1 if settings.debug else settings.workers,
    )


if __name__ == "__main__":
    main()