"""
SuperGuard Core - Pushover Notifier Plugin

Push notifications via Pushover.net.
"""

import asyncio
import logging
from typing import List

import aiohttp

from superguard_core.core.plugins import NotifierPlugin, NotificationPayload, PluginConfig


logger = logging.getLogger(__name__)


class PushoverNotifierPlugin(NotifierPlugin):
    """Pushover notifier via Pushover.net API."""

    name = "pushover"
    version = "1.0.0"
    plugin_type = "notifier"
    description = "Push notifications via Pushover.net"
    author = "SuperGuard Team"

    PUSHOVER_API = "https://api.pushover.net/1/messages.json"

    def __init__(self, config: PluginConfig, event_bus):
        super().__init__(config, event_bus)
        self._app_token: str = ""
        self._http_session: aiohttp.ClientSession | None = None

    async def initialize(self) -> None:
        self._app_token = self.config.get("app_token", "")
        if not self._app_token:
            raise ValueError("Pushover requires app_token")

        self._http_session = aiohttp.ClientSession()
        await self._set_status(self.PluginStatus.LOADED)
        self._initialized = True
        logger.info("Pushover notifier initialized")

    async def send(self, payload: NotificationPayload, targets: List[str]) -> bool:
        """Send push to targets (list of user keys)."""
        if not targets:
            logger.warning("No Pushover user keys provided")
            return False

        priority_map = {
            "low": -1,
            "normal": 0,
            "high": 1,
            "critical": 2,
        }

        for user_key in targets:
            try:
                data = {
                    "token": self._app_token,
                    "user": user_key,
                    "title": f"SuperGuard: {payload.title}",
                    "message": payload.message,
                    "priority": priority_map.get(payload.priority, 0),
                }

                # Add URL if media available
                if payload.media_urls:
                    data["url"] = payload.media_urls[0]
                    data["url_title"] = "View in SuperGuard"

                async with self._http_session.post(self.PUSHOVER_API, data=data) as resp:
                    if resp.status == 200:
                        logger.info(f"Pushover sent to user: {payload.title}")
                    else:
                        error_text = await resp.text()
                        logger.error(f"Pushover failed ({resp.status}): {error_text}")
                        return False

            except Exception as e:
                logger.error(f"Pushover send error: {e}")
                return False

        return True

    async def test(self, target: str) -> bool:
        """Send test push."""
        test_payload = NotificationPayload(
            title="SuperGuard Test",
            message="This is a test push notification from SuperGuard.",
            priority="normal",
        )
        return await self.send(test_payload, [target])

    @property
    def supported_targets(self) -> List[str]:
        return ["user_key"]

    async def shutdown(self) -> None:
        if self._http_session:
            await self._http_session.close()
        await self._set_status(self.PluginStatus.UNLOADED)