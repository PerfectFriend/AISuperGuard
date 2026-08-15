"""
SuperGuard Core - Cameras API Routes
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks
from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from superguard_core.core.auth import get_current_user, verify_site_access, get_user_sites, require_role
from superguard_core.core.database import get_session, Camera, CameraType, CameraStatus, Site, Detector, UserRole
from superguard_core.core.events import get_event_bus, publish_system_event
from superguard_core.services.camera_manager import CameraManager, get_camera_manager

router = APIRouter()


@router.get("")
async def list_cameras(
    site_id: int,
    current_user = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """List cameras for site."""
    await verify_site_access(site_id, current_user, session)
    
    result = await session.execute(
        select(Camera)
        .where(Camera.site_id == site_id)
        .order_by(Camera.position)
    )
    cameras = result.scalars().all()
    
    return [
        {
            "id": c.id,
            "uuid": c.uuid,
            "name": c.name,
            "description": c.description,
            "type": c.type.value,
            "url": c.url,
            "username": c.username,
            "onvif_profile": c.onvif_profile,
            "width": c.width,
            "height": c.height,
            "fps": c.fps,
            "zone_config": c.zone_config,
            "detector_id": c.detector_id,
            "status": c.status.value,
            "last_frame_at": c.last_frame_at.isoformat() if c.last_frame_at else None,
            "error_message": c.error_message,
            "is_enabled": c.is_enabled,
            "position": c.position,
            "created_at": c.created_at.isoformat(),
        }
        for c in cameras
    ]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_camera(
    site_id: int,
    camera_data: dict,
    current_user = Depends(require_role(UserRole.ADMIN, UserRole.OPERATOR)),
    session: AsyncSession = Depends(get_session),
):
    """Add new camera to site."""
    await verify_site_access(site_id, current_user, session)
    
    # Validate detector if provided
    detector_id = camera_data.get("detector_id")
    if detector_id:
        from superguard_core.core.database import Detector
        result = await session.execute(
            select(Detector).where(Detector.id == detector_id, Detector.site_id == site_id)
        )
        if not result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Detector not found in this site",
            )
    
    # Get max position
    result = await session.execute(
        select(func.coalesce(func.max(Camera.position), -1)).where(Camera.site_id == site_id)
    )
    max_pos = result.scalar() or -1
    
    camera = Camera(
        site_id=site_id,
        name=camera_data.get("name"),
        description=camera_data.get("description"),
        type=CameraType(camera_data.get("type", "rtsp")),
        url=camera_data.get("url"),
        username=camera_data.get("username"),
        password=camera_data.get("password"),
        onvif_profile=camera_data.get("onvif_profile"),
        zone_config=camera_data.get("zone_config"),
        detector_id=detector_id,
        is_enabled=camera_data.get("is_enabled", True),
        position=max_pos + 1,
    )
    session.add(camera)
    await session.commit()
    await session.refresh(camera)
    
    # Start camera if manager exists
    try:
        from superguard_core.services.camera_manager import get_camera_manager
        from superguard_core.core.plugins import PluginManager
        from superguard_core.core.events import EventBus
        pm = PluginManager()
        await pm.discover_plugins()
        bus = await get_event_bus()
        cm = await get_camera_manager(site_id, pm, bus)
        cm.set_session_factory(get_session)
        await cm.add_camera(camera)
    except Exception as e:
        logger.warning(f"Failed to auto-start camera: {e}")
    
    await publish_system_event("camera_created", {"site_id": site_id, "camera_id": camera.id})
    
    return {
        "id": camera.id,
        "uuid": camera.uuid,
        "name": camera.name,
        "type": camera.type.value,
        "url": camera.url,
        "status": camera.status.value,
        "is_enabled": camera.is_enabled,
        "position": camera.position,
    }


@router.get("/{camera_id}")
async def get_camera(
    site_id: int,
    camera_id: int,
    current_user = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Get camera details."""
    await verify_site_access(site_id, current_user, session)
    
    result = await session.execute(
        select(Camera)
        .where(Camera.id == camera_id, Camera.site_id == site_id)
    )
    camera = result.scalar_one_or_none()
    
    if not camera:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Camera not found",
        )
    
    # Get detector info
    detector_info = None
    if camera.detector_id:
        from superguard_core.core.database import Detector
        result = await session.execute(
            select(Detector).where(Detector.id == camera.detector_id)
        )
        detector = result.scalar_one_or_none()
        if detector:
            detector_info = {
                "id": detector.id,
                "name": detector.name,
                "plugin": detector.plugin,
            }
    
    # Get camera manager stats
    stats = None
    try:
        from superguard_core.services.camera_manager import get_camera_manager
        from superguard_core.core.plugins import PluginManager
        from superguard_core.core.events import EventBus
        pm = PluginManager()
        await pm.discover_plugins()
        bus = await get_event_bus()
        cm = await get_camera_manager(site_id, pm, bus)
        stats = cm.get_camera_stats(camera_id)
    except Exception:
        pass
    
    return {
        "id": camera.id,
        "uuid": camera.uuid,
        "name": camera.name,
        "description": camera.description,
        "type": camera.type.value,
        "url": camera.url,
        "username": camera.username,
        "onvif_profile": camera.onvif_profile,
        "width": camera.width,
        "height": camera.height,
        "fps": camera.fps,
        "zone_config": camera.zone_config,
        "detector_id": camera.detector_id,
        "detector": detector_info,
        "status": camera.status.value,
        "last_frame_at": camera.last_frame_at.isoformat() if camera.last_frame_at else None,
        "error_message": camera.error_message,
        "is_enabled": camera.is_enabled,
        "position": camera.position,
        "created_at": camera.created_at.isoformat(),
        "updated_at": camera.updated_at.isoformat(),
        "stats": stats,
    }


