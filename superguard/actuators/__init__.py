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

Key features:
- Thread-safe operations (per-actuator locks)
- Local Tuya control via tinytuya with ARP-based IP rediscovery on DHCP renew
- Cloud Tuya control via Tuya Cloud API (works from anywhere)
- Automatic retry with IP rediscovery on connection failures
- Per-camera actuator bindings (many-to-many)
- Persistent binding storage in SettingsStore
"""

import threading
import time
import json
import hmac
import hashlib
import requests
from abc import ABC, abstractmethod
from typing import Dict, Type, Optional, Any, List
from dataclasses import dataclass

from ..config import TuyaPlugConfig, SuperGuardConfig


# ============================================================================
# BASE ACTUATOR
# ============================================================================

class BaseActuator(ABC):
    """Abstract base class for all actuators (switches, relays, lights, sirens, etc.).
    
    Defines the standard interface that all actuator implementations must provide.
    Each actuator runs in its own thread context, so implementations should be
    thread-safe or use the provided _lock.
    
    Attributes:
        config: Raw configuration dict passed at creation
        name: Human-readable name (from config["name"])
        _lock: Threading lock for thread-safe operations
        _last_status: Cached last known ON/OFF status
        _last_power: Cached last known power reading (watts)
    """
    
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
        """Check if actuator is responsive. Default: try get_status.
        
        Returns:
            True if get_status() succeeds (doesn't raise), False otherwise
        """
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
    """Singleton registry for actuator types.
    
    Maps string type names (e.g., "tuya", "tuya_cloud") to actuator classes.
    Thread-safe registration and lookup.
    
    Usage:
        ActuatorRegistry.register("tuya", TuyaActuator)
        actuator = ActuatorRegistry.create("tuya", config_dict)
    """
    
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
        """Register an actuator type by name.
        
        Args:
            name: Type identifier (lowercase, e.g., "tuya", "sonoff")
            actuator_class: Class inheriting from BaseActuator
        """
        instance = cls()
        with instance._lock:
            instance._actuators[name.lower()] = actuator_class
    
    @classmethod
    def get(cls, name: str) -> Optional[Type[BaseActuator]]:
        """Get actuator class by name.
        
        Args:
            name: Type identifier (case-insensitive)
            
        Returns:
            Actuator class or None if not registered
        """
        instance = cls()
        return instance._actuators.get(name.lower())
    
    @classmethod
    def create(cls, name: str, config: Dict[str, Any]) -> BaseActuator:
        """Create actuator instance by type name.
        
        Args:
            name: Registered type name
            config: Configuration dict for actuator constructor
            
        Returns:
            Actuator instance
            
        Raises:
            ValueError: If type name not registered
        """
        actuator_class = cls.get(name)
        if not actuator_class:
            raise ValueError(f"Unknown actuator type: {name}")
        return actuator_class(config)
    
    @classmethod
    def list_types(cls) -> List[str]:
        """List registered actuator type names."""
        instance = cls()
        return list(instance._actuators.keys())


# Global registry instance
actuator_registry = ActuatorRegistry()


# ============================================================================
# TUYA ACTUATOR (Cloud Control via Tuya Cloud API)
# ============================================================================

class TuyaCloudActuator(BaseActuator):
    """Tuya Smart Plug actuator using Tuya Cloud API (works from anywhere, no local IP needed).
    
    Uses Tuya IoT Platform Cloud API with HMAC-SHA256 signatures.
    Requires: device_id, access_id, access_secret from Tuya Cloud project.
    
    Advantages:
    - Works from any network (no local connectivity needed)
    - Can control plugs when away from home network
    - Provides power/energy monitoring via cloud
    
    Disadvantages:
    - Requires internet connectivity
    - Rate limited by Tuya
    - Higher latency (cloud round-trip)
    - Currently returns error 1108 (project config issue)
    
    DPS (Data Point) codes for standard Tuya plugs:
    - DPS_RELAY = "1": Relay switch (boolean)
    - "cur_power": Current power in 0.1W units
    """
    
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
        """Generate HMAC-SHA256 signature for Tuya Cloud API.
        
        Signature = HMAC-SHA256(access_secret, access_id + timestamp)
        Returned as uppercase hex string.
        
        Args:
            t: Timestamp in milliseconds as string
            
        Returns:
            Uppercase hex signature
        """
        msg = f"{self.access_id}{t}".encode()
        key = self.access_secret.encode()
        return hmac.new(key, msg, hashlib.sha256).hexdigest().upper()
    
    def _get_token(self) -> bool:
        """Obtain access token from Tuya Cloud.
        
        Calls /v1.0/token with grant_type=1.
        Stores token and expiry (with 60s buffer).
        
        Returns:
            True if token obtained successfully
        """
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
        """Get authenticated headers, refreshing token if needed.
        
        Thread-safe token management. Refreshes if expired or missing.
        
        Returns:
            Headers dict with client_id, access_token, sign, t, sign_method
            or None if token acquisition failed
        """
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
        """Send command to device via Tuya Cloud API.
        
        Args:
            commands: List of {"code": dps_code, "value": value} dicts
            
        Returns:
            True if API returns success=true
        """
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
        """Get current relay status via Cloud API.
        
        Returns cached status if API unavailable.
        """
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
        """Get current power consumption in watts via Cloud API.
        
        Returns power in watts (API returns 0.1W units).
        """
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
    """Tuya Smart Plug actuator using local control (tinytuya 3.4+).
    
    Direct LAN control via Tuya's local protocol (encrypted with local_key).
    No internet required - works entirely on local network.
    
    Key features:
    - ARP-based IP rediscovery: On DHCP renew (mobile hotspot), discovers
      new IP by MAC address from ARP table
    - Automatic retry with IP rediscovery on connection failures
    - Thread-safe device connection management
    - Power/voltage monitoring via local DPS codes
    
    DPS codes for standard Tuya plugs (tinytuya uses integer DPS):
    - DPS_RELAY = 1: Relay switch (bool)
    - DPS_VOLTAGE = 20: Voltage (0.1V units)
    - DPS_POWER = 22: Power (0.1W units)
    - DPS_ENERGY = 23: Energy (Wh)
    
    Required config:
    - ip: Current IP address (may change on DHCP)
    - device_id: 20-char Tuya device ID
    - local_key: 16-char local encryption key
    - mac: MAC address for ARP rediscovery (format: aa:bb:cc:dd:ee:ff)
    """
    
    # DPS codes for standard Tuya plugs (integer for tinytuya)
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
        # MAC address for ARP-based IP discovery on DHCP renew
        self.mac = config.get("mac", "").lower()
        
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
        """Get or create Tuya device with fresh connection.
        
        Lazy initialization with ARP-based IP discovery:
        1. If device exists, return it
        2. If MAC configured, try ARP discovery for current IP
        3. Create new tinytuya.OutletDevice with current IP
        4. Configure socket: non-persistent, timeout
        
        Thread-safe via _conn_lock.
        """
        import tinytuya
        with self._conn_lock:
            if self._device is None:
                # Try to discover IP if current one doesn't work
                if self.mac:
                    discovered_ip = self._discover_ip_by_mac()
                    if discovered_ip and discovered_ip != self.ip:
                        print(f"  ARP discovery: {self.name} IP changed from {self.ip} to {discovered_ip}")
                        self.ip = discovered_ip
                
                self._device = tinytuya.OutletDevice(
                    dev_id=self.device_id,
                    address=self.ip,
                    local_key=self.local_key,
                    version=self.version
                )
                self._device.set_socketPersistent(False)
                self._device.set_socketTimeout(self.connection_timeout)
            return self._device
    
    def _discover_ip_by_mac(self) -> Optional[str]:
        """Discover current IP address of the plug by MAC address from ARP table.
        
        Runs `arp -a` and parses output for the configured MAC.
        Works on Windows and Linux (different output formats).
        
        Windows format: "  192.168.137.113       d8-c8-0c-d6-45-6c     dynamic"
        Linux format:   "? (192.168.137.113) at d8:c8:0c:d6:45:6c [ether] on eth0"
        
        Returns:
            IP address as string, or None if not found
        """
        if not self.mac:
            return None
        
        try:
            import subprocess
            import re
        
            # Get ARP table
            result = subprocess.run(["arp", "-a"], capture_output=True, text=True, timeout=5)
            if result.returncode != 0:
                return None
        
            # Parse ARP table for our MAC
            # Normalize MAC to lowercase with hyphens (Windows format)
            mac_normalized = self.mac.replace(":", "-").lower()
        
            for line in result.stdout.split("\n"):
                if mac_normalized in line.lower():
                    # Extract IP from line (first IPv4 pattern)
                    ip_match = re.search(r"(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})", line)
                    if ip_match:
                        return ip_match.group(1)
        
            return None
        except Exception as e:
            print(f"  ARP discovery error for {self.name}: {e}")
            return None
    
    def _execute_with_retry(self, func, max_retries=2):
        """Execute a function with retry on connection failure.
        
        On connection error (timeout, socket error, unreachable, refused):
        1. Attempt ARP rediscovery if MAC available
        2. If new IP found, update self.ip and force new device creation
        3. Retry (up to max_retries times)
        
        Args:
            func: Callable to execute (turn_on, turn_off, get_status, etc.)
            max_retries: Maximum retry attempts (default 2 = 3 total tries)
            
        Returns:
            Function result on success
            
        Raises:
            Last exception if all retries exhausted
        """
        last_error = None
        for attempt in range(max_retries + 1):
            try:
                return func()
            except Exception as e:
                last_error = e
                # Check if it's a connection error
                error_str = str(e).lower()
                if any(keyword in error_str for keyword in ["connection", "timeout", "socket", "unreachable", "refused"]):
                    if self.mac and attempt < max_retries:
                        print(f"  Connection error, attempting ARP rediscovery for {self.name} (attempt {attempt + 1}/{max_retries})")
                        discovered_ip = self._discover_ip_by_mac()
                        if discovered_ip and discovered_ip != self.ip:
                            print(f"  ARP discovery: {self.name} IP changed from {self.ip} to {discovered_ip}")
                            self.ip = discovered_ip
                            # Force new device creation on next call
                            with self._conn_lock:
                                self._device = None
                            continue
                if attempt == max_retries:
                    raise
        raise last_error
    
    def turn_on(self) -> bool:
        """Turn the plug ON via local control with retry."""
        def _do():
            device = self._get_device()
            result = device.set_status(True, self.DPS_RELAY)
            if result:
                self._last_status = True
            return bool(result)
        return self._execute_with_retry(_do)
    
    def turn_off(self) -> bool:
        """Turn the plug OFF via local control with retry."""
        def _do():
            device = self._get_device()
            result = device.set_status(False, self.DPS_RELAY)
            if result:
                self._last_status = False
            return bool(result)
        return self._execute_with_retry(_do)
    
    def get_status(self) -> bool:
        """Get current relay status via local control with retry."""
        def _do():
            device = self._get_device()
            status = device.status()
            if status and "dps" in status:
                relay_state = status["dps"].get(str(self.DPS_RELAY), False)
                self._last_status = bool(relay_state)
                return bool(relay_state)
            return self._last_status if self._last_status is not None else False
        return self._execute_with_retry(_do)
    
    def get_power(self) -> Optional[float]:
        """Get current power consumption in watts via local control with retry."""
        def _do():
            device = self._get_device()
            status = device.status()
            if status and "dps" in status:
                power_raw = status["dps"].get(str(self.DPS_POWER), 0)
                return float(power_raw) / 10.0
            return None
        return self._execute_with_retry(_do)
    
    def get_voltage(self) -> Optional[float]:
        """Get current voltage in volts via local control with retry."""
        def _do():
            device = self._get_device()
            status = device.status()
            if status and "dps" in status:
                voltage_raw = status["dps"].get(str(self.DPS_VOLTAGE), 0)
                return float(voltage_raw) / 10.0
            return None
        return self._execute_with_retry(_do)


# Auto-register
actuator_registry.register("tuya", TuyaActuator)
actuator_registry.register("tinytuya", TuyaActuator)


# ============================================================================
# ACTUATOR MANAGER
# ============================================================================

class ActuatorManager:
    """Manages multiple actuators and their camera bindings.
    
    Responsibilities:
    - Instantiate actuators from config (via ActuatorRegistry)
    - Manage many-to-many camera <-> actuator bindings
    - Persist bindings to SettingsStore (camera_actuator_bindings)
    - Provide ON/OFF control for all actuators bound to a camera
    - Health checking and status reporting
    
    Binding flow:
    1. Config defines actuator.cameras = [1,2,3] (which cameras this plug serves)
    2. On init, _load_camera_bindings() reads persisted bindings from SettingsStore
    3. If no persisted bindings, auto-creates from actuator.cameras config
    4. User can modify via /plug command -> set_camera_binding() -> persists
    5. On alarm: set_actuators(True, cam_id) turns ON all bound actuators
    """
    
    def __init__(self, config: SuperGuardConfig):
        self.config = config
        self._actuators: Dict[str, BaseActuator] = {}
        self._camera_bindings: Dict[int, List[str]] = {}  # cam_id -> [actuator_names]
        self._lock = threading.Lock()
        
        # Initialize actuators from config
        self._init_actuators()
    
    @property
    def actuators(self) -> Dict[str, BaseActuator]:
        """Get all actuators (for testing/debugging)."""
        return self._actuators
    
    @property
    def camera_bindings(self) -> Dict[int, List[str]]:
        """Get camera-actuator bindings (for testing/debugging)."""
        return self._camera_bindings
    
    def _init_actuators(self):
        """Initialize all actuators from config.
        
        Iterates config.actuators (list of TuyaPlugConfig), creates each
        via ActuatorRegistry.create(type, config_dict).
        Then loads camera bindings from persistent storage.
        """
        if not self.config.actuators:
            return
        
        for act_cfg in self.config.actuators:
            try:
                actuator = actuator_registry.create(act_cfg.type, act_cfg.__dict__)
                self._actuators[act_cfg.name] = actuator
                print(f"  Initialized actuator: {act_cfg.name} ({act_cfg.type})")
            except Exception as e:
                print(f"  Failed to init actuator {act_cfg.name}: {e}")
        
        # Load camera bindings from settings
        self._load_camera_bindings()
    
    def _load_camera_bindings(self):
        """Load camera-actuator bindings from persistent settings.
        
        Reads camera_actuator_bindings from SettingsStore.
        Keys are camera IDs (stored as strings in JSON, converted to int).
        
        If no bindings found, AUTO-INITIALIZES from actuator config's 'cameras' field:
        - For each actuator, for each camera in actuator.cameras
        - Creates binding: cam_id -> [actuator_name, ...]
        - Saves to persistent storage
        """
        try:
            from ..storage import SettingsStore
            store = SettingsStore(self.config)
            settings = store.load()
            bindings = settings.get("camera_actuator_bindings", {})
            # Convert string keys to int
            self._camera_bindings = {int(k): v for k, v in bindings.items()}
        except Exception:
            self._camera_bindings = {}
        
        # If no bindings in settings, initialize from actuator config's 'cameras' field
        if not self._camera_bindings:
            for act_cfg in self.config.actuators:
                for cam_id in act_cfg.cameras:
                    if cam_id not in self._camera_bindings:
                        self._camera_bindings[cam_id] = []
                    if act_cfg.name not in self._camera_bindings[cam_id]:
                        self._camera_bindings[cam_id].append(act_cfg.name)
            # Save initial bindings
            self._save_camera_bindings()
    
    def _save_camera_bindings(self):
        """Save camera-actuator bindings to persistent settings.
        
        Writes camera_actuator_bindings to SettingsStore.
        Keys converted to strings for JSON compatibility.
        Uses force_flush() for immediate write (atomic tmp+replace).
        """
        try:
            from ..storage import SettingsStore
            store = SettingsStore(self.config)
            settings = store.load()
            settings["camera_actuator_bindings"] = {str(k): v for k, v in self._camera_bindings.items()}
            store.force_flush()
        except Exception as e:
            print(f"  Failed to save camera bindings: {e}")
    
    def set_camera_binding(self, cam_id: int, actuator_names: List[str]):
        """Set actuator binding for a camera and persist.
        
        Args:
            cam_id: Camera ID
            actuator_names: List of actuator names to bind (empty = unbind all)
        """
        with self._lock:
            self._camera_bindings[cam_id] = actuator_names
            self._save_camera_bindings()
    
    def get_camera_bindings(self, cam_id: int) -> List[str]:
        """Get actuator names bound to a camera."""
        return self._camera_bindings.get(cam_id, [])
    
    def set_actuators(self, state: bool, cam_id: int) -> Dict[str, bool]:
        """Turn ON/OFF all actuators bound to a camera.
        
        Called by SuperGuardBot on alarm trigger (True) and cancel (False).
        
        Args:
            state: True = ON, False = OFF
            cam_id: Camera ID to control actuators for
            
        Returns:
            Dict of actuator_name -> success (bool)
        """
        actuators = self.get_camera_bindings(cam_id)
        results = {}
        for name in actuators:
            actuator = self._actuators.get(name)
            if actuator:
                try:
                    if state:
                        results[name] = actuator.turn_on()
                    else:
                        results[name] = actuator.turn_off()
                except Exception as e:
                    print(f"  Actuator {name} error: {e}")
                    results[name] = False
            else:
                results[name] = False
        return results
    
    def get_actuator(self, name: str) -> Optional[BaseActuator]:
        """Get actuator by name."""
        return self._actuators.get(name)
    
    def list_all(self) -> Dict[str, Dict]:
        """List all actuators with their status and power.
        
        Returns:
            Dict: name -> {type, status, power_w} or {error}
        """
        result = {}
        for name, actuator in self._actuators.items():
            try:
                status = actuator.get_status()
                power = actuator.get_power()
                result[name] = {
                    "type": type(actuator).__name__,
                    "status": status,
                    "power_w": power,
                }
            except Exception as e:
                result[name] = {"error": str(e)}
        return result
    
    def test_all(self) -> Dict[str, bool]:
        """Test all actuators (health check).
        
        Returns:
            Dict: name -> True/False (responsive)
        """
        results = {}
        for name, actuator in self._actuators.items():
            try:
                results[name] = actuator.health_check()
            except Exception:
                results[name] = False
        return results
    
    def get_for_camera(self, cam_id: int) -> List[BaseActuator]:
        """Get all actuator instances bound to a camera.
        
        Used by SuperGuardBot.set_actuators() for direct control.
        
        Args:
            cam_id: Camera ID
            
        Returns:
            List of BaseActuator instances
        """
        names = self.get_camera_bindings(cam_id)
        return [self._actuators[n] for n in names if n in self._actuators]


# Auto-register local Tuya
actuator_registry.register("tuya", TuyaActuator)
actuator_registry.register("tinytuya", TuyaActuator)