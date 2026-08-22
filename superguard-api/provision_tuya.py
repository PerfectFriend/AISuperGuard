#!/usr/bin/env python3
"""
Tuya Actuator Credentials Provisioning Tool
===========================================
Updates actuator configs with real Tuya Cloud credentials.

Usage:
    python3 provision_tuya.py --actuator <id> --device-id <id> --local-key <key> [--ip <ip>]

Or interactive:
    python3 provision_tuya.py --interactive
"""

import asyncio
import argparse
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from app.core.database import get_db
from app.models.models import Actuator
from app.core.encryption import get_encryption
from sqlalchemy import select, update


async def list_actuators():
    """List all enabled actuators."""
    async for db in get_db():
        result = await db.execute(select(Actuator).where(Actuator.is_enabled == True))
        actuators = result.scalars().all()
        enc = get_encryption()
        
        print("\n📋 Available Actuators:")
        print("-" * 80)
        for a in actuators:
            config = dict(a.config)
            decrypted = enc.decrypt_dict(config)
            print(f"  ID: {a.id}")
            print(f"  Name: {a.name}")
            print(f"  Type: {a.type.value}")
            print(f"  MAC: {decrypted.get('mac', 'N/A')}")
            print(f"  IP: {decrypted.get('ip', 'N/A')}")
            print(f"  Device ID: {decrypted.get('device_id', 'N/A')[:10]}...")
            print(f"  Local Key: {decrypted.get('local_key', 'N/A')[:10]}...")
            print()


async def update_actuator(actuator_id: str, device_id: str, local_key: str, ip: str | None = None):
    """Update actuator with real Tuya credentials."""
    async for db in get_db():
        result = await db.execute(select(Actuator).where(Actuator.id == actuator_id))
        actuator = result.scalar_one_or_none()
        
        if not actuator:
            print(f"❌ Actuator {actuator_id} not found!")
            return False
        
        config = dict(actuator.config)
        enc = get_encryption()
        
        # Encrypt new credentials
        new_config = {
            'ip': enc.encrypt(ip) if ip else config.get('ip'),
            'device_id': enc.encrypt(device_id),
            'local_key': enc.encrypt(local_key),
            'version': config.get('version', 3.4),
            'port': config.get('port', 6668),
            'mac': config.get('mac'),
        }
        
        await db.execute(
            update(Actuator)
            .where(Actuator.id == actuator_id)
            .values(config=new_config)
        )
        await db.commit()
        
        print(f"✅ Updated {actuator.name} ({actuator_id[:8]}...)")
        print(f"   Device ID: {device_id}")
        print(f"   Local Key: {local_key}")
        if ip:
            print(f"   IP: {ip}")
        return True


async def interactive_mode():
    """Interactive provisioning."""
    await list_actuators()
    
    while True:
        actuator_id = input("\nEnter actuator ID (or 'q' to quit): ").strip()
        if actuator_id.lower() == 'q':
            break
        
        # Validate actuator exists
        actuator = None
        async for db in get_db():
            result = await db.execute(select(Actuator).where(Actuator.id == actuator_id))
            actuator = result.scalar_one_or_none()
        
        if not actuator:
            print(f"❌ Actuator {actuator_id} not found!")
            continue
        
        print(f"\nUpdating: {actuator.name}")
        device_id = input("Enter Tuya Device ID: ").strip()
        local_key = input("Enter Tuya Local Key: ").strip()
        ip_input = input("Enter IP (optional, press Enter to keep current): ").strip()
        
        if not device_id or not local_key:
            print("❌ Device ID and Local Key are required!")
            continue
        
        await update_actuator(actuator_id, device_id, local_key, ip_input if ip_input else None)
        print("✅ Done!\n")


async def test_actuator(actuator_id: str):
    """Test actuator connection with current credentials."""
    from app.services.actuator_engine import get_actuator_engine
    from app.services.redis_manager import get_redis_manager
    
    print(f"\n🔌 Testing actuator {actuator_id[:8]}...")
    redis_manager = await get_redis_manager()
    engine = await get_actuator_engine(redis_manager)
    
    instance = engine.actuators.get(actuator_id)
    if not instance:
        print(f"❌ Actuator not loaded in engine!")
        return
    
    print(f"   Name: {instance.config.name}")
    print(f"   Type: {instance.config.type}")
    print(f"   IP: {instance.config.ip}")
    print(f"   Device ID: {instance.config.device_id[:10]}...")
    
    try:
        result = await instance.actuator.test_connection()
        print(f"   Connection test: {'✅ PASS' if result else '❌ FAIL'}")
        
        if result:
            status = await instance.actuator.get_status()
            print(f"   Current state: {'ON' if status else 'OFF' if status is not None else 'UNKNOWN'}")
    except Exception as e:
        print(f"   Error: {e}")


def main():
    parser = argparse.ArgumentParser(description="Provision Tuya actuator credentials")
    parser.add_argument("--actuator", help="Actuator UUID")
    parser.add_argument("--device-id", help="Tuya Device ID")
    parser.add_argument("--local-key", help="Tuya Local Key")
    parser.add_argument("--ip", help="Device IP (optional)")
    parser.add_argument("--test", action="store_true", help="Test actuator connection")
    parser.add_argument("--list", action="store_true", help="List all actuators")
    parser.add_argument("--interactive", "-i", action="store_true", help="Interactive mode")
    
    args = parser.parse_args()
    
    if args.list:
        asyncio.run(list_actuators())
    elif args.test and args.actuator:
        asyncio.run(test_actuator(args.actuator))
    elif args.actuator and args.device_id and args.local_key:
        asyncio.run(update_actuator(args.actuator, args.device_id, args.local_key, args.ip))
    elif args.interactive:
        asyncio.run(interactive_mode())
    else:
        parser.print_help()


if __name__ == "__main__":
    main()