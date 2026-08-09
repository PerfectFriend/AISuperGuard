#!/usr/bin/env python3
"""SuperGuard bot launcher — надёжный запуск через файл (не -m, чтобы
cmdline не содержал 'superguard.main' и kill_other_instances не убивал сам бот)."""
import sys, os
sys.path.insert(0, r"C:\SuperGuard")
from superguard.main import main
if __name__ == "__main__":
    main()
