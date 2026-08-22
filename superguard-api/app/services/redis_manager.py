"""
Redis Pub/Sub manager for cross-worker WebSocket broadcasting.
Replaces in-memory ConnectionManager when running multiple workers.
"""
import json
import asyncio
from typing import Dict, Set, Optional
from contextlib import asynccontextmanager

import redis.asyncio as redis
from fastapi import WebSocket

from app.core.config import settings


class RedisConnectionManager:
    """
    Manages WebSocket connections across multiple workers using Redis pub/sub.
    
    Each worker maintains its local connections, but broadcasts go through Redis
    so all workers receive messages for their connections.
    """
    
    def __init__(self):
        self.local_connections: Dict[str, Set[WebSocket]] = {}
        self._redis: Optional[redis.Redis] = None
        self._pubsub: Optional[redis.client.PubSub] = None
        self._listener_task: Optional[asyncio.Task] = None
        self._running = False
    
    async def initialize(self):
        """Initialize Redis connection and start listener."""
        if self._running:
            return
        
        self._redis = redis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True
        )
        
        self._pubsub = self._redis.pubsub()
        await self._pubsub.subscribe(settings.redis_pubsub_channel)
        
        self._running = True
        self._listener_task = asyncio.create_task(self._listen())
        
        print(f"[RedisConnectionManager] Connected to Redis, subscribed to {settings.redis_pubsub_channel}")
    
    async def shutdown(self):
        """Shutdown Redis connection and stop listener."""
        self._running = False
        
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
        
        if self._pubsub:
            await self._pubsub.unsubscribe(settings.redis_pubsub_channel)
            await self._pubsub.close()
        
        if self._redis:
            await self._redis.close()
        
        print("[RedisConnectionManager] Shutdown complete")
    
    async def _listen(self):
        """Listen for messages on Redis pub/sub channel."""
        try:
            async for message in self._pubsub.listen():
                if message["type"] == "message":
                    await self._handle_message(message["data"])
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"[RedisConnectionManager] Listener error: {e}")
    
    async def _handle_message(self, data: str):
        """Handle incoming message from Redis."""
        try:
            msg = json.loads(data)
            site_id = msg.get("site_id")
            payload = msg.get("payload")
            
            if site_id and site_id in self.local_connections:
                dead = []
                for ws in self.local_connections[site_id]:
                    try:
                        await ws.send_text(json.dumps(payload))
                    except Exception:
                        dead.append(ws)
                
                for ws in dead:
                    self.local_connections[site_id].discard(ws)
                    
        except Exception as e:
            print(f"[RedisConnectionManager] Error handling message: {e}")
    
    async def connect(self, websocket: WebSocket, site_id: str):
        """Accept connection and add to local pool."""
        await websocket.accept()
        if site_id not in self.local_connections:
            self.local_connections[site_id] = set()
        self.local_connections[site_id].add(websocket)
    
    def disconnect(self, websocket: WebSocket, site_id: str):
        """Remove connection from local pool."""
        if site_id in self.local_connections:
            self.local_connections[site_id].discard(websocket)
            if not self.local_connections[site_id]:
                del self.local_connections[site_id]
    
    async def broadcast(self, site_id: str, message: dict):
        """Broadcast message to all workers via Redis pub/sub."""
        if not self._redis:
            await self.initialize()
        
        payload = {
            "site_id": site_id,
            "payload": message
        }
        
        await self._redis.publish(
            settings.redis_pubsub_channel,
            json.dumps(payload)
        )
    
    async def broadcast_local(self, site_id: str, message: dict):
        """Broadcast to local connections only (for messages originating from this worker)."""
        if site_id in self.local_connections:
            data = json.dumps(message, default=str)
            dead = []
            for ws in self.local_connections[site_id]:
                try:
                    await ws.send_text(data)
                except Exception:
                    dead.append(ws)
            
            for ws in dead:
                self.local_connections[site_id].discard(ws)


# Global instance
_redis_manager: Optional[RedisConnectionManager] = None


async def get_redis_manager() -> RedisConnectionManager:
    """Get or create the Redis connection manager."""
    global _redis_manager
    if _redis_manager is None:
        _redis_manager = RedisConnectionManager()
        await _redis_manager.initialize()
    return _redis_manager


@asynccontextmanager
async def redis_manager_lifespan():
    """Lifespan context manager for FastAPI startup/shutdown."""
    manager = RedisConnectionManager()
    await manager.initialize()
    try:
        yield manager
    finally:
        await manager.shutdown()