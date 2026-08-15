"""
SuperGuard Core - Alarms API Routes
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from superguard_core.core.auth import get_current_user, verify_site_access, require_role
from superguard_core.core.database import get_session, Alarm, AlarmStatus, AlarmMedia, MediaType, Camera, UserRole
from superguard_core.core.events import get_event_bus, publish_alarm, Streams
from superguard_core.services.alarm_engine import AlarmEngine, get_alarm_engine

router = APIRouter()


@router.get("")
async def list_alarms(
    site_id: int,
    current_user = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    status_filter: Optional[str] = Query(None),
    camera_id: Optional[int] = Query(None),
    since: Optional[str] = Query(None),
):
    """List alarms for site with filters."""
    await verify_site_access(site_id, current_user, session)
    
    from datetime import datetime
    from superguard_core.services.alarm_engine import get_alarm_engine
    from superguard_core.core.plugins import PluginManager
    from superguard_core.core.events import EventBus
    
    pm = PluginManager()
    await pm.discover_plugins()
    bus = await get_event_bus()
    ae = await get_alarm_engine(site_id, bus)
    ae.set_session_factory(get_session)
    
    # Parse since
    since_dt = None
    if since:
        try:
            since_dt = datetime.fromisoformat(since.replace('Z', '+00:00'))
        except:
            pass
    
    status_enum = None
    if status_filter:
        try:
            status_enum = AlarmStatus(status_filter)
        except:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status: {status_filter}",
            )
    
    alarms = await ae.get_alarm_history(
        limit=limit,
        offset=offset,
        status_filter=status_enum,
        camera_id=camera_id,
        since=since_dt,
    )
    
    # Get media count for each alarm
    alarm_ids = [a.id for a in alarms]
    media_counts = {}
    if alarm_ids:
        result = await session.execute(
            select(AlarmMedia.alarm_id, func.count(AlarmMedia.id))
            .where(AlarmMedia.alarm_id.in_(alarm_ids))
            .group_by(AlarmMedia.alarm_id)
        )
        media_counts = {row[0]: row[1] for row in result.all()}
    
    return [
        {
            "id": a.id,
            "uuid": a.uuid,
            "camera_id": a.camera_id,
            "detector_id": a.detector_id,
            "actuator_id": a.actuator_id,
            "status": a.status.value,
            "trigger_data": a.trigger_data,
            "started_at": a.started_at.isoformat(),
            "ended_at": a.ended_at.isoformat() if a.ended_at else None,
            "acknowledged_at": a.acknowledged_at.isoformat() if a.acknowledged_at else None,
            "acknowledged_by": a.acknowledged_by,
            "auto_cancel_at": a.auto_cancel_at.isoformat() if a.auto_cancel_at else None,
            "media_count": media_counts.get(a.id, 0),
        }
        for a in alarms
    ]


@router.get("/active")
async def get_active_alarms(
    site_id: int,
    current_user = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Get currently active alarms."""
    await verify_site_access(site_id, current_user, session)
    
    from superguard_core.services.alarm_engine import get_alarm_engine
    from superguard_core.core.plugins import PluginManager
    from superguard_core.core.events import EventBus
    
    pm = PluginManager()
    await pm.discover_plugins()
    bus = await get_event_bus()
    ae = await get_alarm_engine(site_id, bus)
    ae.set_session_factory(get_session)
    
    alarms = await ae.get_active_alarms()
    
    # Get camera names
    camera_ids = list(set(a.camera_id for a in alarms))
    cameras = {}
    if camera_ids:
        result = await session.execute(select(Camera).where(Camera.id.in_(camera_ids)))
        cameras = {c.id: c.name for c in result.scalars().all()}
    
    return [
        {
            "id": a.id,
            "uuid": a.uuid,
            "camera_id": a.camera_id,
            "camera_name": cameras.get(a.camera_id),
            "detector_id": a.detector_id,
            "status": a.status.value,
            "trigger_data": a.trigger_data,
            "started_at": a.started_at.isoformat(),
            "auto_cancel_at": a.auto_cancel_at.isoformat() if a.auto_cancel_at else None,
        }
        for a in alarms
    ]


