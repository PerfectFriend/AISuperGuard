"""
SuperGuard Alarm - Configuration Module

Loads and validates all configuration from environment variables and .env files.
Provides typed config objects with defaults.

Configuration sources (priority order):
1. OS environment variables (highest)
2. sguard.env file in project root
3. Hardcoded defaults (lowest)

All secrets (tokens, keys) MUST be in sguard.env or OS env - never in code.
"""
import os
import json
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Any

from .logging_config import get_logger, setup_logging

# Initialize structured logging
logger = get_logger(__name__)
setup_logging(
    log_level=os.environ.get("SG_LOG_LEVEL", "INFO"),
    log_file=os.environ.get("SG_LOG_FILE"),
    json_format=os.environ.get("SG_LOG_JSON", "true").lower() == "true"
)


@dataclass
class TelegramConfig:
    """Telegram bot configuration.
    
    Attributes:
        token: Bot token from @BotFather (required)
        chat_id: Target chat ID for messages/alerts (default: 143293811)
        api_id: Telegram MTProto API ID from my.telegram.org (for Telethon)
        api_hash: Telegram MTProto API Hash from my.telegram.org (for Telethon)
    """
    token: str
    chat_id: int = 143293811
    # Telethon MTProto API (for MTProto client - bypasses Bot API rate limits)
    api_id: int = 0
    api_hash: str = ""


@dataclass
class TuyaPlugConfig:
    """Single Tuya plug configuration.
    
    Supports both local (tinytuya) and cloud (Tuya Cloud API) control modes.
    For local control: ip, device_id, local_key are required.
    For cloud control: access_id, access_secret, region are required.
    
    Attributes:
        name: Human-readable name (e.g., "plug1", "plug2")
        ip: Local IP address (DHCP - may change on hotspot reconnect)
        device_id: Tuya device ID (20-char string from Tuya app)
        local_key: Local encryption key (from Tuya app device details)
        version: Tuya protocol version (3.3 or 3.4)
        port: Local TCP port (default 6668)
        cameras: List of camera IDs this plug is bound to (many-to-many)
        type: Actuator type identifier ("tuya" for local, "tuya_cloud" for cloud)
        mac: MAC address for ARP-based IP rediscovery on DHCP renew
        access_id: Tuya Cloud Access ID (for cloud control)
        access_secret: Tuya Cloud Access Secret (for cloud control)
        region: Tuya Cloud region (cn, us, eu, in)
    """
    name: str
    ip: str = ""
    device_id: str = ""
    local_key: str = ""
    version: float = 3.4
    port: int = 6668
    cameras: List[int] = field(default_factory=list)
    type: str = "tuya"
    # MAC address for ARP-based IP discovery on DHCP renew
    mac: str = ""
    # Cloud API fields (for tuya_cloud type)
    access_id: str = ""
    access_secret: str = ""
    region: str = "eu"


@dataclass
class CameraConfig:
    """Single camera configuration.
    
    Attributes:
        cam_id: Unique camera identifier (1-32)
        name: Human-readable name for UI
        url: Stream/snapshot URL (RTSP, HLS .m3u8, or JPG HTTP)
    """
    cam_id: int
    name: str
    url: str


@dataclass
class TuyaCloudConfig:
    """Tuya Cloud API configuration for auto-discovery.
    
    Used by tuya_cloud.py background sync to discover plug IPs
    when local control is unavailable (different network).
    
    Attributes:
        access_id: Tuya IoT Platform Access ID
        access_secret: Tuya IoT Platform Access Secret
        region: API region endpoint (cn, us, eu, in)
        schema: Tuya schema (smartlife, tuya)
    """
    access_id: Optional[str] = None
    access_secret: Optional[str] = None
    region: str = "eu"
    schema: str = "smartlife"
    
    @property
    def enabled(self) -> bool:
        """True if cloud credentials are configured."""
        return bool(self.access_id and self.access_secret)


@dataclass
class DetectionConfig:
    """Detection algorithm parameters.
    
    All times in seconds. Fractions are 0.0-1.0.
    
    Attributes:
        update_every: Telegram live frame update interval during alarm
        detect_every: YOLO inference interval per camera
        yellow_min_fraction: Minimum yellow pixel fraction in bbox to match
        min_conf: YOLO confidence threshold
        min_yellow_vehicles: Minimum matching detections to count as hit
        require_frames: Consecutive hit frames required to trigger alarm
        auto_resolve_frames: Clean frames required to auto-resolve alarm
    """
    update_every: float = 2.0
    detect_every: float = 1.5
    yellow_min_fraction: float = 0.15
    min_conf: float = 0.35
    min_yellow_vehicles: int = 1
    require_frames: int = 2
    auto_resolve_frames: int = 5


