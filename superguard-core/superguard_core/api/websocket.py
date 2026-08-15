"""
SuperGuard Core - WebSocket API

Real-time updates for alarms, camera status, actuator states.
"""

import asyncio
import json
import logging
from typing import Dict, List, Set
from uuid import uuid4

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from superguard_core.core.auth import get_current_user, verify_site_access
from superguard_core.core.database import get_session, Site, Alarm, AlarmStatus
from superguard_core.core.events import EventBus, get_event_bus, Streams

router = APIRouter()
logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections per site."""
    
    def __init__(self):
        self.site_connections: Dict[int, Set[WebSocket]] = {}
        self.connection_info: Dict[WebSocket, Dict] = {}
    
    async def connect(self, websocket: WebSocket, site_id: int, user_id: int):
        """Accept and register connection."""
        await websocket.accept()
        
        if site_id not in self.site_connections:
            self.site_connections[site_id] = set()
        
        self.site_connections[site_id].add(websocket)
        self.connection_info[websocket] = {
            "site_id": site_id,
            "user_id": user_id,
            "connected_at": asyncio.get_event_loop().time(),
        }
        
        logger.info(f"WebSocket connected: site={site_id}, user={user_id}")
    
    def disconnect(self, websocket: WebSocket):
        """Remove connection."""
        info = self.connection_info.get(websocket)
        if info:
            site_id = info["site_id"]
            if site_id in self.site_connections:
                self.site_connections[site_id].discard(websocket)
                if not self.site_connections[site_id]:
                    del self.site_connections[site_id]
            del self.connection_info[websocket]
            logger.info(f"WebSocket disconnected: site={site_id}, user={info['user_id']}")
    
    async def send_to_site(self, site_id: int, message: dict):
        """Broadcast message to all connections for a site."""
        if site_id not in self.site_connections:
            return
        
        dead_connections = []
        for ws in self.site_connections[site_id]:
            try:
                await ws.send_json(message)
            except Exception:
                dead_connections.append(ws)
        
        # Clean up dead connections
        for ws in dead_connections:
            self.disconnect(ws)
    
    async def send_personal(self, websocket: WebSocket, message: dict):
        """Send message to specific connection."""
        try:
            await websocket.send_json(message)
        except Exception:
            self.disconnect(websocket)


manager = ConnectionManager()


@router.websocket("/sites/{site_id}/alarms")
async def alarms_websocket(
    websocket: WebSocket,
    site_id: int,
    token: str = Query(...),
):
    """WebSocket for real-time alarm events."""
    
    # Verify token and site access
    try:
        # Create a temporary session for auth
        from superguard_core.core.auth import decode_token, get_session
        from superguard_core.core.database import get_session_factory
        
        payload = decode_token(token)
        user_id = int(payload.get("sub", 0))
        
        factory = get_session_factory()
        async with factory() as session:
            from superguard_core.core.auth import get_current_user
            from superguard_core.core.database import User
            
            result = await session.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
            
            if not user or not user.is_active:
                await websocket.close(code=4001, reason="Invalid user")
                return
            
            # Verify site access
            site_result = await session.execute(select(Site).where(Site.id == site_id))
            site = site_result.scalar_one_or_none()
            
            if not site:
                await websocket.close(code=4004, reason="Site not found")
                return
            
            # Check user has access to site
            from superguard_core.core.auth import get_user_sites
            user_sites = await get_user_sites(user, session)
            if site_id not in user_sites:
                await websocket.close(code=4003, reason="Access denied")
                return
        
        # Connect
        await manager.connect(websocket, site_id, user_id)
        
        # Send initial active alarms
        async with factory() as session:
            result = await session.execute(
                select(Alarm)
                .where(
                    Alarm.site_id == site_id,
                    Alarm.status.in_([AlarmStatus.ACTIVE, AlarmStatus.ACKNOWLEDGED])
                )
                .order_by(Alarm.started_at.desc())
            )
            active_alarms = result.scalars().all()
            
            await websocket.send_json({
                "type": "initial_state",
                "data": {
                    "active_alarms": [
                        {
                            "id": a.id,
                            "uuid": a.uuid,
                            "camera_id": a.camera_id,
                            "status": a.status.value,
                            "started_at": a.started_at.isoformat(),
                            "trigger_data": a.trigger_data,
                        }
                        for a in active_alarms
                    ]
                }
            })
        
        # Subscribe to alarm events
        bus = await get_event_bus()
        consumer_group = f"ws-alarms-{site_id}-{uuid4().hex[:8]}"
        
        async def alarm_handler(event):
            """Handle alarm events from event bus."""
            await websocket.send_json({
                "type": "alarm_event",
                "data": event.payload,
            })
        
        await bus.subscribe(Streams.ALARMS_EVENTS, alarm_handler, group=consumer_group)
        
        try:
            # Keep connection alive, handle incoming messages
            while True:
                data = await websocket.receive_json()
                
                # Handle client messages (ping, ack requests, etc.)
                msg_type = data.get("type")
                
                if msg_type == "ping":
                    await websocket.send_json({"type": "pong"})
                
                elif msg_type == "acknowledge":
                    alarm_id = data.get("alarm_id")
                    if alarm_id:
                        # This would call the alarm engine
                        # For now, just acknowledge receipt
                        await websocket.send_json({
                            "type": "acknowledged",
                            "alarm_id": alarm_id,
                        })
                
        except WebSocketDisconnect:
            pass
        finally:
            await bus.unsubscribe(Streams.ALARMS_EVENTS, group=consumer_group)
            manager.disconnect(websocket)
            
    except Exception as e:
        logger.error(f"WebSocket auth error: {e}")
        await websocket.close(code=4000, reason="Authentication failed")


@router.websocket("/sites/{site_id}/cameras")
async def cameras_websocket(
    websocket: WebSocket,
    site_id: int,
    token: str = Query(...),
):
    """WebSocket for real-time camera status and frames."""
    
    try:
        from superguard_core.core.auth import decode_token
        from superguard_core.core.database import get_session_factory, Site
        
        payload = decode_token(token)
        user_id = int(payload.get("sub", 0))
        
        factory = get_session_factory()
        async with factory() as session:
            result = await session.execute(select(Site).where(Site.id == site_id))
            site = result.scalar_one_or_none()
            
            if not site:
                await websocket.close(code=4004, reason="Site not found")
                return
            
            from superguard_core.core.database import User
            result = await session.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
            
            if not user or not user.is_active:
                await websocket.close(code=4001, reason="Invalid user")
                return
            
            from superguard_core.core.auth import get_user_sites
            user_sites = await get_user_sites(user, session)
            if site_id not in user_sites:
                await websocket.close(code=4003, reason="Access denied")
                return
        
        await manager.connect(websocket, site_id, user_id)
        
        # Subscribe to camera events
        bus = await get_event_bus()
        consumer_group = f"ws-cameras-{site_id}-{uuid4().hex[:8]}"
        
        async def camera_handler(event):
            await websocket.send_json({
                "type": "camera_event",
                "data": event.payload,
            })
        
        await bus.subscribe(Streams.CAMERA_EVENTS, camera_handler, group=consumer_group)
        
        try:
            while True:
                data = await websocket.receive_json()
                
                if data.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
                    
        except WebSocketDisconnect:
            pass
        finally:
            await bus.unsubscribe(Streams.CAMERA_EVENTS, group=consumer_group)
            manager.disconnect(websocket)
            
    except Exception as e:
        logger.error(f"Camera WebSocket error: {e}")
        await websocket.close(code=4000, reason="Error")


@router.websocket("/sites/{site_id}/actuators")
async def actuators_websocket(
    websocket: WebSocket,
    site_id: int,
    token: str = Query(...),
):
    """WebSocket for real-time actuator state changes."""
    
    try:
        from superguard_core.core.auth import decode_token
        from superguard_core.core.database import get_session_factory, Site, User
        from superguard_core.core.auth import get_user_sites
        
        payload = decode_token(token)
        user_id = int(payload.get("sub", 0))
        
        factory = get_session_factory()
        async with factory() as session:
            result = await session.execute(select(Site).where(Site.id == site_id))
            site = result.scalar_one_or_none()
            
            if not site:
                await websocket.close(code=4004, reason="Site not found")
                return
            
            result = await session.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
            
            if not user or not user.is_active:
                await websocket.close(code=4001, reason="Invalid user")
                return
            
            user_sites = await get_user_sites(user, session)
            if site_id not in user_sites:
                await websocket.close(code=4003, reason="Access denied")
                return
        
        await manager.connect(websocket, site_id, user_id)
        
        bus = await get_event_bus()
        consumer_group = f"ws-actuators-{site_id}-{uuid4().hex[:8]}"
        
        async def actuator_handler(event):
            await websocket.send_json({
                "type": "actuator_event",
                "data": event.payload,
            })
        
        await bus.subscribe(Streams.ACTUATORS_STATES, actuator_handler, group=consumer_group)
        await bus.subscribe(Streams.ACTUATORS_EVENTS, actuator_handler, group=consumer_group)
        
        try:
            while True:
                data = await websocket.receive_json()
                
                if data.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
                    
        except WebSocketDisconnect:
            pass
        finally:
            await bus.unsubscribe(Streams.ACTUATORS_STATES, group=consumer_group)
            await bus.unsubscribe(Streams.ACTUATORS_EVENTS, group=consumer_group)
            manager.disconnect(websocket)
            
    except Exception as e:
        logger.error(f"Actuator WebSocket error: {e}")
        await websocket.close(code=4000, reason="Error")


@router.websocket("/sites/{site_id}/all")
async def all_events_websocket(
    websocket: WebSocket,
    site_id: int,
    token: str = Query(...),
):
    """Combined WebSocket for all real-time events (alarms, cameras, actuators)."""
    
    try:
        from superguard_core.core.auth import decode_token
        from superguard_core.core.database import get_session_factory, Site, User
        from superguard_core.core.auth import get_user_sites
        
        payload = decode_token(token)
        user_id = int(payload.get("sub", 0))
        
        factory = get_session_factory()
        async with factory() as session:
            result = await session.execute(select(Site).where(Site.id == site_id))
            site = result.scalar_one_or_none()
            
            if not site:
                await websocket.close(code=4004, reason="Site not found")
                return
            
            result = await session.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
            
            if not user or not user.is_active:
                await websocket.close(code=4001, reason="Invalid user")
                return
            
            user_sites = await get_user_sites(user, session)
            if site_id not in user_sites:
                await websocket.close(code=4003, reason="Access denied")
                return
        
        await manager.connect(websocket, site_id, user_id)
        
        bus = await get_event_bus()
        consumer_group = f"ws-all-{site_id}-{uuid4().hex[:8]}"
        
        streams_to_subscribe = [
            Streams.ALARMS_EVENTS,
            Streams.CAMERA_EVENTS,
            Streams.ACTUATORS_STATES,
            Streams.ACTUATORS_EVENTS,
            Streams.SYSTEM_EVENTS,
        ]
        
        async def event_handler(event):
            await websocket.send_json({
                "stream": event.stream,
                "type": event.type,
                "data": event.payload,
                "timestamp": event.timestamp,
            })
        
        for stream in streams_to_subscribe:
            await bus.subscribe(stream, event_handler, group=consumer_group)
        
        try:
            # Send initial state
            async with factory() as session:
                # Active alarms
                result = await session.execute(
                    select(Alarm)
                    .where(
                        Alarm.site_id == site_id,
                        Alarm.status.in_([AlarmStatus.ACTIVE, AlarmStatus.ACKNOWLEDGED])
                    )
                )
                active_alarms = result.scalars().all()
                
                await websocket.send_json({
                    "type": "initial_state",
                    "data": {
                        "active_alarms": [
                            {
                                "id": a.id,
                                "camera_id": a.camera_id,
                                "status": a.status.value,
                                "started_at": a.started_at.isoformat(),
                            }
                            for a in active_alarms
                        ]
                    }
                })
            
            while True:
                data = await websocket.receive_json()
                
                if data.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
                    
        except WebSocketDisconnect:
            pass
        finally:
            for stream in streams_to_subscribe:
                await bus.unsubscribe(stream, group=consumer_group)
            manager.disconnect(websocket)
            
    except Exception as e:
        logger.error(f"All-events WebSocket error: {e}")
        await websocket.close(code=4000, reason="Error")