#!/usr/bin/env python3
"""Tests for bridge + monitor (SuperGuard state watching)."""
import json
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bridge import Bridge, SGState  # noqa: E402
from monitor import Monitor  # noqa: E402

PASS = FAIL = 0

def check(name, fn):
    global PASS, FAIL
    try:
        fn()
        PASS += 1
        print(f"  ✓ {name}")
    except Exception as e:
        FAIL += 1
        print(f"  ✗ {name}: {type(e).__name__}: {e}")

def make_state_dir():
    d = tempfile.mkdtemp(prefix="sg-state-")
    return d

def write_status(d, **kw):
    data = {
        "active_camera": 2, "auto_mode": True, "alarm_active": False,
        "alarm_camera": None, "zone": "N3x4 C9", "target": "red car",
        "plugs": ["plug1"], "camera_names": {"1": "Cam1", "2": "Cam2"},
        "alarm_frame": "", "timestamp": time.time(),
    }
    data.update(kw)
    with open(os.path.join(d, "status.json"), "w", encoding="utf-8") as f:
        json.dump(data, f)

def test_read_status():
    d = make_state_dir()
    write_status(d)
    b = Bridge(d)
    st = b.read_status()
    assert st is not None
    assert st.active_camera == 2
    assert st.zone == "N3x4 C9"
    assert st.active_camera_name == "Cam2"
    assert st.alarm_active is False

def test_missing_status():
    d = make_state_dir()
    b = Bridge(d)
    assert b.read_status() is None
    assert b.status_changed() is False

def test_status_changed_detection():
    d = make_state_dir()
    write_status(d)
    b = Bridge(d)
    b.read_status()
    assert b.status_changed() is True   # first read after file exists
    # rewrite different content
    time.sleep(0.05)
    write_status(d, zone="N2x2 C1")
    assert b.status_changed() is True

def test_frame_detection():
    d = make_state_dir()
    b = Bridge(d)
    assert b.has_new_frame() is False
    path = os.path.join(d, "alarm_live.jpg")
    with open(path, "wb") as f:
        f.write(b"jpegdata")
    assert b.has_new_frame() is True
    assert b.has_new_frame() is False  # unchanged
    with open(path, "wb") as f:
        f.write(b"jpegdata2")
    assert b.has_new_frame() is True

def test_monitor_events():
    d = make_state_dir()
    write_status(d)
    m = Monitor(d, interval=0.2)
    events = {"on": 0, "off": 0, "status": 0}
    m.on_alarm_on = lambda s: events.__setitem__("on", events["on"] + 1)
    m.on_alarm_off = lambda s: events.__setitem__("off", events["off"] + 1)
    m.on_status = lambda s: events.__setitem__("status", events["status"] + 1)
    m.start()
    time.sleep(0.5)
    # trigger alarm
    write_status(d, alarm_active=True, alarm_camera=2, timestamp=time.time())
    time.sleep(0.6)
    # resolve
    write_status(d, alarm_active=False, timestamp=time.time())
    time.sleep(0.6)
    m.stop()
    assert events["on"] >= 1, f"alarm_on events: {events}"
    assert events["off"] >= 1, f"alarm_off events: {events}"
    assert events["status"] >= 2, f"status events: {events}"

print("BRIDGE/MONITOR TESTS")
check("read status", test_read_status)
check("missing status", test_missing_status)
check("status changed", test_status_changed_detection)
check("frame detection", test_frame_detection)
check("monitor alarm events", test_monitor_events)
print(f"ИТОГ: {PASS} PASS, {FAIL} FAIL")
sys.exit(1 if FAIL else 0)