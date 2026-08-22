"""
SuperGuard API - Configuration Settings
"""
from pathlib import Path
from typing import List
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "SuperGuard API"
    app_version: str = "0.1.0"
    debug: bool = False
    api_prefix: str = "/api/v1"

    # Server
    host: str = "0.0.0.0"
    port: int = 3001
    workers: int = 2

    # Database
    database_url: str = "sqlite+aiosqlite:///./superguard.db"
    # PostgreSQL (for production)
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "superguard"
    postgres_password: str = "superguard"
    postgres_db: str = "superguard"

    @property
    def database_url_async(self) -> str:
        """Return async database URL - PostgreSQL if configured, else SQLite."""
        if self.postgres_host and self.postgres_port and self.postgres_user:
            return f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        return self.database_url

    # Redis
    redis_url: str = "redis://localhost:6379/0"
    redis_pubsub_channel: str = "superguard:ws"

    # JWT
    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "RS256"
    jwt_private_key_path: str = "./keys/private.pem"
    jwt_public_key_path: str = "./keys/public.pem"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    # Encryption for sensitive actuator config (local_key, passwords)
    encryption_key: str = ""

    # CORS
    cors_origins: List[str] = Field(
        default=["http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:3001", "http://127.0.0.1:3001"]
    )

    # MediaMTX
    mediamtx_api_url: str = "http://localhost:9997"
    mediamtx_webrtc_url: str = "webrtc://localhost:8554"
    mediamtx_hls_url: str = "http://localhost:8888"

    # Tuya Cloud
    tuya_client_id: str = ""
    tuya_client_secret: str = ""
    tuya_region: str = "eu"

    # MQTT
    mqtt_broker: str = "localhost"
    mqtt_port: int = 1883
    mqtt_username: str = ""
    mqtt_password: str = ""
    mqtt_topic_prefix: str = "superguard"

    # Logging
    log_level: str = "INFO"
    log_format: str = "json"
    log_file: str = "./logs/superguard-api.log"

    # Telemetry
    otel_endpoint: str = "http://localhost:4317"
    otel_service_name: str = "superguard-api"

    # Backup
    backup_dir: str = "./backups"
    backup_schedule: str = "0 3 * * *"

    # Detection Engine
    detection_detect_every: float = 0.5
    detection_update_every: float = 2.0
    detection_min_conf: float = 0.35
    detection_yellow_min_fraction: float = 0.15
    detection_auto_resolve_frames: int = 10
    detection_require_frames: int = 2

    # Telegram
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    telegram_enabled: bool = False

    # Language
    language: str = "ru"


settings = Settings()

# Ensure directories exist
Path(settings.log_file).parent.mkdir(parents=True, exist_ok=True)
Path(settings.backup_dir).mkdir(parents=True, exist_ok=True)
Path(settings.jwt_private_key_path).parent.mkdir(parents=True, exist_ok=True)