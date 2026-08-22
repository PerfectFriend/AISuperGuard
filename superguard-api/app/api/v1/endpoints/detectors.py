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
    """
    Test a specific detector on a camera frame.
    
    Fetches a frame from the camera, runs the detector's YOLO model on it,
    and returns all detections with confidence, bounding boxes, and timing info.
    """
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
    
    # Create YOLO detector with this detector's config
    from ultralytics import YOLO
    import cv2
    import time as time_module
    
    # Fetch frame from camera
    cap = cv2.VideoCapture(camera.stream_url)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000)
    cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, 10000)
    
    ret, frame = cap.read()
    cap.release()
    
    if not ret or frame is None:
        return {
            "status": "warning",
            "message": "Failed to fetch frame from camera",
            "detector": detector.name,
            "camera": camera.name
        }
    
    # Downscale for YOLO if needed
    h, w = frame.shape[:2]
    if w > 1280:
        scale = 1280 / w
        frame = cv2.resize(frame, (1280, int(h * scale)))
    
    # Load YOLO model with detector's config
    model_path = detector.model_path or 'yolo11n.pt'
    model = YOLO(model_path)
    
    # Run detection with timing
    start_time = time_module.time()
    results = model(frame, conf=detector.confidence_threshold or 0.25, imgsz=640, verbose=False)
    inference_time_ms = round((time_module.time() - start_time) * 1000, 2)
    
    # Parse detections
    detections = []
    for r in results:
        boxes = r.boxes
        for box in boxes:
            x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
            conf = box.conf[0].cpu().numpy()
            cls = int(box.cls[0].cpu().numpy())
            class_name = model.names[cls] if cls < len(model.names) else f"class_{cls}"
            
            detections.append({
                "class": class_name,
                "confidence": float(conf),
                "box": [float(x1), float(y1), float(x2), float(y2)],
                "class_id": cls
            })
    
    # Apply class filter if detector has classes specified
    if detector.classes:
        detections = [d for d in detections if d["class_id"] in detector.classes]
    
    return {
        "status": "ok",
        "message": f"Detector '{detector.name}' tested on camera '{camera.name}'",
        "detector": {
            "id": detector.id,
            "name": detector.name,
            "model": detector.model_path or 'yolo11n.pt',
            "confidence_threshold": detector.confidence_threshold,
            "classes": detector.classes
        },
        "camera": {
            "id": camera.id,
            "name": camera.name
        },
        "detections": detections,
        "frame_shape": [frame.shape[1], frame.shape[0]],  # width, height
        "inference_time_ms": round(inference_time_ms, 2),
        "detection_count": len(detections)
    }

@router.post("/detectors/{detector_id}/test/{camera_id}")
async def test_detector_on_camera(
    detector_id: str,
    camera_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Test a detector on a specific camera (alternative endpoint format).
    
    Same as /sites/{site_id}/detectors/{detector_id}/test but with camera_id in path.
    """
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
    
    # Create YOLO detector with this detector's config
    from ultralytics import YOLO
    import cv2
    import time as time_module
    
    # Fetch frame from camera
    cap = cv2.VideoCapture(camera.stream_url)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000)
    cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, 10000)
    
    ret, frame = cap.read()
    cap.release()
    
    if not ret or frame is None:
        return {
            "status": "warning",
            "message": "Failed to fetch frame from camera",
            "detector": detector.name,
            "camera": camera.name
        }
    
    # Downscale for YOLO if needed
    h, w = frame.shape[:2]
    if w > 1280:
        scale = 1280 / w
        frame = cv2.resize(frame, (1280, int(h * scale)))
    
    # Load YOLO model with detector's config
    model_path = detector.model_path or 'yolo11n.pt'
    model = YOLO(model_path)
    
    # Run detection with timing
    start_time = time_module.time()
    results = model(frame, conf=detector.confidence_threshold or 0.25, imgsz=640, verbose=False)
    inference_time_ms = round((time_module.time() - start_time) * 1000, 2)
    
    # Parse detections
    detections = []
    for r in results:
        boxes = r.boxes
        if boxes is not None:
            for box in boxes:
                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                conf = box.conf[0].cpu().numpy()
                cls = int(box.cls[0].cpu().numpy())
                class_name = model.names[cls] if cls < len(model.names) else f"class_{cls}"
                
                detections.append({
                    "class": class_name,
                    "confidence": float(conf),
                    "box": [float(x1), float(y1), float(x2), float(y2)],
                    "class_id": cls
                })
    
    # Apply class filter if detector has classes specified
    if detector.classes:
        detections = [d for d in detections if d["class_id"] in detector.classes]
    
    return {
        "status": "ok",
        "message": f"Detector '{detector.name}' tested on camera '{camera.name}'",
        "detector": {
            "id": detector.id,
            "name": detector.name,
            "model": detector.model_path or 'yolo11n.pt',
            "confidence_threshold": detector.confidence_threshold,
            "classes": detector.classes
        },
        "camera": {
            "id": camera.id,
            "name": camera.name
        },
        "detections": detections,
        "frame_shape": [frame.shape[1], frame.shape[0]],  # width, height
        "inference_time_ms": round(inference_time_ms, 2),
        "detection_count": len(detections)
    }