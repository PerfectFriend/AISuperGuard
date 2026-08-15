"""
SuperGuard Core - Detectors API Routes
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from superguard_core.core.auth import get_current_user, verify_site_access, require_role
from superguard_core.core.database import get_session, Detector, Camera, UserRole
from superguard_core.core.events import get_event_bus, publish_system_event
from superguard_core.services.detection_engine import DetectionEngine, get_detection_engine

router = APIRouter()


@router.get("")
async def list_detectors(
    site_id: int,
    current_user = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """List detectors for site."""
    await verify_site_access(site_id, current_user, session)
    
    result = await session.execute(
        select(Detector).where(Detector.site_id == site_id).order_by(Detector.created_at.desc())
    )
    detectors = result.scalars().all()
    
    # Count cameras using each detector
    from sqlalchemy import func
    cam_counts = {}
    for det in detectors:
        result = await session.execute(
            select(func.count(Camera.id)).where(Camera.detector_id == det.id)
        )
        cam_counts[det.id] = result.scalar() or 0
    
    return [
        {
            "id": d.id,
            "uuid": d.uuid,
            "name": d.name,
            "description": d.description,
            "plugin": d.plugin,
            "config": d.config,
            "classes": d.classes,
            "confidence_threshold": d.confidence_threshold,
            "iou_threshold": d.iou_threshold,
            "interval": d.interval,
            "is_enabled": d.is_enabled,
            "camera_count": cam_counts.get(d.id, 0),
            "created_at": d.created_at.isoformat(),
        }
        for d in detectors
    ]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_detector(
    site_id: int,
    detector_data: dict,
    current_user = Depends(require_role(UserRole.ADMIN, UserRole.OPERATOR)),
    session: AsyncSession = Depends(get_session),
):
    """Create new detector."""
    await verify_site_access(site_id, current_user, session)
    
    # Validate plugin exists
    from superguard_core.core.plugins import PluginManager
    pm = PluginManager()
    await pm.discover_plugins()
    
    plugin_name = detector_data.get("plugin")
    plugin_meta = None
    for meta in pm.get_available_detectors():
        if meta.name == plugin_name:
            plugin_meta = meta
            break
    
    if not plugin_meta:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Detector plugin not found: {plugin_name}",
        )
    
    detector = Detector(
        site_id=site_id,
        name=detector_data.get("name"),
        description=detector_data.get("description"),
        plugin=plugin_name,
        config=detector_data.get("config", {}),
        classes=detector_data.get("classes", []),
        confidence_threshold=detector_data.get("confidence_threshold", 0.35),
        iou_threshold=detector_data.get("iou_threshold", 0.45),
        interval=detector_data.get("interval", 1.0),
        is_enabled=detector_data.get("is_enabled", True),
    )
    session.add(detector)
    await session.commit()
    await session.refresh(detector)
    
    # Start detection engine
    try:
        from superguard_core.core.plugins import PluginManager
        from superguard_core.core.events import EventBus
        bus = await get_event_bus()
        de = await get_detection_engine(site_id, pm, bus)
        de.set_session_factory(get_session)
        
        # Load this detector
        result = await session.execute(
            select(Camera).where(Camera.detector_id == detector.id, Camera.is_enabled == True)
        )
        cam_ids = [c.id for c in result.scalars().all()]
        if cam_ids:
            await de._start_detector(detector, cam_ids)
    except Exception as e:
        logger.warning(f"Failed to auto-start detector: {e}")
    
    await publish_system_event("detector_created", {"site_id": site_id, "detector_id": detector.id})
    
    return {
        "id": detector.id,
        "uuid": detector.uuid,
        "name": detector.name,
        "plugin": detector.plugin,
        "is_enabled": detector.is_enabled,
    }


@router.get("/{detector_id}")
async def get_detector(
    site_id: int,
    detector_id: int,
    current_user = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Get detector details."""
    await verify_site_access(site_id, current_user, session)
    
    result = await session.execute(
        select(Detector).where(Detector.id == detector_id, Detector.site_id == site_id)
    )
    detector = result.scalar_one_or_none()
    
    if not detector:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Detector not found",
        )
    
    # Get cameras using this detector
    from sqlalchemy import select
    result = await session.execute(
        select(Camera).where(Camera.detector_id == detector_id)
    )
    cameras = result.scalars().all()
    
    # Get engine stats
    stats = None
    try:
        from superguard_core.services.detection_engine import get_detection_engine
        from superguard_core.core.plugins import PluginManager
        from superguard_core.core.events import EventBus
        pm = PluginManager()
        await pm.discover_plugins()
        bus = await get_event_bus()
        de = await get_detection_engine(site_id, pm, bus)
        stats = de.get_pipeline_stats(detector_id)
    except Exception:
        pass
    
    return {
        "id": detector.id,
        "uuid": detector.uuid,
        "name": detector.name,
        "description": detector.description,
        "plugin": detector.plugin,
        "config": detector.config,
        "classes": detector.classes,
        "confidence_threshold": detector.confidence_threshold,
        "iou_threshold": detector.iou_threshold,
        "interval": detector.interval,
        "is_enabled": detector.is_enabled,
        "cameras": [
            {"id": c.id, "name": c.name, "status": c.status.value}
            for c in cameras
        ],
        "stats": stats,
        "created_at": detector.created_at.isoformat(),
        "updated_at": detector.updated_at.isoformat(),
    }


