"""
Actuator Engine - Executes actuator commands from alarm system.
Listens for WS actuator.command events and controls hardware.
Supports: Tuya, Sonoff, Shelly, Tasmota, GPIO, MQTT, HTTP
"""
import asyncio
import logging
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any, List
from abc import ABC, abstractmethod

from app.core.encryption import get_encryption

logger = logging.getLogger(__name__)


# ============================================================================
# Actuator Discovery Utilities
# ============================================================================

class ActuatorDiscovery:
    """Static utility for IP discovery and connectivity checks."""

    @staticmethod
    def discover_ip_by_mac(mac: str) -> Optional[str]:
        """Discover IP of device by MAC from ARP/neighbor cache."""
        if not mac:
            return None
        mac_lower = mac.lower()
        try:
            result = subprocess.run(
                ['ip', 'neigh', 'show'], capture_output=True, text=True, timeout=5
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
        """Ping host to check reachability."""
        try:
            result = subprocess.run(
                ['ping', '-c', '1', '-W', str(timeout), ip],
                capture_output=True, timeout=timeout + 2
            )
            return result.returncode == 0
        except Exception:
            return False


# ============================================================================
# Base Actuator Interface
# ============================================================================

class BaseActuator(ABC):
    """Abstract base for all actuator types."""

    @abstractmethod
    async def test_connection(self) -> bool:
        pass

    @abstractmethod
    async def get_status(self) -> Optional[bool]:
        pass

    @abstractmethod
    async def set_state(self, turn_on: bool) -> bool:
        pass

    @abstractmethod
    async def rediscover_ip(self) -> Optional[str]:
        pass


# ============================================================================
# Configuration Dataclass
# ============================================================================

@dataclass
class ActuatorConfig:
    """Actuator configuration from DB."""
    id: str
    name: str
    type: str
    ip: str
    device_id: str = ""
    local_key: str = ""
    mac: str = ""
    port: int = 6668
    version: float = 3.4
    # Sonoff
    sonoff_apikey: str = ""
    # Shelly
    shelly_auth_key: str = ""
    # Tasmota
    tasmota_username: str = ""
    tasmota_password: str = ""
    # MQTT
    mqtt_topic: str = ""
    mqtt_broker: str = ""
    mqtt_username: str = ""
    mqtt_password: str = ""
    # HTTP
    http_on_url: str = ""
    http_off_url: str = ""
    http_status_url: str = ""
    http_headers: Dict[str, str] = field(default_factory=dict)
    # GPIO
    gpio_pin: int = -1
    gpio_active_low: bool = False


# ============================================================================
# Tuya Actuator
# ============================================================================

class TuyaActuator(BaseActuator):
    """Tuya actuator using tinytuya."""

    def __init__(self, config: ActuatorConfig):
        self.config = config
        self.encryption = get_encryption()

    def _decrypt_fields(self):
        """Decrypt sensitive fields from DB."""
        self.config.ip = self.encryption.decrypt(self.config.ip)
        self.config.device_id = self.encryption.decrypt(self.config.device_id)
        self.config.local_key = self.encryption.decrypt(self.config.local_key)

    async def _get_device(self):
        self._decrypt_fields()
        try:
            import tinytuya
        except ImportError:
            return None
        device = tinytuya.OutletDevice(
            dev_id=self.config.device_id,
            address=self.config.ip,
            local_key=self.config.local_key,
            version=self.config.version
        )
        device.set_socketPersistent(False)
        device.set_socketTimeout(5)
        return device

    async def test_connection(self) -> bool:
        device = await self._get_device()
        if not device:
            return ActuatorDiscovery.ping_host(self.config.ip)
        try:
            status = device.status()
            return status is not None and 'dps' in status
        except Exception:
            return False

    async def get_status(self) -> Optional[bool]:
        device = await self._get_device()
        if not device:
            return None
        try:
            status = device.status()
            if status and 'dps' in status:
                return bool(status['dps'].get('1', False))
        except Exception:
            pass
        return None

    async def set_state(self, turn_on: bool) -> bool:
        device = await self._get_device()
        if not device:
            return False
        try:
            result = device.set_status(turn_on, switch=1)
            return result is not None
        except Exception:
            return False

    async def rediscover_ip(self) -> Optional[str]:
        return ActuatorDiscovery.discover_ip_by_mac(self.config.mac)


# ============================================================================
# Sonoff Actuator (eWeLink / Local LAN)
# ============================================================================

class SonoffActuator(BaseActuator):
    """Sonoff via eWeLink API or local LAN DIY mode."""

    def __init__(self, config: ActuatorConfig):
        self.config = config
        self.encryption = get_encryption()

    def _decrypt_fields(self):
        self.config.ip = self.encryption.decrypt(self.config.ip)
        self.config.device_id = self.encryption.decrypt(self.config.device_id)
        if self.config.sonoff_apikey:
            self.config.sonoff_apikey = self.encryption.decrypt(self.config.sonoff_apikey)

    async def test_connection(self) -> bool:
        self._decrypt_fields()
        try:
            import aiohttp
        except ImportError:
            return ActuatorDiscovery.ping_host(self.config.ip)

        if self.config.sonoff_apikey:
            # Cloud API
            headers = {'Authorization': f'Bearer {self.config.sonoff_apikey}'}
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        f'https://api.coolkit.cc:8080/api/user/device/{self.config.device_id}',
                        headers=headers, timeout=5
                    ) as resp:
                        return resp.status == 200
            except Exception:
                return False
        else:
            # Local LAN
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        f'http://{self.config.ip}:8081/zeroconf/info', timeout=5
                    ) as resp:
                        return resp.status == 200
            except Exception:
                return ActuatorDiscovery.ping_host(self.config.ip)

    async def get_status(self) -> Optional[bool]:
        self._decrypt_fields()
        try:
            import aiohttp
        except ImportError:
            return None

        if self.config.sonoff_apikey:
            headers = {'Authorization': f'Bearer {self.config.sonoff_apikey}'}
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        f'https://api.coolkit.cc:8080/api/user/device/{self.config.device_id}',
                        headers=headers, timeout=5
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            return data.get('params', {}).get('switch') == 'on'
            except Exception:
                pass
        else:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        f'http://{self.config.ip}:8081/zeroconf/info',
                        json={"deviceid": "", "data": {}}, timeout=5
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            return data.get('data', {}).get('switch') == 'on'
            except Exception:
                pass
        return None

    async def set_state(self, turn_on: bool) -> bool:
        self._decrypt_fields()
        try:
            import aiohttp
        except ImportError:
            return False

        if self.config.sonoff_apikey:
            headers = {
                'Authorization': f'Bearer {self.config.sonoff_apikey}',
                'Content-Type': 'application/json'
            }
            payload = {'deviceid': self.config.device_id, 'params': {'switch': 'on' if turn_on else 'off'}}
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        'https://api.coolkit.cc:8080/api/user/device/control',
                        headers=headers, json=payload, timeout=5
                    ) as resp:
                        return resp.status == 200
            except Exception:
                return False
        else:
            payload = {"deviceid": "", "data": {"switch": "on" if turn_on else "off"}}
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        f'http://{self.config.ip}:8081/zeroconf/switch',
                        json=payload, timeout=5
                    ) as resp:
                        return resp.status == 200
            except Exception:
                return False

    async def rediscover_ip(self) -> Optional[str]:
        return ActuatorDiscovery.discover_ip_by_mac(self.config.mac)


