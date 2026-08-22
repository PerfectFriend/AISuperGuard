"""
WebSocket endpoint for real-time alarm events, camera status, actuator state.
"""
import json
import asyncio
from typing import Dict, Set
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import uuid

router = APIRouter()


class ConnectionManager:
    """Manages WebSocket connections per site."""
    def __init__(self):
        self.connections: Dict[str, Set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, site_id: str):
        await websocket.accept()
        if site_id not in self.connections:
            self.connections[site_id] = set()
        self.connections[site_id].add(websocket)

    def disconnect(self, websocket: WebSocket, site_id: str):
        if site_id in self.connections:
            self.connections[site_id].discard(websocket)

    async def broadcast(self, site_id: str, message: dict):
        if site_id in self.connections:
            data = json.dumps(message, default=str)
            dead = []
            for ws in self.connections[site_id]:
                try:
                    await ws.send_text(data)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                self.connections[site_id].discard(ws)


manager = ConnectionManager()


@router.websocket("/ws/{site_id}")
async def websocket_endpoint(websocket: WebSocket, site_id: str):
    """
    Real-time events for a specific site.

    Event types (server → client):
    - alarm.triggered: { type, payload: AlarmResponse }
    - alarm.acknowledged: { type, payload: { alarmId, userId } }
    - alarm.resolved: { type, payload: { alarmId } }
    - camera.status: { type, payload: { cameraId, status, isOnline } }
    - actuator.status: { type, payload: { actuatorId, state, power } }
    - detection.stats: { type, payload: { cameraId, fps, detections } }
    - system.health: { type, payload: SystemHealth }
    """
    # Validate JWT token from query params before accepting connection
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4401, reason="Missing token")
        return
    
    from app.core.security import decode_token
    payload = decode_token(token)
    if not payload:
        await websocket.close(code=4401, reason="Invalid token")
        return
    
    await manager.connect(websocket, site_id)
    try:
        # Send initial welcome
        await websocket.send_text(json.dumps({
            "type": "connection.established",
            "payload": {"site_id": site_id}
        }))

        # Listen for client messages (ping/pong, subscriptions)
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            if msg.get("type") == "ping":
                await websocket.send_text(json.dumps({"type": "pong", "payload": {}}))

    except WebSocketDisconnect:
        manager.disconnect(websocket, site_id)
    except Exception:
        manager.disconnect(websocket, site_id)


# Helper to broadcast alarm events from services
async def broadcast_alarm(site_id: str, alarm_data: dict):
    await manager.broadcast(site_id, {"type": "alarm.triggered", "payload": alarm_data})


async def broadcast_camera_status(site_id: str, camera_id: str, is_online: bool):
    await manager.broadcast(site_id, {
        "type": "camera.status",
        "payload": {"cameraId": camera_id, "isOnline": is_online}
    })


async def broadcast_actuator_status(site_id: str, actuator_id: str, state: bool, power: float = None):
    await manager.broadcast(site_id, {
        "type": "actuator.status",
        "payload": {"actuatorId": actuator_id, "state": state, "power": power}
    })


# New: detection stats and alarm events from detection engine
async def broadcast_detection_stats(site_id: str, data: dict):
    await manager.broadcast(site_id, {"type": "detection.stats", "payload": data})


async def broadcast_alarm_resolved(site_id: str, data: dict):
    await manager.broadcast(site_id, {"type": "alarm.resolved", "payload": data})