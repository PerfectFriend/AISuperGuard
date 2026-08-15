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

class BaseActuator(ABC):

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.name = config.get('name', 'unknown')
        self._lock = threading.Lock()
        self._last_status: Optional[bool] = None
        self._last_power: Optional[float] = None

    @abstractmethod
    def turn_on(self) -> bool:
        pass

    @abstractmethod
    def turn_off(self) -> bool:
        pass

    @abstractmethod
    def get_status(self) -> bool:
        pass

    def get_power(self) -> Optional[float]:
        return None

    def get_voltage(self) -> Optional[float]:
        return None

    def health_check(self) -> bool:
        try:
            return self.get_status() is not None
        except Exception:
            return False

    def __repr__(self):
        return f'<{self.__class__.__name__} name={self.name}>'

class ActuatorRegistry:
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
        instance = cls()
        with instance._lock:
            instance._actuators[name.lower()] = actuator_class

    @classmethod
    def get(cls, name: str) -> Optional[Type[BaseActuator]]:
        instance = cls()
        return instance._actuators.get(name.lower())

    @classmethod
    def create(cls, name: str, config: Dict[str, Any]) -> BaseActuator:
        actuator_class = cls.get(name)
        if not actuator_class:
            raise ValueError(f'Unknown actuator type: {name}')
        return actuator_class(config)

    @classmethod
    def list_types(cls) -> List[str]:
        instance = cls()
        return list(instance._actuators.keys())
actuator_registry = ActuatorRegistry()

class TuyaCloudActuator(BaseActuator):
    DPS_RELAY = '1'

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.device_id = config.get('device_id')
        self.access_id = config.get('access_id')
        self.access_secret = config.get('access_secret')
        self.region = config.get('region', 'eu')
        if not all([self.device_id, self.access_id, self.access_secret]):
            raise ValueError('TuyaCloudActuator requires device_id, access_id, and access_secret in config')
        self.REGION_URLS = {'cn': 'https://openapi.tuyacn.com', 'us': 'https://openapi.tuyaus.com', 'eu': 'https://openapi.tuyaeu.com', 'in': 'https://openapi.tuyain.com'}
        self.base_url = self.REGION_URLS.get(self.region, 'https://openapi.tuyaeu.com')
        self._token: Optional[str] = None
        self._token_expire: float = 0
        self._lock = threading.Lock()

    def _get_sign(self, t: str) -> str:
        msg = f'{self.access_id}{t}'.encode()
        key = self.access_secret.encode()
        return hmac.new(key, msg, hashlib.sha256).hexdigest().upper()

    def _get_token(self) -> bool:
        import time
        t = str(int(time.time() * 1000))
        sign = self._get_sign(t)
        headers = {'client_id': self.access_id, 'sign': sign, 't': t, 'sign_method': 'HMAC-SHA256'}
        try:
            r = requests.post(f'{self.base_url}/v1.0/token?grant_type=1', headers=headers, timeout=10)
            if r.status_code == 200:
                data = r.json()
                if data.get('success'):
                    self._token = data['result']['access_token']
                    self._token_expire = time.time() + data['result']['expire_time'] - 60
                    return True
        except Exception as e:
            print(f'  [TuyaCloudActuator] Token error: {e}')
        return False

    def _headers(self) -> Optional[Dict[str, str]]:
        import time
        with self._lock:
            if not self._token or time.time() >= self._token_expire:
                if not self._get_token():
                    return None
            t = str(int(time.time() * 1000))
            sign = self._get_sign(t)
            return {'client_id': self.access_id, 'access_token': self._token, 'sign': sign, 't': t, 'sign_method': 'HMAC-SHA256'}

    def _send_command(self, commands: List[Dict]) -> bool:
        headers = self._headers()
        if not headers:
            return False
        payload = {'commands': commands}
        try:
            r = requests.post(f'{self.base_url}/v1.0/devices/{self.device_id}/commands', headers=headers, json=payload, timeout=10)
            if r.status_code == 200:
                data = r.json()
                return data.get('success', False)
        except Exception as e:
            print(f'  [TuyaCloudActuator] Command error: {e}')
        return False

    def turn_on(self) -> bool:
        result = self._send_command([{'code': self.DPS_RELAY, 'value': True}])
        if result:
            self._last_status = True
        return result

    def turn_off(self) -> bool:
        result = self._send_command([{'code': self.DPS_RELAY, 'value': False}])
        if result:
            self._last_status = False
        return result

    def get_status(self) -> bool:
        headers = self._headers()
        if not headers:
            return self._last_status if self._last_status is not None else False
        try:
            r = requests.get(f'{self.base_url}/v1.0/devices/{self.device_id}/status', headers=headers, timeout=10)
            if r.status_code == 200:
                data = r.json()
                if data.get('success'):
                    for item in data['result']:
                        if item.get('code') == self.DPS_RELAY:
                            status = bool(item.get('value', False))
                            self._last_status = status
                            return status
        except Exception as e:
            print(f'  [TuyaCloudActuator] Status error: {e}')
        return self._last_status if self._last_status is not None else False

    def get_power(self) -> Optional[float]:
        headers = self._headers()
        if not headers:
            return None
        try:
            r = requests.get(f'{self.base_url}/v1.0/devices/{self.device_id}/status', headers=headers, timeout=10)
            if r.status_code == 200:
                data = r.json()
                if data.get('success'):
                    for item in data['result']:
                        if item.get('code') == 'cur_power':
                            return float(item.get('value', 0)) / 10.0
        except Exception as e:
            print(f'  [TuyaCloudActuator] Power error: {e}')
        return None
