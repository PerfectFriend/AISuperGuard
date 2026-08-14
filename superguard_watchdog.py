#!/usr/bin/env python3
"""
SuperGuard Alarm - Standalone Launcher with Watchdog
Runs SuperGuard as a reliable service with auto-restart and health checks.
"""

import os
import sys
import time
import signal
import subprocess
import threading
from pathlib import Path

BASE_DIR = Path(__file__).parent.absolute()
SUPERGUARD_DIR = BASE_DIR / "superguard"
HERMES_VENV = Path(r"C:\Users\tomas\AppData\Local\hermes\hermes-agent\venv")

class SuperGuardWatchdog:
    def __init__(self):
        self.process = None
        self.running = False
        self.restart_count = 0
        self.max_restarts = 10
        self.restart_window = 300  # 5 minutes
        self.restart_times = []
        
    def start_superguard(self):
        """Start SuperGuard main process."""
        env = os.environ.copy()
        env["PYTHONPATH"] = str(BASE_DIR) + ";" + env.get("PYTHONPATH", "")
        env["VIRTUAL_ENV"] = str(HERMES_VENV)
        
        python_exe = HERMES_VENV / "Scripts" / "python.exe"
        if not python_exe.exists():
            python_exe = sys.executable
        
        cmd = [str(python_exe), str(BASE_DIR / "run_bot.py")]
        
        print(f"[{time.strftime('%H:%M:%S')}] Starting SuperGuard: {' '.join(cmd)}")
        
        self.process = subprocess.Popen(
            cmd,
            cwd=str(SUPERGUARD_DIR),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1
        )
        
        # Start log reader thread
        threading.Thread(target=self._read_logs, daemon=True).start()
        
    def _read_logs(self):
        """Read and print logs from SuperGuard process."""
        if not self.process or not self.process.stdout:
            return
            
        for line in self.process.stdout:
            if line:
                print(f"[{time.strftime('%H:%M:%S')}] SG: {line.rstrip()}")
    
    def is_healthy(self):
        """Check if SuperGuard process is alive."""
        if self.process is None:
            return False
        return self.process.poll() is None
    
    def stop(self):
        """Stop SuperGuard gracefully."""
        self.running = False
        if self.process and self.process.poll() is None:
            print(f"[{time.strftime('%H:%M:%S')}] Stopping SuperGuard (PID {self.process.pid})...")
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                print(f"[{time.strftime('%H:%M:%S')}] Force killing SuperGuard...")
                self.process.kill()
                self.process.wait()
    
    def run(self):
        """Main watchdog loop."""
        self.running = True
        print(f"[{time.strftime('%H:%M:%S')}] SuperGuard Watchdog started")
        
        # Kill any existing instances first
        self._kill_existing()
        
        while self.running:
            if not self.is_healthy():
                if self.process is not None:
                    exit_code = self.process.poll()
                    print(f"[{time.strftime('%H:%M:%S')}] SuperGuard exited with code {exit_code}")
                
                # Check restart rate limiting
                now = time.time()
                self.restart_times = [t for t in self.restart_times if now - t < self.restart_window]
                
                if len(self.restart_times) >= self.max_restarts:
                    print(f"[{time.strftime('%H:%M:%S')}] Too many restarts ({len(self.restart_times)}/{self.max_restarts} in {self.restart_window}s). Waiting...")
                    time.sleep(60)
                    continue
                
                self.restart_times.append(now)
                self.restart_count += 1
                print(f"[{time.strftime('%H:%M:%S')}] Restarting SuperGuard (attempt #{self.restart_count})...")
                
                self.start_superguard()
            
            time.sleep(5)
    
    def _kill_existing(self):
        """Kill other python processes running superguard."""
        import psutil
        mypid = os.getpid()
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                if proc.info['name'] == 'python.exe' and proc.info['pid'] != mypid:
                    cmdline = ' '.join(proc.info['cmdline'] or [])
                    if 'superguard' in cmdline.lower() or 'panic_mode' in cmdline.lower():
                        print(f"[{time.strftime('%H:%M:%S')}] Killing stale: PID {proc.info['pid']} - {cmdline[:80]}")
                        proc.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

def main():
    watchdog = SuperGuardWatchdog()
    
    def signal_handler(sig, frame):
        print(f"\n[{time.strftime('%H:%M:%S')}] Shutdown signal received")
        watchdog.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        watchdog.run()
    except KeyboardInterrupt:
        watchdog.stop()

if __name__ == "__main__":
    main()