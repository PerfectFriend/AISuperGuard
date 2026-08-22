"""
Actuator health monitoring and IP discovery service.
Runs periodic keep-alive checks and auto-rediscovers IPs via MAC/ARP.
Sends Telegram alerts if actuator is offline for 3+ minutes.

Supports multiple actuator types:
- Tuya (tinytuya)
- Sonoff (eWeLink API / MQTT)
- Shelly (HTTP API / MQTT)
- Tasmota (HTTP API / MQTT)
- GPIO (local Raspberry Pi / sysfs)
- MQTT (generic MQTT broker)
- HTTP (generic REST API)
"""
import asyncio
import subprocess
import threading
import os
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from abc import ABC, abstractmethod

try:
    import tinytuya
except ImportError:
    tinytuya = None

try:
    import aiohttp
except ImportError:
    aiohttp = None

try:
    import paho.mqtt.client as mqtt
except ImportError:
    mqtt = None

from app.core.encryption import get_encryption


# ============================================================================
# Actuator Discovery Utilities
# ============================================================================

class ActuatorDiscovery:
    """Static utility class for IP discovery and basic connectivity checks."""
    
    @staticmethod
    def discover_ip_by_mac(mac: str) -> Optional[str]:
        """
        Discover current IP address of device by MAC address from ARP/neighbor cache.
        
        Uses `ip neigh` (Linux) or falls back to /proc/net/arp.
        """
        if not mac:
            return None
        
        mac_lower = mac.lower()
        
        try:
            # Try `ip neigh show` first (modern Linux)
            result = subprocess.run(
                ['ip', 'neigh', 'show'], 
                capture_output=True, 
                text=True, 
                timeout=5
            )
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    if 'lladdr' in line:
                        parts = line.split()
                        try:
                            lladdr_idx = parts.index('lladdr')
                            if lladdr_idx + 1 < len(parts):
                                found_mac = parts[lladdr_idx + 1]
                                ip_addr = parts[0]
                                if found_mac.lower() == mac_lower:
                                    return ip_addr
                        except ValueError:
                            pass
        except Exception:
            pass
        
        # Fallback to /proc/net/arp
        try:
            with open('/proc/net/arp', 'r') as f:
                for line in f:
                    parts = line.split()
                    if len(parts) >= 4:
                        ip_addr = parts[0]
                        hw_addr = parts[3]
                        if hw_addr.lower() == mac_lower:
                            return ip_addr
        except Exception:
            pass
        
        return None
    
    @staticmethod
    def ping_host(ip: str, timeout: int = 2) -> bool:
        """Ping a host to check if it's reachable."""
        try:
            result = subprocess.run(
                ['ping', '-c', '1', '-W', str(timeout), ip],
                capture_output=True,
                timeout=timeout + 2
            )
            return result.returncode == 0
        except Exception:
            return False


# ============================================================================
# Base Actuator Interface
# ============================================================================

class BaseActuator(ABC):
    """Abstract base class for all actuator types."""
    
    @abstractmethod
    async def test_connection(self) -> bool:
        """Test if actuator is reachable and responsive."""
        pass
    
    @abstractmethod
    async def get_status(self) -> Optional[bool]:
        """Get current on/off status. Returns True=on, False=off, None=unknown."""
        pass
    
    @abstractmethod
    async def set_state(self, turn_on: bool) -> bool:
        """Set actuator state. Returns True if command succeeded."""
        pass
    
    @abstractmethod
    async def rediscover_ip(self) -> Optional[str]:
        """Attempt to rediscover IP address. Returns new IP or None."""
        pass


# ============================================================================
# Tuya Actuator Implementation
# ============================================================================

@dataclass
class ActuatorConfig:
    """Actuator configuration extracted from DB."""
    id: str
    name: str
    type: str
    ip: str
    device_id: str
    local_key: str
    mac: str
    port: int = 6668
    version: float = 3.4
    # Sonoff specific
    sonoff_apikey: str = ""
    # Shelly specific
    shelly_auth_key: str = ""
    # Tasmota specific
    tasmota_username: str = ""
    tasmota_password: str = ""
    # MQTT specific
    mqtt_topic: str = ""
    mqtt_broker: str = ""
    mqtt_username: str = ""
    mqtt_password: str = ""
    # HTTP specific
    http_on_url: str = ""
    http_off_url: str = ""
    http_status_url: str = ""
    http_headers: Dict[str, str] = field(default_factory=dict)
    # GPIO specific
    gpio_pin: int = -1
    gpio_active_low: bool = False


