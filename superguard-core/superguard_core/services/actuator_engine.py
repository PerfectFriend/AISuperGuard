"""
SuperGuard Core - Actuator Engine Service

Manages actuator commands: on/off/toggle, state sync, retry with rediscovery.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from superguard_core.core.config import get_settings
from superguard_core.core.database import Actuator, ActuatorState
from superguard_core.core.events import EventBus, publish_actuator_command, publish_actuator_state, Streams
from superguard_core.core.plugins import PluginManager, ActuatorPlugin, PluginConfig


logger = logging.getLogger(__name__)


@dataclass
class ActuatorInstance:
    """Runtime actuator instance."""
    actuator: Actuator
    plugin: ActuatorPlugin
    last_state: Optional[ActuatorState] = None
    pending_command: Optional[str] = None
    is_online: bool = True


class ActuatorEngine:
    """Manages actuators for a site."""
    
    def __init__(
        self,
        plugin_manager: PluginManager,
        event_bus: EventBus,
        site_id: int,
    ):
        self.plugin_manager = plugin_manager
        self.event_bus = event_bus
        self.site_id = site_id
        self.actuators: Dict[int, ActuatorInstance] = {}
        self._running = False
        self._session_factory = None
        self._command_queue: asyncio.Queue = asyncio.Queue()
        self._worker_task: Optional[asyncio.Task] = None
    
    def set_session_factory(self, factory):
        """Set database session factory."""
        self._session_factory = factory
    
    async def start(self) -> None:
        """Start actuator engine."""
        self._running = True
        self._worker_task = asyncio.create_task(self._command_worker())
        logger.info(f"ActuatorEngine started for site {self.site_id}")
    
    async def stop(self) -> None:
        """Stop actuator engine."""
        self._running = False
        
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        
        for instance in list(self.actuators.values()):
            try:
                await instance.plugin.shutdown()
            except Exception:
                pass
        
        self.actuators.clear()
        logger.info(f"ActuatorEngine stopped for site {self.site_id}")
    
    async def load_actuators(self, actuators: List[Actuator]) -> None:
        """Load and initialize actuators from database."""
        for actuator in actuators:
            if actuator.is_enabled and actuator.site_id == self.site_id:
                await self._init_actuator(actuator)
    
    async def add_actuator(self, actuator: Actuator) -> None:
        """Add new actuator."""
        if actuator.is_enabled:
            await self._init_actuator(actuator)
    
    async def remove_actuator(self, actuator_id: int) -> None:
        """Remove actuator."""
        if actuator_id in self.actuators:
            instance = self.actuators[actuator_id]
            try:
                await instance.plugin.shutdown()
            except Exception:
                pass
            del self.actuators[actuator_id]
    
    async def update_actuator(self, actuator: Actuator) -> None:
        """Update actuator configuration."""
        actuator_id = actuator.id
        if actuator_id in self.actuators:
            instance = self.actuators[actuator_id]
            try:
                await instance.plugin.shutdown()
            except Exception:
                pass
            del self.actuators[actuator_id]
        
        if actuator.is_enabled:
            await self._init_actuator(actuator)
    
    async def _init_actuator(self, actuator: Actuator) -> None:
        """Initialize single actuator."""
        try:
            # Find plugin
            plugin_name = actuator.plugin
            plugin_class = self.plugin_manager.get_plugin_class(
                self.plugin_manager.metadata.get(plugin_name, None) and self.plugin_manager.metadata[plugin_name].plugin_type,
                plugin_name
            )
            
            if not plugin_class:
                for name, meta in self.plugin_manager.metadata.items():
                    if meta.plugin_type.value == "actuator" and name == plugin_name:
                        plugin_class = meta.entry_point.load()
                        break
            
            if not plugin_class:
                raise ValueError(f"No actuator plugin found: {plugin_name}")
            
            # Load plugin
            plugin_config = PluginConfig(enabled=True, site_id=self.site_id, **actuator.config)
            plugin = await self.plugin_manager.load_plugin(
                self.plugin_manager.metadata[plugin_name].plugin_type,
                plugin_name,
                plugin_config,
                self.event_bus,
            )
            
            # Initialize with actuator config
            await plugin.initialize(actuator)
            
            # Create instance
            instance = ActuatorInstance(actuator=actuator, plugin=plugin)
            self.actuators[actuator.id] = instance
            
            # Get initial state
            try:
                state = await plugin.get_state()
                instance.last_state = state
                await self._update_actuator_state(actuator.id, state.is_on)
            except Exception as e:
                logger.warning(f"Failed to get initial state for actuator {actuator.id}: {e}")
                instance.is_online = False
            
            logger.info(f"Actuator {actuator.id} ({actuator.name}) initialized")
            
        except Exception as e:
            logger.error(f"Failed to initialize actuator {actuator.id}: {e}")
    
    async def trigger_actuator(self, actuator_id: int, turn_on: bool, alarm_id: Optional[int] = None) -> bool:
        """Queue actuator command (turn on/off)."""
        command = "turn_on" if turn_on else "turn_off"
        await self._command_queue.put({
            "actuator_id": actuator_id,
            "command": command,
            "alarm_id": alarm_id,
            "timestamp": datetime.now().isoformat(),
        })
        return True
    
    async def manual_command(self, actuator_id: int, command: str) -> ActuatorState:
        """Execute manual command immediately (bypass queue)."""
        if actuator_id not in self.actuators:
            raise ValueError(f"Actuator {actuator_id} not found")
        
        instance = self.actuators[actuator_id]
        return await self._execute_command(instance, command)
    
    async def get_state(self, actuator_id: int) -> Optional[ActuatorState]:
        """Get current actuator state."""
        if actuator_id in self.actuators:
            instance = self.actuators[actuator_id]
            try:
                state = await instance.plugin.get_state()
                instance.last_state = state
                return state
            except Exception as e:
                logger.error(f"Failed to get state for actuator {actuator_id}: {e}")
                instance.is_online = False
        return None
    
    async def test_actuator(self, actuator_id: int) -> bool:
        """Test actuator connectivity."""
        if actuator_id in self.actuators:
            instance = self.actuators[actuator_id]
            try:
                return await instance.plugin.test_connection()
            except Exception:
                return False
        return False
    
    async def _command_worker(self) -> None:
        """Background worker processing command queue."""
        while self._running:
            try:
                command_data = await asyncio.wait_for(self._command_queue.get(), timeout=1.0)
                await self._process_command(command_data)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Command worker error: {e}")
                await asyncio.sleep(1)
    
    async def _process_command(self, command_data: Dict[str, Any]) -> None:
        """Process single command from queue."""
        actuator_id = command_data["actuator_id"]
        command = command_data["command"]
        alarm_id = command_data.get("alarm_id")
        
        if actuator_id not in self.actuators:
            logger.warning(f"Actuator {actuator_id} not found for command")
            return
        
        instance = self.actuators[actuator_id]
        
        # Execute with retry
        settings = get_settings()
        max_retries = settings.actuator_retry_attempts
        retry_delay = settings.actuator_retry_delay
        
        for attempt in range(max_retries):
            try:
                state = await self._execute_command(instance, command)
                
                # Update database state
                await self._update_actuator_state(actuator_id, state.is_on, alarm_id)
                
                # Publish state change
                await publish_actuator_state(self.event_bus, actuator_id, {
                    "is_on": state.is_on,
                    "last_changed": state.last_changed.isoformat(),
                    "metadata": state.metadata,
                })
                
                # If this was an alarm-triggered command, publish command event
                if alarm_id:
                    await publish_actuator_command(self.event_bus, actuator_id, command, {
                        "alarm_id": alarm_id,
                        "success": True,
                    })
                
                logger.info(f"Actuator {actuator_id} {command} succeeded")
                return
                
            except Exception as e:
                logger.warning(f"Actuator {actuator_id} {command} attempt {attempt + 1} failed: {e}")
                
                if attempt < max_retries - 1:
                    # Try rediscovery for Tuya plugins
                    if settings.actuator_rediscovery_enabled and "tuya" in instance.actuator.plugin:
                        await self._try_rediscovery(instance)
                    
                    await asyncio.sleep(retry_delay * (attempt + 1))
                else:
                    # All retries failed
                    logger.error(f"Actuator {actuator_id} {command} failed after {max_retries} attempts")
                    
                    if alarm_id:
                        await publish_actuator_command(self.event_bus, actuator_id, command, {
                            "alarm_id": alarm_id,
                            "success": False,
                            "error": str(e),
                        })
    
    async def _execute_command(self, instance: ActuatorInstance, command: str) -> ActuatorState:
        """Execute single command on actuator plugin."""
        if command == "turn_on":
            return await instance.plugin.turn_on()
        elif command == "turn_off":
            return await instance.plugin.turn_off()
        elif command == "toggle":
            return await instance.plugin.toggle()
        else:
            raise ValueError(f"Unknown command: {command}")
    
    async def _try_rediscovery(self, instance: ActuatorInstance) -> None:
        """Try to rediscover actuator IP via ARP (for Tuya)."""
        try:
            # This would be implemented in TuyaLocalActuatorPlugin
            # For now, just log
            logger.info(f"Attempting rediscovery for actuator {instance.actuator.id}")
            # await instance.plugin.rediscover()
        except Exception as e:
            logger.warning(f"Rediscovery failed: {e}")
    
    async def _update_actuator_state(
        self,
        actuator_id: int,
        is_on: bool,
        alarm_id: Optional[int] = None,
    ) -> None:
        """Update actuator state in database."""
        if not self._session_factory:
            return
        
        try:
            async with self._session_factory() as session:
                from sqlalchemy import update
                await session.execute(
                    update(Actuator)
                    .where(Actuator.id == actuator_id)
                    .values(
                        last_state=is_on,
                        last_command_at=datetime.now(),
                    )
                )
                await session.commit()
        except Exception as e:
            logger.error(f"Failed to update actuator state: {e}")
    
    async def sync_states(self) -> None:
        """Sync all actuator states from hardware."""
        for actuator_id, instance in self.actuators.items():
            try:
                state = await instance.plugin.get_state()
                instance.last_state = state
                await self._update_actuator_state(actuator_id, state.is_on)
            except Exception as e:
                logger.error(f"State sync failed for actuator {actuator_id}: {e}")
                instance.is_online = False
    
    def get_actuator_stats(self, actuator_id: int) -> Optional[Dict[str, Any]]:
        """Get actuator statistics."""
        if actuator_id in self.actuators:
            instance = self.actuators[actuator_id]
            return {
                "actuator_id": actuator_id,
                "name": instance.actuator.name,
                "plugin": instance.actuator.plugin,
                "is_online": instance.is_online,
                "last_state": instance.last_state.is_on if instance.last_state else None,
                "last_changed": instance.last_state.last_changed.isoformat() if instance.last_state else None,
                "camera_bindings": instance.actuator.camera_bindings,
            }
        return None
    
    def get_all_stats(self) -> List[Dict[str, Any]]:
        """Get stats for all actuators."""
        return [self.get_actuator_stats(aid) for aid in self.actuators.keys()]


# Factory
_actuator_engines: Dict[int, ActuatorEngine] = {}


async def get_actuator_engine(
    site_id: int,
    plugin_manager: PluginManager,
    event_bus: EventBus,
) -> ActuatorEngine:
    """Get or create actuator engine for site."""
    if site_id not in _actuator_engines:
        _actuator_engines[site_id] = ActuatorEngine(plugin_manager, event_bus, site_id)
        await _actuator_engines[site_id].start()
    return _actuator_engines[site_id]


async def close_all_actuator_engines() -> None:
    """Close all actuator engines."""
    for engine in _actuator_engines.values():
        await engine.stop()
    _actuator_engines.clear()