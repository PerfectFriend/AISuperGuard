import os
import json
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Any

@dataclass
class TelegramConfig:
    token: str
    chat_id: int = 143293811
    api_id: int = 0
    api_hash: str = ''

@dataclass
class TuyaPlugConfig:
    name: str
    ip: str = ''
    device_id: str = ''
    local_key: str = ''
    version: float = 3.4
    port: int = 6668
    cameras: List[int] = field(default_factory=list)
    type: str = 'tuya'
    mac: str = ''
    access_id: str = ''
    access_secret: str = ''
    region: str = 'eu'

@dataclass
class CameraConfig:
    cam_id: int
    name: str
    url: str

@dataclass
class TuyaCloudConfig:
    access_id: Optional[str] = None
    access_secret: Optional[str] = None
    region: str = 'eu'
    schema: str = 'smartlife'

    @property
    def enabled(self) -> bool:
        return bool(self.access_id and self.access_secret)

@dataclass
class DetectionConfig:
    update_every: float = 2.0
    detect_every: float = 1.5
    yellow_min_fraction: float = 0.15
    min_conf: float = 0.35
    min_yellow_vehicles: int = 1
    require_frames: int = 2
    auto_resolve_frames: int = 5

@dataclass
class SuperGuardConfig:
    telegram: TelegramConfig
    plugs: List[TuyaPlugConfig]
    cameras: Dict[int, CameraConfig]
    tuya_cloud: TuyaCloudConfig
    detection: DetectionConfig
    base_dir: str

    @property
    def actuators(self) -> List[TuyaPlugConfig]:
        return self.plugs

    @property
    def settings_file(self) -> str:
        return os.path.join(self.base_dir, 'sguard_settings.json')

    @property
    def frame_dir(self) -> str:
        project_root = os.path.dirname(self.base_dir)
        return os.path.join(project_root, 'saved_frames')