@router.patch("/{detector_id}")
async def update_detector(
    site_id: int,
    detector_id: int,
    detector_data: dict,
    current_user = Depends(require_role(UserRole.ADMIN, UserRole.OPERATOR)),
    session: AsyncSession = Depends(get_session),
):
    """Update detector configuration."""
    await verify_site_access(site_id, current_user, session)
    
    result = await session.execute(
        select(Detector).where(Detector.id == detector_id, Detector.site_id == site_id)
    )
    detector = result.scalar_one_or_none()
    
    if not detector:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Detector not found",
        )
    
    # Update fields
    for field in ["name", "description", "config", "classes", "confidence_threshold", 
                  "iou_threshold", "interval", "is_enabled"]:
        if field in detector_data:
            setattr(detector, field, detector_data[field])
    
    if "plugin" in detector_data:
        # Validate plugin
        from superguard_core.core.plugins import PluginManager
        pm = PluginManager()
        await pm.discover_plugins()
        if detector_data["plugin"] not in [m.name for m in pm.get_available_detectors()]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Detector plugin not found: {detector_data['plugin']}",
            )
        detector.plugin = detector_data["plugin"]
    
    await session.commit()
    await session.refresh(detector)
    
    # Update detection engine
    try:
        from superguard_core.services.detection_engine import get_detection_engine
        from superguard_core.core.plugins import PluginManager
        from superguard_core.core.events import EventBus
        pm = PluginManager()
        await pm.discover_plugins()
        bus = await get_event_bus()
        de = await get_detection_engine(site_id, pm, bus)
        de.set_session_factory(get_session)
        await de.update_detector(detector)
    except Exception as e:
        logger.warning(f"Failed to update detection engine: {e}")
    
    await publish_system_event("detector_updated", {"site_id": site_id, "detector_id": detector.id})
    
    return {
        "id": detector.id,
        "uuid": detector.uuid,
        "name": detector.name,
        "plugin": detector.plugin,
        "is_enabled": detector.is_enabled,
    }


