"""
SuperGuard Core - Actuators API Routes
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from superguard_core.core.auth import get_current_user, verify_site_access, require_role
from superguard_core.core.database import get_session, Actuator, Camera, UserRole
from superguard_core.core.events import get_event_bus, publish_system_event
from superguard_core.services.actuator_engine import ActuatorEngine, get_actuator_engine

router = APIRouter()


@router.get("")
async def list_actuators(
    site_id: int,
    current_user = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """List actuators for site."""
    await verify_site_access(site_id, current_user, session)
    
    result = await session.execute(
        select(Actuator).where(Actuator.site_id == site_id).order_by(Actuator.created_at.desc())
    )
    actuators = result.scalars().all()
    
    return [
        {
            "id": a.id,
            "uuid": a.uuid,
            "name": a.name,
            "description": a.description,
            "plugin": a.plugin,
            "config": a.config,
            "camera_bindings": a.camera_bindings,
            "is_enabled": a.is_enabled,
            "last_state": a.last_state,
            "last_command_at": a.last_command_at.isoformat() if a.last_command_at else None,
            "created_at": a.created_at.isoformat(),
        }
        for a in actuators
    ]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_actuator(
    site_id: int,
    actuator_data: dict,
    current_user = Depends(require_role(UserRole.ADMIN, UserRole.OPERATOR)),
    session: AsyncSession = Depends(get_session),
):
    """Create new actuator."""
    await verify_site_access(site_id, current_user, session)
    
    # Validate plugin
    from superguard_core.core.plugins import PluginManager
    pm = PluginManager()
    await pm.discover_plugins()
    
    plugin_name = actuator_data.get("plugin")
    plugin_meta = None
    for meta in pm.get_available_plugins():
        if meta.plugin_type.value == "actuator" and meta.name == plugin_name:
            plugin_meta = meta
            break
    
    if not plugin_meta:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Actuator plugin not found: {plugin_name}",
        )
    
    # Validate camera bindings
    camera_bindings = actuator_data.get("camera_bindings", [])
    if camera_bindings:
        result = await session.execute(
            select(Camera.id).where(Camera.id.in_(camera_bindings), Camera.site_id == site_id)
        )
        valid_cameras = [row[0] for row in result.all()]
        if len(valid_cameras) != len(camera_bindings):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="One or more camera IDs are invalid",
            )
        camera_bindings = valid_cameras
    
    actuator = Actuator(
        site_id=site_id,
        name=actuator_data.get("name"),
        description=actuator_data.get("description"),
        plugin=plugin_name,
        config=actuator_data.get("config", {}),
        camera_bindings=camera_bindings,
        is_enabled=actuator_data.get("is_enabled", True),
    )
    session.add(actuator)
    await session.commit()
    await session.refresh(actuator)
    
    # Start actuator engine
    try:
        from superguard_core.core.plugins import PluginManager
        from superguard_core.core.events import EventBus
        bus = await get_event_bus()
        ae = await get_actuator_engine(site_id, pm, bus)
        ae.set_session_factory(get_session)
        await ae.add_actuator(actuator)
    except Exception as e:
        logger.warning(f"Failed to auto-start actuator: {e}")
    
    await publish_system_event("actuator_created", {"site_id": site_id, "actuator_id": actuator.id})
    
    return {
        "id": actuator.id,
        "uuid": actuator.uuid,
        "name": actuator.name,
        "plugin": actuator.plugin,
        "is_enabled": actuator.is_enabled,
    }


@router.get("/{actuator_id}")
async def get_actuator(
    site_id: int,
    actuator_id: int,
    current_user = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Get actuator details."""
    await verify_site_access(site_id, current_user, session)
    
    result = await session.execute(
        select(Actuator).where(Actuator.id == actuator_id, Actuator.site_id == site_id)
    )
    actuator = result.scalar_one_or_none()
    
    if not actuator:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Actuator not found",
        )
    
    # Get bound cameras
    from sqlalchemy import select
    result = await session.execute(
        select(Camera).where(Camera.id.in_(actuator.camera_bindings))
    )
    cameras = result.scalars().all()
    
    # Get engine stats
    stats = None
    try:
        from superguard_core.services.actuator_engine import get_actuator_engine
        from superguard_core.core.plugins import PluginManager
        from superguard_core.core.events import EventBus
        pm = PluginManager()
        await pm.discover_plugins()
        bus = await get_event_bus()
        ae = await get_actuator_engine(site_id, pm, bus)
        stats = ae.get_actuator_stats(actuator_id)
    except Exception:
        pass
    
    return {
        "id": actuator.id,
        "uuid": actuator.uuid,
        "name": actuator.name,
        "description": actuator.description,
        "plugin": actuator.plugin,
        "config": actuator.config,
        "camera_bindings": actuator.camera_bindings,
        "cameras": [
            {"id": c.id, "name": c.name}
            for c in cameras
        ],
        "is_enabled": actuator.is_enabled,
        "last_state": actuator.last_state,
        "last_command_at": actuator.last_command_at.isoformat() if actuator.last_command_at else None,
        "stats": stats,
        "created_at": actuator.created_at.isoformat(),
        "updated_at": actuator.updated_at.isoformat(),
    }