def load_env_file(path: str) -> Dict[str, str]:
    env = {}
    if os.path.exists(path):
        with open(path, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and (not line.startswith('#')) and ('=' in line):
                    k, v = line.split('=', 1)
                    env[k.strip()] = v.strip()
    return env

def parse_actuator_configs(raw: str, defaults: Dict[str, Any]) -> List[TuyaPlugConfig]:
    if not raw.strip():
        return [TuyaPlugConfig(**defaults)]
    try:
        data = json.loads(raw)
        plugs = []
        for item in data:
            plugs.append(TuyaPlugConfig(name=item['name'], type=item.get('type', 'tuya'), cameras=item.get('cameras', []), ip=item.get('ip', ''), device_id=item.get('device_id', ''), local_key=item.get('local_key', ''), version=item.get('version', 3.4), port=item.get('port', 6668), mac=item.get('mac', ''), access_id=item.get('access_id', ''), access_secret=item.get('access_secret', ''), region=item.get('region', 'eu')))
        return plugs
    except Exception as e:
        print(f'  WARNING: SG_ACTUATORS parse error: {e}, using defaults')
        return [TuyaPlugConfig(**defaults)]

def load_config(base_dir: str) -> SuperGuardConfig:
    project_root = os.path.dirname(base_dir)
    env_path = os.path.join(project_root, 'sguard.env')
    env = load_env_file(env_path)
    for key in ['SG_TELEGRAM_BOT_TOKEN', 'SG_CHAT_ID', 'SG_PLUG_IP', 'SG_PLUG_ID', 'SG_PLUG_KEY', 'SG_CAM_URL', 'TUYA_ACCESS_ID', 'TUYA_ACCESS_SECRET', 'TUYA_REGION', 'TUYA_SCHEMA', 'SG_ACTUATORS']:
        if key in os.environ:
            env[key] = os.environ[key]
    token = env.get('SG_TELEGRAM_BOT_TOKEN')
    if not token:
        raise SystemExit('SG_TELEGRAM_BOT_TOKEN not set in sguard.env')
    plug_key = env.get('SG_PLUG_KEY')
    if not plug_key:
        raise SystemExit('SG_PLUG_KEY not set in sguard.env')
    telegram = TelegramConfig(token=token, chat_id=int(env.get('SG_CHAT_ID', '143293811')), api_id=int(env.get('TG_API_ID', '0')), api_hash=env.get('TG_API_HASH', ''))
    default_plug = {'name': 'plug1', 'ip': env.get('SG_PLUG_IP', '192.168.137.109'), 'device_id': env.get('SG_PLUG_ID', 'bfd23bfc0bdd93b6904c3s'), 'local_key': plug_key, 'version': 3.4, 'port': 6668, 'cameras': [1, 2, 3, 4, 5, 6, 7, 8]}
    plugs = parse_actuator_configs(env.get('SG_ACTUATORS', ''), default_plug)
    cam_url = env.get('SG_CAM_URL', 'https://atcs.banjarkota.go.id:5443/LiveApp/streams/Ptzparungsari.m3u8')
    CAMERA_URLS = {1: cam_url, 2: 'https://cwwp2.dot.ca.gov/data/d9/cctv/image/sr203mammothmountain/sr203mammothmountain.jpg', 3: 'https://cwwp2.dot.ca.gov/data/d9/cctv/image/us395conwaysummit/us395conwaysummit.jpg', 4: 'https://cwwp2.dot.ca.gov/data/d9/cctv/image/us6stateline/us6stateline.jpg', 5: 'https://cwwp2.dot.ca.gov/data/d9/cctv/image/us395crestview/us395crestview.jpg', 6: 'https://cocam.carsprogram.org/Live_View/I70199RoadSurface.jpg', 7: 'https://itscameras.dot.state.oh.us:443/images/toledo/SR2-EB-Approach.jpg', 8: 'https://itscameras.dot.state.oh.us:443/images/CMH/2134.jpg'}
    CAMERA_NAMES = {1: '1: Indonesia - Banjar PTZ (HLS)', 2: '2: CA Mono - Mammoth Mountain', 3: '3: CA Mono - Conway Summit', 4: '4: CA Mono - Stateline', 5: '5: CA Mono - Crestview', 6: '6: CO DOT - I-70 Road Surface', 7: '7: OH DOT - Toledo SR-2 EB Approach', 8: '8: OH DOT - Columbus CMH 2134'}
    for i in range(2, 33):
        url_key = f'SG_CAM{i}_URL'
        name_key = f'SG_CAM{i}_NAME'
        if url_key in env:
            CAMERA_URLS[i] = env[url_key]
            CAMERA_NAMES[i] = env.get(name_key, f'Camera {i}')
    cameras = {}
    for cam_id, url in CAMERA_URLS.items():
        cameras[cam_id] = CameraConfig(cam_id=cam_id, name=CAMERA_NAMES.get(cam_id, f'Camera {cam_id}'), url=url)
    tuya_cloud = TuyaCloudConfig(access_id=env.get('TUYA_ACCESS_ID'), access_secret=env.get('TUYA_ACCESS_SECRET'), region=env.get('TUYA_REGION', 'eu'), schema=env.get('TUYA_SCHEMA', 'smartlife'))
    detection = DetectionConfig(update_every=float(env.get('SG_UPDATE_EVERY', '2.0')), detect_every=float(env.get('SG_DETECT_EVERY', '1.5')), yellow_min_fraction=float(env.get('SG_YELLOW_MIN_FRACTION', '0.15')), min_conf=float(env.get('SG_MIN_CONF', '0.35')), min_yellow_vehicles=int(env.get('SG_MIN_YELLOW_VEHICLES', '1')), require_frames=int(env.get('SG_REQUIRE_FRAMES', '2')), auto_resolve_frames=int(env.get('SG_AUTO_RESOLVE_FRAMES', '5')))
    return SuperGuardConfig(telegram=telegram, plugs=plugs, cameras=cameras, tuya_cloud=tuya_cloud, detection=detection, base_dir=base_dir)