@router.patch("/{camera_id}")
async def update_camera(
    site_id: int,
    camera_id: int,
    camera_data: dict,
    current_user = Depends(require_role(UserRole.ADMIN, UserRole.OPERATOR)),
    session: AsyncSession = Depends(get_session),
):
    """Update camera configuration."""
    await verify_site_access(site_id, current_user, session)
    
    result = await session.execute(
        select(Camera).where(Camera.id == camera_id, Camera.site_id == site_id)
    )
    camera = result.scalar_one_or_none()
    
    if not camera:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Camera not found",
        )
    
    # Validate detector if changing
    if "detector_id" in camera_data and camera_data["detector_id"]:
        from superguard_core.core.database import Detector
        result = await session.execute(
            select(Detector).where(Detector.id == camera_data["detector_id"], Detector.site_id == site_id)
        )
        if not result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Detector not found in this site",
            )
        camera.detector_id = camera_data["detector_id"]
    
    # Update fields
    for field in ["name", "description", "url", "username", "password", "onvif_profile", 
                  "zone_config", "is_enabled", "position"]:
        if field in camera_data:
            setattr(camera, field, camera_data[field])
    
    if "type" in camera_data:
        camera.type = CameraType(camera_data["type"])
    
    await session.commit()
    await session.refresh(camera)
    
    # Update camera manager
    try:
        from superguard_core.services.camera_manager import get_camera_manager
        from superguard_core.core.plugins import PluginManager
        from superguard_core.core.events import EventBus
        pm = PluginManager()
        await pm.discover_plugins()
        bus = await get_event_bus()
        cm = await get_camera_manager(site_id, pm, bus)
        cm.set_session_factory(get_session)
        await cm.update_camera(camera)
    except Exception as e:
        logger.warning(f"Failed to update camera manager: {e}")
    
    await publish_system_event("camera_updated", {"site_id": site_id, "camera_id": camera.id})
    
    return {
        "id": camera.id,
        "uuid": camera.uuid,
        "name": camera.name,
        "type": camera.type.value,
        "url": camera.url,
        "status": camera.status.value,
        "is_enabled": camera.is_enabled,
        "position": camera.position,
    }


@router.delete("/{camera_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_camera(
    site_id: int,
    camera_id: int,
    current_user = Depends(require_role(UserRole.ADMIN)),
    session: AsyncSession = Depends(get_session),
):
    """Delete camera."""
    await verify_site_access(site_id, current_user, session)
    
    result = await session.execute(
        select(Camera).where(Camera.id == camera_id, Camera.site_id == site_id)
    )
    camera = result.scalar_one_or_none()
    
    if not camera:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Camera not found",
        )
    
    # Stop camera manager
    try:
        from superguard_core.services.camera_manager import get_camera_manager
        from superguard_core.core.plugins import PluginManager
        from superguard_core.core.events import EventBus
        pm = PluginManager()
        await pm.discover_plugins()
        bus = await get_event_bus()
        cm = await get_camera_manager(site_id, pm, bus)
        await cm.remove_camera(camera_id)
    except Exception:
        pass
    
    await session.delete(camera)
    await session.commit()
    
    await publish_system_event("camera_deleted", {"site_id": site_id, "camera_id": camera_id})


@router.post("/{camera_id}/test")
async def test_camera(
    site_id: int,
    camera_id: int,
    current_user = Depends(require_role(UserRole.ADMIN, UserRole.OPERATOR)),
    session: AsyncSession = Depends(get_session),
):
    """Test camera connection."""
    await verify_site_access(site_id, current_user, session)
    
    result = await session.execute(
        select(Camera).where(Camera.id == camera_id, Camera.site_id == site_id)
    )
    camera = result.scalar_one_or_none()
    
    if not camera:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Camera not found",
        )
    
    # Try to connect and get a frame
    try:
        from superguard_core.services.camera_manager import get_camera_manager
        from superguard_core.core.plugins import PluginManager
        from superguard_core.core.events import EventBus
        pm = PluginManager()
        await pm.discover_plugins()
        bus = await get_event_bus()
        cm = await get_camera_manager(site_id, pm, bus)
        
        # Get snapshot
        frame = await cm.get_snapshot(camera_id)
        
        if frame:
            # Update camera status
            await session.execute(
                update(Camera)
                .where(Camera.id == camera_id)
                .values(status=CameraStatus.ONLINE, error_message=None)
            )
            await session.commit()
            
            return {
                "success": True,
                "message": "Camera connection successful",
                "width": frame.image.shape[1] if hasattr(frame.image, 'shape') else 0,
                "height": frame.image.shape[0] if hasattr(frame.image, 'shape') else 0,
            }
        else:
            raise Exception("No frame received")
            
    except Exception as e:
        # Update camera status
        await session.execute(
            update(Camera)
            .where(Camera.id == camera_id)
            .values(status=CameraStatus.ERROR, error_message=str(e))
        )
        await session.commit()
        
        return {
            "success": False,
            "message": f"Camera connection failed: {e}",
        }