# ============================================================================
# Shelly Actuator
# ============================================================================

class ShellyActuator(BaseActuator):
    """Shelly via HTTP RPC API."""

    def __init__(self, config: ActuatorConfig):
        self.config = config
        self.encryption = get_encryption()

    def _decrypt_fields(self):
        self.config.ip = self.encryption.decrypt(self.config.ip)
        if self.config.shelly_auth_key:
            self.config.shelly_auth_key = self.encryption.decrypt(self.config.shelly_auth_key)

    async def test_connection(self) -> bool:
        self._decrypt_fields()
        try:
            import aiohttp
        except ImportError:
            return ActuatorDiscovery.ping_host(self.config.ip)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f'http://{self.config.ip}/rpc/Shelly.GetStatus', timeout=5
                ) as resp:
                    return resp.status == 200
        except Exception:
            return ActuatorDiscovery.ping_host(self.config.ip)

    async def get_status(self) -> Optional[bool]:
        self._decrypt_fields()
        try:
            import aiohttp
        except ImportError:
            return None
        try:
            auth = None
            if self.config.shelly_auth_key:
                auth = aiohttp.BasicAuth('admin', self.config.shelly_auth_key)
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f'http://{self.config.ip}/rpc/Switch.GetStatus',
                    json={"id": 0}, auth=auth, timeout=5
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get('output', False)
        except Exception:
            pass
        return None

    async def set_state(self, turn_on: bool) -> bool:
        self._decrypt_fields()
        try:
            import aiohttp
        except ImportError:
            return False
        try:
            auth = None
            if self.config.shelly_auth_key:
                auth = aiohttp.BasicAuth('admin', self.config.shelly_auth_key)
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f'http://{self.config.ip}/rpc/Switch.Set',
                    json={"id": 0, "on": turn_on}, auth=auth, timeout=5
                ) as resp:
                    return resp.status == 200
        except Exception:
            return False

    async def rediscover_ip(self) -> Optional[str]:
        return ActuatorDiscovery.discover_ip_by_mac(self.config.mac)


