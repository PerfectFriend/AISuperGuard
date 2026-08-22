"""
Actuators endpoints - CRUD, command, test, bindings
"""
import uuid
from typing import List
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models import Actuator, User
from app.api.v1.endpoints.auth import get_current_user
from app.schemas import ActuatorCreate, ActuatorUpdate, ActuatorResponse, ActuatorCommand
from app.core.encryption import get_encryption
from app.services.actuator_health import ActuatorConfig, ActuatorDiscovery

router = APIRouter()


@router.get("/sites/{site_id}/actuators", response_model=List[ActuatorResponse])
async def list_actuators(
    site_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Actuator).where(Actuator.site_id == site_id).order_by(Actuator.created_at)
    )
    actuators = result.scalars().all()
    
    # Decrypt sensitive fields for response
    encryption = get_encryption()
    for act in actuators:
        if act.config:
            act.config = encryption.decrypt_dict(act.config)
    
    return actuators


@router.post("/sites/{site_id}/actuators", response_model=ActuatorResponse, status_code=201)
async def create_actuator(
    site_id: str,
    req: ActuatorCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Encrypt sensitive fields in config
    encryption = get_encryption()
    req.config = encryption.encrypt_dict(req.config or {})
    
    act = Actuator(site_id=site_id, **req.model_dump())
    db.add(act)
    await db.flush()
    return act


@router.get("/sites/{site_id}/actuators/{actuator_id}", response_model=ActuatorResponse)
async def get_actuator(
    site_id: str,
    actuator_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Actuator).where(Actuator.id == actuator_id, Actuator.site_id == site_id)
    )
    act = result.scalar_one_or_none()
    if not act:
        raise HTTPException(status_code=404, detail="Actuator not found")
    
    # Decrypt sensitive fields for response
    encryption = get_encryption()
    if act.config:
        act.config = encryption.decrypt_dict(act.config)
    
    return act


@router.patch("/sites/{site_id}/actuators/{actuator_id}", response_model=ActuatorResponse)
async def update_actuator(
    site_id: str,
    actuator_id: str,
    req: ActuatorUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Actuator).where(Actuator.id == actuator_id, Actuator.site_id == site_id)
    )
    act = result.scalar_one_or_none()
    if not act:
        raise HTTPException(status_code=404, detail="Actuator not found")

    # Encrypt sensitive fields in config if provided
    encryption = get_encryption()
    update_data = req.model_dump(exclude_unset=True)
    if 'config' in update_data:
        update_data['config'] = encryption.encrypt_dict(update_data['config'] or {})
    
    for k, v in update_data.items():
        setattr(act, k, v)
    await db.flush()
    return act


@router.delete("/sites/{site_id}/actuators/{actuator_id}", status_code=204)
async def delete_actuator(
    site_id: str,
    actuator_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Actuator).where(Actuator.id == actuator_id, Actuator.site_id == site_id)
    )
    act = result.scalar_one_or_none()
    if not act:
        raise HTTPException(status_code=404, detail="Actuator not found")
    await db.delete(act)
    await db.flush()


@router.post("/sites/{site_id}/actuators/{actuator_id}/command")
async def command_actuator(
    site_id: str,
    actuator_id: str,
    req: ActuatorCommand,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Get actuator from DB
    result = await db.execute(
        select(Actuator).where(Actuator.id == actuator_id, Actuator.site_id == site_id)
    )
    actuator = result.scalar_one_or_none()
    if not actuator:
        raise HTTPException(status_code=404, detail="Actuator not found")
    
    # Decrypt config for use
    encryption = get_encryption()
    cfg = encryption.decrypt_dict(actuator.config or {})
    
    if actuator.type.value not in ('tuya', 'tinytuya'):
        raise HTTPException(status_code=400, detail=f"Actuator type {actuator.type.value} not supported for commands")
    
    config = ActuatorConfig(
        id=actuator.id,
        name=actuator.name,
        type=actuator.type.value,
        ip=cfg.get('ip', ''),
        device_id=cfg.get('device_id', ''),
        local_key=cfg.get('local_key', ''),
        mac=cfg.get('mac', ''),
        port=cfg.get('port', 6668),
        version=cfg.get('version', 3.4),
    )
    
    action = req.action
    turn_on = action == 'on' or (action == 'toggle' and not actuator.last_status)
    
    # Send real command to Tuya
    success = ActuatorDiscovery.set_tuya_state(config, turn_on)
    
    if success:
        # Update last_status in DB immediately
        actuator.last_status = turn_on
        actuator.last_seen = datetime.utcnow()
        await db.commit()
        
        return {
            "actuator_id": str(actuator_id),
            "action": action,
            "status": "ok",
            "message": f"Command '{action}' executed successfully",
            "new_state": turn_on
        }
    else:
        raise HTTPException(status_code=500, detail="Failed to send command to actuator")


@router.post("/sites/{site_id}/actuators/{actuator_id}/test")
async def test_actuator(
    site_id: str,
    actuator_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Test actuator connectivity with IP rediscovery via MAC if needed. Returns actual state."""
    # Verify actuator belongs to site
    result = await db.execute(
        select(Actuator).where(Actuator.id == actuator_id, Actuator.site_id == site_id)
    )
    actuator = result.scalar_one_or_none()
    if not actuator:
        raise HTTPException(status_code=404, detail="Actuator not found")
    
    # Use the health monitor for testing with rediscovery
    from app.services.actuator_health import ActuatorHealthMonitor
    from app.core.database import get_db as get_db_factory
    
    monitor = ActuatorHealthMonitor(get_db_factory)
    result = await monitor.test_actuator(actuator_id)
    
    # Also get actual on/off state if online
    actual_status = None
    if result.get('online') and actuator.type.value in ('tuya', 'tinytuya'):
        # Decrypt config for use
        encryption = get_encryption()
        cfg = encryption.decrypt_dict(actuator.config or {})
        
        config = ActuatorConfig(
            id=actuator.id,
            name=actuator.name,
            type=actuator.type.value,
            ip=cfg.get('ip', ''),
            device_id=cfg.get('device_id', ''),
            local_key=cfg.get('local_key', ''),
            mac=cfg.get('mac', ''),
            port=cfg.get('port', 6668),
            version=cfg.get('version', 3.4),
        )
        actual_status = ActuatorDiscovery.get_tuya_status(config)
        if actual_status is not None:
            actuator.last_status = actual_status
            actuator.last_seen = datetime.utcnow()
            await db.commit()
    
    return {
        "status": "ok" if result.get("online") else "offline",
        "message": f"Actuator {'online' if result.get('online') else 'offline'}",
        "details": result,
        "actual_state": actual_status
    }


@router.get("/sites/{site_id}/actuators/find-by-mac/{mac}")
async def find_by_mac(
    site_id: str,
    mac: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Find actuator IP by MAC address via ARP."""
    from app.services.actuator_health import ActuatorDiscovery
    ip = ActuatorDiscovery.discover_ip_by_mac(mac)
    return {"ip": ip}


@router.post("/sites/{site_id}/telegram/alert")
async def telegram_alert(
    site_id: str,
    data: dict,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Send custom Telegram alert (e.g., from frontend for actuator offline)."""
    from app.services.telegram_bot import get_telegram_bot
    bot = await get_telegram_bot()
    if bot:
        try:
            await bot.send_message(data.get('message', 'Alert'))
            return {"status": "sent"}
        except Exception as e:
            return {"status": "error", "message": str(e)}
    return {"status": "error", "message": "Telegram bot not available"}