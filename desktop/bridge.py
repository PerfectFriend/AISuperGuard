#!/usr/bin/env python3
"""
SuperGuard Desktop - bridge: read SuperGuard runtime state.

SuperGuard writes a JSON state file + live alarm frame into a shared
`desktop_state/` directory. This module reads them.

Expected files (written by superguard):
  desktop_state/status.json      - full runtime state (see STATUS_KEYS)
  desktop_state/alarm_live.jpg   - latest live frame during alarm
"""
import json
import os
import time
from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class SGState:
    """Parsed SuperGuard state (mirrors status.json)."""
    active_camera: Optional[int] = None
    auto_mode: bool = False
    alarm_active: bool = False
    alarm_camera: Optional[int] = None
    zone: str = ""
    target: str = ""
    plugs: list = field(default_factory=list)
    camera_names: Dict[int, str] = field(default_factory=dict)
    alarm_frame: str = ""
    timestamp: float = 0.0
    raw: dict = field(default_factory=dict)

    @property
    def active_camera_name(self) -> str:
        return self.camera_names.get(self.active_camera or -1, f"cam{self.active_camera}")

    @property
    def alarm_camera_name(self) -> str:
        return self.camera_names.get(self.alarm_camera or -1, f"cam{self.alarm_camera}")


class Bridge:
    """Reads and watches the SuperGuard desktop_state directory."""

    def __init__(self, state_dir: str):
        self.state_dir = state_dir
        self.status_path = os.path.join(state_dir, "status.json")
        self.alarm_frame_path = os.path.join(state_dir, "alarm_live.jpg")
        self._last_status_hash = None
        self._last_frame_sig = (0.0, 0)  # (mtime, size)
        self._last_state: Optional[SGState] = None

    # ------------------------------------------------------------------ read
    def read_status(self) -> Optional[SGState]:
        """Read and parse status.json. Returns None if missing/invalid."""
        if not os.path.exists(self.status_path):
            return None
        try:
            with open(self.status_path, encoding="utf-8") as f:
                raw = json.load(f)
            state = SGState(
                active_camera=raw.get("active_camera"),
                auto_mode=bool(raw.get("auto_mode", False)),
                alarm_active=bool(raw.get("alarm_active", False)),
                alarm_camera=raw.get("alarm_camera"),
                zone=raw.get("zone", ""),
                target=raw.get("target", ""),
                plugs=list(raw.get("plugs", [])),
                camera_names={int(k): v for k, v in raw.get("camera_names", {}).items()},
                alarm_frame=raw.get("alarm_frame", ""),
                timestamp=float(raw.get("timestamp", 0)),
                raw=raw,
            )
            self._last_state = state
            return state
        except Exception:
            return self._last_state  # keep last known good on transient errors

    def has_new_frame(self) -> bool:
        """True if alarm_live.jpg changed since last call."""
        if not os.path.exists(self.alarm_frame_path):
            return False
        st = os.stat(self.alarm_frame_path)
        sig = (st.st_mtime, st.st_size)
        if sig != self._last_frame_sig:
            self._last_frame_sig = sig
            return True
        return False

    def status_changed(self) -> bool:
        """True if status.json content changed since last call."""
        if not os.path.exists(self.status_path):
            return False
        try:
            with open(self.status_path, "rb") as f:
                h = hash(f.read())
        except Exception:
            return False
        if h != self._last_status_hash:
            self._last_status_hash = h
            return True
        return False

    def read_alarm_frame(self) -> Optional[bytes]:
        """Read current alarm live frame bytes."""
        if not os.path.exists(self.alarm_frame_path):
            return None
        try:
            with open(self.alarm_frame_path, "rb") as f:
                return f.read()
        except Exception:
            return None


if __name__ == "__main__":
    d = sys.argv[1] if len(sys.argv) > 1 else r"C:\SuperGuard\desktop_state"
    b = Bridge(d)
    st = b.read_status()
    if st is None:
        print("status.json не найден — SuperGuard не запущен или не пишет состояние")
    else:
        print(f"active_cam={st.active_camera} auto={st.auto_mode} "
              f"alarm={st.alarm_active} cam={st.alarm_camera}")
        print(f"zone={st.zone} target={st.target} plugs={st.plugs}")
