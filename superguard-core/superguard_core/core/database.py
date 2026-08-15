"""
SuperGuard Core - Database Layer

SQLAlchemy 2.0 async models with Alembic migrations.
"""

from datetime import datetime
from enum import Enum as PyEnum
from typing import Optional, List, Dict, Any
from uuid import uuid4

from sqlalchemy import (
    String, Text, Integer, Float, Boolean, DateTime, ForeignKey,
    Enum as SQLEnum, JSON, Index, UniqueConstraint, func
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.ext.asyncio import (
    AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
)

from superguard_core.core.config import get_settings


class Base(DeclarativeBase):
    """Base class for all models."""
    pass


class UserRole(PyEnum):
    """User roles."""
    ADMIN = "admin"
    OPERATOR = "operator"
    VIEWER = "viewer"


class CameraType(PyEnum):
    """Camera types."""
    RTSP = "rtsp"
    HLS = "hls"
    JPG = "jpg"
    ONVIF = "onvif"
    WEBCAM = "webcam"


class CameraStatus(PyEnum):
    """Camera connection status."""
    ONLINE = "online"
    OFFLINE = "offline"
    CONNECTING = "connecting"
    ERROR = "error"


class AlarmStatus(PyEnum):
    """Alarm status."""
    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    FALSE_POSITIVE = "false_positive"


class MediaType(PyEnum):
    """Alarm media types."""
    FRAME = "frame"
    VIDEO = "video"
    SNAPSHOT = "snapshot"


# Association tables
site_users = Table(
    "site_users",
    Base.metadata,
    Column("site_id", Integer, ForeignKey("sites.id", ondelete="CASCADE"), primary_key=True),
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("role", SQLEnum(UserRole), default=UserRole.VIEWER),
    Column("created_at", DateTime, default=func.now()),
)


class Site(Base):
    """Site/Location being monitored."""
    __tablename__ = "sites"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())
    
    # Relationships
    cameras: Mapped[List["Camera"]] = relationship(back_populates="site", cascade="all, delete-orphan")
    detectors: Mapped[List["Detector"]] = relationship(back_populates="site", cascade="all, delete-orphan")
    actuators: Mapped[List["Actuator"]] = relationship(back_populates="site", cascade="all, delete-orphan")
    alarms: Mapped[List["Alarm"]] = relationship(back_populates="site", cascade="all, delete-orphan")
    notification_rules: Mapped[List["NotificationRule"]] = relationship(back_populates="site", cascade="all, delete-orphan")
    users: Mapped[List["User"]] = relationship(secondary=site_users, back_populates="sites")


class User(Base):
    """System user."""
    __tablename__ = "users"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=lambda: str(uuid4()))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    role: Mapped[UserRole] = mapped_column(SQLEnum(UserRole), default=UserRole.VIEWER)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())
    
    # Relationships
    sites: Mapped[List[Site]] = relationship(secondary=site_users, back_populates="users")
    acknowledged_alarms: Mapped[List["Alarm"]] = relationship(back_populates="acknowledged_by_user")


