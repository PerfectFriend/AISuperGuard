import json
import time
import threading
import requests
import hmac
import hashlib
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from ..config import TuyaCloudConfig, SuperGuardConfig, TuyaPlugConfig
from ..actuators import actuator_registry, BaseActuator

@dataclass
class TuyaDevice:
    id: str
    name: str
    category: str
    ip: str
    local_key: Optional[str] = None
    status: List[Dict] = None

class TuyaCloudClient:
    REGION_URLS = {'cn': 'https://openapi.tuyacn.com', 'us': 'https://openapi.tuyaus.com', 'eu': 'https://openapi.tuyaeu.com', 'in': 'https://openapi.tuyain.com'}
    PLUG_CATEGORIES = ['kg', 'cz', 'wk', 'wkz']

    def __init__(self, config: TuyaCloudConfig):
        self.config = config
        self.base_url = self.REGION_URLS.get(config.region, 'https://openapi.tuyaeu.com')
        self.token: Optional[str] = None
        self.token_expire: float = 0
        self._lock = threading.Lock()

    def _get_sign(self, t: str) -> str:
        msg = f'{self.config.access_id}{t}'.encode()
        key = self.config.access_secret.encode()
        return hmac.new(key, msg, hashlib.sha256).hexdigest().upper()

    def _get_token(self) -> bool:
        import time
        t = str(int(time.time() * 1000))
        sign = self._get_sign(t)
        headers = {'client_id': self.config.access_id, 'sign': sign, 't': t, 'sign_method': 'HMAC-SHA256'}
        try:
            r = requests.get(f'{self.base_url}/v1.0/token?grant_type=1', headers=headers, timeout=10)
            if r.status_code == 200:
                data = r.json()
                if data.get('success'):
                    self.token = data['result']['access_token']
                    self.token_expire = time.time() + data['result']['expire_time'] - 60
                    return True
        except Exception as e:
            print(f'  [TuyaCloud] Token error: {e}')
        return False

    def _headers(self) -> Optional[Dict[str, str]]:
        import time
        with self._lock:
            if not self.token or time.time() >= self.token_expire:
                if not self._get_token():
                    return None
            t = str(int(time.time() * 1000))
            sign = self._get_sign(t)
            return {'client_id': self.config.access_id, 'access_token': self.token, 'sign': sign, 't': t, 'sign_method': 'HMAC-SHA256'}

    def get_devices(self) -> List[TuyaDevice]:
        headers = self._headers()
        if not headers:
            return []
        try:
            r = requests.get(f'{self.base_url}/v1.0/users/smart/devices', headers=headers, timeout=10)
            if r.status_code == 200:
                data = r.json()
                if data.get('success'):
                    devices = []
                    for d in data['result']:
                        devices.append(TuyaDevice(id=d.get('id', ''), name=d.get('name', ''), category=d.get('category', ''), ip=d.get('ip', ''), local_key=d.get('local_key'), status=d.get('status', [])))
                    return devices
        except Exception as e:
            print(f'  [TuyaCloud] Devices error: {e}')
        return []

    def get_device_status(self, device_id: str) -> Optional[Dict]:
        headers = self._headers()
        if not headers:
            return None
        try:
            r = requests.get(f'{self.base_url}/v1.0/devices/{device_id}/status', headers=headers, timeout=10)
            if r.status_code == 200:
                data = r.json()
                if data.get('success'):
                    return data['result']
        except Exception as e:
            print(f'  [TuyaCloud] Device status error: {e}')
        return None

class TuyaCloudSync:

    def __init__(self, config: SuperGuardConfig):
        self.config = config
        self.client: Optional[TuyaCloudClient] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._last_sync = 0
        self._sync_interval = 300
        if config.tuya_cloud.enabled:
            self.client = TuyaCloudClient(config.tuya_cloud)
            print(f'  [TuyaCloud] Initialized for region={config.tuya_cloud.region}')

    def start(self):
        if not self.client or self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._sync_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)

    def _sync_loop(self):
        while self._running:
            time.sleep(self._sync_interval)
            if not self._running:
                break
            try:
                self.sync_once()
            except Exception as e:
                print(f'  [TuyaCloud] Sync error: {e}')

    def sync_once(self) -> bool:
        if not self.client:
            return False
        print('  [TuyaCloud] Syncing devices...')
        devices = self.client.get_devices()
        if not devices:
            return False
        plugs = [d for d in devices if d.category in self.client.PLUG_CATEGORIES]
        if not plugs:
            return False
        print(f'  [TuyaCloud] Found {len(plugs)} plugs')
        changes_made = False
        for plug in plugs:
            dev_id = plug.id
            new_ip = plug.ip
            for plug_config in self.config.plugs:
                if plug_config.device_id == dev_id:
                    if new_ip and new_ip != plug_config.ip:
                        old_ip = plug_config.ip
                        plug_config.ip = new_ip
                        print(f'  [TuyaCloud] Updated {plug_config.name} IP: {old_ip} -> {new_ip}')
                        changes_made = True
                        self._update_env_actuators()
                        self._reinitialize_actuator(plug_config)
        self._last_sync = time.time()
        return changes_made

    def _update_env_actuators(self):
        import os
        env_path = os.path.join(self.config.base_dir, 'sguard.env')
        actuator_data = []
        for plug in self.config.plugs:
            actuator_data.append({'name': plug.name, 'type': plug.type, 'cameras': plug.cameras, 'ip': plug.ip, 'device_id': plug.device_id, 'local_key': plug.local_key, 'version': plug.version, 'port': plug.port})
        lines = []
        found = False
        if os.path.exists(env_path):
            with open(env_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip().startswith('SG_ACTUATORS='):
                        lines.append(f'SG_ACTUATORS={json.dumps(actuator_data)}\n')
                        found = True
                    else:
                        lines.append(line)
        if not found:
            lines.append(f'SG_ACTUATORS={json.dumps(actuator_data)}\n')
        temp_path = env_path + '.tmp'
        try:
            with open(temp_path, 'w', encoding='utf-8') as f:
                f.writelines(lines)
            os.replace(temp_path, env_path)
            print(f'  [TuyaCloud] Updated sguard.env')
        except Exception as e:
            print(f'  [TuyaCloud] Env write error: {e}')

    def _reinitialize_actuator(self, plug_config: TuyaPlugConfig):
        try:
            actuator_class = actuator_registry.get(plug_config.type)
            if not actuator_class:
                return
            actuator_config = {'name': plug_config.name, 'ip': plug_config.ip, 'device_id': plug_config.device_id, 'local_key': plug_config.local_key, 'version': plug_config.version, 'port': plug_config.port}
            print(f'  [TuyaCloud] Actuator {plug_config.name} needs reinit with IP {plug_config.ip}')
        except Exception as e:
            print(f'  [TuyaCloud] Reinit error: {e}')

    def force_sync(self) -> bool:
        return self.sync_once()

def create_tuya_cloud_sync(config: SuperGuardConfig) -> Optional[TuyaCloudSync]:
    if not config.tuya_cloud.enabled:
        return None
    sync = TuyaCloudSync(config)
    sync.start()
    return sync