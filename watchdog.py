#!/usr/bin/env python3
"""
SuperGuard Bot Watchdog

Monitors SuperGuard bot health via status.json heartbeat and restarts on failure.

Architecture:
- Checks desktop_state/status.json every 10 seconds (CHECK_INTERVAL)
- Bot writes heartbeat (timestamp) every detection cycle (~1-2s)
- If heartbeat missing for 30 seconds (3 missed checks = MAX_MISSED) -> restart
- 60 second startup grace (STARTUP_GRACE) for bot to initialize cameras/YOLO
- Kills all stale bot processes before starting fresh instance
- Runs as standalone daemon (can be installed as Windows service via NSSM)

State machine:
- STARTUP: waiting for first status.json (up to STARTUP_GRACE)
- HEALTHY: heartbeat OK, missed=0
- DEGRADED: heartbeat missed 1-2 times
- RESTARTING: missed >= MAX_MISSED -> kill_all_bots -> start_bot -> reset

Files:
- status.json: Written by bot (SuperGuardBot.write_status()), watched by watchdog
- watchdog.log: This watchdog's log
- run_bot.py: Bot entry point script

Designed for 24/7 operation on Windows.
"""
import os
import sys
import time
import signal
import subprocess
import json
import psutil
from pathlib import Path
from datetime import datetime

# Configuration constants
BOT_DIR = Path(r"C:\SuperGuard")
STATUS_FILE = BOT_DIR.parent / "desktop_state" / "status.json"
LOG_FILE = BOT_DIR / "watchdog.log"
BOT_SCRIPT = "run_bot.py"
CHECK_INTERVAL = 10  # seconds between heartbeat checks
MAX_MISSED = 3  # 3 missed checks = 30 seconds tolerance after first heartbeat
STARTUP_GRACE = 60  # seconds to wait for first status.json (bot startup time)