@router.patch("/{actuator_id}")
async def update_actuator(
    site_id: int,
    actuator_id: int,
    actuator_data: dict,
    current_user = Depends(require_role(UserRole.ADMIN, UserRole.OPERATOR)),
    session: AsyncSession = Depends(get_session),
):
    """Update actuator configuration."""
    await verify_site_access(site_id, current_user, session)
    
    result = await session.execute(
        select(Actuator).where(Actuator.id == actuator_id, Actuator.site_id == site_id)
    )
    actuator = result.scalar_one_or_none()
    
    if not actuator:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Actuator not found",
        )
    
    # Validate camera bindings if changing
    if "camera_bindings" in actuator_data:
        camera_bindings = actuator_data["camera_bindings"]
        if camera_bindings:
            from sqlalchemy import select
            result = await session.execute(
                select(Camera.id).where(Camera.id.in_(camera_bindings), Camera.site_id == site_id)
            )
            valid_cameras = [row[0] for row in result.all()]
            if len(valid_cameras) != len(camera_bindings):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="One or more camera IDs are invalid",
                )
            actuator.camera_bindings = valid_cameras
        else:
            actuator.camera_bindings = []
    
    # Update fields
    for field in ["name", "description", "config", "is_enabled"]:
        if field in actuator_data:
            setattr(actuator, field, actuator_data[field])
    
    if "plugin" in actuator_data:
        from superguard_core.core.plugins import PluginManager
        pm = PluginManager()
        await pm.discover_plugins()
        if actuator_data["plugin"] not in [m.name for m in pm.get_available_plugins() if m.plugin_type.value == "actuator"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Actuator plugin not found: {actuator_data['plugin']}",
            )
        actuator.plugin = actuator_data["plugin"]
    
    await session.commit()
    await session.refresh(actuator)
    
    # Update actuator engine
    try:
        from superguard_core.services.actuator_engine import get_actuator_engine
        from superguard_core.core.plugins import PluginManager
        from superguard_core.core.events import EventBus
        pm = PluginManager()
        await pm.discover_plugins()
        bus = await get_event_bus()
        ae = await get_actuator_engine(site_id, pm, bus)
        ae.set_session_factory(get_session)
        await ae.update_actuator(actuator)
    except Exception as e:
        logger.warning(f"Failed to update actuator engine: {e}")
    
    await publish_system_event("actuator_updated", {"site_id": site_id, "actuator_id": actuator.id})
    
    return {
        "id": actuator.id,
        "uuid": actuator.uuid,
        "name": actuator.name,
        "plugin": actuator.plugin,
        "is_enabled": actuator.is_enabled,
    }


@router.delete("/{actuator_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_actuator(
    site_id: int,
    actuator_id: int,
    current_user = Depends(require_role(UserRole.ADMIN)),
    session: AsyncSession = Depends(get_session),
):
    """Delete actuator."""
    await verify_site_access(site_id, current_user, session)
    
    result = await session.execute(
        select(Actuator).where(Actuator.id == actuator_id, Actuator.site_id == site_id)
    )
    actuator = result.scalar_one_or_none()
    
    if not actuator:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Actuator not found",
        )
    
    # Stop actuator engine
    try:
        from superguard_core.services.actuator_engine import get_actuator_engine
        from superguard_core.core.plugins import PluginManager
        from superguard_core.core.events import EventBus
        pm = PluginManager()
        await pm.discover_plugins()
        bus = await get_event_bus()
        ae = await get_actuator_engine(site_id, pm, bus)
        await ae.remove_actuator(actuator_id)
    except Exception:
        pass
    
    await session.delete(actuator)
    await session.commit()
    
    await publish_system_event("actuator_deleted", {"site_id": site_id, "actuator_id": actuator_id})


