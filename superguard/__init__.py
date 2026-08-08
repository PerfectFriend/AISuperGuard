"""
SuperGuard Alarm - Modular AI Video Surveillance System

A standalone Telegram bot for AI-powered video surveillance with:
- YOLOv11n object detection
- HSV color filtering
- Grid-based zone targeting
- Multi-camera support (8 cameras)
- Multi-actuator support (Tuya, Sonoff, Shelly, ESPHome, Zigbee)
- Per-camera settings (zone, target, actuator binding)
- Tuya Cloud auto-discovery
- 3-language interface (RU/EN/ES)
- Atomic settings persistence

Architecture:
superguard/
├── main.py              # Entry point, application lifecycle
├── config.py            # Configuration loading & validation
├── models/              # Core data models
│   ├── Zone, Target, CameraSettings, Alarm state machine
├── detectors/           # Detection pipeline
│   ├── YOLODetector, ColorFilter, ZoneFilter, DetectionPipeline
├── cameras/             # Camera abstraction
│   ├── BaseCamera, JPGCamera, HLSCamera, CameraManager
├── actuators/           # Actuator abstraction
│   ├── BaseActuator, TuyaActuator, ActuatorRegistry, ActuatorManager
├── telegram/            # Telegram bot layer
│   ├── TelegramClient, CommandRouter, SuperGuardBot
├── storage/             # Persistence
│   ├── SettingsStore, EnvWriter
└── tuya_cloud/          # Tuya Cloud sync
    ├── TuyaCloudClient, TuyaCloudSync
"""
__version__ = "2.0.0"
__author__ = "Master Inquisitor"