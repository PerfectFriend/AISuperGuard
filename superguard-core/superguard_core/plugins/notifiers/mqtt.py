"""
SuperGuard Core - MQTT Notifier Plugin

MQTT notifications for Home Assistant integration.
Publishes alarm events to MQTT topics for HASS auto-discovery.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import List

import aiomqtt

from superguard_core.core.plugins import NotifierPlugin, NotificationPayload, PluginConfig


logger = logging.getLogger(__name__)


class MqttNotifierPlugin(NotifierPlugin):
    """MQTT notifier for Home Assistant and custom integrations."""

    name = "mqtt"
    version = "1.0.0"
    plugin_type = "notifier"
    description = "MQTT notifications for Home Assistant"
    author = "SuperGuard Team"

    def __init__(self, config: PluginConfig, event_bus):
        super().__init__(config, event_bus)
        self._host: str = ""
        self._port: int = 1883
        self._username: str = ""
        self._password: str = ""
        self._topic_prefix: str = "superguard"
        self._client: aiomqtt.Client | None = None
        self._connect_task: asyncio.Task | None = None

    async def initialize(self) -> None:
        self._host = self.config.get("host", "localhost")
        self._port = self.config.get("port", 1883)
        self._username = self.config.get("username", "")
        self._password = self.config.get("password", "")
        self._topic_prefix = self.config.get("topic_prefix", "superguard")

        await self._set_status(self.PluginStatus.LOADED)
        self._initialized = True
        logger.info(f"MQTT notifier initialized: {self._host}:{self._port}")

    async def _ensure_connected(self):
        if self._client is None:
            self._client = aiomqtt.Client(
                hostname=self._host,
                port=self._port,
                username=self._username or None,
                password=self._password or None,
            )
            await self._client.__aenter__()

    async def send(self, payload: NotificationPayload, targets: List[str]) -> bool:
        """Publish to MQTT topics. Targets can be topic suffixes or ignored."""
        try:
            await self._ensure_connected()

            topic = f"{self._topic_prefix}/alarm"
            message = {
                "title": payload.title,
                "message": payload.message,
                "priority": payload.priority,
                "timestamp": datetime.now().isoformat(),
                "media_urls": payload.media_urls,
                "metadata": payload.metadata,
            }

            await self._client.publish(topic, json.dumps(message), qos=1, retain=False)

            # Also publish specific event type
            event_topic = f"{self._topic_prefix}/events/{payload.metadata.get('trigger', 'alarm')}"
            await self._client.publish(event_topic, json.dumps(message), qos=1)

            logger.info(f"MQTT published to {topic}: {payload.title}")
            return True

        except Exception as e:
            logger.error(f"MQTT publish failed: {e}")
            self._client = None  # Force reconnect
            return False

    async def test(self, target: str) -> bool:
        """Publish test message."""
        test_payload = NotificationPayload(
            title="SuperGuard MQTT Test",
            message="Test notification from SuperGuard MQTT notifier",
            priority="normal",
            metadata={"trigger": "test"},
        )
        return await self.send(test_payload, [target])

    @property
    def supported_targets(self) -> List[str]:
        return ["topic_suffix"]

    async def shutdown(self) -> None:
        if self._client:
            await self._client.__aexit__(None, None, None)
            self._client = None
        await self._set_status(self.PluginStatus.UNLOADED)