@router.post("/{actuator_id}/command")
async def execute_actuator_command(
    site_id: int,
    actuator_id: int,
    command_data: dict,
    current_user = Depends(require_role(UserRole.ADMIN, UserRole.OPERATOR)),
    session: AsyncSession = Depends(get_session),
):
    """Execute manual actuator command (on/off/toggle)."""
    await verify_site_access(site_id, current_user, session)
    
    result = await session.execute(
        select(Actuator).where(Actuator.id == actuator_id, Actuator.site_id == site_id)
    )
    actuator = result.scalar_one_or_none()
    
    if not actuator:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Actuator not found",
        )
    
    command = command_data.get("command")  # turn_on, turn_off, toggle
    if command not in ["turn_on", "turn_off", "toggle"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid command. Use: turn_on, turn_off, toggle",
        )
    
    try:
        from superguard_core.services.actuator_engine import get_actuator_engine
        from superguard_core.core.plugins import PluginManager
        from superguard_core.core.events import EventBus
        pm = PluginManager()
        await pm.discover_plugins()
        bus = await get_event_bus()
        ae = await get_actuator_engine(site_id, pm, bus)
        ae.set_session_factory(get_session)
        
        state = await ae.manual_command(actuator_id, command)
        
        return {
            "success": True,
            "command": command,
            "state": {
                "is_on": state.is_on,
                "last_changed": state.last_changed.isoformat(),
            }
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Command failed: {e}",
        )


@router.post("/{actuator_id}/test")
async def test_actuator(
    site_id: int,
    actuator_id: int,
    current_user = Depends(require_role(UserRole.ADMIN, UserRole.OPERATOR)),
    session: AsyncSession = Depends(get_session),
):
    """Test actuator connectivity."""
    await verify_site_access(site_id, current_user, session)
    
    result = await session.execute(
        select(Actuator).where(Actuator.id == actuator_id, Actuator.site_id == site_id)
    )
    actuator = result.scalar_one_or_none()
    
    if not actuator:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Actuator not found",
        )
    
    try:
        from superguard_core.services.actuator_engine import get_actuator_engine
        from superguard_core.core.plugins import PluginManager
        from superguard_core.core.events import EventBus
        pm = PluginManager()
        await pm.discover_plugins()
        bus = await get_event_bus()
        ae = await get_actuator_engine(site_id, pm, bus)
        
        success = await ae.test_actuator(actuator_id)
        
        return {"success": success}
        
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/{actuator_id}/sync")
async def sync_actuator_state(
    site_id: int,
    actuator_id: int,
    current_user = Depends(require_role(UserRole.ADMIN, UserRole.OPERATOR)),
    session: AsyncSession = Depends(get_session),
):
    """Sync actuator state from hardware."""
    await verify_site_access(site_id, current_user, session)
    
    try:
        from superguard_core.services.actuator_engine import get_actuator_engine
        from superguard_core.core.plugins import PluginManager
        from superguard_core.core.events import EventBus
        pm = PluginManager()
        await pm.discover_plugins()
        bus = await get_event_bus()
        ae = await get_actuator_engine(site_id, pm, bus)
        ae.set_session_factory(get_session)
        
        await ae.sync_states()
        
        return {"success": True}
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Sync failed: {e}",
        )


@router.get("/available/plugins")
async def list_available_actuator_plugins(
    current_user = Depends(get_current_user),
):
    """List available actuator plugins."""
    from superguard_core.core.plugins import PluginManager
    pm = PluginManager()
    await pm.discover_plugins()
    
    plugins = pm.get_available_plugins()
    actuators = [p for p in plugins if p.plugin_type.value == "actuator"]
    
    return [
        {
            "name": p.name,
            "version": p.version,
            "description": p.description,
            "author": p.author,
            "config_schema": p.config_class.model_json_schema() if p.config_class != PluginConfig else {},
        }
        for p in actuators
    ]


import logging
logger = logging.getLogger(__name__)