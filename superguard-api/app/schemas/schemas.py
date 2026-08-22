"""
SuperGuard API - Pydantic Schemas (Request/Response models)
"""
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum

from pydantic import BaseModel, Field, EmailStr, ConfigDict
from app.core.config import settings
from app.models.models import UserRole

# ============================================================================
# Auth
# ============================================================================

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 900


class RefreshRequest(BaseModel):
    refresh_token: str


class LoginRequest(BaseModel):
    username: str  # Can be username or email
    password: str


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    email: Optional[EmailStr] = None
    password: str = Field(min_length=8)
    full_name: Optional[str] = None
    invite_token: str  # Required for registration


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    username: str
    email: Optional[str] = None
    full_name: Optional[str] = None
    is_active: bool
    is_superuser: bool
    created_at: datetime


# ============================================================================
# Sites
# ============================================================================

class SiteCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None
    timezone: str = "UTC"
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class SiteUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    timezone: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    is_active: Optional[bool] = None


class SiteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: Optional[str] = None
    timezone: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    camera_count: int = 0
    actuator_count: int = 0
    detector_count: int = 0
    active_alarms: int = 0


class DashboardResponse(BaseModel):
    site: SiteResponse
    cameras: List[Any] = []
    actuators: List[Any] = []
    detectors: List[Any] = []
    active_alarms: List[Any] = []
    system_health: Dict[str, Any] = {}


# ============================================================================
# Cameras
# ============================================================================

class CameraType(str, Enum):
    rtsp = "rtsp"
    onvif = "onvif"
    http = "http"
    hls = "hls"
    webcam = "webcam"
    file = "file"


class ZoneCreate(BaseModel):
    rows: int = Field(default=3, ge=1, le=20)
    cols: int = Field(default=4, ge=1, le=20)
    cell: int = Field(default=1, ge=1)


class CameraCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None
    type: CameraType = CameraType.rtsp
    stream_url: str
    username: Optional[str] = None
    password: Optional[str] = None
    width: int = 1920
    height: int = 1080
    fps: float = 25.0
    ptz_enabled: bool = False
    zone: Optional[ZoneCreate] = None


class CameraUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    stream_url: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    is_enabled: Optional[bool] = None
    ptz_enabled: Optional[bool] = None


class ZoneResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    rows: int
    cols: int
    cell: int


class CameraResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    site_id: str
    name: str
    description: Optional[str] = None
    type: CameraType
    stream_url: str
    width: int
    height: int
    fps: float
    is_enabled: bool
    is_online: bool
    last_seen: Optional[datetime] = None
    ptz_enabled: bool
    zone: Optional[ZoneResponse] = None
    created_at: datetime


class CameraDiscoverRequest(BaseModel):
    network_range: Optional[str] = "192.168.1.0/24"
    scan_onvif: bool = True
    scan_upnp: bool = True


class DiscoveredCamera(BaseModel):
    ip: str
    port: int = 80
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    onvif: bool = False
    url: Optional[str] = None


# ============================================================================
# Detectors
# ============================================================================

class DetectorType(str, Enum):
    yolo = "yolo"
    motion = "motion"
    custom = "custom"


class DetectorCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None
    type: DetectorType = DetectorType.yolo
    model_path: Optional[str] = None
    classes: List[int] = []
    color_ranges: List[Dict[str, Any]] = []
    confidence_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    iou_threshold: float = Field(default=0.45, ge=0.0, le=1.0)
    min_detections: int = Field(default=1, ge=1)
    require_frames: int = Field(default=3, ge=1)
    auto_resolve_frames: int = Field(default=10, ge=1)
    update_every: float = Field(default=2.0, ge=0.1)
    detect_every: float = Field(default=0.5, ge=0.1)


class DetectorUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    model_path: Optional[str] = None
    classes: Optional[List[int]] = None
    color_ranges: Optional[List[Dict[str, Any]]] = None
    confidence_threshold: Optional[float] = Field(None, ge=0.0, le=1.0)
    iou_threshold: Optional[float] = Field(None, ge=0.0, le=1.0)
    is_enabled: Optional[bool] = None
    require_frames: Optional[int] = None
    auto_resolve_frames: Optional[int] = None


class DetectorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    site_id: str
    name: str
    description: Optional[str] = None
    type: DetectorType
    model_path: Optional[str] = None
    classes: List[int]
    confidence_threshold: float
    iou_threshold: float
    is_enabled: bool
    require_frames: int
    auto_resolve_frames: int
    created_at: datetime


# ============================================================================
# Actuators
# ============================================================================

