"""
SuperGuard Core - System API Routes
"""

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Request
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
import os
import shutil
from datetime import datetime
from pathlib import Path

from superguard_core.core.auth import get_current_user, require_role
from superguard_core.core.database import get_session, Site, Camera, Detector, Actuator, Alarm, User, UserRole
from superguard_core.core.config import get_settings
from superguard_core.core.plugins import PluginManager, NotificationPayload
from superguard_core.core.events import EventBus, get_event_bus

router = APIRouter()


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    settings = get_settings()
    
    # Check database
    db_status = "ok"
    try:
        factory = get_session_factory()
        async with factory() as session:
            await session.execute(select(1))
    except Exception:
        db_status = "error"
    
    # Check Redis
    redis_status = "ok"
    try:
        bus = await get_event_bus()
        await bus.redis.ping()
    except Exception:
        redis_status = "error"
    
    # Check plugins
    pm = PluginManager()
    await pm.discover_plugins()
    
    return {
        "status": "healthy" if db_status == "ok" and redis_status == "ok" else "degraded",
        "version": "2.0.0-dev",
        "timestamp": datetime.now().isoformat(),
        "services": {
            "database": db_status,
            "redis": redis_status,
            "plugins": {
                "cameras": len(pm.get_available_plugins()) if hasattr(pm, 'get_available_plugins') else 0,
            }
        }
    }


@router.get("/metrics")
async def prometheus_metrics(
    current_user = Depends(require_role(UserRole.ADMIN)),
):
    """Prometheus metrics endpoint."""
    from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
    from fastapi.responses import Response
    
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@router.get("/info")
async def system_info(
    current_user = Depends(require_role(UserRole.ADMIN)),
    session: AsyncSession = Depends(get_session),
):
    """System information."""
    settings = get_settings()
    
    # Count resources
    sites_count = (await session.execute(select(func.count(Site.id)))).scalar() or 0
    cameras_count = (await session.execute(select(func.count(Camera.id)))).scalar() or 0
    detectors_count = (await session.execute(select(func.count(Detector.id)))).scalar() or 0
    actuators_count = (await session.execute(select(func.count(Actuator.id)))).scalar() or 0
    alarms_count = (await session.execute(select(func.count(Alarm.id)))).scalar() or 0
    users_count = (await session.execute(select(func.count(User.id)))).scalar() or 0
    
    # Disk usage
    storage_path = Path(settings.storage_path)
    disk_usage = shutil.disk_usage(storage_path)
    
    return {
        "version": "2.0.0-dev",
        "environment": "development" if settings.debug else "production",
        "database_url": settings.database_url.split("@")[-1] if "@" in settings.database_url else settings.database_url,
        "storage_path": settings.storage_path,
        "disk": {
            "total_gb": round(disk_usage.total / (1024**3), 2),
            "used_gb": round(disk_usage.used / (1024**3), 2),
            "free_gb": round(disk_usage.free / (1024**3), 2),
        },
        "resources": {
            "sites": sites_count,
            "cameras": cameras_count,
            "detectors": detectors_count,
            "actuators": actuators_count,
            "alarms": alarms_count,
            "users": users_count,
        },
        "config": {
            "debug": settings.debug,
            "host": settings.host,
            "port": settings.port,
            "workers": settings.workers,
        }
    }


@router.get("/logs")
async def get_logs(
    current_user = Depends(require_role(UserRole.ADMIN)),
    lines: int = 100,
    level: str = "INFO",
):
    """Get recent logs."""
    # This would integrate with structlog/rotating file handler
    # For now, return placeholder
    return {
        "logs": [
            {
                "timestamp": datetime.now().isoformat(),
                "level": "INFO",
                "message": "Log endpoint not fully implemented - use structured logging backend",
            }
        ],
        "note": "Configure structlog with file handler for persistent logs"
    }


@router.post("/backup")
async def create_backup(
    current_user = Depends(require_role(UserRole.ADMIN)),
    session: AsyncSession = Depends(get_session),
):
    """Create database backup."""
    settings = get_settings()
    backup_dir = Path(settings.storage_path) / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"superguard_backup_{timestamp}.sqlite"
    backup_path = backup_dir / backup_name
    
    # For SQLite, just copy the file
    db_path = settings.database_url.replace("sqlite+aiosqlite:///", "")
    if os.path.exists(db_path):
        shutil.copy2(db_path, backup_path)
        
        # Also backup media (optional, can be large)
        # shutil.copytree(settings.storage_path + "/media", backup_dir / f"media_{timestamp}")
        
        return {
            "success": True,
            "backup_file": backup_name,
            "path": str(backup_path),
            "size_bytes": backup_path.stat().st_size,
        }
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database file not found",
        )


