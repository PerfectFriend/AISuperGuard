#!/usr/bin/env python3
"""
SuperGuard Desktop - monitor: polls SuperGuard state and fires events.

Events (via callbacks):
  on_status(state)   - status.json changed
  on_alarm_on(state) - alarm became active
  on_alarm_off(state)- alarm was resolved
  on_frame()         - new alarm live frame available
"""
import threading
import time
from typing import Callable, Optional

from bridge import Bridge, SGState


class Monitor:
    """Background poller for SuperGuard runtime state."""

    def __init__(self, state_dir: str, interval: float = 1.0):
        self.bridge = Bridge(state_dir)
        self.interval = interval
        self.on_status: Optional[Callable[[SGState], None]] = None
        self.on_alarm_on: Optional[Callable[[SGState], None]] = None
        self.on_alarm_off: Optional[Callable[[SGState], None]] = None
        self.on_frame: Optional[Callable[[], None]] = None

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._prev_alarm = False

    # -------------------------------------------------------------- control
    def start(self):
        if self._running:
            return
        self._running = True
        # baseline
        st = self.bridge.read_status()
        if st:
            self._prev_alarm = st.alarm_active
            if self.on_status:
                self.on_status(st)
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)

    # ----------------------------------------------------------------- loop
    def _loop(self):
        while self._running:
            try:
                self._tick()
            except Exception as e:
                print(f"[monitor] error: {e}")
            time.sleep(self.interval)

    def _tick(self):
        # 1. status changes
        if self.bridge.status_changed():
            st = self.bridge.read_status()
            if st and self.on_status:
                self.on_status(st)
            # alarm transitions
            if st:
                if st.alarm_active and not self._prev_alarm:
                    if self.on_alarm_on:
                        self.on_alarm_on(st)
                elif not st.alarm_active and self._prev_alarm:
                    if self.on_alarm_off:
                        self.on_alarm_off(st)
                self._prev_alarm = st.alarm_active
        # 2. new alarm frame
        if self.bridge.has_new_frame():
            if self.on_frame:
                self.on_frame()


if __name__ == "__main__":
    import sys
    m = Monitor(sys.argv[1] if len(sys.argv) > 1 else r"C:\SuperGuard\desktop_state")
    m.on_status = lambda s: print(f"[status] cam={s.active_camera} alarm={s.alarm_active}")
    m.on_alarm_on = lambda s: print(f"🚨 ALARM ON cam={s.alarm_camera}")
    m.on_alarm_off = lambda s: print(f"✅ ALARM OFF")
    m.on_frame = lambda: print("[frame] new live frame")
    print("Мониторинг... Ctrl+C для выхода")
    m.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        m.stop()