# ============================================================================
# Tasmota Actuator
# ============================================================================

class TasmotaActuator(BaseActuator):
    """Tasmota via HTTP API."""

    def __init__(self, config: ActuatorConfig):
        self.config = config
        self.encryption = get_encryption()

    def _decrypt_fields(self):
        self.config.ip = self.encryption.decrypt(self.config.ip)
        if self.config.tasmota_username:
            self.config.tasmota_username = self.encryption.decrypt(self.config.tasmota_username)
        if self.config.tasmota_password:
            self.config.tasmota_password = self.encryption.decrypt(self.config.tasmota_password)

    async def test_connection(self) -> bool:
        self._decrypt_fields()
        try:
            import aiohttp
        except ImportError:
            return ActuatorDiscovery.ping_host(self.config.ip)
        try:
            auth = None
            if self.config.tasmota_username and self.config.tasmota_password:
                auth = aiohttp.BasicAuth(self.config.tasmota_username, self.config.tasmota_password)
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f'http://{self.config.ip}/cm?cmnd=Status%200', auth=auth, timeout=5
                ) as resp:
                    return resp.status == 200
        except Exception:
            return ActuatorDiscovery.ping_host(self.config.ip)

    async def get_status(self) -> Optional[bool]:
        self._decrypt_fields()
        try:
            import aiohttp
        except ImportError:
            return None
        try:
            auth = None
            if self.config.tasmota_username and self.config.tasmota_password:
                auth = aiohttp.BasicAuth(self.config.tasmota_username, self.config.tasmota_password)
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f'http://{self.config.ip}/cm?cmnd=Power', auth=auth, timeout=5
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get('POWER', 'OFF') == 'ON'
        except Exception:
            pass
        return None

    async def set_state(self, turn_on: bool) -> bool:
        self._decrypt_fields()
        try:
            import aiohttp
        except ImportError:
            return False
        try:
            auth = None
            if self.config.tasmota_username and self.config.tasmota_password:
                auth = aiohttp.BasicAuth(self.config.tasmota_username, self.config.tasmota_password)
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f'http://{self.config.ip}/cm?cmnd=Power%20{"On" if turn_on else "Off"}',
                    auth=auth, timeout=5
                ) as resp:
                    return resp.status == 200
        except Exception:
            return False

    async def rediscover_ip(self) -> Optional[str]:
        return ActuatorDiscovery.discover_ip_by_mac(self.config.mac)


# ============================================================================
# MQTT Actuator
# ============================================================================

class MQTTActuator(BaseActuator):
    """Generic MQTT actuator."""

    def __init__(self, config: ActuatorConfig):
        self.config = config
        self.encryption = get_encryption()
        self._client = None

    def _decrypt_fields(self):
        self.config.mqtt_broker = self.encryption.decrypt(self.config.mqtt_broker)
        self.config.mqtt_topic = self.encryption.decrypt(self.config.mqtt_topic)
        if self.config.mqtt_username:
            self.config.mqtt_username = self.encryption.decrypt(self.config.mqtt_username)
        if self.config.mqtt_password:
            self.config.mqtt_password = self.encryption.decrypt(self.config.mqtt_password)

    def _get_client(self):
        if self._client is None:
            try:
                import paho.mqtt.client as mqtt
            except ImportError:
                return None
            self._decrypt_fields()
            self._client = mqtt.Client()
            if self.config.mqtt_username and self.config.mqtt_password:
                self._client.username_pw_set(self.config.mqtt_username, self.config.mqtt_password)
            self._client.connect(self.config.mqtt_broker, 1883, 60)
            self._client.loop_start()
        return self._client

    async def test_connection(self) -> bool:
        client = self._get_client()
        return client is not None and client.is_connected()

    async def get_status(self) -> Optional[bool]:
        # MQTT is async - status comes via subscription
        # For now return None, real implementation would subscribe to status topic
        return None

    async def set_state(self, turn_on: bool) -> bool:
        client = self._get_client()
        if not client or not client.is_connected():
            return False
        try:
            payload = "ON" if turn_on else "OFF"
            result = client.publish(self.config.mqtt_topic, payload, qos=1, retain=True)
            return result.rc == 0
        except Exception:
            return False

    async def rediscover_ip(self) -> Optional[str]:
        return None  # MQTT doesn't use IP discovery