@router.get("/{camera_id}/snapshot")
async def get_camera_snapshot(
    site_id: int,
    camera_id: int,
    current_user = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Get single snapshot from camera."""
    await verify_site_access(site_id, current_user, session)
    
    result = await session.execute(
        select(Camera).where(Camera.id == camera_id, Camera.site_id == site_id)
    )
    camera = result.scalar_one_or_none()
    
    if not camera:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Camera not found",
        )
    
    try:
        from superguard_core.services.camera_manager import get_camera_manager
        from superguard_core.core.plugins import PluginManager
        from superguard_core.core.events import EventBus
        pm = PluginManager()
        await pm.discover_plugins()
        bus = await get_event_bus()
        cm = await get_camera_manager(site_id, pm, bus)
        
        frame = await cm.get_snapshot(camera_id)
        
        if frame:
            import base64
            import cv2
            _, buffer = cv2.imencode('.jpg', frame.image)
            img_base64 = base64.b64encode(buffer).decode('utf-8')
            return {
                "camera_id": camera_id,
                "timestamp": frame.timestamp,
                "image_base64": img_base64,
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Could not get snapshot",
            )
            
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Snapshot failed: {e}",
        )


@router.post("/{camera_id}/ptz")
async def ptz_control(
    site_id: int,
    camera_id: int,
    ptz_data: dict,
    current_user = Depends(require_role(UserRole.ADMIN, UserRole.OPERATOR)),
    session: AsyncSession = Depends(get_session),
):
    """Control PTZ (pan/tilt/zoom)."""
    await verify_site_access(site_id, current_user, session)
    
    result = await session.execute(
        select(Camera).where(Camera.id == camera_id, Camera.site_id == site_id)
    )
    camera = result.scalar_one_or_none()
    
    if not camera:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Camera not found",
        )
    
    command = ptz_data.get("command")  # left, right, up, down, zoom_in, zoom_out, preset
    if not command:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Command required",
        )
    
    try:
        from superguard_core.services.camera_manager import get_camera_manager
        from superguard_core.core.plugins import PluginManager
        from superguard_core.core.events import EventBus
        pm = PluginManager()
        await pm.discover_plugins()
        bus = await get_event_bus()
        cm = await get_camera_manager(site_id, pm, bus)
        
        success = await cm.ptz_control(camera_id, command, **ptz_data.get("params", {}))
        
        return {"success": success, "command": command}
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"PTZ control failed: {e}",
        )


@router.post("/discover")
async def discover_cameras(
    site_id: int,
    current_user = Depends(require_role(UserRole.ADMIN, UserRole.OPERATOR)),
    session: AsyncSession = Depends(get_session),
):
    """Discover cameras on network using ONVIF/UPnP."""
    await verify_site_access(site_id, current_user, session)
    
    try:
        from superguard_core.services.camera_manager import CameraManager
        discovered = await CameraManager.discover_cameras(timeout=10)
        
        return {
            "discovered": [
                {
                    "name": c.name,
                    "url": c.url,
                    "type": c.type,
                    "manufacturer": c.manufacturer,
                    "model": c.model,
                    "mac_address": c.mac_address,
                    "ip_address": c.ip_address,
                    "onvif_profile": c.onvif_profile,
                    "extra": c.extra,
                }
                for c in discovered
            ]
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Discovery failed: {e}",
        )


@router.get("/{camera_id}/stream")
async def get_camera_stream(
    site_id: int,
    camera_id: int,
    current_user = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Get stream URLs (WebRTC, HLS, RTSP) for camera."""
    await verify_site_access(site_id, current_user, session)
    
    result = await session.execute(
        select(Camera).where(Camera.id == camera_id, Camera.site_id == site_id)
    )
    camera = result.scalar_one_or_none()
    
    if not camera:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Camera not found",
        )
    
    settings = get_settings()
    
    return {
        "camera_id": camera_id,
        "webrtc": f"http://localhost:{settings.mediamtx_webrtc_port}/camera_{camera_id}",
        "hls": f"http://localhost:{settings.mediamtx_hls_port}/camera_{camera_id}/index.m3u8",
        "rtsp": f"rtsp://localhost:{settings.mediamtx_rtsp_port}/camera_{camera_id}",
        "snapshot": f"http://localhost:{settings.mediamtx_hls_port}/camera_{camera_id}/snapshot.jpg",
    }


from superguard_core.core.config import get_settings
import logging
logger = logging.getLogger(__name__)