actuator_registry.register('tuya_cloud', TuyaCloudActuator)
actuator_registry.register('tuya-cloud', TuyaCloudActuator)

class TuyaActuator(BaseActuator):
    DPS_RELAY = 1
    DPS_VOLTAGE = 20
    DPS_POWER = 22
    DPS_ENERGY = 23

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        import tinytuya
        self.ip = config.get('ip')
        self.device_id = config.get('device_id')
        self.local_key = config.get('local_key')
        self.mac = config.get('mac', '').lower()
        if not all([self.ip, self.device_id, self.local_key]):
            raise ValueError('TuyaActuator requires ip, device_id, and local_key in config')
        self.port = config.get('port', 6668)
        self.version = config.get('version', 3.4)
        self.connection_timeout = config.get('connection_timeout', 5)
        self._device: Optional[tinytuya.OutletDevice] = None
        self._conn_lock = threading.Lock()

    def _get_device(self):
        import tinytuya
        with self._conn_lock:
            if self._device is None:
                if self.mac:
                    discovered_ip = self._discover_ip_by_mac()
                    if discovered_ip and discovered_ip != self.ip:
                        print(f'  ARP discovery: {self.name} IP changed from {self.ip} to {discovered_ip}')
                        self.ip = discovered_ip
                self._device = tinytuya.OutletDevice(dev_id=self.device_id, address=self.ip, local_key=self.local_key, version=self.version)
                self._device.set_socketPersistent(False)
                self._device.set_socketTimeout(self.connection_timeout)
            return self._device

    def _discover_ip_by_mac(self) -> Optional[str]:
        if not self.mac:
            return None
        try:
            import subprocess
            import re
            result = subprocess.run(['arp', '-a'], capture_output=True, text=True, timeout=5)
            if result.returncode != 0:
                return None
            mac_normalized = self.mac.replace(':', '-').lower()
            for line in result.stdout.split('\n'):
                if mac_normalized in line.lower():
                    ip_match = re.search('(\\d{1,3}\\.\\d{1,3}\\.\\d{1,3}\\.\\d{1,3})', line)
                    if ip_match:
                        return ip_match.group(1)
            return None
        except Exception as e:
            print(f'  ARP discovery error for {self.name}: {e}')
            return None

    def _execute_with_retry(self, func, max_retries=2):
        last_error = None
        for attempt in range(max_retries + 1):
            try:
                return func()
            except Exception as e:
                last_error = e
                error_str = str(e).lower()
                if any((keyword in error_str for keyword in ['connection', 'timeout', 'socket', 'unreachable', 'refused'])):
                    if self.mac and attempt < max_retries:
                        print(f'  Connection error, attempting ARP rediscovery for {self.name} (attempt {attempt + 1}/{max_retries})')
                        discovered_ip = self._discover_ip_by_mac()
                        if discovered_ip and discovered_ip != self.ip:
                            print(f'  ARP discovery: {self.name} IP changed from {self.ip} to {discovered_ip}')
                            self.ip = discovered_ip
                            with self._conn_lock:
                                self._device = None
                            continue
                if attempt == max_retries:
                    raise
        raise last_error

    def turn_on(self) -> bool:

        def _do():
            device = self._get_device()
            result = device.set_status(True, self.DPS_RELAY)
            if result:
                self._last_status = True
            return bool(result)
        return self._execute_with_retry(_do)

    def turn_off(self) -> bool:

        def _do():
            device = self._get_device()
            result = device.set_status(False, self.DPS_RELAY)
            if result:
                self._last_status = False
            return bool(result)
        return self._execute_with_retry(_do)

    def get_status(self) -> bool:

        def _do():
            device = self._get_device()
            status = device.status()
            if status and 'dps' in status:
                relay_state = status['dps'].get(str(self.DPS_RELAY), False)
                self._last_status = bool(relay_state)
                return bool(relay_state)
            return self._last_status if self._last_status is not None else False
        return self._execute_with_retry(_do)

    def get_power(self) -> Optional[float]:

        def _do():
            device = self._get_device()
            status = device.status()
            if status and 'dps' in status:
                power_raw = status['dps'].get(str(self.DPS_POWER), 0)
                return float(power_raw) / 10.0
            return None
        return self._execute_with_retry(_do)

    def get_voltage(self) -> Optional[float]:

        def _do():
            device = self._get_device()
            status = device.status()
            if status and 'dps' in status:
                voltage_raw = status['dps'].get(str(self.DPS_VOLTAGE), 0)
                return float(voltage_raw) / 10.0
            return None
        return self._execute_with_retry(_do)