# ============================================================================
# HTTP Actuator
# ============================================================================

class HTTPActuator(BaseActuator):
    """Generic HTTP REST actuator."""

    def __init__(self, config: ActuatorConfig):
        self.config = config
        self.encryption = get_encryption()

    def _decrypt_fields(self):
        self.config.ip = self.encryption.decrypt(self.config.ip)
        self.config.http_on_url = self.encryption.decrypt(self.config.http_on_url)
        self.config.http_off_url = self.encryption.decrypt(self.config.http_off_url)
        self.config.http_status_url = self.encryption.decrypt(self.config.http_status_url)
        # Decrypt headers
        for k, v in self.config.http_headers.items():
            self.config.http_headers[k] = self.encryption.decrypt(v)

    async def test_connection(self) -> bool:
        self._decrypt_fields()
        try:
            import aiohttp
        except ImportError:
            return ActuatorDiscovery.ping_host(self.config.ip)
        if not self.config.http_status_url:
            return False
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.config.http_status_url,
                                       headers=self.config.http_headers, timeout=5) as resp:
                    return resp.status == 200
        except Exception:
            return ActuatorDiscovery.ping_host(self.config.ip)

    async def get_status(self) -> Optional[bool]:
        self._decrypt_fields()
        if not self.config.http_status_url:
            return None
        try:
            import aiohttp
        except ImportError:
            return None
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.config.http_status_url,
                                       headers=self.config.http_headers, timeout=5) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        # Assume JSON with "state" or "on" field
                        return data.get('state') or data.get('on')
        except Exception:
            pass
        return None

    async def set_state(self, turn_on: bool) -> bool:
        self._decrypt_fields()
        url = self.config.http_on_url if turn_on else self.config.http_off_url
        if not url:
            return False
        try:
            import aiohttp
        except ImportError:
            return False
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=self.config.http_headers, timeout=5) as resp:
                    return resp.status == 200
        except Exception:
            return False

    async def rediscover_ip(self) -> Optional[str]:
        return None


# ============================================================================
# GPIO Actuator (Raspberry Pi local)
# ============================================================================

class GPIOActuator(BaseActuator):
    """Local GPIO actuator for Raspberry Pi."""

    def __init__(self, config: ActuatorConfig):
        self.config = config

    async def test_connection(self) -> bool:
        return self.config.gpio_pin >= 0

    async def get_status(self) -> Optional[bool]:
        if self.config.gpio_pin < 0:
            return None
        try:
            # Read sysfs GPIO
            with open(f'/sys/class/gpio/gpio{self.config.gpio_pin}/value', 'r') as f:
                val = int(f.read().strip())
            return bool(val ^ self.config.gpio_active_low)
        except Exception:
            return None

    async def set_state(self, turn_on: bool) -> bool:
        if self.config.gpio_pin < 0:
            return False
        try:
            val = 1 if (turn_on ^ self.config.gpio_active_low) else 0
            with open(f'/sys/class/gpio/gpio{self.config.gpio_pin}/value', 'w') as f:
                f.write(str(val))
            return True
        except Exception:
            return False

    async def rediscover_ip(self) -> Optional[str]:
        return None


# ============================================================================
# Actuator Factory
# ============================================================================

def create_actuator(config: ActuatorConfig) -> BaseActuator:
    """Factory to create actuator by type."""
    type_map = {
        'tuya': TuyaActuator,
        'sonoff': SonoffActuator,
        'shelly': ShellyActuator,
        'tasmota': TasmotaActuator,
        'mqtt': MQTTActuator,
        'http': HTTPActuator,
        'gpio': GPIOActuator,
    }
    actuator_class = type_map.get(config.type.lower())
    if not actuator_class:
        raise ValueError(f"Unknown actuator type: {config.type}")
    return actuator_class(config)


