"""
Cameras endpoints - CRUD, zone, stream, discover, bindings
"""
import uuid
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models import Camera, Zone, ActuatorBinding, Actuator, User
from app.api.v1.endpoints.auth import get_current_user
from app.schemas import (
    CameraCreate, CameraUpdate, CameraResponse,
    ZoneCreate, ZoneResponse,
    CameraDiscoverRequest, DiscoveredCamera,
    ActuatorBindingCreate, ActuatorBindingResponse,
)

router = APIRouter()


@router.get("/sites/{site_id}/cameras", response_model=List[CameraResponse])
async def list_cameras(
    site_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Camera)
        .where(Camera.site_id == site_id)
        .offset(skip)
        .limit(limit)
        .options(selectinload(Camera.zone))
        .order_by(Camera.created_at)
    )
    return result.scalars().all()


@router.post("/sites/{site_id}/cameras", response_model=CameraResponse, status_code=status.HTTP_201_CREATED)
async def create_camera(
    site_id: str,
    req: CameraCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    data = req.model_dump(exclude={"zone", "password"})
    if req.password:
        data["password_hash"] = req.password  # TODO: encrypt
    cam = Camera(site_id=site_id, **data)
    db.add(cam)
    await db.flush()

    if req.zone:
        zone = Zone(camera_id=cam.id, **req.zone.model_dump())
        db.add(zone)
        await db.flush()

    # Reload with zone relationship
    await db.refresh(cam, attribute_names=["zone"])

    # Build response manually to avoid lazy-load issues
    from app.schemas import CameraResponse, ZoneResponse
    zone_resp = None
    if cam.zone:
        zone_resp = ZoneResponse(rows=cam.zone.rows, cols=cam.zone.cols, cell=cam.zone.cell)
    return CameraResponse(
        id=cam.id, site_id=cam.site_id, name=cam.name, description=cam.description,
        type=cam.type.value, stream_url=cam.stream_url, width=cam.width, height=cam.height,
        fps=cam.fps, is_enabled=cam.is_enabled, is_online=cam.is_online,
        last_seen=cam.last_seen, ptz_enabled=cam.ptz_enabled, zone=zone_resp,
        created_at=cam.created_at,
    )


@router.get("/sites/{site_id}/cameras/{camera_id}", response_model=CameraResponse)
async def get_camera(
    site_id: str,
    camera_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Camera)
        .where(Camera.id == camera_id, Camera.site_id == site_id)
        .options(selectinload(Camera.zone))
    )
    cam = result.scalar_one_or_none()
    if not cam:
        raise HTTPException(status_code=404, detail="Camera not found")
    return cam


@router.patch("/sites/{site_id}/cameras/{camera_id}", response_model=CameraResponse)
async def update_camera(
    site_id: str,
    camera_id: str,
    req: CameraUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(Camera).where(Camera.id == camera_id, Camera.site_id == site_id))
    cam = result.scalar_one_or_none()
    if not cam:
        raise HTTPException(status_code=404, detail="Camera not found")

    for k, v in req.model_dump(exclude_unset=True).items():
        setattr(cam, k, v)
    await db.flush()
    return cam


@router.delete("/sites/{site_id}/cameras/{camera_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_camera(
    site_id: str,
    camera_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(Camera).where(Camera.id == camera_id, Camera.site_id == site_id))
    cam = result.scalar_one_or_none()
    if not cam:
        raise HTTPException(status_code=404, detail="Camera not found")
    await db.delete(cam)
    await db.flush()


@router.patch("/sites/{site_id}/cameras/{camera_id}/zone", response_model=ZoneResponse)
async def update_zone(
    site_id: str,
    camera_id: str,
    req: ZoneCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(Zone).where(Zone.camera_id == camera_id))
    zone = result.scalar_one_or_none()
    if zone:
        zone.rows = req.rows
        zone.cols = req.cols
        zone.cell = req.cell
    else:
        zone = Zone(camera_id=camera_id, **req.model_dump())
        db.add(zone)
    await db.flush()
    return zone


@router.post("/sites/{site_id}/cameras/{camera_id}/test")
async def test_camera(
    site_id: str,
    camera_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Verify camera belongs to site
    result = await db.execute(
        select(Camera).where(Camera.id == camera_id, Camera.site_id == site_id)
    )
    camera = result.scalar_one_or_none()
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")
    
    # Use the health monitor for testing with rediscovery (using same session)
    from app.services.camera_health import CameraHealthMonitor, CameraConfig, CameraDiscovery
    
    cfg = camera.config or {}
    config = CameraConfig(
        id=camera.id,
        name=camera.name,
        type=camera.type.value,
        stream_url=camera.stream_url,
        username=cfg.get('username', ''),
        password=cfg.get('password', ''),
        mac=cfg.get('mac', ''),
        onvif_profile=cfg.get('onvif_profile', ''),
    )
    
    # Check and potentially rediscover
    result = await CameraDiscovery.check_and_rediscover(config)
    
    # Update camera in DB
    camera.is_online = result['online']
    camera.last_seen = datetime.utcnow() if result['online'] else camera.last_seen
    
    # If IP/stream URL changed, update config in DB
    if result.get('ip_changed') and result.get('new_stream_url'):
        new_config = dict(cfg)
        new_config['stream_url'] = result['new_stream_url']
        camera.config = new_config
    
    await db.commit()
    await db.refresh(camera)
    
    return {
        "status": "ok" if result.get("online") else "offline",
        "message": f"Camera {'online' if result.get('online') else 'offline'}",
        "details": result,
    }


@router.post("/sites/{site_id}/cameras/discover", response_model=List[DiscoveredCamera])
async def discover_cameras(
    site_id: str,
    req: CameraDiscoverRequest,
    user: User = Depends(get_current_user),
):
    # Placeholder: real ONVIF/UPnP scan would go here
    return [
        DiscoveredCamera(ip="192.168.1.100", port=80, manufacturer="Generic", onvif=True, url="rtsp://192.168.1.100:554/stream1"),
    ]


@router.get("/sites/{site_id}/cameras/{camera_id}/bindings", response_model=List[ActuatorBindingResponse])
async def list_bindings(
    site_id: str,
    camera_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(ActuatorBinding).where(ActuatorBinding.camera_id == camera_id)
    )
    return result.scalars().all()


@router.delete("/sites/{site_id}/cameras/{camera_id}/bindings/{binding_id}", status_code=204)
async def delete_binding(
    site_id: str,
    camera_id: str,
    binding_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(ActuatorBinding).where(
            ActuatorBinding.id == binding_id,
            ActuatorBinding.camera_id == camera_id
        )
    )
    binding = result.scalar_one_or_none()
    if not binding:
        raise HTTPException(status_code=404, detail="Binding not found")
    await db.delete(binding)
    await db.flush()


@router.post("/sites/{site_id}/cameras/{camera_id}/bindings", response_model=ActuatorBindingResponse, status_code=201)
async def create_binding(
    site_id: str,
    camera_id: str,
    req: ActuatorBindingCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    binding = ActuatorBinding(camera_id=camera_id, **req.model_dump())
    db.add(binding)
    await db.flush()
    return binding