actuator_registry.register('tuya', TuyaActuator)
actuator_registry.register('tinytuya', TuyaActuator)

class ActuatorManager:

    def __init__(self, config: SuperGuardConfig):
        self.config = config
        self._actuators: Dict[str, BaseActuator] = {}
        self._camera_bindings: Dict[int, List[str]] = {}
        self._lock = threading.Lock()
        self._init_actuators()

    @property
    def actuators(self) -> Dict[str, BaseActuator]:
        return self._actuators

    @property
    def camera_bindings(self) -> Dict[int, List[str]]:
        return self._camera_bindings

    def _init_actuators(self):
        if not self.config.actuators:
            return
        for act_cfg in self.config.actuators:
            try:
                actuator = actuator_registry.create(act_cfg.type, act_cfg.__dict__)
                self._actuators[act_cfg.name] = actuator
                print(f'  Initialized actuator: {act_cfg.name} ({act_cfg.type})')
            except Exception as e:
                print(f'  Failed to init actuator {act_cfg.name}: {e}')
        self._load_camera_bindings()

    def _load_camera_bindings(self):
        try:
            from ..storage import SettingsStore
            store = SettingsStore(self.config)
            settings = store.load()
            bindings = settings.get('camera_actuator_bindings', {})
            self._camera_bindings = {int(k): v for k, v in bindings.items()}
        except Exception:
            self._camera_bindings = {}
        if not self._camera_bindings:
            for act_cfg in self.config.actuators:
                for cam_id in act_cfg.cameras:
                    if cam_id not in self._camera_bindings:
                        self._camera_bindings[cam_id] = []
                    if act_cfg.name not in self._camera_bindings[cam_id]:
                        self._camera_bindings[cam_id].append(act_cfg.name)
            self._save_camera_bindings()

    def _save_camera_bindings(self):
        try:
            from ..storage import SettingsStore
            store = SettingsStore(self.config)
            settings = store.load()
            settings['camera_actuator_bindings'] = {str(k): v for k, v in self._camera_bindings.items()}
            store.force_flush()
        except Exception as e:
            print(f'  Failed to save camera bindings: {e}')

    def set_camera_binding(self, cam_id: int, actuator_names: List[str]):
        with self._lock:
            self._camera_bindings[cam_id] = actuator_names
            self._save_camera_bindings()

    def get_camera_bindings(self, cam_id: int) -> List[str]:
        return self._camera_bindings.get(cam_id, [])

    def set_actuators(self, state: bool, cam_id: int) -> Dict[str, bool]:
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
                    print(f'  Actuator {name} error: {e}')
                    results[name] = False
            else:
                results[name] = False
        return results

    def get_actuator(self, name: str) -> Optional[BaseActuator]:
        return self._actuators.get(name)

    def list_all(self) -> Dict[str, Dict]:
        result = {}
        for name, actuator in self._actuators.items():
            try:
                status = actuator.get_status()
                power = actuator.get_power()
                result[name] = {'type': type(actuator).__name__, 'status': status, 'power_w': power}
            except Exception as e:
                result[name] = {'error': str(e)}
        return result

    def test_all(self) -> Dict[str, bool]:
        results = {}
        for name, actuator in self._actuators.items():
            try:
                results[name] = actuator.health_check()
            except Exception:
                results[name] = False
        return results

    def get_for_camera(self, cam_id: int) -> List[BaseActuator]:
        names = self.get_camera_bindings(cam_id)
        return [self._actuators[n] for n in names if n in self._actuators]
actuator_registry.register('tuya', TuyaActuator)
actuator_registry.register('tinytuya', TuyaActuator)