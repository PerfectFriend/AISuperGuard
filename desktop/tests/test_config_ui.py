#!/usr/bin/env python3
"""Tests for config_ui helpers (GUI-free)."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config_ui import (parse_cameras_text, cameras_to_text,  # noqa: E402
                       validate_actuators_json, build_env_content,
                       read_env, write_env)

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

def test_parse_cameras():
    cams = parse_cameras_text("5=https://x/live.m3u8|Камера 5\n6=rtsp://u:p@1.2.3.4/stream\n# comment\n\n")
    assert 5 in cams and cams[5] == ("https://x/live.m3u8", "Камера 5"), cams
    assert 6 in cams and cams[6] == ("rtsp://u:p@1.2.3.4/stream", ""), cams
    assert len(cams) == 2

def test_roundtrip():
    cams = {2: ("rtsp://a", "Cam 2"), 3: ("https://b.jpg", "")}
    text = cameras_to_text(cams)
    back = parse_cameras_text(text)
    assert back == cams, (text, back)

def test_validate_actuators():
    ok, data = validate_actuators_json('[{"name": "plug1", "type": "tuya", "cameras": [1]}]')
    assert ok and data[0]["name"] == "plug1"
    ok, err = validate_actuators_json('{bad json')
    assert not ok and "JSON" in str(err)
    ok, err = validate_actuators_json('{"name": "x"}')
    assert not ok

def test_build_env_content():
    env = {"SG_TELEGRAM_BOT_TOKEN": "tok", "SG_CHAT_ID": "1",
           "TUYA_ACCESS_ID": "aid", "SG_CAM_URL": "https://cam1"}
    cams = {2: ("rtsp://cam2", "Cam 2"), 3: ("https://cam3.jpg", "")}
    content = build_env_content(env, cams, '[{"name": "plug1"}]')
    assert "SG_TELEGRAM_BOT_TOKEN=tok" in content
    assert "SG_CAM2_URL=rtsp://cam2" in content
    assert "SG_CAM2_NAME=Cam 2" in content
    assert "SG_CAM3_URL=https://cam3.jpg" in content
    assert "SG_ACTUATORS=[{\"name\": \"plug1\"}]" in content
    assert "TUYA_ACCESS_ID=aid" in content
    assert "SG_CAM1" not in content or "SG_CAM1_NAME" not in content  # cam1 via SG_CAM_URL
    # camera 1 url must be in SG_CAM_URL
    assert "SG_CAM_URL=https://cam1" in content

def test_write_read_env(tmp=None):
    tmp = tempfile.mkdtemp(prefix="sg-cfg-")
    path = os.path.join(tmp, "sguard.env")
    write_env(path, "A=1\nB=two\n")
    env = read_env(path)
    assert env == {"A": "1", "B": "two"}, env
    # atomic: no .tmp leftover
    assert not os.path.exists(path + ".tmp")

print("CONFIG-UI TESTS")
check("parse cameras text", test_parse_cameras)
check("cameras roundtrip", test_roundtrip)
check("validate actuators JSON", test_validate_actuators)
check("build env content", test_build_env_content)
check("atomic write/read", test_write_read_env)
print(f"ИТОГ: {PASS} PASS, {FAIL} FAIL")
sys.exit(1 if FAIL else 0)