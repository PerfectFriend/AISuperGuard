#!/usr/bin/env python3
"""
SuperGuard Core - Migration Script v1 to v2

Migrates legacy SuperGuard v1 configuration (sguard.env + sguard_settings.json)
to SuperGuard Core v2 database.
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from superguard_core.core.config import Settings, load_yaml_config, merge_configs
from superguard_core.core.database import (
    init_db, close_db, get_session_factory, Base,
    Site, Camera, Detector, Actuator, Alarm, User, UserRole, site_users
)
from superguard_core.core.auth import get_password_hash


async def load_v1_config() -> dict:
    """Load v1 configuration from sguard.env and sguard_settings.json."""
    config = {}
    
    # Load sguard.env
    env_path = Path.cwd().parent / "sguard.env"
    if not env_path.exists():
        env_path = Path("C:/SuperGuard/sguard.env")
    if not env_path.exists():
        raise FileNotFoundError("sguard.env not found")
    
    with open(env_path, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                config[key] = value
    
    # Load sguard_settings.json
    settings_path = Path.cwd().parent / "superguard" / "sguard_settings.json"
    if not settings_path.exists():
        settings_path = Path("C:/SuperGuard/superguard/sguard_settings.json")
    if settings_path.exists():
        with open(settings_path, 'r') as f:
            config['sguard_settings'] = json.load(f)
    
    # Parse actuators JSON
    if 'SG_ACTUATORS' in config:
        try:
            config['actuators_parsed'] = json.loads(config['SG_ACTUATORS'])
        except:
            config['actuators_parsed'] = []
    
    return config


async def migrate_v1_to_v2():
    """Main migration function."""
    print("Loading v1 configuration...")
    v1_config = await load_v1_config()
    
    print("Initializing v2 database...")
    settings = Settings()
    await init_db(settings.database_url)
    
    session_factory = get_session_factory()
    
    async with session_factory() as session:
        # Create main site
        print("Creating main site...")
        site = Site(
            name="Main Site",
            description="Migrated from SuperGuard v1",
            address=v1_config.get('SG_CAM2_NAME', ''),
            timezone="UTC",
        )
        session.add(site)
        await session.flush()
        print(f"  Site created: {site.id} - {site.name}")
        
        # Create admin user
        print("Creating admin user...")
        admin = User(
            email="admin@superguard.local",
            password_hash=get_password_hash("admin123"),  # Change on first login!
            full_name="Administrator",
            role=UserRole.ADMIN,
        )
        session.add(admin)
        await session.flush()
        
        # Assign admin to site
        await session.execute(
            site_users.insert().values(user_id=admin.id, site_id=site.id, role=UserRole.ADMIN)
        )
        print(f"  Admin user created: {admin.id} - {admin.email}")
        
        # Migrate cameras
        print("Migrating cameras...")
        camera_map = {}  # old index -> new id
        for i in range(1, 9):
            url_key = f'SG_CAM{i}_URL'
            name_key = f'SG_CAM{i}_NAME'
            type_key = f'SG_CAM{i}_TYPE'
            
            if url_key not in v1_config:
                continue
            
            cam_type = v1_config.get(type_key, 'rtsp').lower()
            type_map = {'rtsp': 'rtsp', 'hls': 'hls', 'jpg': 'jpg', 'jpeg': 'jpg'}
            
            camera = Camera(
                site_id=site.id,
                name=v1_config.get(name_key, f'Camera {i}'),
                type=type_map.get(cam_type, 'rtsp'),
                url=v1_config[url_key],
                username='admin' if 'admin' in v1_config[url_key] else None,
                password='123456' if '123456' in v1_config[url_key] else None,
                position=i - 1,
                is_enabled=True,
            )
            session.add(camera)
            await session.flush()
            camera_map[i] = camera.id
            print(f"  Camera {i}: {camera.name} ({camera.type}) -> ID {camera.id}")
        
        # Migrate detectors - create default YOLO detector
        print("Creating default detector...")
        detector = Detector(
            site_id=site.id,
            name="YOLO11n Default",
            description="Migrated from v1 YOLO detector",
            plugin="yolo_onnx",
            config={
                "model_path": v1_config.get('SG_YOLO_MODEL', './yolo11n.pt'),
                "imgsz": 640,
                "device": "cpu",
            },
            classes=["person", "bicycle", "car", "motorcycle", "bus", "truck"],
            confidence_threshold=float(v1_config.get('SG_MIN_CONF', '0.35')),
            iou_threshold=0.45,
            interval=float(v1_config.get('SG_DETECT_EVERY', '1.5')),
            is_enabled=True,
        )
        session.add(detector)
        await session.flush()
        print(f"  Detector created: {detector.id} - {detector.name}")
        
        # Assign detector to all cameras
        for cam_id in camera_map.values():
            await session.execute(
                Camera.__table__.update()
                .where(Camera.id == cam_id)
                .values(detector_id=detector.id)
            )
        
        # Migrate actuators
        print("Migrating actuators...")
        actuators_parsed = v1_config.get('actuators_parsed', [])
        actuator_map = {}  # name -> id
        
        for act_config in actuators_parsed:
            actuator = Actuator(
                site_id=site.id,
                name=act_config.get('name', 'Unknown'),
                plugin='tuya_local' if act_config.get('type') == 'tuya' else act_config.get('type', 'tuya_local'),
                config={
                    'device_id': act_config.get('device_id'),
                    'local_key': act_config.get('local_key'),
                    'ip': act_config.get('ip'),
                    'mac': act_config.get('mac'),
                    'version': act_config.get('version', 3.4),
                    'port': act_config.get('port', 6668),
                },
                camera_bindings=act_config.get('cameras', []),
                is_enabled=True,
            )
            session.add(actuator)
            await session.flush()
            actuator_map[act_config.get('name')] = actuator.id
            print(f"  Actuator: {actuator.name} ({actuator.plugin}) -> ID {actuator.id}")
        
        # Migrate notification rules - Telegram
        if v1_config.get('SG_TELEGRAM_BOT_TOKEN') and v1_config.get('SG_CHAT_ID'):
            print("Creating Telegram notification rule...")
            from superguard_core.core.database import NotificationRule
            notif = NotificationRule(
                site_id=site.id,
                name="Telegram Alerts",
                description="Migrated from v1 Telegram bot",
                trigger="alarm_created",
                notifier_plugin="telegram",
                notifier_config={
                    'bot_token': v1_config.get('SG_TELEGRAM_BOT_TOKEN'),
                    'chat_id': v1_config.get('SG_CHAT_ID'),
                },
                is_enabled=True,
            )
            session.add(notif)
            print(f"  Notification rule created: {notif.name}")
        
        await session.commit()
        print("\nMigration completed successfully!")
        print(f"Site ID: {site.id}")
        print(f"Admin: admin@superguard.local / admin123 (CHANGE PASSWORD!)")
        print(f"Database: {settings.database_url}")


async def main():
    """Entry point."""
    try:
        await migrate_v1_to_v2()
    except Exception as e:
        print(f"Migration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())