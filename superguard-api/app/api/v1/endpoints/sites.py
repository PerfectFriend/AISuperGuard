"""
Sites endpoints - CRUD, dashboard, wizard
"""
import uuid
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models import Site, Camera, Actuator, Detector, Alarm, AlarmState, User
from app.api.v1.endpoints.auth import get_current_user
from app.schemas import (
    SiteCreate,
    SiteUpdate,
    SiteResponse,
    DashboardResponse,
    CameraResponse,
    ActuatorResponse,
    DetectorResponse,
    AlarmResponse,
)

router = APIRouter()


@router.get("", response_model=List[SiteResponse])
async def list_sites(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Site)
        .where(Site.is_active == True)
        .offset(skip)
        .limit(limit)
        .order_by(Site.created_at.desc())
    )
    sites = result.scalars().all()

    # Add counts
    out = []
    for s in sites:
        cams = await db.execute(select(func.count(Camera.id)).where(Camera.site_id == s.id))
        acts = await db.execute(select(func.count(Actuator.id)).where(Actuator.site_id == s.id))
        dets = await db.execute(select(func.count(Detector.id)).where(Detector.site_id == s.id))
        alms = await db.execute(
            select(func.count(Alarm.id)).where(
                Alarm.site_id == s.id,
                Alarm.state == AlarmState.triggered,
            )
        )
        resp = SiteResponse.model_validate(s)
        resp.camera_count = cams.scalar_one()
        resp.actuator_count = acts.scalar_one()
        resp.detector_count = dets.scalar_one()
        resp.active_alarms = alms.scalar_one()
        out.append(resp)
    return out


@router.post("", response_model=SiteResponse, status_code=status.HTTP_201_CREATED)
async def create_site(
    req: SiteCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    site = Site(**req.model_dump())
    db.add(site)
    await db.flush()

    # Create default detector for site
    default_det = Detector(
        site_id=site.id,
        name="YOLO11n Default",
        type="yolo",
        model_path="models/yolo11n.onnx",
        classes=[2, 5, 7],
        confidence_threshold=0.5,
        require_frames=3,
        auto_resolve_frames=10,
    )
    db.add(default_det)
    await db.flush()

    return SiteResponse.model_validate(site)


@router.get("/{site_id}", response_model=SiteResponse)
async def get_site(
    site_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(Site).where(Site.id == site_id))
    site = result.scalar_one_or_none()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    return SiteResponse.model_validate(site)


@router.patch("/{site_id}", response_model=SiteResponse)
async def update_site(
    site_id: str,
    req: SiteUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(Site).where(Site.id == site_id))
    site = result.scalar_one_or_none()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    for k, v in req.model_dump(exclude_unset=True).items():
        setattr(site, k, v)

    # Manually update updated_at to avoid greenlet issues with func.now() onupdate
    site.updated_at = datetime.utcnow()
    
    await db.flush()
    return SiteResponse.model_validate(site)


@router.delete("/{site_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_site(
    site_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(Site).where(Site.id == site_id))
    site = result.scalar_one_or_none()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    await db.delete(site)
    await db.flush()


@router.get("/{site_id}/dashboard", response_model=DashboardResponse)
async def get_dashboard(
    site_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(Site).where(Site.id == site_id))
    site = result.scalar_one_or_none()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    cams_result = await db.execute(
        select(Camera).where(Camera.site_id == site_id).order_by(Camera.created_at).options(selectinload(Camera.zone))
    )
    cameras = cams_result.scalars().all()

    acts_result = await db.execute(
        select(Actuator).where(Actuator.site_id == site_id).order_by(Actuator.created_at)
    )
    actuators = acts_result.scalars().all()

    dets_result = await db.execute(
        select(Detector).where(Detector.site_id == site_id)
    )
    detectors = dets_result.scalars().all()

    alarms_result = await db.execute(
        select(Alarm).where(
            Alarm.site_id == site_id,
            Alarm.state == AlarmState.triggered,
        ).order_by(Alarm.created_at.desc()).limit(10)
    )
    active_alarms = alarms_result.scalars().all()

    import time as _time
    health = {
        "status": "healthy",
        "cameras_online": sum(1 for c in cameras if c.is_online),
        "cameras_total": len(cameras),
        "actuators_online": sum(1 for a in actuators if a.is_online),
        "active_alarms": len(active_alarms),
        "uptime_seconds": _time.time(),
    }

    return DashboardResponse(
        site=SiteResponse.model_validate(site),
        cameras=[CameraResponse.model_validate(c) for c in cameras],
        actuators=[ActuatorResponse.model_validate(a) for a in actuators],
        detectors=[DetectorResponse.model_validate(d) for d in detectors],
        active_alarms=[AlarmResponse.model_validate(a) for a in active_alarms],
        system_health=health,
    )