class Camera(Base):
    """Camera configuration."""
    __tablename__ = "cameras"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=lambda: str(uuid4()))
    site_id: Mapped[int] = mapped_column(Integer, ForeignKey("sites.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    type: Mapped[CameraType] = mapped_column(SQLEnum(CameraType), default=CameraType.RTSP)
    url: Mapped[str] = mapped_column(Text)
    username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    password: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    onvif_profile: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    width: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    height: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    fps: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    zone_config: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    detector_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("detectors.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[CameraStatus] = mapped_column(SQLEnum(CameraStatus), default=CameraStatus.OFFLINE)
    last_frame_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    position: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())
    
    # Relationships
    site: Mapped[Site] = relationship(back_populates="cameras")
    detector: Mapped[Optional["Detector"]] = relationship(back_populates="cameras")
    alarms: Mapped[List["Alarm"]] = relationship(back_populates="camera")
    media: Mapped[List["AlarmMedia"]] = relationship(back_populates="camera")


class Detector(Base):
    """Detector configuration."""
    __tablename__ = "detectors"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=lambda: str(uuid4()))
    site_id: Mapped[int] = mapped_column(Integer, ForeignKey("sites.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    plugin: Mapped[str] = mapped_column(String(64))
    config: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    classes: Mapped[List[str]] = mapped_column(JSON, default=list)
    confidence_threshold: Mapped[float] = mapped_column(Float, default=0.35)
    iou_threshold: Mapped[float] = mapped_column(Float, default=0.45)
    interval: Mapped[float] = mapped_column(Float, default=1.0)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())
    
    # Relationships
    site: Mapped[Site] = relationship(back_populates="detectors")
    cameras: Mapped[List[Camera]] = relationship(back_populates="detector")
    alarms: Mapped[List["Alarm"]] = relationship(back_populates="detector")


class Actuator(Base):
    """Actuator (smart plug, relay, siren, etc.) configuration."""
    __tablename__ = "actuators"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=lambda: str(uuid4()))
    site_id: Mapped[int] = mapped_column(Integer, ForeignKey("sites.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    plugin: Mapped[str] = mapped_column(String(64))
    config: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    camera_bindings: Mapped[List[int]] = mapped_column(JSON, default=list)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_state: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    last_command_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())
    
    # Relationships
    site: Mapped[Site] = relationship(back_populates="actuators")
    alarms: Mapped[List["Alarm"]] = relationship(back_populates="actuator")


class Alarm(Base):
    """Alarm event."""
    __tablename__ = "alarms"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=lambda: str(uuid4()))
    site_id: Mapped[int] = mapped_column(Integer, ForeignKey("sites.id", ondelete="CASCADE"), index=True)
    camera_id: Mapped[int] = mapped_column(Integer, ForeignKey("cameras.id", ondelete="CASCADE"), index=True)
    detector_id: Mapped[int] = mapped_column(Integer, ForeignKey("detectors.id", ondelete="CASCADE"), index=True)
    actuator_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("actuators.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[AlarmStatus] = mapped_column(SQLEnum(AlarmStatus), default=AlarmStatus.ACTIVE, index=True)
    trigger_data: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), index=True)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    acknowledged_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    auto_cancel_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    
    # Relationships
    site: Mapped[Site] = relationship(back_populates="alarms")
    camera: Mapped[Camera] = relationship(back_populates="alarms")
    detector: Mapped[Detector] = relationship(back_populates="alarms")
    actuator: Mapped[Optional[Actuator]] = relationship(back_populates="alarms")
    acknowledged_by_user: Mapped[Optional[User]] = relationship(back_populates="acknowledged_alarms")
    media: Mapped[List["AlarmMedia"]] = relationship(back_populates="alarm", cascade="all, delete-orphan")


class AlarmMedia(Base):
    """Alarm media (frames, videos)."""
    __tablename__ = "alarm_media"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=lambda: str(uuid4()))
    alarm_id: Mapped[int] = mapped_column(Integer, ForeignKey("alarms.id", ondelete="CASCADE"), index=True)
    camera_id: Mapped[int] = mapped_column(Integer, ForeignKey("cameras.id", ondelete="CASCADE"), index=True)
    type: Mapped[MediaType] = mapped_column(SQLEnum(MediaType))
    path: Mapped[str] = mapped_column(String(512))
    thumbnail_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=func.now(), index=True)
    metadata: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    file_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    duration: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # Relationships
    alarm: Mapped[Alarm] = relationship(back_populates="media")
    camera: Mapped[Camera] = relationship(back_populates="media")


class NotificationRule(Base):
    """Notification rules for alarms."""
    __tablename__ = "notification_rules"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=lambda: str(uuid4()))
    site_id: Mapped[int] = mapped_column(Integer, ForeignKey("sites.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    trigger: Mapped[str] = mapped_column(String(64))  # alarm_created, alarm_acknowledged, etc.
    notifier_plugin: Mapped[str] = mapped_column(String(64))
    notifier_config: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    schedule: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)  # cron-like
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())
    
    # Relationships
    site: Mapped[Site] = relationship(back_populates="notification_rules")


# Database engine and session
_engine: Optional[AsyncEngine] = None
_session_factory: Optional[async_sessionmaker[AsyncSession]] = None


async def init_db(database_url: str) -> None:
    """Initialize database engine and create tables."""
    global _engine, _session_factory
    
    _engine = create_async_engine(
        database_url,
        echo=get_settings().debug,
        pool_pre_ping=True,
        pool_recycle=3600,
    )
    
    _session_factory = async_sessionmaker(
        _engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    
    # Create tables
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """Close database connections."""
    global _engine, _session_factory
    if _engine:
        await _engine.dispose()
    _engine = None
    _session_factory = None


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Get session factory."""
    if _session_factory is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _session_factory


async def get_session() -> AsyncSession:
    """Get database session (for dependency injection)."""
    factory = get_session_factory()
    async with factory() as session:
        yield session