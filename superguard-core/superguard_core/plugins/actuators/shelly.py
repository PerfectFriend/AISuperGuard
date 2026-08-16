"""
SuperGuard Core - Shelly Actuator Plugin

Shelly smart plug/relay control via HTTP/CoAP/MQTT.
Supports: Shelly Plug S, Shelly 1, Shelly 2.5, Shelly Plus, etc.
"""

import asyncio
import logging
import time
from datetime import datetime
from typing import Optional

import aiohttp

from superguard_core.core.plugins import ActuatorPlugin, ActuatorState, PluginConfig
from superguard_core.core.database import Actuator


logger = logging.getLogger(__name__)


class ShellyActuatorPlugin(ActuatorPlugin):
    """Shelly actuator via HTTP REST API (Gen1/Gen2)."""

    name = "shelly"
    version = "1.0.0"
    plugin_type = "actuator"
    description = "Shelly smart plug/relay via HTTP API"
    author = "SuperGuard Team"

    def __init__(self, config: PluginConfig, event_bus):
        super().__init__(config, event_bus)
        self._actuator: Optional[Actuator] = None
        self._ip: str = ""
        self._channel: int = 0
        self._auth_user: str = ""
        self._auth_pass: str = ""
        self._current_state: bool = False
        self._http_session: Optional[aiohttp.ClientSession] = None

    async def initialize(self, actuator: Actuator) -> None:
        self._actuator = actuator
        self._ip = actuator.config.get("ip", "")
        self._channel = actuator.config.get("channel", 0)
        self._auth_user = actuator.config.get("username", "")
        self._auth_pass = actuator.config.get("password", "")

        if not self._ip:
            raise ValueError("Shelly requires ip address")

        self._http_session = aiohttp.ClientSession()
        await self._set_status(self.PluginStatus.LOADED)
        self._initialized = True
        logger.info(f"Shelly actuator {actuator.id} initialized at {self._ip} channel {self._channel}")

    async def turn_on(self) -> ActuatorState:
        return await self._send_command("on")

    async def turn_off(self) -> ActuatorState:
        return await self._send_command("off")

    async def toggle(self) -> ActuatorState:
        return await self._send_command("toggle")

    async def get_state(self) -> ActuatorState:
        try:
            url = f"http://{self._ip}/relay/{self._channel}"
            auth = aiohttp.BasicAuth(self._auth_user, self._auth_pass) if self._auth_user else None
            async with self._http_session.get(url, auth=auth) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self._current_state = data.get("ison", False)
            return ActuatorState(
                is_on=self._current_state,
                last_changed=datetime.now(),
                metadata={"source": "shelly", "channel": self._channel},
            )
        except Exception as e:
            logger.error(f"Shelly get_state failed: {e}")
            raise

    async def test_connection(self) -> bool:
        try:
            url = f"http://{self._ip}/status"
            auth = aiohttp.BasicAuth(self._auth_user, self._auth_pass) if self._auth_user else None
            async with self._http_session.get(url, auth=auth, timeout=5) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self._current_state = data.get("relays", [{}])[self._channel].get("ison", False)
                    return True
            return False
        except Exception:
            return False

    async def _send_command(self, action: str) -> ActuatorState:
        if action == "toggle":
            url = f"http://{self._ip}/relay/{self._channel}?turn=toggle"
        else:
            url = f"http://{self._ip}/relay/{self._channel}?turn={action}"

        auth = aiohttp.BasicAuth(self._auth_user, self._auth_pass) if self._auth_user else None
        async with self._http_session.get(url, auth=auth) as resp:
            if resp.status == 200:
                data = await resp.json()
                self._current_state = data.get("ison", action == "on")
                logger.info(f"Shelly {self._actuator.id} action={action}, state={self._current_state}")
            elif resp.status == 401:
                raise RuntimeError("Shelly auth failed")
            else:
                raise RuntimeError(f"Shelly returned {resp.status}")

        return ActuatorState(
            is_on=self._current_state,
            last_changed=datetime.now(),
            metadata={"source": "shelly", "channel": self._channel, "action": action},
        )

    async def shutdown(self) -> None:
        if self._http_session:
            await self._http_session.close()
        await self._set_status(self.PluginStatus.UNLOADED)