@router.delete("/{detector_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_detector(
    site_id: int,
    detector_id: int,
    current_user = Depends(require_role(UserRole.ADMIN)),
    session: AsyncSession = Depends(get_session),
):
    """Delete detector."""
    await verify_site_access(site_id, current_user, session)
    
    result = await session.execute(
        select(Detector).where(Detector.id == detector_id, Detector.site_id == site_id)
    )
    detector = result.scalar_one_or_none()
    
    if not detector:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Detector not found",
        )
    
    # Check if any cameras use this detector
    from sqlalchemy import select, func
    result = await session.execute(
        select(func.count(Camera.id)).where(Camera.detector_id == detector_id)
    )
    if result.scalar() > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete detector: cameras are using it",
        )
    
    # Stop detection engine
    try:
        from superguard_core.services.detection_engine import get_detection_engine
        from superguard_core.core.plugins import PluginManager
        from superguard_core.core.events import EventBus
        pm = PluginManager()
        await pm.discover_plugins()
        bus = await get_event_bus()
        de = await get_detection_engine(site_id, pm, bus)
        # The pipeline will be stopped when detector is removed
    except Exception:
        pass
    
    await session.delete(detector)
    await session.commit()
    
    await publish_system_event("detector_deleted", {"site_id": site_id, "detector_id": detector_id})


@router.post("/{detector_id}/test")
async def test_detector(
    site_id: int,
    detector_id: int,
    test_data: dict,
    current_user = Depends(require_role(UserRole.ADMIN, UserRole.OPERATOR)),
    session: AsyncSession = Depends(get_session),
):
    """Test detector on a frame (base64 encoded image)."""
    await verify_site_access(site_id, current_user, session)
    
    result = await session.execute(
        select(Detector).where(Detector.id == detector_id, Detector.site_id == site_id)
    )
    detector = result.scalar_one_or_none()
    
    if not detector:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Detector not found",
        )
    
    # Get frame from test_data or camera
    frame_data = test_data.get("frame_base64")
    camera_id = test_data.get("camera_id")
    
    if not frame_data and not camera_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either frame_base64 or camera_id required",
        )
    
    try:
        from superguard_core.services.detection_engine import get_detection_engine
        from superguard_core.core.plugins import PluginManager
        from superguard_core.core.events import EventBus
        import base64
        import numpy as np
        import cv2
        
        pm = PluginManager()
        await pm.discover_plugins()
        bus = await get_event_bus()
        de = await get_detection_engine(site_id, pm, bus)
        de.set_session_factory(get_session)
        
        if frame_data:
            # Decode base64 image
            img_bytes = base64.b64decode(frame_data)
            nparr = np.frombuffer(img_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            from superguard_core.core.plugins import CameraFrame
            frame = CameraFrame(
                image=img,
                timestamp=time.time(),
                camera_id=camera_id or 0,
            )
        elif camera_id:
            # Get snapshot from camera
            from superguard_core.services.camera_manager import get_camera_manager
            cm = await get_camera_manager(site_id, pm, bus)
            frame = await cm.get_snapshot(camera_id)
            if not frame:
                raise Exception("Could not get frame from camera")
        else:
            raise Exception("No frame source")
        
        # Process frame
        processed = await de.test_detector(detector_id, frame)
        
        # Encode annotated frame back to base64
        _, buffer = cv2.imencode('.jpg', processed.annotated)
        annotated_base64 = base64.b64encode(buffer).decode('utf-8')
        
        return {
            "success": True,
            "detections": [
                {
                    "class_id": d.class_id,
                    "class_name": d.class_name,
                    "confidence": d.confidence,
                    "bbox": d.bbox,
                }
                for d in processed.detections
            ],
            "annotated_base64": annotated_base64,
            "processing_time": processed.processing_time,
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


@router.get("/available/plugins")
async def list_available_detector_plugins(
    current_user = Depends(get_current_user),
):
    """List available detector plugins."""
    from superguard_core.core.plugins import PluginManager
    pm = PluginManager()
    await pm.discover_plugins()
    
    plugins = pm.get_available_plugins()
    detectors = [p for p in plugins if p.plugin_type.value == "detector"]
    
    return [
        {
            "name": p.name,
            "version": p.version,
            "description": p.description,
            "author": p.author,
            "config_schema": p.config_class.model_json_schema() if p.config_class != PluginConfig else {},
        }
        for p in detectors
    ]


import time
import logging
logger = logging.getLogger(__name__)