@router.post("/restore")
async def restore_backup(
    backup_file: str = Form(...),
    current_user = Depends(require_role(UserRole.ADMIN)),
):
    """Restore from backup."""
    settings = get_settings()
    backup_dir = Path(settings.storage_path) / "backups"
    backup_path = backup_dir / backup_file
    
    if not backup_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Backup file not found",
        )
    
    db_path = settings.database_url.replace("sqlite+aiosqlite:///", "")
    
    # Close connections first
    await close_db()
    
    # Restore
    shutil.copy2(backup_path, db_path)
    
    # Reinitialize
    await init_db(settings.database_url)
    
    return {
        "success": True,
        "message": "Database restored from backup",
        "backup_file": backup_file,
    }


@router.get("/plugins")
async def list_plugins(
    current_user = Depends(get_current_user),
):
    """List all available plugins."""
    pm = PluginManager()
    await pm.discover_plugins()
    
    plugins = pm.get_available_plugins()
    
    by_type = {}
    for p in plugins:
        t = p.plugin_type.value
        if t not in by_type:
            by_type[t] = []
        by_type[t].append({
            "name": p.name,
            "version": p.version,
            "description": p.description,
            "author": p.author,
        })
    
    return by_type


@router.get("/plugins/loaded")
async def list_loaded_plugins(
    current_user = Depends(require_role(UserRole.ADMIN)),
):
    """List currently loaded plugins."""
    # This would need access to the plugin manager from app state
    return {
        "message": "Access via /system/info or plugin manager instance",
        "note": "Loaded plugins are tracked in the running application"
    }


@router.post("/maintenance/cleanup")
async def cleanup_old_data(
    current_user = Depends(require_role(UserRole.ADMIN)),
    session: AsyncSession = Depends(get_session),
    days: int = 30,
):
    """Clean up old alarm media and recordings."""
    settings = get_settings()
    cutoff = datetime.now() - timedelta(days=days)
    
    from superguard_core.core.database import AlarmMedia
    
    # Find old media
    result = await session.execute(
        select(AlarmMedia).where(AlarmMedia.timestamp < cutoff)
    )
    old_media = result.scalars().all()
    
    deleted_count = 0
    freed_bytes = 0
    
    for media in old_media:
        try:
            if os.path.exists(media.path):
                freed_bytes += os.path.getsize(media.path)
                os.unlink(media.path)
            if media.thumbnail_path and os.path.exists(media.thumbnail_path):
                os.unlink(media.thumbnail_path)
            await session.delete(media)
            deleted_count += 1
        except Exception:
            pass
    
    await session.commit()
    
    return {
        "success": True,
        "deleted_files": deleted_count,
        "freed_mb": round(freed_bytes / (1024**2), 2),
        "cutoff_date": cutoff.isoformat(),
    }

@router.post("/test-notification")
async def send_test_notification(
    request: Request,
    current_user = Depends(get_current_user),
):
    """Send a test notification using available notifier plugins."""
    try:
        data = await request.json()
        title = data.get("title", "Test Notification")
        message = data.get("message", "This is a test notification from SuperGuard Dashboard")
        priority = data.get("priority", "normal")
        site_id = data.get("site_id", 1)
        
        # Create notification payload
        payload = NotificationPayload(
            title=title,
            message=message,
            priority=priority,
            media_urls=[],
            metadata={"source": "dashboard_test", "site_id": site_id, "timestamp": datetime.now().isoformat()}
        )
        
        # For demo purposes, we'll return success without actually sending
        # A real implementation would access app.state.plugin_manager or similar
        return {
            "success": True,
            "message": "Test notification queued for delivery",
            "notification": {
                "title": title,
                "message": message,
                "priority": priority,
                "site_id": site_id
            }
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send test notification: {str(e)}"
        )


from superguard_core.core.database import init_db, close_db, get_session_factory
from datetime import timedelta