@router.get("/{alarm_id}")
async def get_alarm(
    site_id: int,
    alarm_id: int,
    current_user = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Get alarm details with media."""
    await verify_site_access(site_id, current_user, session)
    
    result = await session.execute(
        select(Alarm)
        .where(Alarm.id == alarm_id, Alarm.site_id == site_id)
        .options(selectinload(Alarm.media))
    )
    alarm = result.scalar_one_or_none()
    
    if not alarm:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alarm not found",
        )
    
    # Get camera and detector names
    camera_result = await session.execute(select(Camera).where(Camera.id == alarm.camera_id))
    camera = camera_result.scalar_one_or_none()
    
    from superguard_core.core.database import Detector
    detector_result = await session.execute(select(Detector).where(Detector.id == alarm.detector_id))
    detector = detector_result.scalar_one_or_none()
    
    return {
        "id": alarm.id,
        "uuid": alarm.uuid,
        "camera_id": alarm.camera_id,
        "camera_name": camera.name if camera else None,
        "detector_id": alarm.detector_id,
        "detector_name": detector.name if detector else None,
        "actuator_id": alarm.actuator_id,
        "status": alarm.status.value,
        "trigger_data": alarm.trigger_data,
        "started_at": alarm.started_at.isoformat(),
        "ended_at": alarm.ended_at.isoformat() if alarm.ended_at else None,
        "acknowledged_at": alarm.acknowledged_at.isoformat() if alarm.acknowledged_at else None,
        "acknowledged_by": alarm.acknowledged_by,
        "auto_cancel_at": alarm.auto_cancel_at.isoformat() if alarm.auto_cancel_at else None,
        "media": [
            {
                "id": m.id,
                "uuid": m.uuid,
                "type": m.type.value,
                "path": m.path,
                "thumbnail_path": m.thumbnail_path,
                "timestamp": m.timestamp.isoformat(),
                "file_size": m.file_size,
                "duration": m.duration,
                "metadata": m.metadata,
            }
            for m in alarm.media
        ],
    }


@router.post("/{alarm_id}/acknowledge")
async def acknowledge_alarm(
    site_id: int,
    alarm_id: int,
    current_user = Depends(require_role(UserRole.ADMIN, UserRole.OPERATOR)),
    session: AsyncSession = Depends(get_session),
):
    """Acknowledge alarm."""
    await verify_site_access(site_id, current_user, session)
    
    from superguard_core.services.alarm_engine import get_alarm_engine
    from superguard_core.core.plugins import PluginManager
    from superguard_core.core.events import EventBus
    
    pm = PluginManager()
    await pm.discover_plugins()
    bus = await get_event_bus()
    ae = await get_alarm_engine(site_id, bus)
    ae.set_session_factory(get_session)
    
    try:
        alarm = await ae.acknowledge_alarm(alarm_id, current_user.id)
        return {
            "success": True,
            "alarm_id": alarm.id,
            "status": alarm.status.value,
            "acknowledged_at": alarm.acknowledged_at.isoformat(),
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/{alarm_id}/resolve")
async def resolve_alarm(
    site_id: int,
    alarm_id: int,
    resolve_data: dict,
    current_user = Depends(require_role(UserRole.ADMIN, UserRole.OPERATOR)),
    session: AsyncSession = Depends(get_session),
):
    """Resolve alarm (resolved or false_positive)."""
    await verify_site_access(site_id, current_user, session)
    
    reason = resolve_data.get("reason", "resolved")
    if reason not in ["resolved", "false_positive"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reason must be 'resolved' or 'false_positive'",
        )
    
    from superguard_core.services.alarm_engine import get_alarm_engine
    from superguard_core.core.plugins import PluginManager
    from superguard_core.core.events import EventBus
    
    pm = PluginManager()
    await pm.discover_plugins()
    bus = await get_event_bus()
    ae = await get_alarm_engine(site_id, bus)
    ae.set_session_factory(get_session)
    
    try:
        alarm = await ae.resolve_alarm(alarm_id, current_user.id, reason)
        return {
            "success": True,
            "alarm_id": alarm.id,
            "status": alarm.status.value,
            "ended_at": alarm.ended_at.isoformat(),
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/{alarm_id}/trigger-actuator")
async def trigger_actuator_for_alarm(
    site_id: int,
    alarm_id: int,
    trigger_data: dict,
    current_user = Depends(require_role(UserRole.ADMIN, UserRole.OPERATOR)),
    session: AsyncSession = Depends(get_session),
):
    """Manually trigger actuator for alarm."""
    await verify_site_access(site_id, current_user, session)
    
    action = trigger_data.get("action")  # on, off
    if action not in ["on", "off"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Action must be 'on' or 'off'",
        )
    
    result = await session.execute(
        select(Alarm).where(Alarm.id == alarm_id, Alarm.site_id == site_id)
    )
    alarm = result.scalar_one_or_none()
    
    if not alarm:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alarm not found",
        )
    
    if not alarm.actuator_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No actuator bound to this alarm",
        )
    
    from superguard_core.services.actuator_engine import get_actuator_engine
    from superguard_core.core.plugins import PluginManager
    from superguard_core.core.events import EventBus
    
    pm = PluginManager()
    await pm.discover_plugins()
    bus = await get_event_bus()
    ae = await get_actuator_engine(site_id, pm, bus)
    ae.set_session_factory(get_session)
    
    try:
        state = await ae.manual_command(alarm.actuator_id, "turn_on" if action == "on" else "turn_off")
        return {
            "success": True,
            "actuator_id": alarm.actuator_id,
            "state": {"is_on": state.is_on},
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Actuator command failed: {e}",
        )


@router.get("/stats/summary")
async def get_alarm_stats(
    site_id: int,
    current_user = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Get alarm statistics summary."""
    await verify_site_access(site_id, current_user, session)
    
    from datetime import datetime, timedelta
    
    now = datetime.now()
    day_ago = now - timedelta(days=1)
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)
    
    # Total counts by status
    status_counts = {}
    for status_enum in AlarmStatus:
        result = await session.execute(
            select(func.count(Alarm.id))
            .where(Alarm.site_id == site_id, Alarm.status == status_enum)
        )
        status_counts[status_enum.value] = result.scalar() or 0
    
    # Recent counts
    result = await session.execute(
        select(func.count(Alarm.id))
        .where(Alarm.site_id == site_id, Alarm.started_at >= day_ago)
    )
    last_24h = result.scalar() or 0
    
    result = await session.execute(
        select(func.count(Alarm.id))
        .where(Alarm.site_id == site_id, Alarm.started_at >= week_ago)
    )
    last_7d = result.scalar() or 0
    
    result = await session.execute(
        select(func.count(Alarm.id))
        .where(Alarm.site_id == site_id, Alarm.started_at >= month_ago)
    )
    last_30d = result.scalar() or 0
    
    # By camera
    result = await session.execute(
        select(Alarm.camera_id, func.count(Alarm.id))
        .where(Alarm.site_id == site_id, Alarm.started_at >= week_ago)
        .group_by(Alarm.camera_id)
        .order_by(func.count(Alarm.id).desc())
    )
    by_camera = {row[0]: row[1] for row in result.all()}
    
    # Get camera names
    camera_names = {}
    if by_camera:
        cam_ids = list(by_camera.keys())
        result = await session.execute(select(Camera.id, Camera.name).where(Camera.id.in_(cam_ids)))
        camera_names = {row[0]: row[1] for row in result.all()}
    
    return {
        "by_status": status_counts,
        "recent": {
            "last_24h": last_24h,
            "last_7d": last_7d,
            "last_30d": last_30d,
        },
        "by_camera": [
            {"camera_id": cid, "camera_name": camera_names.get(cid), "count": count}
            for cid, count in by_camera.items()
        ],
        "engine_stats": None,  # Would come from alarm engine
    }


from typing import Optional