# ============================================================================
# Tuya Actuator Implementation
# ============================================================================

class TuyaActuator(BaseActuator):
    """Tuya actuator using tinytuya library."""
    
    def __init__(self, config: ActuatorConfig):
        self.config = config
    
    async def test_connection(self) -> bool:
        return await self._test_tuya_connection()
    
    async def get_status(self) -> Optional[bool]:
        return await self._get_tuya_status()
    
    async def set_state(self, turn_on: bool) -> bool:
        return await self._set_tuya_state(turn_on)
    
    async def rediscover_ip(self) -> Optional[str]:
        return ActuatorDiscovery.discover_ip_by_mac(self.config.mac)
    
    async def _test_tuya_connection(self) -> bool:
        if not tinytuya:
            return ActuatorDiscovery.ping_host(self.config.ip)
        
        try:
            device = tinytuya.OutletDevice(
                dev_id=self.config.device_id,
                address=self.config.ip,
                local_key=self.config.local_key,
                version=self.config.version
            )
            device.set_socketPersistent(False)
            device.set_socketTimeout(5)
            status = device.status()
            return status is not None and 'dps' in status
        except Exception:
            return False
    
    async def _get_tuya_status(self) -> Optional[bool]:
        if not tinytuya:
            return None
        
        try:
            device = tinytuya.OutletDevice(
                dev_id=self.config.device_id,
                address=self.config.ip,
                local_key=self.config.local_key,
                version=self.config.version
            )
            device.set_socketPersistent(False)
            device.set_socketTimeout(5)
            status = device.status()
            if status and 'dps' in status:
                return bool(status['dps'].get('1', False))
            return None
        except Exception:
            return None
    
    async def _set_tuya_state(self, turn_on: bool) -> bool:
        if not tinytuya:
            return False
        
        try:
            device = tinytuya.OutletDevice(
                dev_id=self.config.device_id,
                address=self.config.ip,
                local_key=self.config.local_key,
                version=self.config.version
            )
            device.set_socketPersistent(False)
            device.set_socketTimeout(5)
            result = device.set_status(turn_on, switch=1)
            return result is not None
        except Exception:
            return False
    
    async def rediscover_ip(self) -> Optional[str]:
        return ActuatorDiscovery.discover_ip_by_mac(self.config.mac)


# ============================================================================
# Sonoff Actuator Implementation (eWeLink API)
# ============================================================================

