"""
Alarms endpoints - list, detail, ack, silence, media, WebSocket
"""
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models import Alarm, AlarmMedia, AlarmState as AlarmStateModel, User
from app.api.v1.endpoints.auth import get_current_user
from app.schemas import AlarmResponse, AlarmAck, AlarmMediaResponse, AlarmState

router = APIRouter()


@router.get("/sites/{site_id}/alarms", response_model=List[AlarmResponse])
async def list_alarms(
    site_id: str,
    state: Optional[AlarmState] = None,
    camera_id: Optional[uuid.UUID] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = select(Alarm).where(Alarm.site_id == site_id)
    if state:
        query = query.where(Alarm.state == state.value)
    if camera_id:
        query = query.where(Alarm.camera_id == camera_id)
    query = query.order_by(Alarm.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/sites/{site_id}/alarms/{alarm_id}", response_model=AlarmResponse)
async def get_alarm(
    site_id: str,
    alarm_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Alarm).where(Alarm.id == alarm_id, Alarm.site_id == site_id)
    )
    alarm = result.scalar_one_or_none()
    if not alarm:
        raise HTTPException(status_code=404, detail="Alarm not found")
    return alarm


@router.post("/sites/{site_id}/alarms/{alarm_id}/ack", response_model=AlarmResponse)
async def acknowledge_alarm(
    site_id: str,
    alarm_id: str,
    req: AlarmAck,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Alarm).where(Alarm.id == alarm_id, Alarm.site_id == site_id)
    )
    alarm = result.scalar_one_or_none()
    if not alarm:
        raise HTTPException(status_code=404, detail="Alarm not found")
    if alarm.state != AlarmStateModel.triggered:
        raise HTTPException(status_code=400, detail=f"Alarm is {alarm.state.value}, cannot ack")

    alarm.state = AlarmStateModel.acknowledged
    alarm.acknowledged_by = user.id
    alarm.acknowledged_at = datetime.now(timezone.utc)
    if req.note:
        alarm.alarm_metadata = {**(alarm.alarm_metadata or {}), "ack_note": req.note}
    await db.flush()
    return alarm


@router.post("/sites/{site_id}/alarms/{alarm_id}/silence", response_model=AlarmResponse)
async def silence_alarm(
    site_id: str,
    alarm_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Alarm).where(Alarm.id == alarm_id, Alarm.site_id == site_id)
    )
    alarm = result.scalar_one_or_none()
    if not alarm:
        raise HTTPException(status_code=404, detail="Alarm not found")

    alarm.state = AlarmStateModel.silenced
    alarm.acknowledged_by = user.id
    alarm.acknowledged_at = datetime.now(timezone.utc)
    await db.flush()
    return alarm


@router.get("/sites/{site_id}/alarms/{alarm_id}/media", response_model=List[AlarmMediaResponse])
async def list_alarm_media(
    site_id: str,
    alarm_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(AlarmMedia).where(AlarmMedia.alarm_id == alarm_id).order_by(AlarmMedia.created_at)
    )
    return result.scalars().all()