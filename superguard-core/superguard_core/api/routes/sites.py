"""
SuperGuard Core - Sites API Routes
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from superguard_core.core.auth import get_current_user, require_role, verify_site_access, get_user_sites
from superguard_core.core.database import get_session, Site, Camera, Detector, Actuator, Alarm, UserRole
from superguard_core.core.events import get_event_bus, publish_system_event

router = APIRouter()


@router.get("")
async def list_sites(
    current_user = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """List sites accessible to current user."""
    site_ids = await get_user_sites(current_user, session)
    
    if not site_ids:
        return []
    
    result = await session.execute(
        select(Site)
        .where(Site.id.in_(site_ids), Site.is_active == True)
        .order_by(Site.created_at.desc())
    )
    sites = result.scalars().all()
    
    return [
        {
            "id": s.id,
            "uuid": s.uuid,
            "name": s.name,
            "description": s.description,
            "address": s.address,
            "timezone": s.timezone,
            "latitude": s.latitude,
            "longitude": s.longitude,
            "is_active": s.is_active,
            "created_at": s.created_at.isoformat(),
            "stats": {
                "cameras": 0,
                "detectors": 0,
                "actuators": 0,
                "active_alarms": 0,
            }
        }
        for s in sites
    ]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_site(
    site_data: dict,
    current_user = Depends(require_role(UserRole.ADMIN)),
    session: AsyncSession = Depends(get_session),
):
    """Create new site (admin only)."""
    site = Site(
        name=site_data.get("name"),
        description=site_data.get("description"),
        address=site_data.get("address"),
        timezone=site_data.get("timezone", "UTC"),
        latitude=site_data.get("latitude"),
        longitude=site_data.get("longitude"),
    )
    session.add(site)
    await session.flush()
    
    # Assign creator as admin
    from superguard_core.core.database import site_users
    await session.execute(
        site_users.insert().values(user_id=current_user.id, site_id=site.id, role=UserRole.ADMIN)
    )
    
    await session.commit()
    await session.refresh(site)
    
    await publish_system_event("site_created", {"site_id": site.id, "name": site.name})
    
    return {
        "id": site.id,
        "uuid": site.uuid,
        "name": site.name,
        "description": site.description,
        "address": site.address,
        "timezone": site.timezone,
        "latitude": site.latitude,
        "longitude": site.longitude,
        "is_active": site.is_active,
        "created_at": site.created_at.isoformat(),
    }


@router.get("/{site_id}")
async def get_site(
    site_id: int,
    current_user = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Get site details with stats."""
    site = await verify_site_access(site_id, current_user, session)
    
    # Get stats
    cameras_count = await session.execute(
        select(func.count(Camera.id)).where(Camera.site_id == site_id)
    )
    detectors_count = await session.execute(
        select(func.count(Detector.id)).where(Detector.site_id == site_id)
    )
    actuators_count = await session.execute(
        select(func.count(Actuator.id)).where(Actuator.site_id == site_id)
    )
    active_alarms = await session.execute(
        select(func.count(Alarm.id))
        .where(Alarm.site_id == site_id, Alarm.status == "active")
    )
    
    return {
        "id": site.id,
        "uuid": site.uuid,
        "name": site.name,
        "description": site.description,
        "address": site.address,
        "timezone": site.timezone,
        "latitude": site.latitude,
        "longitude": site.longitude,
        "is_active": site.is_active,
        "created_at": site.created_at.isoformat(),
        "updated_at": site.updated_at.isoformat(),
        "stats": {
            "cameras": cameras_count.scalar() or 0,
            "detectors": detectors_count.scalar() or 0,
            "actuators": actuators_count.scalar() or 0,
            "active_alarms": active_alarms.scalar() or 0,
        }
    }


