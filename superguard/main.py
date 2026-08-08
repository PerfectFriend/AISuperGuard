#!/usr/bin/env python3
"""
SuperGuard Alarm - Main Entry Point

Modular architecture:
- config: Configuration loading & validation
- models: Core data models (Zone, Target, CameraSettings, Alarm)
- detectors: YOLO + HSV color + zone filtering pipeline
- cameras: JPG/HLS camera abstraction with CameraManager
- actuators: Multi-protocol actuator layer (Tuya, Sonoff, Shelly, ESPHome, Zigbee)
- telegram: Telegram bot with command router, callbacks, menus
- storage: Atomic JSON persistence + .env writer
- tuya_cloud: Background Tuya Cloud sync for IP discovery

This replaces the monolithic panic_mode.py (~1800 lines) with ~20 focused modules.
"""
import os
import sys
import threading
import time
import signal
from pathlib import Path

# Add project root to path
BASE_DIR = Path(__file__).parent.absolute()
sys.path.insert(0, str(BASE_DIR))

# Import all modules
from superguard.config import load_config, SuperGuardConfig
from superguard.models import Alarm, CameraSettings, Zone, Target
from superguard.cameras import CameraManager
from superguard.actuators import ActuatorManager
from superguard.telegram import SuperGuardBot
from superguard.storage import SettingsStore, EnvWriter
from superguard.tuya_cloud import create_tuya_cloud_sync


class SuperGuardApplication:
    """Main application class - wires all components and manages lifecycle."""
    
    def __init__(self, config: SuperGuardConfig):
        self.config = config
        self.running = False
        self.threads: list[threading.Thread] = []
        
        # Core components
        self.bot: SuperGuardBot = None
        self.tuya_sync = None
        self.settings_store = SettingsStore(config)
        self.env_writer = EnvWriter(os.path.join(config.base_dir, "sguard.env"))
        
        # Frame directory
        os.makedirs(config.frame_dir, exist_ok=True)
    
    def initialize(self):
        """Initialize all components in correct order."""
        print("Initializing SuperGuard Alarm...")
        
        # 1. Load persisted settings FIRST (commands need them)
        self.settings_store.load()
        print("  Settings loaded")
        
        # 2. Create bot (which creates CameraManager, ActuatorManager, etc.)
        self.bot = SuperGuardBot(self.config)
        self.bot.settings_store = self.settings_store  # Inject shared store
        self.bot.load_settings()  # This loads camera settings into bot
        print("  Bot created")
        
        # 3. Set up bot menu
        self.bot.set_bot_menu()
        print("  Bot menu set")
        
        # 4. Initialize Tuya Cloud sync (background)
        self.tuya_sync = create_tuya_cloud_sync(self.config)
        if self.tuya_sync:
            print("  Tuya Cloud sync started")
        
        print("Initialization complete")
    
    def start(self):
        """Start all background threads."""
        if self.running:
            return
        
        self.running = True
        print("Starting SuperGuard Alarm...")
        
        # Start Telegram poll loop
        poll_thread = threading.Thread(target=self.bot.poll_loop, daemon=True, name="telegram-poll")
        poll_thread.start()
        self.threads.append(poll_thread)
        print("  Telegram poll loop started")
        
        # Start detection loop (main thread runs this)
        print("  Starting detection loop...")
        try:
            self.bot.detection_loop()
        except KeyboardInterrupt:
            print("\nShutdown requested")
        finally:
            self.shutdown()
    
    def shutdown(self):
        """Graceful shutdown of all components."""
        if not self.running:
            return
        
        self.running = False
        print("\nShutting down...")
        
        # Stop Tuya sync
        if self.tuya_sync:
            self.tuya_sync.stop()
            print("  Tuya Cloud sync stopped")
        
        # Stop cameras
        self.bot.camera_manager.stop_all()
        print("  Cameras stopped")
        
        # Flush settings
        self.settings_store.force_flush()
        print("  Settings flushed")
        
        # Wait for threads (with timeout)
        for t in self.threads:
            if t.is_alive():
                t.join(timeout=2)
        
        print("Shutdown complete")


def kill_other_instances():
    """Kill other python.exe processes running panic_mode or main.py."""
    import subprocess
    try:
        import psutil
        mypid = psutil.Process().pid
        ps_script = f"""$mypid = {mypid}
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
Where-Object {{ $_.CommandLine -match '(panic_mode|main\\.py|superguard)' -and $_.ProcessId -ne $mypid }} |
ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force; Write-Output ('killed ' + $_.ProcessId) }}
"""
        with open("kill_zombies.ps1", "w", encoding="utf-8") as f:
            f.write(ps_script)
        r = subprocess.run(["powershell", "-NoProfile", "-File", "kill_zombies.ps1"],
                          capture_output=True, text=True, timeout=20, encoding="utf-8", errors="ignore")
        if r.stdout.strip():
            print(f"  Killed stale instances: {r.stdout.strip()}")
    except Exception as e:
        print(f"  Zombie kill error: {e}")


def main():
    """Entry point."""
    # Kill any other instances first
    kill_other_instances()
    
    # Load configuration
    config = load_config(str(BASE_DIR))
    
    # Create and run application
    app = SuperGuardApplication(config)
    app.initialize()
    app.start()


if __name__ == "__main__":
    main()