def log(msg):
    """Write message to console and log file with timestamp.
    
    Args:
        msg: Message string to log
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def kill_all_bots():
    """Kill all python processes running run_bot.py or main.py.
    
    Finds and terminates stale bot processes to ensure clean restart.
    Safety checks:
    - Only targets python.exe processes
    - Filters by cmdline containing run_bot.py, superguard.main, or panic_mode
    - Never kills current process (os.getpid() check)
    - Never kills watchdog itself (excluded by cmdline filter)
    
    Returns:
        List of killed PIDs
    """
    killed = []
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if proc.info['name'] and 'python' in proc.info['name'].lower():
                cmdline = ' '.join(proc.info['cmdline'] or [])
                if 'run_bot.py' in cmdline or 'superguard.main' in cmdline or 'panic_mode' in cmdline:
                    if proc.info['pid'] != os.getpid():
                        proc.kill()
                        killed.append(proc.info['pid'])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    if killed:
        log(f"Killed stale bot processes: {killed}")
    return killed


def check_heartbeat():
    """Check status.json timestamp - if older than CHECK_INTERVAL, bot is dead.
    
    Reads desktop_state/status.json written by SuperGuardBot.write_status().
    Expected format: {"timestamp": 1234567890.123, ...}
    
    Returns:
        Tuple (status, message):
        - (True, "ok (age Xs)") - heartbeat fresh
        - (False, "heartbeat age Xs > 10s") - heartbeat stale
        - (None, "no status.json" or "status check error: ...") - unknown/startup
    """
    try:
        if not STATUS_FILE.exists():
            return None, "no status.json"  # None = unknown, don't count as miss yet
        
        with open(STATUS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        ts = data.get("timestamp", 0)
        age = time.time() - ts
        
        if age > CHECK_INTERVAL:
            return False, f"heartbeat age {age:.1f}s > {CHECK_INTERVAL}s"
        
        return True, f"ok (age {age:.1f}s)"
    except Exception as e:
        return None, f"status check error: {e}"  # None = unknown


def start_bot():
    """Start bot as detached background process.
    
    Uses subprocess.Popen with:
    - CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS: Independent process group,
      won't receive console signals (Ctrl+C) from watchdog
    - stdout/stderr = DEVNULL: Discard output (bot logs to its own file)
    - cwd=BOT_DIR: Run from SuperGuard directory
    
    Returns:
        PID of started process
    """
    log("Starting bot...")
    proc = subprocess.Popen(
        [sys.executable, BOT_SCRIPT],
        cwd=str(BOT_DIR),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    )
    log(f"Bot started with PID {proc.pid}")
    return proc.pid


def main():
    """Main watchdog loop.
    
    State machine:
    - last_heartbeat_ok: True=healthy, False=degraded
    - missed: consecutive missed heartbeats (reset to 0 on healthy)
    - startup_wait: seconds waited for first heartbeat (resets on first OK)
    
    Flow:
    1. Initial cleanup: kill_all_bots()
    2. Start first bot instance
    3. Loop every CHECK_INTERVAL:
       a. check_heartbeat() -> (ok, msg)
       b. ok=True: reset missed, startup_wait, last_heartbeat_ok=True
       c. ok=False: missed++, log, if missed>=MAX_MISSED -> restart
       d. ok=None: startup_wait++, if >STARTUP_GRACE -> treat as miss
    """
    log("=== WATCHDOG STARTED ===")
    
    # Initial cleanup - ensure no stale processes
    kill_all_bots()
    time.sleep(2)
    
    # Start first instance
    bot_pid = start_bot()
    last_heartbeat_ok = True
    missed = 0
    startup_wait = 0
    
    while True:
        time.sleep(CHECK_INTERVAL)
        
        # Check heartbeat
        ok, msg = check_heartbeat()
        
        if ok is True:
            # Heartbeat healthy
            if not last_heartbeat_ok:
                log(f"Heartbeat restored: {msg}")
            missed = 0
            startup_wait = 0
            last_heartbeat_ok = True
        elif ok is False:
            # Heartbeat stale - bot may be hung/crashed
            missed += 1
            log(f"Heartbeat missed ({missed}/{MAX_MISSED}): {msg}")
            last_heartbeat_ok = False
            
            if missed >= MAX_MISSED:
                log("HEARTBEAT LOST - RESTARTING BOT")
                kill_all_bots()
                time.sleep(2)
                bot_pid = start_bot()
                missed = 0
                startup_wait = 0
                last_heartbeat_ok = True  # Give it a chance to start
        else:
            # ok is None - status.json not ready yet (startup) or read error
            if startup_wait < STARTUP_GRACE:
                startup_wait += CHECK_INTERVAL
                log(f"Waiting for first heartbeat ({startup_wait}/{STARTUP_GRACE}s): {msg}")
            else:
                # Startup grace exceeded - treat as miss
                missed += 1
                log(f"Startup grace exceeded, heartbeat missed ({missed}/{MAX_MISSED}): {msg}")
                last_heartbeat_ok = False
                
                if missed >= MAX_MISSED:
                    log("HEARTBEAT LOST - RESTARTING BOT")
                    kill_all_bots()
                    time.sleep(2)
                    bot_pid = start_bot()
                    missed = 0
                    startup_wait = 0
                    last_heartbeat_ok = True


if __name__ == "__main__":
    # Ensure single watchdog instance
    for proc in psutil.process_iter(['pid', 'cmdline']):
        try:
            cmdline = ' '.join(proc.info['cmdline'] or [])
            if 'watchdog' in cmdline and proc.info['pid'] != os.getpid():
                log(f"Another watchdog running (PID {proc.info['pid']}), exiting")
                sys.exit(0)
        except:
            pass
    
    try:
        main()
    except KeyboardInterrupt:
        log("Watchdog stopped by user")
    except Exception as e:
        log(f"Watchdog crashed: {e}")
        raise