class ActuatorType(str, Enum):
    tuya = "tuya"
    sonoff = "sonoff"
    shelly = "shelly"
    tasmota = "tasmota"
    gpio = "gpio"
    mqtt = "mqtt"
    http = "http"


class ActuatorCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None
    type: ActuatorType
    config: Dict[str, Any] = {}
    is_enabled: bool = True


class ActuatorUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    is_enabled: Optional[bool] = None


class ActuatorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    site_id: str
    name: str
    description: Optional[str] = None
    type: ActuatorType
    config: Dict[str, Any] = {}
    is_enabled: bool
    is_online: bool
    last_status: Optional[bool] = None
    last_power_w: Optional[float] = None
    last_seen: Optional[datetime] = None
    created_at: datetime


class ActuatorCommand(BaseModel):
    action: str = Field(pattern="^(on|off|toggle)$")


class ActuatorBindingCreate(BaseModel):
    actuator_id: Optional[str] = None
    detector_id: Optional[str] = None
    is_active: bool = True


class ActuatorBindingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    camera_id: str
    actuator_id: str
    detector_id: Optional[str] = None
    is_active: bool


# ============================================================================
# Alarms
# ============================================================================

class AlarmState(str, Enum):
    triggered = "triggered"
    acknowledged = "acknowledged"
    resolved = "resolved"
    silenced = "silenced"


class AlarmResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    site_id: str
    camera_id: str
    detector_id: str
    state: AlarmState
    confidence: Optional[float] = None
    detection_class: Optional[str] = None
    color_fraction: Optional[float] = None
    acknowledged_by: Optional[str] = None
    acknowledged_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    created_at: datetime


class AlarmAck(BaseModel):
    note: Optional[str] = None


class AlarmMediaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    alarm_id: str
    media_type: str
    url: Optional[str] = None
    thumbnail_path: Optional[str] = None
    created_at: datetime


# ============================================================================
# Notifiers
# ============================================================================

class NotifierType(str, Enum):
    telegram = "telegram"
    email = "email"
    pushover = "pushover"
    webhook = "webhook"
    mqtt = "mqtt"
    signal = "signal"


class NotifierCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    type: NotifierType
    config: Dict[str, Any] = {}
    notify_on_trigger: bool = True
    notify_on_ack: bool = False
    notify_on_resolve: bool = True


class NotifierResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    site_id: str
    name: str
    type: NotifierType
    config: Dict[str, Any] = {}
    is_enabled: bool
    notify_on_trigger: bool
    notify_on_ack: bool
    notify_on_resolve: bool
    created_at: datetime


# ============================================================================
# System
# ============================================================================

class SystemHealth(BaseModel):
    status: str = "healthy"
    version: str
    database: str = "connected"
    redis: str = "connected"
    uptime_seconds: float
    cameras_online: int = 0
    cameras_total: int = 0
    active_alarms: int = 0


# ============================================================================
# Rules
# ============================================================================

class RuleAction(str, Enum):
    on = "on"
    off = "off"
    toggle = "toggle"


class RuleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None
    camera_id: str
    detector_id: Optional[str] = None
    actuator_id: str
    action: RuleAction = RuleAction.on
    is_enabled: bool = True
    cooldown_seconds: int = Field(default=30, ge=0)


class RuleUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    camera_id: Optional[str] = None
    detector_id: Optional[str] = None
    actuator_id: Optional[str] = None
    action: Optional[RuleAction] = None
    is_enabled: Optional[bool] = None
    cooldown_seconds: Optional[int] = Field(None, ge=0)


class RuleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    site_id: str
    name: str
    description: Optional[str] = None
    camera_id: str
    detector_id: Optional[str] = None
    actuator_id: str
    action: RuleAction
    is_enabled: bool
    cooldown_seconds: int
    created_at: datetime
    updated_at: datetime


# ============================================================================
# Admin: Invite Tokens & Audit Logs
# ============================================================================

class InviteTokenCreate(BaseModel):
    site_id: Optional[str] = None
    role: UserRole = UserRole.VIEWER
    max_uses: int = Field(default=1, ge=1)
    expires_days: Optional[int] = Field(default=None, ge=1)


class InviteTokenResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    token: str
    site_id: Optional[str]
    role: UserRole
    max_uses: int
    used_count: int
    expires_at: Optional[datetime]
    created_at: datetime
    created_by: str


class AuditLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: Optional[str]
    site_id: Optional[str]
    action: str
    resource_type: Optional[str]
    resource_id: Optional[str]
    details: Dict[str, Any]
    ip_address: Optional[str]
    user_agent: Optional[str]
    created_at: datetime