@dataclass
class SuperGuardConfig:
    """Root configuration container.
    
    Aggregates all subsystem configs. Created by load_config().
    
    Attributes:
        telegram: Bot configuration
        plugs: List of Tuya plug configurations
        cameras: Dict of camera_id -> CameraConfig
        tuya_cloud: Cloud API config (optional)
        detection: Detection algorithm parameters
        base_dir: Absolute path to superguard/ module directory
    """
    telegram: TelegramConfig
    plugs: List[TuyaPlugConfig]
    cameras: Dict[int, CameraConfig]
    tuya_cloud: TuyaCloudConfig
    detection: DetectionConfig
    base_dir: str
    
    @property
    def actuators(self) -> List[TuyaPlugConfig]:
        """Alias for plugs for backward compatibility with ActuatorManager."""
        return self.plugs
    
    @property
    def settings_file(self) -> str:
        """Path to persisted settings JSON (in module dir)."""
        return os.path.join(self.base_dir, "sguard_settings.json")
    
    @property
    def frame_dir(self) -> str:
        """Path to saved frames directory (project_root/saved_frames)."""
        # Frames saved to project_root/saved_frames
        project_root = os.path.dirname(self.base_dir)
        return os.path.join(project_root, "saved_frames")


def load_env_file(path: str) -> Dict[str, str]:
    """Load KEY=VALUE pairs from .env file.
    
    Ignores empty lines, comments (#), and lines without '='.
    Values are NOT parsed - returned as raw strings.
    
    Args:
        path: Path to .env file
        
    Returns:
        Dict of key -> value strings
    """
    env = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()
    return env


def parse_actuator_configs(raw: str, defaults: Dict[str, Any]) -> List[TuyaPlugConfig]:
    """Parse SG_ACTUATORS JSON into TuyaPlugConfig list.

    SG_ACTUATORS is a JSON array of objects, each with plug parameters.
    Falls back to single default plug if JSON is empty or invalid.

    Args:
        raw: Raw JSON string from env
        defaults: Default values dict for missing fields

    Returns:
        List of TuyaPlugConfig objects
    """
    if not raw.strip():
        return [TuyaPlugConfig(**defaults)]

    try:
        data = json.loads(raw)
        plugs = []
        for item in data:
            plugs.append(TuyaPlugConfig(
                name=item["name"],
                type=item.get("type", "tuya"),
                cameras=item.get("cameras", []),
                ip=item.get("ip", ""),
                device_id=item.get("device_id", ""),
                local_key=item.get("local_key", ""),
                version=item.get("version", 3.4),
                port=item.get("port", 6668),
                # MAC for ARP-based IP discovery
                mac=item.get("mac", ""),
                # Cloud fields
                access_id=item.get("access_id", ""),
                access_secret=item.get("access_secret", ""),
                region=item.get("region", "eu"),
            ))
        return plugs
    except Exception as e:
        logger.warning("SG_ACTUATORS parse error: %s, using defaults", e)
        return [TuyaPlugConfig(**defaults)]


