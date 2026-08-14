#!/usr/bin/env python3
"""
Tuya Cloud Device Discovery Script

Discovers all Tuya devices from Cloud API, shows their IPs, device_ids, and categories.
Useful for:
1. Finding IPs of plugs for local control (tinytuya)
2. Getting device_ids for cloud control (TuyaCloudActuator)
3. Verifying Tuya Cloud credentials

Usage:
    python scripts/discover_tuya_devices.py
    python scripts/discover_tuya_devices.py --access-id xxx --access-secret yyy --region eu
"""

import sys
import os
import json
import argparse

# Add project root to path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from superguard.tuya_cloud import TuyaCloudClient, TuyaCloudConfig


def main():
    parser = argparse.ArgumentParser(description="Discover Tuya devices from Cloud API")
    parser.add_argument("--access-id", help="Tuya Cloud Access ID")
    parser.add_argument("--access-secret", help="Tuya Cloud Access Secret")
    parser.add_argument("--region", default="eu", choices=["cn", "us", "eu", "in"], help="Tuya Cloud region")
    parser.add_argument("--schema", default="smartlife", help="Tuya schema (smartlife/tuya)")
    parser.add_argument("--filter-plugs", action="store_true", help="Only show plugs/switches")
    parser.add_argument("--output-json", help="Save results to JSON file")
    args = parser.parse_args()
    
    # Load from sguard.env if not provided
    if not args.access_id or not args.access_secret:
        env_path = os.path.join(BASE_DIR, "sguard.env")
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        if k == "TUYA_ACCESS_ID" and not args.access_id:
                            args.access_id = v
                        elif k == "TUYA_ACCESS_SECRET" and not args.access_secret:
                            args.access_secret = v
                        elif k == "TUYA_REGION" and not args.region:
                            args.region = v
                        elif k == "TUYA_SCHEMA" and not args.schema:
                            args.schema = v
    
    if not args.access_id or not args.access_secret:
        print("ERROR: TUYA_ACCESS_ID and TUYA_ACCESS_SECRET required")
        print("Provide via --access-id/--access-secret or set in sguard.env")
        sys.exit(1)
    
    print(f"Connecting to Tuya Cloud (region={args.region})...")
    
    config = TuyaCloudConfig(
        access_id=args.access_id,
        access_secret=args.access_secret,
        region=args.region,
        schema=args.schema
    )
    
    client = TuyaCloudClient(config)
    devices = client.get_devices()
    
    if not devices:
        print("No devices found or authentication failed")
        sys.exit(1)
    
    # Filter for plugs/switches if requested
    PLUG_CATEGORIES = ["kg", "cz", "wk", "wkz"]  # switch, outlet, etc.
    if args.filter_plugs:
        devices = [d for d in devices if d.category in PLUG_CATEGORIES]
        print(f"\nFound {len(devices)} plug/switch devices:")
    else:
        print(f"\nFound {len(devices)} total devices:")
    
    # Print table
    print("-" * 120)
    print(f"{'Name':<30} {'ID':<25} {'Category':<10} {'IP':<15} {'Online':<8} {'Local Key':<10}")
    print("-" * 120)
    
    results = []
    for d in devices:
        online = "Yes" if d.ip else "No (offline)"
        local_key = d.local_key[:8] + "..." if d.local_key else "N/A"
        print(f"{d.name[:28]:<30} {d.id:<25} {d.category:<10} {d.ip:<15} {online:<8} {local_key:<10}")
        
        results.append({
            "name": d.name,
            "id": d.id,
            "category": d.category,
            "ip": d.ip,
            "online": bool(d.ip),
            "local_key": d.local_key,
            "status": d.status
        })
    
    print("-" * 120)
    
    # Print summary for SG_ACTUATORS config
    plugs = [d for d in devices if d.category in PLUG_CATEGORIES]
    if plugs:
        print("\n\n=== Suggested SG_ACTUATORS config (for local tuya control) ===")
        actuator_configs = []
        for i, d in enumerate(plugs, 1):
            if d.ip and d.local_key:
                actuator_configs.append({
                    "name": f"plug{i}",
                    "type": "tuya",
                    "cameras": list(range((i-1)*4+1, min(i*4+1, 9))),  # 4 cameras per plug
                    "ip": d.ip,
                    "device_id": d.id,
                    "local_key": d.local_key,
                    "version": 3.4,
                    "port": 6668
                })
        
        if actuator_configs:
            print(json.dumps(actuator_configs, indent=2))
        
        print("\n=== Suggested SG_ACTUATORS config (for cloud tuya_cloud control) ===")
        cloud_configs = []
        for i, d in enumerate(plugs, 1):
            cloud_configs.append({
                "name": f"plug{i}",
                "type": "tuya_cloud",
                "cameras": list(range((i-1)*4+1, min(i*4+1, 9))),
                "device_id": d.id,
                "access_id": args.access_id,
                "access_secret": args.access_secret,
                "region": args.region,
                "version": 3.4,
                "port": 6668
            })
        if cloud_configs:
            print(json.dumps(cloud_configs, indent=2))
    
    if args.output_json:
        with open(args.output_json, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"\nResults saved to {args.output_json}")


if __name__ == "__main__":
    main()