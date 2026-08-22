"""
Rules endpoints - CRUD for camera-detector-actuator automation rules
"""
import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models import Rule, Camera, Detector, Actuator, User
from app.api.v1.endpoints.auth import get_current_user
from app.schemas import RuleCreate, RuleUpdate, RuleResponse

router = APIRouter()


@router.get("/sites/{site_id}/rules", response_model=List[RuleResponse])
async def list_rules(
    site_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Rule).where(Rule.site_id == site_id).order_by(Rule.created_at)
    )
    return result.scalars().all()


@router.post("/sites/{site_id}/rules", response_model=RuleResponse, status_code=201)
async def create_rule(
    site_id: str,
    req: RuleCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Validate camera exists
    camera_result = await db.execute(
        select(Camera).where(Camera.id == req.camera_id, Camera.site_id == site_id)
    )
    if not camera_result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Camera not found in site")
    
    # Validate detector if provided
    if req.detector_id:
        detector_result = await db.execute(
            select(Detector).where(Detector.id == req.detector_id, Detector.site_id == site_id)
        )
        if not detector_result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Detector not found in site")
    
    # Validate actuator exists
    actuator_result = await db.execute(
        select(Actuator).where(Actuator.id == req.actuator_id, Actuator.site_id == site_id)
    )
    if not actuator_result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Actuator not found in site")
    
    rule = Rule(site_id=site_id, **req.model_dump())
    db.add(rule)
    await db.flush()
    return rule


@router.get("/sites/{site_id}/rules/{rule_id}", response_model=RuleResponse)
async def get_rule(
    site_id: str,
    rule_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Rule).where(Rule.id == rule_id, Rule.site_id == site_id)
    )
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    return rule


@router.patch("/sites/{site_id}/rules/{rule_id}", response_model=RuleResponse)
async def update_rule(
    site_id: str,
    rule_id: str,
    req: RuleUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Rule).where(Rule.id == rule_id, Rule.site_id == site_id)
    )
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    # Validate foreign keys if provided
    if req.camera_id:
        camera_result = await db.execute(
            select(Camera).where(Camera.id == req.camera_id, Camera.site_id == site_id)
        )
        if not camera_result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Camera not found in site")
    
    if req.detector_id:
        detector_result = await db.execute(
            select(Detector).where(Detector.id == req.detector_id, Detector.site_id == site_id)
        )
        if not detector_result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Detector not found in site")
    
    if req.actuator_id:
        actuator_result = await db.execute(
            select(Actuator).where(Actuator.id == req.actuator_id, Actuator.site_id == site_id)
        )
        if not actuator_result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Actuator not found in site")

    for k, v in req.model_dump(exclude_unset=True).items():
        setattr(rule, k, v)
    await db.flush()
    return rule


@router.delete("/sites/{site_id}/rules/{rule_id}", status_code=204)
async def delete_rule(
    site_id: str,
    rule_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Rule).where(Rule.id == rule_id, Rule.site_id == site_id)
    )
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    await db.delete(rule)
    await db.flush()