# ============================================================================
# Actuator Engine
# ============================================================================

@dataclass
class ActuatorInstance:
    """Runtime actuator instance."""
    config: ActuatorConfig
    actuator: BaseActuator
    last_state: Optional[bool] = None
    is_online: bool = True
    last_seen: Optional[datetime] = None


class ActuatorEngine:
    """
    Manages actuators, listens for WS commands, executes hardware control.
    """
    def __init__(self, ws_manager=None):
        self.ws_manager = ws_manager
        self._running = False
        self._listener_task: Optional[asyncio.Task] = None
        self.actuators: Dict[str, ActuatorInstance] = {}
        self._command_queue: asyncio.Queue = asyncio.Queue()

    async def initialize(self):
        """Load actuators from DB."""
        from app.core.database import get_db
        from app.models.models import Actuator, ActuatorBinding
        from sqlalchemy import select

        async for db in get_db():
            result = await db.execute(
                select(Actuator).where(Actuator.is_enabled == True)
            )
            actuators = result.scalars().all()

            for act in actuators:
                await self._load_actuator(db, act)

            # Load bindings
            await self._load_bindings(db)
            break

    async def _load_actuator(self, db, act: Actuator):
        """Load single actuator from DB."""
        cfg = act.config or {}
        config = ActuatorConfig(
            id=act.id,
            name=act.name,
            type=act.type,
            ip=cfg.get('ip', ''),
            device_id=cfg.get('device_id', ''),
            local_key=cfg.get('local_key', ''),
            mac=cfg.get('mac', ''),
            port=cfg.get('port', 6668),
            version=cfg.get('version', 3.4),
            sonoff_apikey=cfg.get('sonoff_apikey', ''),
            shelly_auth_key=cfg.get('shelly_auth_key', ''),
            tasmota_username=cfg.get('tasmota_username', ''),
            tasmota_password=cfg.get('tasmota_password', ''),
            mqtt_topic=cfg.get('mqtt_topic', ''),
            mqtt_broker=cfg.get('mqtt_broker', ''),
            mqtt_username=cfg.get('mqtt_username', ''),
            mqtt_password=cfg.get('mqtt_password', ''),
            http_on_url=cfg.get('http_on_url', ''),
            http_off_url=cfg.get('http_off_url', ''),
            http_status_url=cfg.get('http_status_url', ''),
            http_headers=cfg.get('http_headers', {}),
            gpio_pin=cfg.get('gpio_pin', -1),
            gpio_active_low=cfg.get('gpio_active_low', False),
        )
        try:
            actuator = create_actuator(config)
            instance = ActuatorInstance(config=config, actuator=actuator)
            self.actuators[act.id] = instance
            logger.info(f"Loaded actuator: {act.name} ({act.type})")
        except Exception as e:
            logger.error(f"Failed to load actuator {act.name}: {e}")

    async def _load_bindings(self, db):
        """Load camera -> actuator bindings."""
        from app.models.models import ActuatorBinding
        from sqlalchemy import select

        result = await db.execute(
            select(ActuatorBinding).where(ActuatorBinding.is_active == True)
        )
        bindings = result.scalars().all()

        for binding in bindings:
            cam_id = str(binding.camera_id)
            act_id = str(binding.actuator_id)
            if cam_id not in self._camera_bindings:
                self._camera_bindings[cam_id] = []
            self._camera_bindings[cam_id].append(act_id)

    _camera_bindings: Dict[str, List[str]] = {}

    def start(self):
        """Start actuator engine - listen for WS commands."""
        if self._running:
            return
        self._running = True
        self._listener_task = asyncio.create_task(self._command_worker())
        logger.info("ActuatorEngine started")

    def stop(self):
        self._running = False
        if self._listener_task:
            self._listener_task.cancel()

    async def _command_worker(self):
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

    async def queue_command(self, actuator_id: str, action: str, alarm_id: Optional[str] = None):
        """Queue actuator command from WS event."""
        await self._command_queue.put({
            "actuator_id": actuator_id,
            "action": action,  # "on" or "off"
            "alarm_id": alarm_id,
            "timestamp": datetime.utcnow().isoformat()
        })

    async def _process_command(self, command_data: Dict[str, Any]):
        """Execute single actuator command."""
        actuator_id = command_data["actuator_id"]
        action = command_data["action"]  # "on" or "off"
        alarm_id = command_data.get("alarm_id")

        instance = self.actuators.get(actuator_id)
        if not instance:
            logger.warning(f"Actuator {actuator_id} not found")
            return

        try:
            # Execute with retries
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    success = await instance.actuator.set_state(action == "on")
                    if success:
                        # Update last state
                        instance.last_state = (action == "on")
                        instance.last_seen = datetime.utcnow()
                        instance.is_online = True

                        # Persist to DB
                        await self._update_db_state(actuator_id, action == "on", alarm_id)

                        # Broadcast state change via WS
                        if self.ws_manager and instance.config.id:
                            await self.ws_manager.broadcast(str(instance.config.id), {
                                "type": "actuator.status",
                                "payload": {
                                    "actuator_id": actuator_id,
                                    "name": instance.config.name,
                                    "state": action == "on",
                                    "timestamp": datetime.utcnow().isoformat()
                                }
                            })
                        logger.info(f"Actuator {instance.config.name} -> {action.upper()}")
                        return
                except Exception as e:
                    logger.warning(f"Actuator {actuator_id} attempt {attempt+1} failed: {e}")
                    if attempt < max_retries - 1:
                        # Try IP rediscovery for Tuya
                        if instance.config.type == 'tuya':
                            new_ip = await instance.actuator.rediscover_ip()
                            if new_ip:
                                instance.config.ip = new_ip
                                logger.info(f"Rediscovered IP for {instance.config.name}: {new_ip}")
                        await asyncio.sleep(1 * (attempt + 1))

            # All retries failed
            instance.is_online = False
            logger.error(f"Actuator {actuator_id} {action} failed after {max_retries} attempts")

            if alarm_id and self.ws_manager:
                await self.ws_manager.broadcast(str(instance.config.id), {
                    "type": "actuator.command",
                    "payload": {
                        "actuator_id": actuator_id,
                        "action": action,
                        "alarm_id": alarm_id,
                        "success": False,
                        "error": "Max retries exceeded"
                    }
                })

        except Exception as e:
            logger.error(f"Error processing command for {actuator_id}: {e}")

    async def _update_db_state(self, actuator_id: str, is_on: bool, alarm_id: Optional[str]):
        """Update actuator state in database."""
        from app.core.database import get_db
        from app.models.models import Actuator, Alarm
        from sqlalchemy import update

        async for db in get_db():
            await db.execute(
                update(Actuator)
                .where(Actuator.id == actuator_id)
                .values(last_status=is_on, last_seen=datetime.utcnow())
            )
            if alarm_id:
                await db.execute(
                    update(Alarm)
                    .where(Alarm.id == alarm_id)
                    .values(alarm_metadata={"actuator_triggered": True})
                )
            await db.commit()
            break

    async def handle_ws_message(self, message: dict):
        """Handle incoming WS message (called by Redis listener)."""
        if message.get("type") == "actuator.command":
            payload = message.get("payload", {})
            actuator_id = payload.get("actuator_id")
            action = payload.get("action")
            alarm_id = payload.get("alarm_id")
            if actuator_id and action in ("on", "off"):
                await self.queue_command(actuator_id, action, alarm_id)

    async def get_all_stats(self) -> List[Dict[str, Any]]:
        """Get stats for all actuators."""
        stats = []
        for act_id, instance in self.actuators.items():
            stats.append({
                "actuator_id": act_id,
                "name": instance.config.name,
                "type": instance.config.type,
                "is_online": instance.is_online,
                "last_state": instance.last_state,
                "last_seen": instance.last_seen.isoformat() if instance.last_seen else None,
            })
        return stats


# Global instance
_actuator_engine: Optional[ActuatorEngine] = None


async def get_actuator_engine(ws_manager=None) -> ActuatorEngine:
    """Get or create actuator engine."""
    global _actuator_engine
    if _actuator_engine is None:
        _actuator_engine = ActuatorEngine(ws_manager)
        await _actuator_engine.initialize()
        _actuator_engine.start()
    return _actuator_engine


async def close_actuator_engine():
    global _actuator_engine
    if _actuator_engine:
        _actuator_engine.stop()
        _actuator_engine = None