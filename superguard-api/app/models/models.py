"""
SuperGuard API - Database ORM Models (SQLite + PostgreSQL compatible)
"""
import enum
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any

from sqlalchemy import (
    String, Text, Integer, Float, Boolean, DateTime, Enum, ForeignKey,
    Index, UniqueConstraint, JSON
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func


# GUID type: stored as String(36) — works in SQLite and PostgreSQL
class GUID(String):
    """Platform-agnostic UUID column type."""
    def __init__(self):
        super().__init__(36)


def _uuid():
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


# ============================================================================
# Sites
# ============================================================================

class Site(Base):
    __tablename__ = "sites"

    id: Mapped[str] = mapped_column(GUID, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    cameras: Mapped[List["Camera"]] = relationship(back_populates="site", cascade="all, delete-orphan")
    actuators: Mapped[List["Actuator"]] = relationship(back_populates="site", cascade="all, delete-orphan")
    detectors: Mapped[List["Detector"]] = relationship(back_populates="site", cascade="all, delete-orphan")
    alarms: Mapped[List["Alarm"]] = relationship(back_populates="site", cascade="all, delete-orphan")
    users: Mapped[List["SiteUser"]] = relationship(back_populates="site", cascade="all, delete-orphan")
    notifiers: Mapped[List["Notifier"]] = relationship(back_populates="site", cascade="all, delete-orphan")
    rules: Mapped[List["Rule"]] = relationship(back_populates="site", cascade="all, delete-orphan")

    __table_args__ = (Index("ix_sites_name", "name"),)


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    OPERATOR = "operator"
    VIEWER = "viewer"


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(GUID, primary_key=True, default=_uuid)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), unique=True, nullable=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False)
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    site_roles: Mapped[List["SiteUser"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    refresh_tokens: Mapped[List["RefreshToken"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    audit_logs: Mapped[List["AuditLog"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class SiteUser(Base):
    __tablename__ = "site_users"

    id: Mapped[str] = mapped_column(GUID, primary_key=True, default=_uuid)
    site_id: Mapped[str] = mapped_column(GUID, ForeignKey("sites.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[str] = mapped_column(GUID, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.VIEWER, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    site: Mapped["Site"] = relationship(back_populates="users")
    user: Mapped["User"] = relationship(back_populates="site_roles")

    __table_args__ = (
        UniqueConstraint("site_id", "user_id", name="uq_site_user"),
        Index("ix_site_users_site_id", "site_id"),
        Index("ix_site_users_user_id", "user_id"),
    )


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[str] = mapped_column(GUID, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(GUID, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    user: Mapped["User"] = relationship(back_populates="refresh_tokens")

    __table_args__ = (
        Index("ix_refresh_tokens_user_id", "user_id"),
        Index("ix_refresh_tokens_expires_at", "expires_at"),
    )


# ============================================================================
# Cameras
# ============================================================================

class CameraType(str, enum.Enum):
    rtsp = "rtsp"
    onvif = "onvif"
    http = "http"
    hls = "hls"
    webcam = "webcam"
    file = "file"


class Camera(Base):
    __tablename__ = "cameras"

    id: Mapped[str] = mapped_column(GUID, primary_key=True, default=_uuid)
    site_id: Mapped[str] = mapped_column(GUID, ForeignKey("sites.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    type: Mapped[CameraType] = mapped_column(Enum(CameraType), default=CameraType.rtsp, nullable=False)
    stream_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    password_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    width: Mapped[int] = mapped_column(Integer, default=1920)
    height: Mapped[int] = mapped_column(Integer, default=1080)
    fps: Mapped[float] = mapped_column(Float, default=25.0)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    is_online: Mapped[bool] = mapped_column(Boolean, default=False)
    last_seen: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    onvif_profile: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    ptz_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    config: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    site: Mapped["Site"] = relationship(back_populates="cameras")
    zone: Mapped[Optional["Zone"]] = relationship(back_populates="camera", uselist=False, cascade="all, delete-orphan")
    actuator_bindings: Mapped[List["ActuatorBinding"]] = relationship(back_populates="camera", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_cameras_site_id", "site_id"),
        Index("ix_cameras_is_enabled", "is_enabled"),
    )


class Zone(Base):
    __tablename__ = "zones"

    id: Mapped[str] = mapped_column(GUID, primary_key=True, default=_uuid)
    camera_id: Mapped[str] = mapped_column(GUID, ForeignKey("cameras.id", ondelete="CASCADE"), unique=True, nullable=False)
    rows: Mapped[int] = mapped_column(Integer, default=3)
    cols: Mapped[int] = mapped_column(Integer, default=4)
    cell: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    camera: Mapped["Camera"] = relationship(back_populates="zone")


# ============================================================================
# Detectors
# ============================================================================

class DetectorType(str, enum.Enum):
    yolo = "yolo"
    motion = "motion"
    custom = "custom"


class Detector(Base):
    __tablename__ = "detectors"

    id: Mapped[str] = mapped_column(GUID, primary_key=True, default=_uuid)
    site_id: Mapped[str] = mapped_column(GUID, ForeignKey("sites.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    type: Mapped[DetectorType] = mapped_column(Enum(DetectorType), default=DetectorType.yolo, nullable=False)
    model_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    model_config: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    # SQLite doesn't have ARRAY — use JSON for lists
    classes: Mapped[List[Any]] = mapped_column(JSON, default=list)
    color_ranges: Mapped[List[Any]] = mapped_column(JSON, default=list)
    confidence_threshold: Mapped[float] = mapped_column(Float, default=0.5)
    iou_threshold: Mapped[float] = mapped_column(Float, default=0.45)
    min_detections: Mapped[int] = mapped_column(Integer, default=1)
    require_frames: Mapped[int] = mapped_column(Integer, default=3)
    auto_resolve_frames: Mapped[int] = mapped_column(Integer, default=10)
    update_every: Mapped[float] = mapped_column(Float, default=2.0)
    detect_every: Mapped[float] = mapped_column(Float, default=0.5)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    site: Mapped["Site"] = relationship(back_populates="detectors")

    __table_args__ = (
        Index("ix_detectors_site_id", "site_id"),
        Index("ix_detectors_is_enabled", "is_enabled"),
    )


# ============================================================================
# Actuators
# ============================================================================

class ActuatorType(str, enum.Enum):
    tuya = "tuya"
    sonoff = "sonoff"
    shelly = "shelly"
    tasmota = "tasmota"
    gpio = "gpio"
    mqtt = "mqtt"
    http = "http"


class Actuator(Base):
    __tablename__ = "actuators"

    id: Mapped[str] = mapped_column(GUID, primary_key=True, default=_uuid)
    site_id: Mapped[str] = mapped_column(GUID, ForeignKey("sites.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    type: Mapped[ActuatorType] = mapped_column(Enum(ActuatorType), nullable=False)
    config: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    is_online: Mapped[bool] = mapped_column(Boolean, default=False)
    last_status: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    last_power_w: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    last_seen: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    site: Mapped["Site"] = relationship(back_populates="actuators")
    bindings: Mapped[List["ActuatorBinding"]] = relationship(back_populates="actuator", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_actuators_site_id", "site_id"),
        Index("ix_actuators_is_enabled", "is_enabled"),
    )


class ActuatorBinding(Base):
    __tablename__ = "actuator_bindings"

    id: Mapped[str] = mapped_column(GUID, primary_key=True, default=_uuid)
    camera_id: Mapped[str] = mapped_column(GUID, ForeignKey("cameras.id", ondelete="CASCADE"), nullable=False)
    actuator_id: Mapped[str] = mapped_column(GUID, ForeignKey("actuators.id", ondelete="CASCADE"), nullable=False)
    detector_id: Mapped[Optional[str]] = mapped_column(GUID, ForeignKey("detectors.id", ondelete="SET NULL"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    camera: Mapped["Camera"] = relationship(back_populates="actuator_bindings")
    actuator: Mapped["Actuator"] = relationship(back_populates="bindings")

    __table_args__ = (
        UniqueConstraint("camera_id", "actuator_id", name="uq_camera_actuator"),
        Index("ix_actuator_bindings_camera_id", "camera_id"),
        Index("ix_actuator_bindings_actuator_id", "actuator_id"),
    )


# ============================================================================
# Alarms
# ============================================================================

class AlarmState(str, enum.Enum):
    triggered = "triggered"
    acknowledged = "acknowledged"
    resolved = "resolved"
    silenced = "silenced"


class Alarm(Base):
    __tablename__ = "alarms"

    id: Mapped[str] = mapped_column(GUID, primary_key=True, default=_uuid)
    site_id: Mapped[str] = mapped_column(GUID, ForeignKey("sites.id", ondelete="CASCADE"), nullable=False)
    camera_id: Mapped[str] = mapped_column(GUID, ForeignKey("cameras.id", ondelete="CASCADE"), nullable=False)
    detector_id: Mapped[str] = mapped_column(GUID, ForeignKey("detectors.id", ondelete="CASCADE"), nullable=False)
    state: Mapped[AlarmState] = mapped_column(Enum(AlarmState), default=AlarmState.triggered, nullable=False)
    trigger_frame_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    trigger_frame_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    detection_class: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    color_fraction: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    acknowledged_by: Mapped[Optional[str]] = mapped_column(GUID, ForeignKey("users.id"), nullable=True)
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    alarm_metadata: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    site: Mapped["Site"] = relationship(back_populates="alarms")
    media: Mapped[List["AlarmMedia"]] = relationship(back_populates="alarm", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_alarms_site_id", "site_id"),
        Index("ix_alarms_camera_id", "camera_id"),
        Index("ix_alarms_state", "state"),
        Index("ix_alarms_created_at", "created_at"),
    )


class AlarmMedia(Base):
    __tablename__ = "alarm_media"

    id: Mapped[str] = mapped_column(GUID, primary_key=True, default=_uuid)
    alarm_id: Mapped[str] = mapped_column(GUID, ForeignKey("alarms.id", ondelete="CASCADE"), nullable=False)
    media_type: Mapped[str] = mapped_column(String(32), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    thumbnail_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    alarm: Mapped["Alarm"] = relationship(back_populates="media")

    __table_args__ = (Index("ix_alarm_media_alarm_id", "alarm_id"),)


# ============================================================================
# Notifiers
# ============================================================================

class NotifierType(str, enum.Enum):
    telegram = "telegram"
    email = "email"
    pushover = "pushover"
    webhook = "webhook"
    mqtt = "mqtt"
    signal = "signal"


class Notifier(Base):
    __tablename__ = "notifiers"

    id: Mapped[str] = mapped_column(GUID, primary_key=True, default=_uuid)
    site_id: Mapped[str] = mapped_column(GUID, ForeignKey("sites.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[NotifierType] = mapped_column(Enum(NotifierType), nullable=False)
    config: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_on_trigger: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_on_ack: Mapped[bool] = mapped_column(Boolean, default=False)
    notify_on_resolve: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    site: Mapped["Site"] = relationship(back_populates="notifiers")

    __table_args__ = (
        Index("ix_notifiers_site_id", "site_id"),
        Index("ix_notifiers_is_enabled", "is_enabled"),
    )


# ============================================================================
# System
# ============================================================================

class SystemLog(Base):
    __tablename__ = "system_logs"

    id: Mapped[str] = mapped_column(GUID, primary_key=True, default=_uuid)
    site_id: Mapped[Optional[str]] = mapped_column(GUID, ForeignKey("sites.id", ondelete="SET NULL"), nullable=True)
    level: Mapped[str] = mapped_column(String(16), nullable=False)
    logger: Mapped[str] = mapped_column(String(128), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)

    __table_args__ = (
        Index("ix_system_logs_site_id", "site_id"),
        Index("ix_system_logs_level", "level"),
    )


class AuditLog(Base):
    """User activity audit log - visible only to admin users."""
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(GUID, primary_key=True, default=_uuid)
    user_id: Mapped[Optional[str]] = mapped_column(GUID, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    site_id: Mapped[Optional[str]] = mapped_column(GUID, ForeignKey("sites.id", ondelete="SET NULL"), nullable=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    resource_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    resource_id: Mapped[Optional[str]] = mapped_column(GUID, nullable=True)
    details: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)

    user: Mapped[Optional["User"]] = relationship(back_populates="audit_logs")

    __table_args__ = (
        Index("ix_audit_logs_user_id", "user_id"),
        Index("ix_audit_logs_site_id", "site_id"),
        Index("ix_audit_logs_action", "action"),
        Index("ix_audit_logs_created_at", "created_at"),
    )


class InviteToken(Base):
    """Invite tokens for user registration - created by admin only."""
    __tablename__ = "invite_tokens"

    id: Mapped[str] = mapped_column(GUID, primary_key=True, default=_uuid)
    token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    created_by: Mapped[str] = mapped_column(GUID, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    site_id: Mapped[Optional[str]] = mapped_column(GUID, ForeignKey("sites.id", ondelete="SET NULL"), nullable=True)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.VIEWER, nullable=False)
    max_uses: Mapped[int] = mapped_column(Integer, default=1)
    used_count: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("ix_invite_tokens_token", "token"),
        Index("ix_invite_tokens_created_by", "created_by"),
    )


# ============================================================================
# Rules
# ============================================================================

class RuleAction(str, enum.Enum):
    on = "on"
    off = "off"
    toggle = "toggle"


class Rule(Base):
    __tablename__ = "rules"

    id: Mapped[str] = mapped_column(GUID, primary_key=True, default=_uuid)
    site_id: Mapped[str] = mapped_column(GUID, ForeignKey("sites.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    camera_id: Mapped[str] = mapped_column(GUID, ForeignKey("cameras.id", ondelete="CASCADE"), nullable=False)
    detector_id: Mapped[Optional[str]] = mapped_column(GUID, ForeignKey("detectors.id", ondelete="SET NULL"), nullable=True)
    actuator_id: Mapped[str] = mapped_column(GUID, ForeignKey("actuators.id", ondelete="CASCADE"), nullable=False)
    action: Mapped[RuleAction] = mapped_column(Enum(RuleAction), default=RuleAction.on, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    cooldown_seconds: Mapped[int] = mapped_column(Integer, default=30)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    site: Mapped["Site"] = relationship(back_populates="rules")
    camera: Mapped["Camera"] = relationship()
    detector: Mapped[Optional["Detector"]] = relationship()
    actuator: Mapped["Actuator"] = relationship()

    __table_args__ = (
        Index("ix_rules_site_id", "site_id"),
        Index("ix_rules_camera_id", "camera_id"),
        Index("ix_rules_actuator_id", "actuator_id"),
    )