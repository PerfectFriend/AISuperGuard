#!/usr/bin/env python3
"""
SuperGuard Hotspot Monitor Service
- Monitors hotspot connectivity
- Auto-restarts bot on WiFi reconnection
- Runs as Windows service with auto-start
"""
import sys
import os
import time
import subprocess
import threading
import signal
import logging
from pathlib import Path

# Windows service imports
try:
    import win32serviceutil
    import win32service
    import win32event
    import servicemanager
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False

# Configuration
PROJECT_DIR = Path(r"C:\SuperGuard")
BOT_SCRIPT = PROJECT_DIR / "run_bot.py"
HOTSPOT_IP = "192.168.137.1"  # Typical hotspot gateway
CHECK_INTERVAL = 10  # seconds
RESTART_DELAY = 5  # seconds after network recovery

# Setup logging
log_file = PROJECT_DIR / "hotspot_monitor.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class HotspotMonitor:
    """Monitors hotspot connectivity and manages bot process."""
    
    def __init__(self):
        self.bot_process = None
        self.running = False
        self.network_up = False
        self.lock = threading.Lock()
        
    def check_hotspot(self) -> bool:
        """Check if hotspot gateway is reachable."""
        try:
            # Ping hotspot gateway
            result = subprocess.run(
                ['ping', '-n', '1', '-w', '2000', '192.168.137.1'],
                capture_output=True,
                timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            return result.returncode == 0
        except Exception as e:
            logger.debug(f"Ping error: {e}")
            return False
    
    def start_bot(self):
        """Start the bot process."""
        with self.lock:
            if self.bot_process and self.bot_process.poll() is None:
                logger.info("Bot already running")
                return
            
            logger.info("Starting SuperGuard bot...")
            try:
                self.bot_process = subprocess.Popen(
                    [sys.executable, str(BOT_SCRIPT)],
                    cwd=str(PROJECT_DIR),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
                )
                logger.info(f"Bot started with PID {self.bot_process.pid}")
            except Exception as e:
                logger.error(f"Failed to start bot: {e}")
                self.bot_process = None
    
    def stop_bot(self):
        """Stop the bot process gracefully."""
        with self.lock:
            if self.bot_process and self.bot_process.poll() is None:
                logger.info("Stopping bot...")
                try:
                    # Send Ctrl+Break to process group (Windows equivalent of SIGTERM)
                    self.bot_process.send_signal(signal.CTRL_BREAK_EVENT)
                    # Wait for graceful shutdown
                    self.bot_process.wait(timeout=10)
                    logger.info("Bot stopped gracefully")
                except subprocess.TimeoutExpired:
                    logger.warning("Bot didn't stop gracefully, killing...")
                    self.bot_process.kill()
                    self.bot_process.wait(timeout=5)
                except Exception as e:
                    logger.error(f"Error stopping bot: {e}")
                finally:
                    self.bot_process = None
            else:
                self.bot_process = None
    
    def monitor_loop(self):
        """Main monitoring loop."""
        logger.info("Starting hotspot monitor loop")
        self.running = True
        last_network_state = False
        bot_restart_pending = False
        
        while self.running:
            try:
                # Check hotspot connectivity
                current_network = self.check_hotspot()
                
                # Network state changed
                if current_network != last_network_state:
                    if current_network:
                        logger.info("Hotspot UP - network recovered")
                        if bot_restart_pending:
                            logger.info("Restarting bot after network recovery...")
                            time.sleep(RESTART_DELAY)
                            self.start_bot()
                            bot_restart_pending = False
                    else:
                        logger.warning("Hotspot DOWN - network lost")
                        self.stop_bot()
                        bot_restart_pending = True
                    
                    last_network_state = current_network
                
                # Check if bot process died unexpectedly
                if self.bot_process and self.bot_process.poll() is not None:
                    logger.warning("Bot process died unexpectedly!")
                    if current_network:
                        logger.info("Restarting bot...")
                        time.sleep(RESTART_DELAY)
                        self.start_bot()
                    else:
                        bot_restart_pending = True
                
                time.sleep(CHECK_INTERVAL)
                
            except Exception as e:
                logger.error(f"Monitor loop error: {e}")
                time.sleep(CHECK_INTERVAL)
        
        # Cleanup on exit
        logger.info("Monitor loop stopping")
        self.stop_bot()


class SuperGuardService:
    """Windows Service wrapper."""
    
    def __init__(self):
        self.monitor = HotspotMonitor()
        self.stop_event = threading.Event()
        
    def start(self):
        logger.info("Starting SuperGuard Hotspot Monitor Service")
        self.monitor.monitor_loop()
    
    def stop(self):
        logger.info("Stopping SuperGuard Hotspot Monitor Service")
        self.monitor.running = False
        self.monitor.stop_bot()


def run_foreground():
    """Run in foreground (for testing/debugging)."""
    monitor = HotspotMonitor()
    try:
        monitor.monitor_loop()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    finally:
        monitor.stop_bot()


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'install':
        if not HAS_WIN32:
            logger.error("pywin32 required for service installation")
            sys.exit(1)
        win32serviceutil.HandleCommandLine(SuperGuardService)
    elif len(sys.argv) > 1 and sys.argv[1] == 'service':
        if not HAS_WIN32:
            logger.error("pywin32 required for service mode")
            sys.exit(1)
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(SuperGuardService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        # Foreground mode
        run_foreground()