class SonoffActuator(BaseActuator):
    """Sonoff actuator using eWeLink API or local LAN mode."""
    
    def __init__(self, config: ActuatorConfig):
        self.config = config
    
    async def test_connection(self) -> bool:
        """Test Sonoff connection via eWeLink API or local LAN."""
        if self.config.sonoff_apikey:
            return await self._test_ewelink()
        else:
            return await self._test_local_lan()
    
    async def get_status(self) -> Optional[bool]:
        if self.config.sonoff_apikey:
            return await self._get_status_ewelink()
        else:
            return await self._get_status_local()
    
    async def set_state(self, turn_on: bool) -> bool:
        if self.config.sonoff_apikey:
            return await self._set_state_ewelink(turn_on)
        else:
            return await self._set_state_local(turn_on)
    
    async def rediscover_ip(self) -> Optional[str]:
        return ActuatorDiscovery.discover_ip_by_mac(self.config.mac)
    
    async def _test_ewelink(self) -> bool:
        """Test via eWeLink cloud API."""
        try:
            import aiohttp
            headers = {'Authorization': f'Bearer {self.config.sonoff_apikey}'}
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f'https://api.coolkit.cc:8080/api/user/device/{self.config.device_id}',
                    headers=headers,
                    timeout=5
                ) as resp:
                    return resp.status == 200
        except Exception:
            return False
    
    async def _test_local_lan(self) -> bool:
        """Test via local LAN (DIY mode)."""
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f'http://{self.config.ip}:8081/zeroconf/info',
                    timeout=5
                ) as resp:
                    return resp.status == 200
        except Exception:
            return ActuatorDiscovery.ping_host(self.config.ip)
    
    async def _get_status_ewelink(self) -> Optional[bool]:
        """Get status via eWeLink API."""
        try:
            import aiohttp
            headers = {'Authorization': f'Bearer {self.config.sonoff_apikey}'}
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f'https://api.coolkit.cc:8080/api/user/device/{self.config.device_id}',
                    headers=headers,
                    timeout=5
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get('params', {}).get('switch') == 'on'
            return None
        except Exception:
            return None
    
    async def _get_status_local(self) -> Optional[bool]:
        """Get status via local LAN."""
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f'http://{self.config.ip}:8081/zeroconf/info',
                    json={"deviceid": "", "data": {}},
                    timeout=5
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get('data', {}).get('switch') == 'on'
            return None
        except Exception:
            return None
    
    async def _set_state_ewelink(self, turn_on: bool) -> bool:
        """Set state via eWeLink API."""
        try:
            import aiohttp
            headers = {
                'Authorization': f'Bearer {self.config.sonoff_apikey}',
                'Content-Type': 'application/json'
            }
            payload = {
                'deviceid': self.config.device_id,
                'params': {'switch': 'on' if turn_on else 'off'}
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    'https://api.coolkit.cc:8080/api/user/device/control',
                    headers=headers,
                    json=payload,
                    timeout=5
                ) as resp:
                    return resp.status == 200
        except Exception:
            return False
    
    async def _set_state_local(self, turn_on: bool) -> bool:
        """Set state via local LAN (DIY mode)."""
        try:
            import aiohttp
            payload = {
                "deviceid": "",
                "data": {"switch": "on" if turn_on else "off"}
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f'http://{self.config.ip}:8081/zeroconf/switch',
                    json=payload,
                    timeout=5
                ) as resp:
                    return resp.status == 200
        except Exception:
            return False
    
    async def _get_status_local(self) -> Optional[bool]:
        """Get status via local LAN."""
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f'http://{self.config.ip}:8081/zeroconf/info',
                    json={"deviceid": "", "data": {}},
                    timeout=5
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get('data', {}).get('switch') == 'on'
            return None
        except Exception:
            return None
    
    async def _set_state_local(self, turn_on: bool) -> bool:
        """Set state via local LAN (DIY mode)."""
        try:
            import aiohttp
            payload = {
                "deviceid": "",
                "data": {"switch": "on" if turn_on else "off"}
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f'http://{self.config.ip}:8081/zeroconf/switch',
                    json=payload,
                    timeout=5
                ) as resp:
                    return resp.status == 200
        except Exception:
            return False


# ============================================================================
# Shelly Actuator Implementation
# ============================================================================

class ShellyActuator(BaseActuator):
    """Shelly actuator using HTTP API."""
    
    def __init__(self, config: ActuatorConfig):
        self.config = config
    
    async def test_connection(self) -> bool:
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f'http://{self.config.ip}/rpc/Shelly.GetStatus',
                    timeout=5
                ) as resp:
                    return resp.status == 200
        except Exception:
            return ActuatorDiscovery.ping_host(self.config.ip)
    
    async def get_status(self) -> Optional[bool]:
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f'http://{self.config.ip}/rpc/Switch.GetStatus',
                    json={"id": 0},
                    timeout=5
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get('output', False)
            return None
        except Exception:
            return None
    
    async def set_state(self, turn_on: bool) -> bool:
        try:
            import aiohttp
            auth = None
            if self.config.shelly_auth_key:
                import base64
                auth = aiohttp.BasicAuth('admin', self.config.shelly_auth_key)
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f'http://{self.config.ip}/rpc/Switch.Set',
                    json={"id": 0, "on": turn_on},
                    auth=auth,
                    timeout=5
                ) as resp:
                    return resp.status == 200
        except Exception:
            return False
    
    async def rediscover_ip(self) -> Optional[str]:
        return ActuatorDiscovery.discover_ip_by_mac(self.config.mac)


# ============================================================================
# Tasmota Actuator Implementation
# ============================================================================

