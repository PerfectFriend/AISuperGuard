"""
SuperGuard Core - Event Bus

Redis Streams based message bus for inter-service communication.
"""

import asyncio
import json
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4

import redis.asyncio as redis
from pydantic import BaseModel

from superguard_core.core.config import get_settings


class Event(BaseModel):
    """Event message."""
    id: str
    stream: str
    type: str
    payload: Dict[str, Any]
    timestamp: str
    source: str = ""
    correlation_id: Optional[str] = None


class EventBus:
    """Redis Streams based event bus."""
    
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
        self._consumers: Dict[str, asyncio.Task] = {}
        self._handlers: Dict[str, List[Callable]] = {}
        self._running = False
    
    @classmethod
    async def create(cls, redis_url: str) -> "EventBus":
        """Create event bus with connection."""
        client = redis.from_url(redis_url, decode_responses=True)
        await client.ping()
        return cls(client)
    
    async def close(self) -> None:
        """Close connections and stop consumers."""
        self._running = False
        for task in self._consumers.values():
            task.cancel()
        await asyncio.gather(*self._consumers.values(), return_exceptions=True)
        await self.redis.close()
    
    async def publish(self, stream: str, payload: Dict[str, Any], 
                     event_type: str = "", source: str = "",
                     correlation_id: Optional[str] = None) -> str:
        """Publish event to stream."""
        event = Event(
            id=str(uuid4()),
            stream=stream,
            type=event_type or "event",
            payload=payload,
            timestamp=datetime.now().isoformat(),
            source=source,
            correlation_id=correlation_id,
        )
        
        # Add to Redis Stream
        await self.redis.xadd(stream, event.model_dump(mode="json"))
        return event.id
    
    async def subscribe(self, stream: str, handler: Callable[[Event], Any],
                       group: str = "superguard", consumer: str = "") -> None:
        """Subscribe to stream with consumer group."""
        if not consumer:
            consumer = f"{group}-{uuid4().hex[:8]}"
        
        # Create consumer group if not exists
        try:
            await self.redis.xgroup_create(stream, group, id="0", mkstream=True)
        except redis.ResponseError:
            pass  # Group already exists
        
        # Register handler
        key = f"{stream}:{group}"
        if key not in self._handlers:
            self._handlers[key] = []
        self._handlers[key].append(handler)
        
        # Start consumer if not running
        if key not in self._consumers:
            self._running = True
            self._consumers[key] = asyncio.create_task(
                self._consume_stream(stream, group, consumer, key)
            )
    
    async def _consume_stream(self, stream: str, group: str, consumer: str, key: str):
        """Consume messages from stream."""
        while self._running:
            try:
                messages = await self.redis.xreadgroup(
                    group, consumer, {stream: ">"}, count=10, block=5000
                )
                
                for stream_name, stream_messages in messages:
                    for msg_id, msg_data in stream_messages:
                        try:
                            event = Event(**msg_data)
                            handlers = self._handlers.get(key, [])
                            for handler in handlers:
                                try:
                                    await handler(event)
                                except Exception as e:
                                    print(f"Handler error: {e}")
                            
                            # Acknowledge
                            await self.redis.xack(stream, group, msg_id)
                        except Exception as e:
                            print(f"Message processing error: {e}")
                            # Still ack to avoid stuck messages
                            await self.redis.xack(stream, group, msg_id)
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Consumer error: {e}")
                await asyncio.sleep(1)
    
    async def unsubscribe(self, stream: str, group: str = "superguard") -> None:
        """Unsubscribe from stream."""
        key = f"{stream}:{group}"
        if key in self._consumers:
            self._consumers[key].cancel()
            del self._consumers[key]
        if key in self._handlers:
            del self._handlers[key]
    
    async def get_stream_info(self, stream: str) -> Dict[str, Any]:
        """Get stream information."""
        try:
            info = await self.redis.xinfo_stream(stream)
            return info
        except redis.ResponseError:
            return {"length": 0, "first_entry": None, "last_entry": None}
    
    async def trim_stream(self, stream: str, max_len: int = 10000) -> int:
        """Trim stream to max length."""
        return await self.redis.xtrim(stream, maxlen=max_len, approximate=True)


# Global event bus instance
_event_bus: Optional[EventBus] = None


async def get_event_bus() -> EventBus:
    """Get global event bus instance."""
    global _event_bus
    if _event_bus is None:
        settings = get_settings()
        _event_bus = await EventBus.create(settings.redis_url)
    return _event_bus


async def close_event_bus() -> None:
    """Close global event bus."""
    global _event_bus
    if _event_bus:
        await _event_bus.close()
        _event_bus = None


# Convenience functions for common events
async def publish_camera_frame(camera_id: int, frame_data: Dict[str, Any]):
    """Publish camera frame event."""
    bus = await get_event_bus()
    await bus.publish("camera.frames", {
        "camera_id": camera_id,
        **frame_data,
    }, event_type="frame", source="camera_manager")


async def publish_detection(camera_id: int, detection_data: Dict[str, Any]):
    """Publish detection event."""
    bus = await get_event_bus()
    await bus.publish("camera.detections", {
        "camera_id": camera_id,
        **detection_data,
    }, event_type="detection", source="detection_engine")


async def publish_alarm(alarm_data: Dict[str, Any]):
    """Publish alarm event."""
    bus = await get_event_bus()
    await bus.publish("alarms.events", alarm_data, event_type="alarm", source="alarm_engine")


async def publish_actuator_command(actuator_id: int, command: str, params: Dict[str, Any] = None):
    """Publish actuator command."""
    bus = await get_event_bus()
    await bus.publish("actuators.commands", {
        "actuator_id": actuator_id,
        "command": command,
        "params": params or {},
    }, event_type="command", source="actuator_engine")


async def publish_actuator_state(actuator_id: int, state: Dict[str, Any]):
    """Publish actuator state change."""
    bus = await get_event_bus()
    await bus.publish("actuators.states", {
        "actuator_id": actuator_id,
        **state,
    }, event_type="state", source="actuator_engine")


async def publish_system_event(event_type: str, data: Dict[str, Any]):
    """Publish system event."""
    bus = await get_event_bus()
    await bus.publish("system.events", data, event_type=event_type, source="system")


# Stream names constants
class Streams:
    CAMERA_FRAMES = "camera.frames"
    CAMERA_DETECTIONS = "camera.detections"
    CAMERA_EVENTS = "camera.events"
    ALARMS_EVENTS = "alarms.events"
    ALARMS_COMMANDS = "alarms.commands"
    ACTUATORS_COMMANDS = "actuators.commands"
    ACTUATORS_STATES = "actuators.states"
    ACTUATORS_EVENTS = "actuators.events"
    NOTIFICATIONS = "notifications"
    PLUGINS_STATUS = "plugins.status"
    SYSTEM_EVENTS = "system.events"
    RECORDING_EVENTS = "recording.events"