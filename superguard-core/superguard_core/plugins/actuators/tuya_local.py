"""
SuperGuard Core - Tuya Local Actuator Plugin

Tuya smart plug control via local LAN protocol (tinytuya).
"""

import asyncio
import logging
from typing import Optional

import tinytuya

from superguard_core.core.plugins import ActuatorPlugin, ActuatorState, PluginConfig
from superguard_core.core.database import Actuator


logger = logging.getLogger(__name__)


class TuyaLocalActuatorPlugin(ActuatorPlugin):
    """Tuya local LAN protocol actuator plugin."""
    
    name = "tuya_local"
    version = "1.0.0"
    plugin_type = "actuator"
    description = "Tuya smart plug via local LAN protocol"
    author = "SuperGuard Team"
    
    def __init__(self, config: PluginConfig, event_bus):
        super().__init__(config, event_bus)
        self._actuator: Optional[Actuator] = None
        self._device: Optional[tinytuya.OutletDevice] = None
        self._device_id: str = ""
        self._local_key: str = ""
        self._ip: str = ""
        self._mac: str = ""
        self._version: float = 3.4
        self._port: int = 6668
        self._current_state: bool = False
    
    async def initialize(self, actuator: Actuator) -> None:
        """Initialize Tuya device."""
        self._actuator = actuator
        self._device_id = actuator.config.get("device_id", "")
        self._local_key = actuator.config.get("local_key", "")
        self._ip = actuator.config.get("ip", "")
        self._mac = actuator.config.get("mac", "")
        self._version = actuator.config.get("version", 3.4)
        self._port = actuator.config.get("port", 6668)
        
        if not self._device_id or not self._local_key:
            raise ValueError("Tuya local requires device_id and local_key")
        
        # Create device
        self._device = tinytuya.OutletDevice(
            dev_id=self._device_id,
            address=self._ip,
            local_key=self._local_key,
            version=self._version,
        )
        self._device.set_port(self._port)
        
        # Set socket timeout
        self._device.set_socketTimeout(5)
        
        # Get initial state
        try:
            await self._update_state()
        except Exception as e:
            logger.warning(f"Failed to get initial state for Tuya {actuator.id}: {e}")
        
        await self._set_status(self.PluginStatus.LOADED)
        self._initialized = True
        
        logger.info(f"Tuya Local actuator {actuator.id} ({actuator.name}) initialized at {self._ip}")
    
    async def turn_on(self) -> ActuatorState:
        """Turn actuator ON."""
        if not self._device:
            raise RuntimeError("Device not initialized")
        
        try:
            # Run in thread pool to avoid blocking
            result = await asyncio.to_thread(self._device.set_status, True, switch=1)
            
            if result and isinstance(result, dict) and result.get('dps', {}).get('1') == True:
                self._current_state = True
                logger.info(f"Tuya {self._actuator.id} turned ON")
            else:
                raise RuntimeError(f"Unexpected response: {result}")
                
        except Exception as e:
            logger.error(f"Tuya {self._actuator.id} turn_on failed: {e}")
            raise
        
        return ActuatorState(
            is_on=True,
            last_changed=asyncio.get_event_loop().time(),
            metadata={"source": "tuya_local"}
        )
    
    async def turn_off(self) -> ActuatorState:
        """Turn actuator OFF."""
        if not self._device:
            raise RuntimeError("Device not initialized")
        
        try:
            result = await asyncio.to_thread(self._device.set_status, False, switch=1)
            
            if result and isinstance(result, dict) and result.get('dps', {}).get('1') == False:
                self._current_state = False
                logger.info(f"Tuya {self._actuator.id} turned OFF")
            else:
                raise RuntimeError(f"Unexpected response: {result}")
                
        except Exception as e:
            logger.error(f"Tuya {self._actuator.id} turn_off failed: {e}")
            raise
        
        return ActuatorState(
            is_on=False,
            last_changed=asyncio.get_event_loop().time(),
            metadata={"source": "tuya_local"}
        )
    
    async def toggle(self) -> ActuatorState:
        """Toggle actuator state."""
        if self._current_state:
            return await self.turn_off()
        else:
            return await self.turn_on()
    
    async def get_state(self) -> ActuatorState:
        """Get current actuator state."""
        await self._update_state()
        return ActuatorState(
            is_on=self._current_state,
            last_changed=asyncio.get_event_loop().time(),
            metadata={"source": "tuya_local"}
        )
    
    async def test_connection(self) -> bool:
        """Test device connectivity."""
        try:
            await asyncio.to_thread(self._device.status)
            return True
        except Exception:
            return False
    
    async def _update_state(self) -> None:
        """Update internal state from device."""
        if not self._device:
            return
        
        try:
            status = await asyncio.to_thread(self._device.status)
            
            if status and isinstance(status, dict):
                dps = status.get('dps', {})
                self._current_state = dps.get('1', False)
                
        except Exception as e:
            logger.debug(f"Failed to update Tuya state: {e}")
    
    async def rediscover(self) -> bool:
        """Rediscover device IP via ARP (for DHCP IP changes)."""
        if not self._mac:
            return False
        
        try:
            import subprocess
            
            # Run arp -a and parse
            result = subprocess.run(['arp', '-a'], capture_output=True, text=True, timeout=5)
            
            mac_normalized = self._mac.lower().replace(':', '-')
            
            for line in result.stdout.split('\n'):
                if mac_normalized in line.lower():
                    # Extract IP
                    parts = line.split()
                    for part in parts:
                        if part.count('.') == 3:  # IPv4
                            new_ip = part.strip('()')
                            if new_ip != self._ip:
                                logger.info(f"Tuya {self._actuator.id} IP changed: {self._ip} -> {new_ip}")
                                self._ip = new_ip
                                self._device.set_address(new_ip)
                                return True
            
            return False
            
        except Exception as e:
            logger.warning(f"ARP rediscovery failed for Tuya {self._actuator.id}: {e}")
            return False
    
    async def shutdown(self) -> None:
        """Shutdown plugin."""
        self._device = None
        await self._set_status(self.PluginStatus.UNLOADED)