import os
import sys
import threading
import time
import signal
from pathlib import Path
BASE_DIR = Path(__file__).parent.absolute()
sys.path.insert(0, str(BASE_DIR))
from superguard.config import load_config, SuperGuardConfig
from superguard.models import Alarm, CameraSettings, Zone, Target
from superguard.cameras import CameraManager
from superguard.actuators import ActuatorManager
from superguard.telegram import SuperGuardBot
from superguard.storage import SettingsStore, EnvWriter
from superguard.tuya_cloud import create_tuya_cloud_sync

class SuperGuardApplication:

    def __init__(self, config: SuperGuardConfig):
        self.config = config
        self.running = False
        self.threads: list[threading.Thread] = []
        self.bot: SuperGuardBot = None
        self.tuya_sync = None
        self.settings_store = SettingsStore(config)
        self.env_writer = EnvWriter(os.path.join(config.base_dir, 'sguard.env'))
        os.makedirs(config.frame_dir, exist_ok=True)

    def initialize(self):
        print('Initializing SuperGuard Alarm...')
        self.settings_store.load()
        print('  Settings loaded')
        self.bot = SuperGuardBot(self.config)
        self.bot.settings_store = self.settings_store
        self.bot.load_settings()
        print('  Bot created')
        self.bot.set_bot_menu()
        print('  Bot menu set')
        self.tuya_sync = create_tuya_cloud_sync(self.config)
        if self.tuya_sync:
            print('  Tuya Cloud sync started')
        print('Initialization complete')

    def start(self):
        if self.running:
            return
        self.running = True
        print('Starting SuperGuard Alarm...')
        poll_thread = threading.Thread(target=self.bot.poll_loop, daemon=True, name='telegram-poll')
        poll_thread.start()
        self.threads.append(poll_thread)
        print('  Telegram poll loop started')
        print('  Starting detection loop...')
        try:
            self.bot.detection_loop()
        except KeyboardInterrupt:
            print('\nShutdown requested')
        except Exception as e:
            print(f'\nDetection loop CRASHED: {e}')
            import traceback
            traceback.print_exc()
        finally:
            self.shutdown()

    def shutdown(self):
        if not self.running:
            return
        self.running = False
        print('\nShutting down...')
        if self.tuya_sync:
            self.tuya_sync.stop()
            print('  Tuya Cloud sync stopped')
        self.bot.camera_manager.stop_all()
        print('  Cameras stopped')
        self.settings_store.force_flush()
        print('  Settings flushed')
        for t in self.threads:
            if t.is_alive():
                t.join(timeout=2)
        print('Shutdown complete')

def kill_other_instances():
    try:
        import psutil
        mypid = os.getpid()
        killed = []
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                if proc.info['pid'] == mypid:
                    continue
                name = (proc.info['name'] or '').lower()
                if 'python' not in name:
                    continue
                cmdline = ' '.join(proc.info['cmdline'] or [])
                cl = cmdline.lower()
                if 'watchdog' in cl:
                    continue
                if 'superguard.main' in cl or 'superguard\\main.py' in cl or 'superguard/main.py' in cl or ('panic_mode' in cl):
                    proc.kill()
                    killed.append(proc.info['pid'])
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        if killed:
            print(f'  Killed stale instances: {killed}')
    except Exception as e:
        print(f'  Zombie kill error: {e}')

def main():
    kill_other_instances()
    config = load_config(str(BASE_DIR))
    app = SuperGuardApplication(config)
    app.initialize()
    app.start()
if __name__ == '__main__':
    main()