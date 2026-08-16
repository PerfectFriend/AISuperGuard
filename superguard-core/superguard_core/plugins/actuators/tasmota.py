"""
SuperGuard Core - Tasmota Actuator Plugin

Tasmota smart plug/relay control via HTTP or MQTT.
Supports: any Tasmota-flashed device (Sonoff with Tasmota, generic relays, etc.)
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional

import aiohttp

from superguard_core.core.plugins import ActuatorPlugin, ActuatorState, PluginConfig
from superguard_core.core.database import Actuator


logger = logging.getLogger(__name__)


class TasmotaActuatorPlugin(ActuatorPlugin):
    """Tasmota actuator via HTTP REST API (cmnd)."""

    name = "tasmota"
    version = "1.0.0"
    plugin_type = "actuator"
    description = "Tasmota-flashed device via HTTP API"
    author = "SuperGuard Team"

    def __init__(self, config: PluginConfig, event_bus):
        super().__init__(config, event_bus)
        self._actuator: Optional[Actuator] = None
        self._ip: str = ""
        self._relay: int = 1
        self._password: str = ""
        self._current_state: bool = False
        self._http_session: Optional[aiohttp.ClientSession] = None

    async def initialize(self, actuator: Actuator) -> None:
        self._actuator = actuator
        self._ip = actuator.config.get("ip", "")
        self._relay = actuator.config.get("relay", 1)
        self._password = actuator.config.get("password", "")

        if not self._ip:
            raise ValueError("Tasmota requires ip address")

        self._http_session = aiohttp.ClientSession()
        await self._set_status(self.PluginStatus.LOADED)
        self._initialized = True
        logger.info(f"Tasmota actuator {actuator.id} initialized at {self._ip} relay {self._relay}")

    async def turn_on(self) -> ActuatorState:
        return await self._send_command(f"Power{self._relay} On")

    async def turn_off(self) -> ActuatorState:
        return await self._send_command(f"Power{self._relay} Off")

    async def toggle(self) -> ActuatorState:
        return await self._send_command(f"Power{self._relay} Toggle")

    async def get_state(self) -> ActuatorState:
        try:
            result = await self._send_query(f"Power{self._relay}")
            state = result.get(f"Power{self._relay}", "OFF") == "ON"
            self._current_state = state
            return ActuatorState(
                is_on=state,
                last_changed=datetime.now(),
                metadata={"source": "tasmota", "relay": self._relay},
            )
        except Exception as e:
            logger.error(f"Tasmota get_state failed: {e}")
            raise

    async def test_connection(self) -> bool:
        try:
            result = await self._send_query("Status")
            return "Status" in result or ("Module" in result)
        except Exception:
            return False

    async def _send_command(self, command: str) -> ActuatorState:
        url = f"http://{self._ip}/cm"
        params = {"cmnd": command}
        if self._password:
            params["password"] = self._password

        async with self._http_session.get(url, params=params) as resp:
            if resp.status == 200:
                data = await resp.json()
                response = data.get(command) or data.get(f"Power{self._relay}", "")
                self._current_state = "ON" in str(response).upper()
                logger.info(f"Tasmota {self._actuator.id} cmd={command}, state={self._current_state}")
            elif resp.status == 401:
                raise RuntimeError("Tasmota auth failed - wrong password")
            else:
                raise RuntimeError(f"Tasmota returned {resp.status}")

        return ActuatorState(
            is_on=self._current_state,
            last_changed=datetime.now(),
            metadata={"source": "tasmota", "command": command, "relay": self._relay},
        )

    async def _send_query(self, command: str) -> dict:
        url = f"http://{self._ip}/cm"
        params = {"cmnd": command}
        if self._password:
            params["password"] = self._password
        async with self._http_session.get(url, params=params) as resp:
            if resp.status == 200:
                return await resp.json()
            return {}

    async def shutdown(self) -> None:
        if self._http_session:
            await self._http_session.close()
        await self._set_status(self.PluginStatus.UNLOADED)
