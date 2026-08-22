"""
Detectors endpoints - CRUD, test on frame
"""
import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models import Detector, User, Camera
from app.api.v1.endpoints.auth import get_current_user
from app.schemas import DetectorCreate, DetectorUpdate, DetectorResponse

router = APIRouter()


@router.get("/sites/{site_id}/detectors", response_model=List[DetectorResponse])
async def list_detectors(
    site_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Detector).where(Detector.site_id == site_id).order_by(Detector.created_at)
    )
    return result.scalars().all()


@router.post("/sites/{site_id}/detectors", response_model=DetectorResponse, status_code=201)
async def create_detector(
    site_id: str,
    req: DetectorCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    det = Detector(site_id=site_id, **req.model_dump())
    db.add(det)
    await db.flush()
    return det


@router.get("/sites/{site_id}/detectors/{detector_id}", response_model=DetectorResponse)
async def get_detector(
    site_id: str,
    detector_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Detector).where(Detector.id == detector_id, Detector.site_id == site_id)
    )
    det = result.scalar_one_or_none()
    if not det:
        raise HTTPException(status_code=404, detail="Detector not found")
    return det


@router.patch("/sites/{site_id}/detectors/{detector_id}", response_model=DetectorResponse)
async def update_detector(
    site_id: str,
    detector_id: str,
    req: DetectorUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Detector).where(Detector.id == detector_id, Detector.site_id == site_id)
    )
    det = result.scalar_one_or_none()
    if not det:
        raise HTTPException(status_code=404, detail="Detector not found")

    for k, v in req.model_dump(exclude_unset=True).items():
        setattr(det, k, v)
    await db.flush()
    return det


@router.delete("/sites/{site_id}/detectors/{detector_id}", status_code=204)
async def delete_detector(
    site_id: str,
    detector_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Detector).where(Detector.id == detector_id, Detector.site_id == site_id)
    )
    det = result.scalar_one_or_none()
    if not det:
        raise HTTPException(status_code=404, detail="Detector not found")
    await db.delete(det)
    await db.flush()


@router.post("/sites/{site_id}/detectors/{detector_id}/test")
async def test_detector(
    site_id: str,
    detector_id: str,
    camera_id: str = Query(None, description="Camera ID to test on (optional, uses first enabled camera if not specified)"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Verify detector belongs to site
    result = await db.execute(
        select(Detector).where(Detector.id == detector_id, Detector.site_id == site_id)
    )
    detector = result.scalar_one_or_none()
    if not detector:
        raise HTTPException(status_code=404, detail="Detector not found")
    
    # Find camera to test with
    if camera_id:
        camera_result = await db.execute(
            select(Camera).where(Camera.id == camera_id, Camera.site_id == site_id)
        )
        camera = camera_result.scalar_one_or_none()
    else:
        camera_result = await db.execute(
            select(Camera).where(Camera.site_id == site_id, Camera.is_enabled == True).limit(1)
        )
        camera = camera_result.scalar_one_or_none()
    
    if not camera:
        return {
            "status": "warning",
            "message": "No enabled cameras in site to test detector",
            "detector": detector.name
        }
    
    # Use the detection engine to test
    from app.api.v1.endpoints.websocket import manager as ws_manager
    from app.services.detection_engine import DetectionEngine
    
    detection_engine = DetectionEngine(ws_manager=ws_manager)
    await detection_engine.initialize()
    
    # Test on camera stream
    test_result = await detection_engine.test_detector_on_camera(detector.id, camera.id)
    
    return {
        "status": "ok",
        "message": f"Detector '{detector.name}' tested on camera '{camera.name}'",
        "detections": test_result.get("detections", []),
        "frame_shape": test_result.get("frame_shape"),
        "inference_time_ms": test_result.get("inference_time_ms")
    }

@router.post("/detectors/{detector_id}/test/{camera_id}")
async def test_detector_on_camera(
    detector_id: str,
    camera_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Verify detector exists
    result = await db.execute(
        select(Detector).where(Detector.id == detector_id)
    )
    detector = result.scalar_one_or_none()
    if not detector:
        raise HTTPException(status_code=404, detail="Detector not found")
    
    # Verify camera exists
    result = await db.execute(
        select(Camera).where(Camera.id == camera_id)
    )
    camera = result.scalar_one_or_none()
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")
    
    # Use the detection engine to test
    from app.api.v1.endpoints.websocket import manager as ws_manager
    from app.services.detection_engine import DetectionEngine
    
    detection_engine = DetectionEngine(ws_manager=ws_manager)
    await detection_engine.initialize()
    
    # Test on camera stream
    test_result = await detection_engine.test_detector_on_camera(detector.id, camera.id)
    
    return {
        "status": "ok",
        "message": f"Detector '{detector.name}' tested on camera '{camera.name}'",
        "detections": test_result.get("detections", []),
        "frame_shape": test_result.get("frame_shape"),
        "inference_time_ms": test_result.get("inference_time_ms")
    }