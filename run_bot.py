#!/usr/bin/env python3
"""SuperGuard bot launcher — надёжный запуск через файл (не -m, чтобы
cmdline не содержал 'superguard.main' и kill_other_instances не убивал сам бот)."""
import sys, os, time
sys.path.insert(0, r"C:\SuperGuard")
print(f"[run_bot {os.getpid()}] start {time.strftime('%H:%M:%S')}", flush=True)
from superguard.main import main
print(f"[run_bot {os.getpid()}] main imported, calling", flush=True)
if __name__ == "__main__":
    main()