class TasmotaActuator(BaseActuator):
    """Tasmota actuator using HTTP API."""
    
    def __init__(self, config: ActuatorConfig):
        self.config = config
    
    async def test_connection(self) -> bool:
        try:
            import aiohttp
            auth = None
            if self.config.tasmota_username and self.config.tasmota_password:
                import aiohttp
                auth = aiohttp.BasicAuth(self.config.tasmota_username, self.config.tasmota_password)
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f'http://{self.config.ip}/cm?cmnd=Status',
                    auth=auth,
                    timeout=5
                ) as resp:
                    return resp.status == 200
        except Exception:
            return ActuatorDiscovery.ping_host(self.config.ip)
    
    async def get_status(self) -> Optional[bool]:
        try:
            import aiohttp
            auth = None
            if self.config.tasmota_username and self.config.tasmota_password:
                import aiohttp
                auth = aiohttp.BasicAuth(self.config.tasmota_username, self.config.tasmota_password)
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f'http://{self.config.ip}/cm?cmnd=Power',
                    auth=auth,
                    timeout=5
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get('POWER') == 'ON'
            return None
        except Exception:
            return None
    
    async def set_state(self, turn_on: bool) -> bool:
        try:
            import aiohttp
            auth = None
            if self.config.tasmota_username and self.config.tasmota_password:
                import aiohttp
                auth = aiohttp.BasicAuth(self.config.tasmota_username, self.config.tasmota_password)
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f'http://{self.config.ip}/cm?cmnd=Power%20{"On" if turn_on else "Off"}',
                    auth=auth,
                    timeout=5
                ) as resp:
                    return resp.status == 200
        except Exception:
            return False
    
    async def rediscover_ip(self) -> Optional[str]:
        return ActuatorDiscovery.discover_ip_by_mac(self.config.mac)


# ============================================================================
# GPIO Actuator Implementation (Raspberry Pi / Linux sysfs)
# ============================================================================

class GPIOActuator(BaseActuator):
    """GPIO actuator using Linux sysfs or libgpiod."""
    
    def __init__(self, config: ActuatorConfig):
        self.config = config
        self._gpio_exported = False
    
    async def test_connection(self) -> bool:
        # GPIO is always local, just check if pin is exported
        return self._ensure_gpio_exported()
    
    async def get_status(self) -> Optional[bool]:
        try:
            value_path = f'/sys/class/gpio/gpio{self.config.gpio_pin}/value'
            with open(value_path, 'r') as f:
                value = int(f.read().strip())
                # Handle active_low
                if self.config.gpio_active_low:
                    return value == 0
                return value == 1
        except Exception:
            return None
    
    async def set_state(self, turn_on: bool) -> bool:
        if not self._ensure_gpio_exported():
            return False
        
        try:
            value_path = f'/sys/class/gpio/gpio{self.config.gpio_pin}/value'
            # Handle active_low
            value = 1 if turn_on else 0
            if self.config.gpio_active_low:
                value = 0 if turn_on else 1
            
            with open(value_path, 'w') as f:
                f.write(str(value))
            return True
        except Exception:
            return False
    
    async def rediscover_ip(self) -> Optional[str]:
        return None  # GPIO is local, no IP
    
    def _ensure_gpio_exported(self) -> bool:
        """Export GPIO pin if not already exported."""
        if self._gpio_exported:
            return True
        
        try:
            export_path = '/sys/class/gpio/export'
            direction_path = f'/sys/class/gpio/gpio{self.config.gpio_pin}/direction'
            
            # Check if already exported
            if not os.path.exists(f'/sys/class/gpio/gpio{self.config.gpio_pin}'):
                with open(export_path, 'w') as f:
                    f.write(str(self.config.gpio_pin))
            
            # Set direction to out
            with open(direction_path, 'w') as f:
                f.write('out')
            
            self._gpio_exported = True
            return True
        except Exception:
            return False


# ============================================================================
# MQTT Actuator Implementation
# ============================================================================

