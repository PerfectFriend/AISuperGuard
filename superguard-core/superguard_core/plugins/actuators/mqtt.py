"""
SuperGuard Core - MQTT Actuator Plugin

Generic MQTT actuator for lights, relays, etc.
"""

import asyncio
import logging
from typing import Optional

import aiomqtt

from superguard_core.core.plugins import ActuatorPlugin, ActuatorState, PluginConfig
from superguard_core.core.database import Actuator


logger = logging.getLogger(__name__)


class MqttActuatorPlugin(ActuatorPlugin):
    """Generic MQTT actuator plugin."""
    
    name = "mqtt"
    version = "1.0.0"
    plugin_type = "actuator"
    description = "Generic MQTT actuator (lights, relays, switches)"
    author = "SuperGuard Team"
    
    def __init__(self, config: PluginConfig, event_bus):
        super().__init__(config, event_bus)
        self._actuator: Optional[Actuator] = None
        self._client: Optional[aiomqtt.Client] = None
        self._host: str = "localhost"
        self._port: int = 1883
        self._username: str = ""
        self._password: str = ""
        self._topic_command: str = ""
        self._topic_state: str = ""
        self._payload_on: str = "ON"
        self._payload_off: str = "OFF"
        self._payload_toggle: str = "TOGGLE"
        self._qos: int = 1
        self._retain: bool = True
        self._current_state: bool = False
        self._state_received: asyncio.Event = asyncio.Event()
    
    async def initialize(self, actuator: Actuator) -> None:
        """Initialize MQTT client."""
        self._actuator = actuator
        
        # Get config
        self._host = actuator.config.get("host", "localhost")
        self._port = actuator.config.get("port", 1883)
        self._username = actuator.config.get("username", "")
        self._password = actuator.config.get("password", "")
        self._topic_command = actuator.config.get("topic_command", "")
        self._topic_state = actuator.config.get("topic_state", self._topic_command)
        self._payload_on = actuator.config.get("payload_on", "ON")
        self._payload_off = actuator.config.get("payload_off", "OFF")
        self._payload_toggle = actuator.config.get("payload_toggle", "TOGGLE")
        self._qos = actuator.config.get("qos", 1)
        self._retain = actuator.config.get("retain", True)
        
        if not self._topic_command:
            raise ValueError("MQTT actuator requires topic_command")
        
        # Connect
        try:
            self._client = aiomqtt.Client(
                hostname=self._host,
                port=self._port,
                username=self._username or None,
                password=self._password or None,
            )
            
            # Start client in background
            self._connect_task = asyncio.create_task(self._run_client())
            
            # Wait for connection
            await asyncio.wait_for(self._connected.wait(), timeout=10)
            
            # Subscribe to state topic
            if self._topic_state:
                await self._client.subscribe(self._topic_state, qos=self._qos)
            
            # Get initial state
            await self._update_state()
            
        except Exception as e:
            raise RuntimeError(f"MQTT connection failed: {e}")
        
        await self._set_status(self.PluginStatus.LOADED)
        self._initialized = True
        
        logger.info(f"MQTT actuator {actuator.id} connected to {self._host}:{self._port}")
    
    _connected = asyncio.Event()
    _connect_task: Optional[asyncio.Task] = None
    
    async def _run_client(self):
        """Run MQTT client loop."""
        try:
            async with self._client:
                self._connected.set()
                
                async for message in self._client.messages:
                    try:
                        payload = message.payload.decode()
                        topic = str(message.topic)
                        
                        if topic == self._topic_state:
                            self._current_state = payload.upper() == self._payload_on.upper()
                            self._state_received.set()
                            
                    except Exception as e:
                        logger.debug(f"MQTT message parse error: {e}")
                        
        except Exception as e:
            logger.error(f"MQTT client error: {e}")
        finally:
            self._connected.clear()
    
    async def turn_on(self) -> ActuatorState:
        """Turn actuator ON."""
        if not self._client:
            raise RuntimeError("MQTT not connected")
        
        await self._client.publish(
            self._topic_command,
            payload=self._payload_on,
            qos=self._qos,
            retain=self._retain,
        )
        
        # Wait for state confirmation
        self._state_received.clear()
        try:
            await asyncio.wait_for(self._state_received.wait(), timeout=5)
        except asyncio.TimeoutError:
            pass
        
        self._current_state = True
        logger.info(f"MQTT {self._actuator.id} turned ON")
        
        return ActuatorState(
            is_on=True,
            last_changed=asyncio.get_event_loop().time(),
            metadata={"source": "mqtt"}
        )
    
    async def turn_off(self) -> ActuatorState:
        """Turn actuator OFF."""
        if not self._client:
            raise RuntimeError("MQTT not connected")
        
        await self._client.publish(
            self._topic_command,
            payload=self._payload_off,
            qos=self._qos,
            retain=self._retain,
        )
        
        self._state_received.clear()
        try:
            await asyncio.wait_for(self._state_received.wait(), timeout=5)
        except asyncio.TimeoutError:
            pass
        
        self._current_state = False
        logger.info(f"MQTT {self._actuator.id} turned OFF")
        
        return ActuatorState(
            is_on=False,
            last_changed=asyncio.get_event_loop().time(),
            metadata={"source": "mqtt"}
        )
    
    async def toggle(self) -> ActuatorState:
        """Toggle actuator state."""
        if not self._client:
            raise RuntimeError("MQTT not connected")
        
        # Send toggle command if supported, else send opposite
        if self._payload_toggle:
            await self._client.publish(
                self._topic_command,
                payload=self._payload_toggle,
                qos=self._qos,
                retain=self._retain,
            )
        else:
            await self._client.publish(
                self._topic_command,
                payload=self._payload_off if self._current_state else self._payload_on,
                qos=self._qos,
                retain=self._retain,
            )
        
        self._state_received.clear()
        try:
            await asyncio.wait_for(self._state_received.wait(), timeout=5)
        except asyncio.TimeoutError:
            pass
        
        return ActuatorState(
            is_on=self._current_state,
            last_changed=asyncio.get_event_loop().time(),
            metadata={"source": "mqtt"}
        )
    
    async def get_state(self) -> ActuatorState:
        """Get current actuator state."""
        await self._update_state()
        return ActuatorState(
            is_on=self._current_state,
            last_changed=asyncio.get_event_loop().time(),
            metadata={"source": "mqtt"}
        )
    
    async def test_connection(self) -> bool:
        """Test MQTT connectivity."""
        return self._connected.is_set() and self._client is not None
    
    async def _update_state(self) -> None:
        """Request state update."""
        if self._client and self._topic_state:
            # Request state if using different command topic
            if self._topic_command != self._topic_state:
                await self._client.publish(
                    self._topic_command,
                    payload="",
                    qos=self._qos,
                    retain=False,
                )
            
            self._state_received.clear()
            try:
                await asyncio.wait_for(self._state_received.wait(), timeout=3)
            except asyncio.TimeoutError:
                pass
    
    async def shutdown(self) -> None:
        """Shutdown plugin."""
        if self._connect_task:
            self._connect_task.cancel()
            try:
                await self._connect_task
            except asyncio.CancelledError:
                pass
        self._client = None
        await self._set_status(self.PluginStatus.UNLOADED)