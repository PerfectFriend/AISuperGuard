"""
SuperGuard Alarm - Actuator Subsystem

Actuator abstraction layer supporting multiple device types:
- Tuya (local + cloud)
- Sonoff/Tasmota (HTTP + MQTT)
- Shelly Gen1/Gen2 (HTTP/CoAP/WS/MQTT)
- ESPHome (native API + MQTT)
- Zigbee (zigbee2mqtt/ZHA/deCONZ)

BaseActuator ABC defines the interface. Each implementation handles
its own protocol. ActuatorRegistry manages type registration and instantiation.
"""
import threading
import time
import json
from abc import ABC, abstractmethod
from typing import Dict, Type, Optional, Any, List
from dataclasses import dataclass

from ..config import TuyaPlugConfig, SuperGuardConfig


# ============================================================================
# BASE ACTUATOR
# ============================================================================

class BaseActuator(ABC):
    """Abstract base class for all actuators (switches, relays, lights, sirens, etc.)."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.name = config.get("name", "unknown")
        self._lock = threading.Lock()
        self._last_status: Optional[bool] = None
        self._last_power: Optional[float] = None
    
    @abstractmethod
    def turn_on(self) -> bool:
        """Turn the actuator ON. Returns True on success."""
        pass
    
    @abstractmethod
    def turn_off(self) -> bool:
        """Turn the actuator OFF. Returns True on success."""
        pass
    
    @abstractmethod
    def get_status(self) -> bool:
        """Get current status (True=ON, False=OFF)."""
        pass
    
    def get_power(self) -> Optional[float]:
        """Get power consumption in watts. Returns None if not supported."""
        return None
    
    def get_voltage(self) -> Optional[float]:
        """Get voltage in volts. Returns None if not supported."""
        return None
    
    def health_check(self) -> bool:
        """Check if actuator is responsive. Default: try get_status."""
        try:
            return self.get_status() is not None
        except Exception:
            return False
    
    def __repr__(self):
        return f"<{self.__class__.__name__} name={self.name}>"


# ============================================================================
# ACTUATOR REGISTRY
# ============================================================================

class ActuatorRegistry:
    """Singleton registry for actuator types."""
    
    _instance: Optional['ActuatorRegistry'] = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._actuators: Dict[str, Type[BaseActuator]] = {}
        return cls._instance
    
    @classmethod
    def register(cls, name: str, actuator_class: Type[BaseActuator]):
        """Register an actuator type by name."""
        instance = cls()
        with instance._lock:
            instance._actuators[name.lower()] = actuator_class
    
    @classmethod
    def get(cls, name: str) -> Optional[Type[BaseActuator]]:
        """Get actuator class by name."""
        instance = cls()
        return instance._actuators.get(name.lower())
    
    @classmethod
    def create(cls, name: str, config: Dict[str, Any]) -> BaseActuator:
        """Create actuator instance by type name."""
        actuator_class = cls.get(name)
        if not actuator_class:
            raise ValueError(f"Unknown actuator type: {name}")
        return actuator_class(config)
    
    @classmethod
    def list_types(cls) -> List[str]:
        """List registered actuator types."""
        instance = cls()
        return list(instance._actuators.keys())


# Global registry instance
actuator_registry = ActuatorRegistry()


# ============================================================================
# TUYA ACTUATOR (Cloud Control via Tuya Cloud API)
# ============================================================================

class TuyaCloudActuator(BaseActuator):
    """Tuya Smart Plug actuator using Tuya Cloud API (works from anywhere, no local IP needed)."""
    
    # Standard Tuya Cloud DPS codes
    DPS_RELAY = "1"      # Relay switch (bool)
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        
        # Required config (from Tuya Cloud project)
        self.device_id = config.get("device_id")
        self.access_id = config.get("access_id")
        self.access_secret = config.get("access_secret")
        self.region = config.get("region", "eu")
        
        if not all([self.device_id, self.access_id, self.access_secret]):
            raise ValueError("TuyaCloudActuator requires device_id, access_id, and access_secret in config")
        
        # Region endpoints
        self.REGION_URLS = {
            "cn": "https://openapi.tuyacn.com",
            "us": "https://openapi.tuyaus.com",
            "eu": "https://openapi.tuyaeu.com",
            "in": "https://openapi.tuyain.com",
        }
        self.base_url = self.REGION_URLS.get(self.region, "https://openapi.tuyaeu.com")
        
        # Auth state
        self._token: Optional[str] = None
        self._token_expire: float = 0
        self._lock = threading.Lock()
        
    def _get_sign(self, t: str) -> str:
        """Generate HMAC-SHA256 signature."""
        msg = f"{self.access_id}{t}".encode()
        key = self.access_secret.encode()
        return hmac.new(key, msg, hashlib.sha256).hexdigest().upper()
    
    def _get_token(self) -> bool:
        """Obtain access token from Tuya Cloud."""
        import time
        t = str(int(time.time() * 1000))
        sign = self._get_sign(t)
        headers = {
            "client_id": self.access_id,
            "sign": sign,
            "t": t,
            "sign_method": "HMAC-SHA256",
        }
        try:
            r = requests.post(f"{self.base_url}/v1.0/token?grant_type=1", 
                            headers=headers, timeout=10)
            if r.status_code == 200:
                data = r.json()
                if data.get("success"):
                    self._token = data["result"]["access_token"]
                    self._token_expire = time.time() + data["result"]["expire_time"] - 60
                    return True
        except Exception as e:
            print(f"  [TuyaCloudActuator] Token error: {e}")
        return False
    
    def _headers(self) -> Optional[Dict[str, str]]:
        """Get authenticated headers, refreshing token if needed."""
        import time
        with self._lock:
            if not self._token or time.time() >= self._token_expire:
                if not self._get_token():
                    return None
            t = str(int(time.time() * 1000))
            sign = self._get_sign(t)
            return {
                "client_id": self.access_id,
                "access_token": self._token,
                "sign": sign,
                "t": t,
                "sign_method": "HMAC-SHA256",
            }
    
    def _send_command(self, commands: List[Dict]) -> bool:
        """Send command to device via Tuya Cloud API."""
        headers = self._headers()
        if not headers:
            return False
        
        payload = {"commands": commands}
        try:
            r = requests.post(
                f"{self.base_url}/v1.0/devices/{self.device_id}/commands",
                headers=headers,
                json=payload,
                timeout=10
            )
            if r.status_code == 200:
                data = r.json()
                return data.get("success", False)
        except Exception as e:
            print(f"  [TuyaCloudActuator] Command error: {e}")
        return False
    
    def turn_on(self) -> bool:
        """Turn the plug ON via Cloud API."""
        result = self._send_command([{"code": self.DPS_RELAY, "value": True}])
        if result:
            self._last_status = True
        return result
    
    def turn_off(self) -> bool:
        """Turn the plug OFF via Cloud API."""
        result = self._send_command([{"code": self.DPS_RELAY, "value": False}])
        if result:
            self._last_status = False
        return result
    
    def get_status(self) -> bool:
        """Get current relay status via Cloud API."""
        headers = self._headers()
        if not headers:
            return self._last_status if self._last_status is not None else False
        
        try:
            r = requests.get(
                f"{self.base_url}/v1.0/devices/{self.device_id}/status",
                headers=headers,
                timeout=10
            )
            if r.status_code == 200:
                data = r.json()
                if data.get("success"):
                    for item in data["result"]:
                        if item.get("code") == self.DPS_RELAY:
                            status = bool(item.get("value", False))
                            self._last_status = status
                            return status
        except Exception as e:
            print(f"  [TuyaCloudActuator] Status error: {e}")
        return self._last_status if self._last_status is not None else False
    
    def get_power(self) -> Optional[float]:
        """Get current power consumption in watts via Cloud API."""
        headers = self._headers()
        if not headers:
            return None
        
        try:
            r = requests.get(
                f"{self.base_url}/v1.0/devices/{self.device_id}/status",
                headers=headers,
                timeout=10
            )
            if r.status_code == 200:
                data = r.json()
                if data.get("success"):
                    for item in data["result"]:
                        if item.get("code") == "cur_power":  # Power in 0.1W
                            return float(item.get("value", 0)) / 10.0
        except Exception as e:
            print(f"  [TuyaCloudActuator] Power error: {e}")
        return None


# Auto-register
actuator_registry.register("tuya_cloud", TuyaCloudActuator)
actuator_registry.register("tuya-cloud", TuyaCloudActuator)


# ============================================================================
# TUYA ACTUATOR (Local Control via tinytuya)
# ============================================================================

class TuyaActuator(BaseActuator):
    """Tuya Smart Plug actuator using local control (tinytuya 3.4+)."""
    
    # DPS codes for standard Tuya plugs
    DPS_RELAY = 1      # Relay (bool)
    DPS_VOLTAGE = 20   # Voltage (0.1V units)
    DPS_POWER = 22     # Power (0.1W units)
    DPS_ENERGY = 23    # Energy (Wh)
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        
        import tinytuya
        
        # Required config
        self.ip = config.get("ip")
        self.device_id = config.get("device_id")
        self.local_key = config.get("local_key")
        
        if not all([self.ip, self.device_id, self.local_key]):
            raise ValueError("TuyaActuator requires ip, device_id, and local_key in config")
        
        # Optional config
        self.port = config.get("port", 6668)
        self.version = config.get("version", 3.4)
        self.connection_timeout = config.get("connection_timeout", 5)
        
        # Internal state
        self._device: Optional[tinytuya.OutletDevice] = None
        self._conn_lock = threading.Lock()
    
    def _get_device(self):
        """Get or create Tuya device with fresh connection."""
        import tinytuya
        with self._conn_lock:
            if self._device is None:
                self._device = tinytuya.OutletDevice(
                    dev_id=self.device_id,
                    address=self.ip,
                    local_key=self.local_key,
                    version=self.version
                )
                self._device.set_socketPersistent(False)
                self._device.set_socketTimeout(self.connection_timeout)
            return self._device
    
    def _execute_with_retry(self, func, max_retries=2):
        """Execute Tuya command with retry on connection failure."""
        last_error = None
        for attempt in range(max_retries + 1):
            try:
                return func()
            except Exception as e:
                last_error = e
                if attempt < max_retries:
                    # Force new connection on next attempt
                    with self._conn_lock:
                        self._device = None
                    time.sleep(0.5)
                else:
                    raise
        raise last_error
    
    def turn_on(self) -> bool:
        """Turn the plug ON."""
        def _on():
            device = self._get_device()
            result = device.set_value(self.DPS_RELAY, True)
            return result
        
        try:
            result = self._execute_with_retry(_on)
            if result:
                self._last_status = True
            return bool(result)
        except Exception as e:
            print(f"TuyaActuator turn_on failed: {e}")
            return False
    
    def turn_off(self) -> bool:
        """Turn the plug OFF."""
        def _off():
            device = self._get_device()
            result = device.set_value(self.DPS_RELAY, False)
            return result
        
        try:
            result = self._execute_with_retry(_off)
            if result:
                self._last_status = False
            return bool(result)
        except Exception as e:
            print(f"TuyaActuator turn_off failed: {e}")
            return False
    
    def get_status(self) -> bool:
        """Get current relay status."""
        def _status():
            device = self._get_device()
            data = device.status()
            if data and "dps" in data:
                return bool(data["dps"].get(self.DPS_RELAY, False))
            return False
        
        try:
            status = self._execute_with_retry(_status)
            self._last_status = status
            return status
        except Exception as e:
            print(f"TuyaActuator get_status failed: {e}")
            return self._last_status if self._last_status is not None else False
    
    def get_power(self) -> Optional[float]:
        """Get current power consumption in watts."""
        def _power():
            device = self._get_device()
            data = device.status()
            if data and "dps" in data:
                raw_power = data["dps"].get(self.DPS_POWER)
                if raw_power is not None:
                    return float(raw_power) / 10.0
            return None
        
        try:
            power = self._execute_with_retry(_power)
            self._last_power = power
            return power
        except Exception as e:
            print(f"TuyaActuator get_power failed: {e}")
            return self._last_power
    
    def get_voltage(self) -> Optional[float]:
        """Get current voltage in volts."""
        def _voltage():
            device = self._get_device()
            data = device.status()
            if data and "dps" in data:
                raw_voltage = data["dps"].get(self.DPS_VOLTAGE)
                if raw_voltage is not None:
                    return float(raw_voltage) / 10.0
            return None
        
        try:
            return self._execute_with_retry(_voltage)
        except Exception as e:
            print(f"TuyaActuator get_voltage failed: {e}")
            return None
    
    def get_energy(self) -> Optional[float]:
        """Get total energy consumption in Wh."""
        def _energy():
            device = self._get_device()
            data = device.status()
            if data and "dps" in data:
                return float(data["dps"].get(self.DPS_ENERGY, 0))
            return None
        
        try:
            return self._execute_with_retry(_energy)
        except Exception as e:
            print(f"TuyaActuator get_energy failed: {e}")
            return None


# Auto-register
actuator_registry.register("tuya", TuyaActuator)


# ============================================================================
# ACTUATOR MANAGER
# ============================================================================

class ActuatorManager:
    """Manages actuator instances and camera-to-actuator bindings."""
    
    def __init__(self, config: SuperGuardConfig):
        self.config = config
        self.actuators: Dict[str, BaseActuator] = {}
        self.camera_bindings: Dict[int, List[str]] = {}  # cam_id -> actuator names
        self._init_from_config()
    
    def _init_from_config(self):
        """Initialize actuators from config and build camera bindings."""
        for plug_config in self.config.plugs:
            # Create actuator instance
            actuator_config = {
                "name": plug_config.name,
                "ip": plug_config.ip,
                "device_id": plug_config.device_id,
                "local_key": plug_config.local_key,
                "version": plug_config.version,
                "port": plug_config.port,
                # Cloud API fields (for tuya_cloud type)
                "access_id": plug_config.access_id,
                "access_secret": plug_config.access_secret,
                "region": plug_config.region,
            }
            
            try:
                actuator = actuator_registry.create(plug_config.type, actuator_config)
                self.actuators[plug_config.name] = actuator
                print(f"  Actuator '{plug_config.name}' ({plug_config.type}) initialized")
            except Exception as e:
                print(f"  Actuator '{plug_config.name}' init failed: {e}")
                continue
            
            # Build camera -> actuator mapping
            for cam_id in plug_config.cameras:
                self.camera_bindings.setdefault(cam_id, []).append(plug_config.name)
        
        print(f"  Camera->Actuator map: {self.camera_bindings}")
    
    def get_for_camera(self, cam_id: int) -> List[BaseActuator]:
        """Get all actuators bound to a camera."""
        names = self.camera_bindings.get(cam_id, [])
        return [self.actuators[name] for name in names if name in self.actuators]
    
    def get_actuator(self, name: str) -> Optional[BaseActuator]:
        """Get actuator by name."""
        return self.actuators.get(name)
    
    def set_camera_binding(self, cam_id: int, actuator_name: str):
        """Bind camera to actuator (updates runtime binding)."""
        if actuator_name not in self.actuators:
            raise ValueError(f"Actuator {actuator_name} not found")
        
        # Remove from other cameras
        for cid, names in self.camera_bindings.items():
            if actuator_name in names and cid != cam_id:
                self.camera_bindings[cid].remove(actuator_name)
        
        # Add to new camera
        self.camera_bindings.setdefault(cam_id, [])
        if actuator_name not in self.camera_bindings[cam_id]:
            self.camera_bindings[cam_id].append(actuator_name)
    
    def set_camera_bindings(self, cam_id: int, actuator_names: List[str]):
        """Replace the full actuator binding list for a camera.
        
        The camera will drive exactly these actuators on alarm.
        Bindings of other cameras are left untouched.
        """
        valid = [n for n in actuator_names if n in self.actuators]
        self.camera_bindings[cam_id] = valid
    
    def list_all(self) -> List[Dict]:
        """List all actuators with status and bound cameras."""
        result = []
        for name, actuator in self.actuators.items():
            # Find cameras bound to this actuator
            cams = [cid for cid, names in self.camera_bindings.items() if name in names]
            
            # Test status
            try:
                status = actuator.get_status() if hasattr(actuator, 'get_status') else True
                status_icon = "🟢" if status else "🔴"
                status_text = "ONLINE" if status else "OFFLINE"
            except Exception as e:
                status_icon = "🔴"
                status_text = f"ERROR: {e}"
            
            result.append({
                "name": name,
                "type": actuator.__class__.__name__,
                "status": status_text,
                "status_icon": status_icon,
                "cameras": cams,
            })
        return result
    
    def test_all(self) -> List[Dict]:
        """Test all actuators, auto-reconnect failed ones."""
        results = []
        for name, actuator in self.actuators.items():
            try:
                status = actuator.get_status()
                if status:
                    results.append({"name": name, "status": "OK", "reconnected": False})
                    continue
            except Exception as e:
                results.append({"name": name, "status": f"ERROR: {e}", "reconnected": False})
            
            # Try to reconnect by reinitializing
            # Find config for this actuator
            plug_config = next((p for p in self.config.plugs if p.name == name), None)
            if plug_config:
                try:
                    actuator_config = {
                        "name": plug_config.name,
                        "ip": plug_config.ip,
                        "device_id": plug_config.device_id,
                        "local_key": plug_config.local_key,
                        "version": plug_config.version,
                        "port": plug_config.port,
                    }
                    new_actuator = actuator_registry.create(plug_config.type, actuator_config)
                    self.actuators[name] = new_actuator
                    status = new_actuator.get_status()
                    if status:
                        results.append({"name": name, "status": "RECONNECTED", "reconnected": True})
                    else:
                        results.append({"name": name, "status": "FAILED", "reconnected": True})
                except Exception as e:
                    results.append({"name": name, "status": f"RECONNECT FAILED: {e}", "reconnected": True})
            else:
                results.append({"name": name, "status": "NO CONFIG", "reconnected": False})
        
        return results