class MQTTActuator(BaseActuator):
    """MQTT actuator using generic MQTT broker."""
    
    def __init__(self, config: ActuatorConfig):
        self.config = config
        self._client = None
    
    async def test_connection(self) -> bool:
        try:
            import paho.mqtt.client as mqtt
            # Quick connection test
            client = mqtt.Client()
            client.username_pw_set(self.config.mqtt_username, self.config.mqtt_password)
            client.connect(self.config.mqtt_broker, 1883, 5)
            client.disconnect()
            return True
        except Exception:
            return False
    
    async def get_status(self) -> Optional[bool]:
        # MQTT is async - status would come via subscription
        # For test purposes, publish get command and wait for response
        return None  # Requires subscription handler
    
    async def set_state(self, turn_on: bool) -> bool:
        try:
            import paho.mqtt.client as mqtt
            client = mqtt.Client()
            if self.config.mqtt_username:
                client.username_pw_set(self.config.mqtt_username, self.config.mqtt_password)
            
            client.connect(self.config.mqtt_broker, 1883, 5)
            payload = "ON" if turn_on else "OFF"
            result = client.publish(self.config.mqtt_topic, payload, qos=1)
            client.disconnect()
            return result.rc == 0
        except Exception:
            return False
    
    async def rediscover_ip(self) -> Optional[str]:
        return None  # MQTT broker IP is fixed in config


# ============================================================================
# HTTP Actuator Implementation (Generic REST)
# ============================================================================

class HTTPActuator(BaseActuator):
    """Generic HTTP actuator using REST API."""
    
    def __init__(self, config: ActuatorConfig):
        self.config = config
    
    async def test_connection(self) -> bool:
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    self.config.http_status_url or self.config.http_on_url,
                    headers=self.config.http_headers,
                    timeout=5
                ) as resp:
                    return resp.status == 200
        except Exception:
            return ActuatorDiscovery.ping_host(self.config.ip)
    
    async def get_status(self) -> Optional[bool]:
        if not self.config.http_status_url:
            return None
        
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    self.config.http_status_url,
                    headers=self.config.http_headers,
                    timeout=5
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        # Expecting {"state": true/false} or similar
                        return data.get('state') or data.get('on') or data.get('value')
            return None
        except Exception:
            return None
    
    async def set_state(self, turn_on: bool) -> bool:
        url = self.config.http_on_url if turn_on else self.config.http_off_url
        if not url:
            return False
        
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    headers=self.config.http_headers,
                    timeout=5
                ) as resp:
                    return resp.status in (200, 201, 204)
        except Exception:
            return False
    
    async def rediscover_ip(self) -> Optional[str]:
        return ActuatorDiscovery.discover_ip_by_mac(self.config.mac)


# ============================================================================
# Actuator Factory
# ============================================================================

def create_actuator(config: ActuatorConfig) -> BaseActuator:
    """
    Factory function to create the appropriate actuator instance based on type.
    
    Args:
        config: ActuatorConfig with all necessary parameters
        
    Returns:
        BaseActuator: Concrete actuator implementation for the given type
        
    Raises:
        ValueError: If actuator type is not supported
    """
    actuator_type = config.type.lower()
    
    if actuator_type in ('tuya', 'tinytuya'):
        return TuyaActuator(config)
    elif actuator_type == 'sonoff':
        return SonoffActuator(config)
    elif actuator_type == 'shelly':
        return ShellyActuator(config)
    elif actuator_type == 'tasmota':
        return TasmotaActuator(config)
    elif actuator_type == 'gpio':
        return GPIOActuator(config)
    elif actuator_type == 'mqtt':
        return MQTTActuator(config)
    elif actuator_type == 'http':
        return HTTPActuator(config)
    else:
        raise ValueError(f"Unsupported actuator type: {config.type}")


# ============================================================================
# Actuator Health Monitor
# ============================================================================