def load_config(base_dir: str) -> SuperGuardConfig:
    """Load complete configuration from sguard.env and environment.
    
    Loads sguard.env from project root (parent of base_dir).
    OS environment variables override .env values.
    
    Args:
        base_dir: Absolute path to superguard/ module directory
        
    Returns:
        Fully populated SuperGuardConfig
        
    Raises:
        SystemExit: If required tokens/keys are missing
    """
    # sguard.env is in the project root (parent of superguard module)
    project_root = os.path.dirname(base_dir)
    env_path = os.path.join(project_root, "sguard.env")
    env = load_env_file(env_path)
    
    # Also check OS environment (overrides .env)
    for key in ["SG_TELEGRAM_BOT_TOKEN", "SG_CHAT_ID", "SG_PLUG_IP", "SG_PLUG_ID", 
                "SG_PLUG_KEY", "SG_CAM_URL", "TUYA_ACCESS_ID", "TUYA_ACCESS_SECRET",
                "TUYA_REGION", "TUYA_SCHEMA", "SG_ACTUATORS"]:
        if key in os.environ:
            env[key] = os.environ[key]
    
    # Validate required
        token = env.get("SG_TELEGRAM_BOT_TOKEN")
        if not token:
            raise SystemExit("SG_TELEGRAM_BOT_TOKEN not set in sguard.env")

        # SG_PLUG_KEY is only required for legacy single-plug config (not SG_ACTUATORS)
        plug_key = env.get("SG_PLUG_KEY")
        has_actuators = bool(env.get("SG_ACTUATORS", "").strip())
        if not plug_key and not has_actuators:
            raise SystemExit("SG_PLUG_KEY not set in sguard.env (or use SG_ACTUATORS for multi-plug)")
    
    # Telegram
    telegram = TelegramConfig(
        token=token,
        chat_id=int(env.get("SG_CHAT_ID", "143293811")),
        api_id=int(env.get("TG_API_ID", "0")),
        api_hash=env.get("TG_API_HASH", ""),
    )
    
    # Default plug (backward compat)
    default_plug = {
        "name": "plug1",
        "ip": env.get("SG_PLUG_IP", "192.168.137.109"),
        "device_id": env.get("SG_PLUG_ID", "bfd23bfc0bdd93b6904c3s"),
        "local_key": plug_key,
        "version": 3.4,
        "port": 6668,
        "cameras": [1, 2, 3, 4, 5, 6, 7, 8],
    }
    
    # Plugs from SG_ACTUATORS
    plugs = parse_actuator_configs(env.get("SG_ACTUATORS", ""), default_plug)
    
    # Cameras
    cam_url = env.get("SG_CAM_URL", "https://atcs.banjarkota.go.id:5443/LiveApp/streams/Ptzparungsari.m3u8")
    
    CAMERA_URLS = {
        1: cam_url,  # Indonesia HLS
        2: "https://cwwp2.dot.ca.gov/data/d9/cctv/image/sr203mammothmountain/sr203mammothmountain.jpg",
        3: "https://cwwp2.dot.ca.gov/data/d9/cctv/image/us395conwaysummit/us395conwaysummit.jpg",
        4: "https://cwwp2.dot.ca.gov/data/d9/cctv/image/us6stateline/us6stateline.jpg",
        5: "https://cwwp2.dot.ca.gov/data/d9/cctv/image/us395crestview/us395crestview.jpg",
        6: "https://cocam.carsprogram.org/Live_View/I70199RoadSurface.jpg",
        7: "https://itscameras.dot.state.oh.us:443/images/toledo/SR2-EB-Approach.jpg",
        8: "https://itscameras.dot.state.oh.us:443/images/CMH/2134.jpg",
    }
    
    CAMERA_NAMES = {
        1: "1: Indonesia - Banjar PTZ (HLS)",
        2: "2: CA Mono - Mammoth Mountain",
        3: "3: CA Mono - Conway Summit",
        4: "4: CA Mono - Stateline",
        5: "5: CA Mono - Crestview",
        6: "6: CO DOT - I-70 Road Surface",
        7: "7: OH DOT - Toledo SR-2 EB Approach",
        8: "8: OH DOT - Columbus CMH 2134",
    }
    
    # Dynamic additional cameras from env (SG_CAM{N}_URL, SG_CAM{N}_NAME)
    # This allows adding/overriding cameras without code changes
    # Check for cameras 2-32 (camera 1 uses SG_CAM_URL)
    for i in range(2, 33):
        url_key = f"SG_CAM{i}_URL"
        name_key = f"SG_CAM{i}_NAME"
        if url_key in env:
            CAMERA_URLS[i] = env[url_key]
            CAMERA_NAMES[i] = env.get(name_key, f"Camera {i}")
    
    cameras = {}
    for cam_id, url in CAMERA_URLS.items():
        cameras[cam_id] = CameraConfig(
            cam_id=cam_id,
            name=CAMERA_NAMES.get(cam_id, f"Camera {cam_id}"),
            url=url,
        )
    
    # Tuya Cloud
    tuya_cloud = TuyaCloudConfig(
        access_id=env.get("TUYA_ACCESS_ID"),
        access_secret=env.get("TUYA_ACCESS_SECRET"),
        region=env.get("TUYA_REGION", "eu"),
        schema=env.get("TUYA_SCHEMA", "smartlife"),
    )
    
    # Detection
    detection = DetectionConfig(
        update_every=float(env.get("SG_UPDATE_EVERY", "2.0")),
        detect_every=float(env.get("SG_DETECT_EVERY", "1.5")),
        yellow_min_fraction=float(env.get("SG_YELLOW_MIN_FRACTION", "0.15")),
        min_conf=float(env.get("SG_MIN_CONF", "0.35")),
        min_yellow_vehicles=int(env.get("SG_MIN_YELLOW_VEHICLES", "1")),
        require_frames=int(env.get("SG_REQUIRE_FRAMES", "2")),
        auto_resolve_frames=int(env.get("SG_AUTO_RESOLVE_FRAMES", "5")),
    )
    
    return SuperGuardConfig(
        telegram=telegram,
        plugs=plugs,
        cameras=cameras,
        tuya_cloud=tuya_cloud,
        detection=detection,
        base_dir=base_dir,
    )