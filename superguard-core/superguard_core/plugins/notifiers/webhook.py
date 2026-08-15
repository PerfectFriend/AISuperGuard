"""
SuperGuard Core - Webhook Notifier Plugin

Generic webhook notifier for integration with external systems.
"""

import asyncio
import logging
from typing import Optional, Dict, Any, List

import aiohttp

from superguard_core.core.plugins import NotifierPlugin, PluginConfig
from superguard_core.core.events import EventBus, Event, Streams


logger = logging.getLogger(__name__)


class WebhookNotifierPlugin(NotifierPlugin):
    """Generic webhook notifier for external integrations."""
    
    name = "webhook"
    version = "1.0.0"
    plugin_type = "notifier"
    description = "Generic webhook notifications"
    author = "SuperGuard Team"
    
    def __init__(self, config: PluginConfig, event_bus: EventBus):
        super().__init__(config, event_bus)
        self._webhooks: List[Dict[str, Any]] = []
        self._session: Optional[aiohttp.ClientSession] = None
        self._retry_count: int = 3
        self._retry_delay: float = 1.0
    
    async def initialize(self, site_id: int) -> None:
        """Initialize webhook notifier."""
        self._webhooks = self.config.get("webhooks", [])
        self._retry_count = self.config.get("retry_count", 3)
        self._retry_delay = self.config.get("retry_delay", 1.0)
        
        if not self._webhooks:
            logger.warning("Webhook notifier initialized without webhooks")
        
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=10),
        )
        
        await self._event_bus.subscribe(
            Streams.ALARMS_EVENTS,
            self._on_event,
            group=f"webhook-alarms-{site_id}"
        )
        
        await self._event_bus.subscribe(
            Streams.CAMERA_EVENTS,
            self._on_event,
            group=f"webhook-cameras-{site_id}"
        )
        
        await self._event_bus.subscribe(
            Streams.ACTUATORS_EVENTS,
            self._on_event,
            group=f"webhook-actuators-{site_id}"
        )
        
        await self._set_status(self.PluginStatus.LOADED)
        self._initialized = True
        
        logger.info(f"Webhook notifier initialized with {len(self._webhooks)} webhooks")
    
    async def _on_event(self, event: Event) -> None:
        """Handle events from event bus."""
        for webhook in self._webhooks:
            # Filter by event type if configured
            event_types = webhook.get("event_types", [])
            if event_types and event.type not in event_types:
                continue
            
            # Filter by stream if configured
            streams = webhook.get("streams", [])
            if streams and event.stream not in streams:
                continue
            
            await self._send_webhook(webhook, event)
    
    async def _send_webhook(self, webhook: Dict[str, Any], event: Event) -> None:
        """Send event to webhook with retries."""
        url = webhook.get("url")
        method = webhook.get("method", "POST").upper()
        headers = webhook.get("headers", {"Content-Type": "application/json"})
        timeout = webhook.get("timeout", 10)
        
        payload = {
            "event_id": event.id,
            "stream": event.stream,
            "type": event.type,
            "timestamp": event.timestamp,
            "payload": event.payload,
        }
        
        for attempt in range(self._retry_count):
            try:
                async with self._session.request(
                    method,
                    url,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=timeout),
                ) as resp:
                    if 200 <= resp.status < 300:
                        logger.debug(f"Webhook {url} delivered: {event.type}")
                        return
                    else:
                        logger.warning(f"Webhook {url} returned {resp.status}")
                        
            except asyncio.TimeoutError:
                logger.warning(f"Webhook {url} timeout (attempt {attempt + 1})")
            except Exception as e:
                logger.warning(f"Webhook {url} error: {e}")
            
            if attempt < self._retry_count - 1:
                await asyncio.sleep(self._retry_delay * (attempt + 1))
        
        logger.error(f"Webhook {url} failed after {self._retry_count} attempts")
    
    async def send_notification(self, event: Event) -> bool:
        """Send notification for any event."""
        sent = False
        for webhook in self._webhooks:
            await self._send_webhook(webhook, event)
            sent = True
        return sent
    
    async def shutdown(self) -> None:
        """Shutdown plugin."""
        if self._session:
            await self._session.close()
        await self._set_status(self.PluginStatus.UNLOADED)