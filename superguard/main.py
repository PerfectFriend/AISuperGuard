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

from superguard.logging_config import get_logger, setup_logging

# Initialize structured logging
logger = get_logger(__name__)
setup_logging(
    log_level=os.environ.get("SG_LOG_LEVEL", "INFO"),
    log_file=os.environ.get("SG_LOG_FILE"),
    json_format=os.environ.get("SG_LOG_JSON", "true").lower() == "true"
)


class SuperGuardApplication:
    """Main application class - wires all components and manages lifecycle.

    Responsibilities:
    - Initialize all subsystems in correct dependency order
    - Manage background threads (Telegram poll, Tuya Cloud sync)
    - Run detection loop in main thread
    - Handle graceful shutdown (SIGINT/SIGTERM)
    - Provide shared SettingsStore and EnvWriter to components

    Initialization order (critical for dependencies):
    1. SettingsStore.load() - must be first, bot commands need persisted settings
    2. SuperGuardBot creation - creates CameraManager, ActuatorManager, AlarmManager
    3. Bot.load_settings() - loads camera settings into bot from shared store
    4. Bot.set_bot_menu() - sets Telegram command menu
    5. Tuya Cloud sync - background thread for cloud-based IP discovery

    Threading model:
    - Main thread: detection_loop() (CPU-intensive YOLO processing)
    - Background thread: bot.poll_loop() (Telegram long-poll)
    - Background thread: TuyaCloudSync (periodic cloud API calls)
    - Per-alarm threads: bot._update_loop(cam_id) (spawned on trigger)
    """

    def __init__(self, config: SuperGuardConfig):
        self.config = config
        self.running = False
        self.threads: list[threading.Thread] = []

        # Core components (initialized in initialize())
        self.bot: SuperGuardBot = None
        self.tuya_sync = None
        self.settings_store = SettingsStore(config)
        self.env_writer = EnvWriter(os.path.join(config.base_dir, "sguard.env"))

        # Frame directory for saved alarm frames
        os.makedirs(config.frame_dir, exist_ok=True)

    def initialize(self):
        """Initialize all components in correct order.

        This separation from __init__ allows:
        - Clean error handling during init
        - Dependency injection (settings_store shared with bot)
        - Easy testing of individual components
        """
        logger.info("Initializing SuperGuard Alarm...")

        # 1. Load persisted settings FIRST (commands need them)
        self.settings_store.load()
        logger.info("Settings loaded")

        # 2. Create bot (which creates CameraManager, ActuatorManager, etc.)
        self.bot = SuperGuardBot(self.config)
        self.bot.settings_store = self.settings_store  # Inject shared store
        self.bot.load_settings()  # This loads camera settings into bot
        logger.info("Bot created")

        # 3. Set up bot menu
        self.bot.set_bot_menu()
        logger.info("Bot menu set")

        # 4. Initialize Tuya Cloud sync (background)
        self.tuya_sync = create_tuya_cloud_sync(self.config, actuator_manager=self.bot.actuator_manager)
        if self.tuya_sync:
            logger.info("Tuya Cloud sync started")

        logger.info("Initialization complete")

    def start(self):
        """Start all background threads and run detection loop.

        Detection loop runs in MAIN thread (blocking) because:
        - YOLO inference is CPU-intensive, should not be in daemon thread
        - Easier to handle KeyboardInterrupt for clean shutdown
        - Main thread owns the process lifetime

        Background threads:
        - telegram-poll: bot.poll_loop() - long-poll getUpdates
        - tuya-cloud-sync: tuya_sync thread - periodic cloud API
        """
        if self.running:
            return

        self.running = True
        logger.info("Starting SuperGuard Alarm...")

        # Start Telegram poll loop
        poll_thread = threading.Thread(target=self.bot.poll_loop, daemon=True, name="telegram-poll")
        poll_thread.start()
        self.threads.append(poll_thread)
        logger.info("Telegram poll loop started")

        # Start detection loop (main thread runs this)
        logger.info("Starting detection loop...")
        try:
            self.bot.detection_loop()
        except KeyboardInterrupt:
            logger.info("Shutdown requested")
        except Exception as e:
            logger.exception("Detection loop CRASHED: %s", e)
        finally:
            self.shutdown()

    def shutdown(self):
        """Graceful shutdown of all components.

        Order matters:
        1. Stop Tuya sync (background thread)
        2. Stop cameras (releases VideoCapture, HTTP sessions)
        3. Flush settings (force_flush cancels debounce timer)
        4. Join background threads with timeout

        Uses timeout on thread joins to avoid hanging on stuck threads.
        """
        if not self.running:
            return

        self.running = False
        logger.info("Shutting down...")

        # Stop Tuya sync
        if self.tuya_sync:
            self.tuya_sync.stop()
            logger.info("Tuya Cloud sync stopped")

        # Stop cameras
        self.bot.camera_manager.stop_all()
        logger.info("Cameras stopped")

        # Flush settings
        self.settings_store.force_flush()
        logger.info("Settings flushed")

        # Wait for threads (with timeout)
        for t in self.threads:
            if t.is_alive():
                t.join(timeout=2)

        logger.info("Shutdown complete")


def kill_other_instances():
    """Kill other python.exe processes running panic_mode or main.py (safe, cmdline-filtered).

    Prevents multiple bot instances from polling getUpdates simultaneously (causes 409 Conflict).

    Safety measures:
    - Never kills current process (mypid check)
    - Only targets python.exe processes
    - Filters by cmdline: 'superguard.main', 'superguard/main.py', 'panic_mode'
    - EXCLUDES watchdog process (watchdog manages the service)
    - Uses psutil for cross-platform process inspection

    Called at startup before initializing to ensure clean state.
    """
    try:
        import psutil
        mypid = os.getpid()
        killed = []
        for proc in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                if proc.info["pid"] == mypid:
                    continue
                name = (proc.info["name"] or "").lower()
                if "python" not in name:
                    continue
                cmdline = " ".join(proc.info["cmdline"] or [])
                cl = cmdline.lower()
                if "watchdog" in cl:
                    continue  # never kill the watchdog itself
                if "superguard.main" in cl or "superguard\\main.py" in cl or "superguard/main.py" in cl or "panic_mode" in cl:
                    proc.kill()
                    killed.append(proc.info["pid"])
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        if killed:
            logger.info("Killed stale instances: %s", killed)
    except Exception as e:
        logger.error("Zombie kill error: %s", e)


def main():
    """Entry point.

    Flow:
    1. Kill other instances (prevents 409 Conflict)
    2. Load configuration (from sguard.env + defaults)
    3. Create SuperGuardApplication
    4. Initialize (loads settings, creates bot, starts Tuya sync)
    5. Start (runs detection loop, manages threads)
    """
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