class ActuatorHealthMonitor:
    """Background monitor that checks all actuators every minute.
    
    Tracks consecutive offline checks and sends Telegram alerts
    after 3 minutes (3 failed checks) of being unreachable.
    """
    
    def __init__(self, db_session_factory):
        self.db_session_factory = db_session_factory
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._lock = threading.Lock()
        # Track offline state: actuator_id -> {'offline_since': datetime, 'alert_sent': bool, 'consecutive_failures': int}
        self._offline_tracking: Dict[str, Dict[str, Any]] = {}
    
    async def start(self, interval: int = 60):
        """Start the periodic health check."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop(interval))
    
    async def stop(self):
        """Stop the monitor."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
    
    async def _run_loop(self, interval: int):
        """Main monitoring loop."""
        while self._running:
            try:
                await self.check_all_actuators()
            except Exception as e:
                print(f"[ActuatorHealthMonitor] Error in check loop: {e}")
            
            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
    
    async def check_all_actuators(self):
        """Check all actuators across all sites."""
        from app.models import Actuator, Site
        from sqlalchemy import select
        
        async for db in self.db_session_factory():
            try:
                # Get all enabled actuators
                result = await db.execute(
                    select(Actuator).where(Actuator.is_enabled == True)
                )
                actuators = result.scalars().all()
                
                for actuator in actuators:
                    await self._check_single_actuator(db, actuator)
                
                await db.commit()
                
            except Exception as e:
                print(f"[ActuatorHealthMonitor] Error checking actuators: {e}")
                await db.rollback()
    
    async def _check_single_actuator(self, db, actuator) -> Dict[str, Any]:
        """Check a single actuator and update its status in DB."""
        # Extract and decrypt config
        cfg = actuator.config or {}
        encryption = get_encryption()
        cfg = encryption.decrypt_dict(cfg)
        
        # Create appropriate actuator instance
        config = ActuatorConfig(
            id=actuator.id,
            name=actuator.name,
            type=actuator.type.value,
            ip=cfg.get('ip', ''),
            device_id=cfg.get('device_id', ''),
            local_key=cfg.get('local_key', ''),
            mac=cfg.get('mac', ''),
            port=cfg.get('port', 6668),
            version=cfg.get('version', 3.4),
            # Sonoff
            sonoff_apikey=cfg.get('sonoff_apikey', ''),
            # Shelly
            shelly_auth_key=cfg.get('shelly_auth_key', ''),
            # Tasmota
            tasmota_username=cfg.get('tasmota_username', ''),
            tasmota_password=cfg.get('tasmota_password', ''),
            # MQTT
            mqtt_topic=cfg.get('mqtt_topic', ''),
            mqtt_broker=cfg.get('mqtt_broker', ''),
            mqtt_username=cfg.get('mqtt_username', ''),
            mqtt_password=cfg.get('mqtt_password', ''),
            # HTTP
            http_on_url=cfg.get('http_on_url', ''),
            http_off_url=cfg.get('http_off_url', ''),
            http_status_url=cfg.get('http_status_url', ''),
            http_headers=cfg.get('http_headers', {}),
            # GPIO
            gpio_pin=cfg.get('gpio_pin', -1),
            gpio_active_low=cfg.get('gpio_active_low', False),
        )
        
        # Create actuator instance
        try:
            actuator_instance = create_actuator(config)
        except ValueError as e:
            print(f"[ActuatorHealthMonitor] Unknown actuator type {actuator.type.value}: {e}")
            return {'online': False, 'error': str(e)}
        
        # Test connection
        online = await actuator_instance.test_connection()
        
        # Update actuator in DB
        actuator.is_online = online
        actuator.last_seen = datetime.utcnow() if online else actuator.last_seen
        
        # If IP changed (for types that support rediscovery), update config
        # Note: IP rediscovery is only for Tuya/Sonoff/Shelly/Tasmota/HTTP
        if hasattr(actuator_instance, 'rediscover_ip'):
            new_ip = await actuator_instance.rediscover_ip()
            if new_ip and new_ip != config.ip:
                # Test new IP
                old_ip = config.ip
                config.ip = new_ip
                new_actuator = create_actuator(config)
                if await new_actuator.test_connection():
                    # IP changed successfully - update DB
                    encryption = get_encryption()
                    new_config = dict(actuator.config or {})
                    new_config['ip'] = new_ip
                    new_config = encryption.encrypt_dict(new_config)
                    actuator.config = new_config
                    print(f"[ActuatorHealthMonitor] {actuator.name}: IP updated {config.ip} -> {new_ip}")
                    return {'online': True, 'ip_changed': True, 'new_ip': new_ip, 'old_ip': config.ip}
        
        # Update offline tracking and send alerts if needed
        await self._update_offline_tracking(actuator.id, online, actuator.name, cfg, db)
        
        return {'online': online}
    
    async def _update_offline_tracking(self, actuator_id: str, online: bool, name: str = "", config: Dict = None, db=None):
        """Track consecutive offline checks and send alert after 3 minutes."""
        now = datetime.utcnow()
        
        with self._lock:
            if actuator_id not in self._offline_tracking:
                self._offline_tracking[actuator_id] = {
                    'offline_since': None,
                    'alert_sent': False,
                    'consecutive_failures': 0
                }
            
            tracking = self._offline_tracking[actuator_id]
            
            if online:
                # Actuator is back online - reset tracking
                if tracking['offline_since'] is not None:
                    print(f"[ActuatorHealthMonitor] {name or actuator_id}: Back online after {tracking['consecutive_failures']} failed checks")
                tracking['offline_since'] = None
                tracking['alert_sent'] = False
                tracking['consecutive_failures'] = 0
            else:
                # Actuator is offline
                tracking['consecutive_failures'] += 1
                
                if tracking['offline_since'] is None:
                    tracking['offline_since'] = datetime.utcnow()
                
                # Check if we should send alert (3 consecutive failures = 3 minutes)
                if tracking['consecutive_failures'] >= 3 and not tracking['alert_sent']:
                    tracking['alert_sent'] = True
                    # Send alert asynchronously
                    asyncio.create_task(self._send_actuator_lost_alert(actuator_id, name, config, db))
    
    async def _send_actuator_lost_alert(self, actuator_id: str, name: str, config: Dict, db):
        """Send Telegram alert when actuator is lost for 3+ minutes."""
        try:
            from app.models import Actuator, Notifier
            from sqlalchemy import select
            
            # Find enabled Telegram notifiers for this actuator's site
            async for db_session in self.db_session_factory():
                # Get the actuator to find its site
                result = await db_session.execute(
                    select(Actuator).where(Actuator.id == actuator_id)
                )
                actuator = result.scalar_one_or_none()
                if not actuator:
                    return
                
                # Find Telegram notifiers for this site
                result = await db_session.execute(
                    select(Notifier).where(
                        Notifier.site_id == actuator.site_id,
                        Notifier.is_enabled == True,
                        Notifier.type == 'telegram'
                    )
                )
                notifiers = result.scalars().all()
                
                for notifier in notifiers:
                    try:
                        await self._send_telegram_alert(notifier, actuator, name)
                    except Exception as e:
                        print(f"[ActuatorHealthMonitor] Failed to send Telegram alert: {e}")
                
                break  # Only need one session
                
        except Exception as e:
            print(f"[ActuatorHealthMonitor] Error sending alert for {actuator_id}: {e}")
    
    async def _send_telegram_alert(self, notifier: 'Notifier', actuator: 'Actuator', name: str):
        """Send Telegram message via Bot API."""
        import requests
        
        bot_token = notifier.config.get('bot_token')
        chat_id = notifier.config.get('chat_id')
        
        if not bot_token or not chat_id:
            return
        
        message = (
            f"🚨 <b>ACTUATOR LOST</b> 🚨\n\n"
            f"<b>Actuator:</b> {name} ({actuator.id[:8]}...)\n"
            f"<b>Site:</b> {actuator.site_id[:8]}...\n"
            f"<b>Last IP:</b> {actuator.config.get('ip', 'unknown')}\n"
            f"<b>MAC:</b> {actuator.config.get('mac', 'unknown')}\n"
            f"<b>Offline for:</b> 3+ minutes (3 consecutive failed checks)\n\n"
            f"⚠️ <b>Possible tampering detected</b> - someone may have deliberately\n"
            f"disconnected the actuator to disable security. Please investigate immediately."
        )
        
        try:
            response = requests.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": message,
                    "parse_mode": "HTML"
                },
                timeout=10
            )
            if response.status_code == 200:
                print(f"[ActuatorHealthMonitor] Telegram alert sent for {name}")
            else:
                print(f"[ActuatorHealthMonitor] Telegram alert failed: {response.text}")
        except Exception as e:
            print(f"[ActuatorHealthMonitor] Telegram send error: {e}")
    
    async def test_actuator(self, actuator_id: str) -> Dict[str, Any]:
        """Test a specific actuator (called from API endpoint)."""
        from app.models import Actuator
        from sqlalchemy import select
        
        async for db in self.db_session_factory():
            result = await db.execute(
                select(Actuator).where(Actuator.id == actuator_id)
            )
            actuator = result.scalar_one_or_none()
            
            if not actuator:
                return {'online': False, 'error': 'Actuator not found'}
            
            check_result = await self._check_single_actuator(db, actuator)
            await db.commit()
            return check_result