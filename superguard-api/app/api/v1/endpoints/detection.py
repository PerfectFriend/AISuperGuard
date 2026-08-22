"""
Detection control endpoints.
"""
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.services.detection_engine import DetectionEngine

router = APIRouter()


@router.post("/trigger/{camera_id}")
async def manual_trigger(
    camera_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Manually trigger an alarm for a camera.
    """
    # Get the detection engine from the app state
    from app.main import app
    detection_engine: DetectionEngine = app.state.detection_engine
    
    # Run the trigger in the background to avoid blocking
    background_tasks.add_task(detection_engine.manual_trigger, camera_id)
    
    return {"status": "trigger initiated", "camera_id": camera_id}


@router.post("/cancel/{camera_id}")
async def manual_cancel(
    camera_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Manually cancel an alarm for a camera.
    """
    from app.main import app
    detection_engine: DetectionEngine = app.state.detection_engine
    
    background_tasks.add_task(detection_engine.manual_cancel, camera_id)
    
    return {"status": "cancel initiated", "camera_id": camera_id}


@router.get("/state/{camera_id}")
async def get_camera_state(
    camera_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Get current detection state for a camera.
    """
    from app.main import app
    detection_engine: DetectionEngine = app.state.detection_engine
    
    state = detection_engine.get_camera_state(camera_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    
    return state