@router.patch("/{site_id}")
async def update_site(
    site_id: int,
    site_data: dict,
    current_user = Depends(require_role(UserRole.ADMIN, UserRole.OPERATOR)),
    session: AsyncSession = Depends(get_session),
):
    """Update site (admin/operator)."""
    site = await verify_site_access(site_id, current_user, session)
    
    if "name" in site_data:
        site.name = site_data["name"]
    if "description" in site_data:
        site.description = site_data["description"]
    if "address" in site_data:
        site.address = site_data["address"]
    if "timezone" in site_data:
        site.timezone = site_data["timezone"]
    if "latitude" in site_data:
        site.latitude = site_data["latitude"]
    if "longitude" in site_data:
        site.longitude = site_data["longitude"]
    if "is_active" in site_data:
        site.is_active = site_data["is_active"]
    
    await session.commit()
    await session.refresh(site)
    
    await publish_system_event("site_updated", {"site_id": site.id})
    
    return {
        "id": site.id,
        "uuid": site.uuid,
        "name": site.name,
        "description": site.description,
        "address": site.address,
        "timezone": site.timezone,
        "latitude": site.latitude,
        "longitude": site.longitude,
        "is_active": site.is_active,
        "created_at": site.created_at.isoformat(),
        "updated_at": site.updated_at.isoformat(),
    }


@router.delete("/{site_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_site(
    site_id: int,
    current_user = Depends(require_role(UserRole.ADMIN)),
    session: AsyncSession = Depends(get_session),
):
    """Delete site (admin only)."""
    site = await verify_site_access(site_id, current_user, session)
    
    await session.delete(site)
    await session.commit()
    
    await publish_system_event("site_deleted", {"site_id": site_id})


@router.get("/{site_id}/dashboard")
async def get_site_dashboard(
    site_id: int,
    current_user = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Get aggregated dashboard data for site."""
    site = await verify_site_access(site_id, current_user, session)
    
    # Cameras with status
    cameras_result = await session.execute(
        select(Camera).where(Camera.site_id == site_id).order_by(Camera.position)
    )
    cameras = cameras_result.scalars().all()
    
    # Active alarms
    alarms_result = await session.execute(
        select(Alarm)
        .where(Alarm.site_id == site_id, Alarm.status == "active")
        .order_by(Alarm.started_at.desc())
        .limit(10)
    )
    active_alarms = alarms_result.scalars().all()
    
    # Recent alarms (last 24h)
    from datetime import datetime, timedelta
    since = datetime.now() - timedelta(hours=24)
    recent_alarms_result = await session.execute(
        select(Alarm)
        .where(Alarm.site_id == site_id, Alarm.started_at >= since)
        .order_by(Alarm.started_at.desc())
        .limit(20)
    )
    recent_alarms = recent_alarms_result.scalars().all()
    
    # Actuators
    actuators_result = await session.execute(
        select(Actuator).where(Actuator.site_id == site_id)
    )
    actuators = actuators_result.scalars().all()
    
    return {
        "site": {
            "id": site.id,
            "uuid": site.uuid,
            "name": site.name,
            "timezone": site.timezone,
        },
        "cameras": [
            {
                "id": c.id,
                "uuid": c.uuid,
                "name": c.name,
                "type": c.type.value,
                "status": c.status.value,
                "is_enabled": c.is_enabled,
                "position": c.position,
                "last_frame_at": c.last_frame_at.isoformat() if c.last_frame_at else None,
            }
            for c in cameras
        ],
        "active_alarms": [
            {
                "id": a.id,
                "uuid": a.uuid,
                "camera_id": a.camera_id,
                "status": a.status.value,
                "started_at": a.started_at.isoformat(),
                "trigger_data": a.trigger_data,
            }
            for a in active_alarms
        ],
        "recent_alarms": [
            {
                "id": a.id,
                "uuid": a.uuid,
                "camera_id": a.camera_id,
                "status": a.status.value,
                "started_at": a.started_at.isoformat(),
                "ended_at": a.ended_at.isoformat() if a.ended_at else None,
            }
            for a in recent_alarms
        ],
        "actuators": [
            {
                "id": a.id,
                "uuid": a.uuid,
                "name": a.name,
                "plugin": a.plugin,
                "is_enabled": a.is_enabled,
                "last_state": a.last_state,
                "camera_bindings": a.camera_bindings,
            }
            for a in actuators
        ],
    }


from datetime import datetime