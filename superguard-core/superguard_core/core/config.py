"""
SuperGuard Core - Configuration

Pydantic Settings with YAML + environment variable support.
"""

from pathlib import Path
from typing import List, Optional
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from YAML + environment variables."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
        case_sensitive=False,
    )
    
    # Application
    debug: bool = Field(default=False, description="Debug mode")
    host: str = Field(default="0.0.0.0", description="Bind host")
    port: int = Field(default=8080, description="Bind port")
    workers: int = Field(default=4, description="Worker processes")
    cors_origins: List[str] = Field(default=["*"], description="CORS allowed origins")
    
    # Database
    database_url: str = Field(
        default="sqlite+aiosqlite:///./data/superguard.db",
        description="SQLAlchemy database URL"
    )
    
    # Redis
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL"
    )
    
    # Storage
    storage_path: str = Field(
        default="./data",
        description="Base path for media storage"
    )
    
    # Auth
    secret_key: str = Field(
        default="",
        description="JWT secret key (auto-generated if empty)"
    )
    algorithm: str = Field(default="RS256", description="JWT algorithm")
    access_token_expire_minutes: int = Field(default=15, description="Access token TTL")
    refresh_token_expire_days: int = Field(default=7, description="Refresh token TTL")
    
    # MediaMTX
    mediamtx_api_url: str = Field(
        default="http://localhost:9997",
        description="MediaMTX API URL"
    )
    mediamtx_rtsp_port: int = Field(default=8554, description="MediaMTX RTSP port")
    mediamtx_hls_port: int = Field(default=8888, description="MediaMTX HLS port")
    mediamtx_webrtc_port: int = Field(default=8889, description="MediaMTX WebRTC port")
    
    # ONVIF Discovery
    onvif_discovery_timeout: int = Field(default=10, description="ONVIF scan timeout (seconds)")
    onvif_discovery_scope: str = Field(default="onvif://www.onvif.org/type/video_encoder", description="ONVIF discovery scope")
    
    # Detection defaults
    default_detection_interval: float = Field(default=1.0, description="Default detection interval (seconds)")
    default_confidence_threshold: float = Field(default=0.35, description="Default YOLO confidence threshold")
    default_iou_threshold: float = Field(default=0.45, description="Default YOLO IoU threshold")
    max_detections_per_frame: int = Field(default=100, description="Max detections per frame")
    
    # Alarm defaults
    default_alarm_cooldown: int = Field(default=30, description="Default alarm cooldown (seconds)")
    default_auto_cancel_after: int = Field(default=300, description="Default auto-cancel after (seconds)")
    alarm_frame_retention_days: int = Field(default=30, description="Alarm media retention")
    
    # Recording
    recording_segment_duration: int = Field(default=300, description="Recording segment duration (seconds)")
    recording_max_segments: int = Field(default=100, description="Max segments per camera")
    recording_codec: str = Field(default="h264", description="Recording codec")
    
    # Actuator defaults
    actuator_retry_attempts: int = Field(default=3, description="Actuator command retry attempts")
    actuator_retry_delay: float = Field(default=1.0, description="Actuator retry delay (seconds)")
    actuator_rediscovery_enabled: bool = Field(default=True, description="Enable ARP rediscovery")
    
    # Notifier defaults
    telegram_bot_token: str = Field(default="", description="Telegram bot token")
    telegram_chat_id: str = Field(default="", description="Telegram chat ID")
    push_pushover_token: str = Field(default="", description="Pushover app token")
    push_pushover_user: str = Field(default="", description="Pushover user key")
    email_smtp_host: str = Field(default="", description="SMTP host")
    email_smtp_port: int = Field(default=587, description="SMTP port")
    email_smtp_user: str = Field(default="", description="SMTP user")
    email_smtp_password: str = Field(default="", description="SMTP password")
    email_from: str = Field(default="", description="From email address")
    
    # Telemetry
    otel_endpoint: str = Field(default="", description="OpenTelemetry collector endpoint")
    otel_service_name: str = Field(default="superguard-core", description="OTEL service name")
    metrics_enabled: bool = Field(default=True, description="Enable Prometheus metrics")
    
    @field_validator("secret_key", mode="before")
    @classmethod
    def generate_secret_key(cls, v: str) -> str:
        if not v:
            import secrets
            return secrets.token_urlsafe(32)
        return v
    
    @field_validator("storage_path", mode="before")
    @classmethod
    def expand_storage_path(cls, v: str) -> str:
        return str(Path(v).expanduser().resolve())


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# YAML config loading (optional overlay)
def load_yaml_config(path: str) -> dict:
    """Load YAML configuration file."""
    import yaml
    config_path = Path(path)
    if not config_path.exists():
        return {}
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def merge_configs(base: dict, overlay: dict) -> dict:
    """Recursively merge two configuration dictionaries."""
    result = base.copy()
    for key, value in overlay.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = merge_configs(result[key], value)
        else:
            result[key] = value
    return result