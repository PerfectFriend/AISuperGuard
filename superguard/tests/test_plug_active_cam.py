#!/usr/bin/env python3
"""
SuperGuard - тест активной камеры и новой команды /plug.

Проверяет:
1. Активная камера устанавливается при тревоге и остаётся активной
2. Активная камера переключается через /cam (switch_camera)
3. /plug 1 2 3 привязывает plug1..plugN к АКТИВНОЙ камере
4. Привязка сохраняется в настройках камеры и применяется при загрузке
5. При тревоге с камеры включаются именно её привязанные розетки
"""
import sys
import time
import json
import numpy as np
import cv2

BASE = r"C:\SuperGuard"
sys.path.insert(0, BASE)

from superguard.config import load_config
from superguard.telegram import SuperGuardBot
from superguard.models import CameraSettings, Alarm

PASS = 0
FAIL = 0
FAILURES = []

def check(name, fn):
    global PASS, FAIL
    try:
        fn()
        PASS += 1
        print(f"  ✓ {name}")
    except Exception as e:
        FAIL += 1
        FAILURES.append((name, e))
        print(f"  ✗ {name}: {type(e).__name__}: {e}")

# --- Моки ---
class MockTelegram:
    def __init__(self):
        self.messages = []
        self.send_photo_calls = []
        self.edit_media_calls = []
        self.next_msg_id = 1000
    
    def send_message(self, chat_id, text, reply_markup=None, parse_mode="HTML"):
        self.messages.append(text)
        return {"message_id": self.next_msg_id}
    
    def send_photo(self, chat_id, photo_bytes, caption, reply_markup=None, parse_mode="HTML"):
        self.send_photo_calls.append((bytes(photo_bytes), caption))
        self.next_msg_id += 1
        return {"message_id": self.next_msg_id}
    
    def edit_message_media(self, chat_id, message_id, photo_bytes, caption, parse_mode="HTML"):
        self.edit_media_calls.append((message_id, bytes(photo_bytes)))
        return {"message_id": message_id}
    
    def edit_message_text(self, chat_id, message_id, text, parse_mode="HTML"):
        return {"message_id": message_id}
    
    def delete_message(self, chat_id, message_id):
        return True
    
    def answer_callback_query(self, cb_id, text):
        return True
    
    def set_my_commands(self, commands, language_code):
        return True
    
    def delete_my_commands(self, language_code):
        return True

class FakeCamera:
    def __init__(self, cam_id):
        self.cam_id = cam_id
        self.frame_counter = 0
        self.alive = True
    
    @property
    def latest(self):
        self.frame_counter += 1
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        cv2.putText(frame, f"cam{self.cam_id} #{self.frame_counter}",
                    (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)
        return frame

class FakeCameraManager:
    def __init__(self):
        self.cameras = {i: FakeCamera(i) for i in range(1, 9)}
        self.active_id = 1
    
    def get(self, cam_id):
        return self.cameras.get(cam_id)
    
    def get_active(self):
        return self.cameras.get(self.active_id)
    
    def set_active(self, cam_id):
        if cam_id in self.cameras:
            self.active_id = cam_id
            return True
        return False
    
    def stop_all(self):
        pass

class FakeActuatorManager:
    """Эмулирует 2 розетки + привязки."""
    def __init__(self):
        self.actuators = {"plug1": "tuya", "plug2": "tuya"}
        self.camera_bindings = {i: ["plug1"] for i in range(1, 5)}
        self.camera_bindings.update({i: ["plug2"] for i in range(5, 9)})
        self.on_calls = []
        self.off_calls = []
    
    def get_for_camera(self, cam_id):
        names = self.camera_bindings.get(cam_id, [])
        return [MockActuator(n, self) for n in names if n in self.actuators]
    
    def get_actuator(self, name):
        return MockActuator(name, self) if name in self.actuators else None
    
    def set_camera_bindings(self, cam_id, names):
        valid = [n for n in names if n in self.actuators]
        self.camera_bindings[cam_id] = valid
    
    def list_all(self):
        result = []
        for name in self.actuators:
            cams = [cid for cid, names in self.camera_bindings.items() if name in names]
            result.append({"name": name, "type": "tuya", "status": "ONLINE",
                           "status_icon": "🟢", "cameras": cams})
        return result
    
    def test_all(self):
        return [{"name": n, "status": "OK", "reconnected": False} for n in self.actuators]

class MockActuator:
    def __init__(self, name, mgr):
        self.name = name
        self._mgr = mgr
    
    def turn_on(self):
        self._mgr.on_calls.append(self.name)
        return True
    
    def turn_off(self):
        self._mgr.off_calls.append(self.name)
        return True
    
    def get_status(self):
        return True

def make_bot():
    config = load_config(BASE + r"\superguard")
    bot = SuperGuardBot.__new__(SuperGuardBot)
    bot.config = config
    bot.tg = MockTelegram()
    bot.camera_manager = FakeCameraManager()
    bot.actuator_manager = FakeActuatorManager()
    bot.camera_settings = {}
    bot.active_camera_id = 1
    bot.lang = "ru"
    bot._load_i18n()
    bot.alarm = Alarm()
    bot.frame_dir = config.frame_dir
    return bot

# --- Тесты ---

def test_alarm_sets_active_camera():
    """Тревога на камере 5 делает её активной."""
    bot = make_bot()
    assert bot.active_camera_id == 1
    frame = bot.camera_manager.cameras[5].latest
    bot.trigger_alarm("TEST", frame, cam_id=5)
    assert bot.alarm.alarm_camera_id == 5
    assert bot.active_camera_id == 5, f"active={bot.active_camera_id}, ожидал 5"
    assert bot.camera_manager.active_id == 5
    bot.alarm.deactivate()

def test_active_camera_stays_after_alarm():
    """После снятия тревоги активная камера НЕ сбрасывается."""
    bot = make_bot()
    frame = bot.camera_manager.cameras[5].latest
    bot.trigger_alarm("TEST", frame, cam_id=5)
    bot.cancel_alarm()
    assert not bot.alarm.is_active
    assert bot.active_camera_id == 5, f"active={bot.active_camera_id} после отмены (ожидал 5 - камера остаётся активной)"

def test_cam_switches_active():
    """Команда /cam 3 переключает активную камеру на 3."""
    bot = make_bot()
    bot.active_camera_id = 5
    bot.switch_camera(3)
    assert bot.active_camera_id == 3
    assert bot.camera_manager.active_id == 3

def test_plug_binds_to_active_camera():
    """/plug 1 2 привязывает plug1, plug2 к активной камере."""
    bot = make_bot()
    bot.active_camera_id = 2
    bot.set_active_camera_plugs(["plug1", "plug2"])
    assert bot.actuator_manager.camera_bindings[2] == ["plug1", "plug2"], \
        bot.actuator_manager.camera_bindings[2]
    # Сохранено в настройках
    settings = bot.get_camera_settings(2)
    assert settings.actuator == ["plug1", "plug2"], settings.actuator
    # Сообщение отправлено
    assert any("plug1, plug2" in m for m in bot.tg.messages), bot.tg.messages

def test_plug_unknown_rejected():
    """/plug 9 (несуществующая) отклоняется."""
    bot = make_bot()
    bot.active_camera_id = 2
    bot.set_active_camera_plugs(["plug9"])
    assert bot.actuator_manager.camera_bindings[2] != ["plug9"]
    assert any("не найдены" in m for m in bot.tg.messages)

def test_alarm_uses_camera_plugs():
    """При тревоге с камеры 5 включается plug2 (её привязка)."""
    bot = make_bot()
    # Камера 5 по умолчанию на plug2
    frame = bot.camera_manager.cameras[5].latest
    bot.trigger_alarm("TEST", frame, cam_id=5)
    assert bot.actuator_manager.on_calls == ["plug2"], bot.actuator_manager.on_calls
    bot.cancel_alarm()
    assert bot.actuator_manager.off_calls == ["plug2"], bot.actuator_manager.off_calls

def test_alarm_uses_custom_plugs():
    """После /plug 1 2 3 на камере 4 тревога включает plug1+plug2+plug3."""
    bot = make_bot()
    bot.active_camera_id = 4
    bot.set_active_camera_plugs(["plug1", "plug2"])
    frame = bot.camera_manager.cameras[4].latest
    bot.trigger_alarm("TEST", frame, cam_id=4)
    assert sorted(bot.actuator_manager.on_calls) == ["plug1", "plug2"], bot.actuator_manager.on_calls
    bot.cancel_alarm()
    assert sorted(bot.actuator_manager.off_calls) == ["plug1", "plug2"]

def test_persistence_roundtrip():
    """Привязка сохраняется в JSON и восстанавливается load_settings."""
    import tempfile, os
    bot = make_bot()
    bot.active_camera_id = 3
    bot.set_active_camera_plugs(["plug2"])
    
    # Проверяем to_dict/from_dict
    settings = bot.get_camera_settings(3)
    d = settings.to_dict()
    assert d["actuator"] == ["plug2"], d
    restored = CameraSettings.from_dict(d)
    assert restored.actuator == ["plug2"], restored.actuator
    
    # Легаси: строка -> список
    legacy = CameraSettings.from_dict({"zone": None, "target": "", "actuator": "plug1"})
    assert legacy.actuator == ["plug1"], legacy.actuator

print("=" * 60)
print("SUPERGUARD: ТЕСТ АКТИВНОЙ КАМЕРЫ И КОМАНДЫ /PLUG")
print("=" * 60)

print("\n[1] Активная камера при тревоге")
check("тревога делает камеру активной", test_alarm_sets_active_camera)
check("камера остаётся активной после снятия", test_active_camera_stays_after_alarm)
check("/cam переключает активную камеру", test_cam_switches_active)

print("\n[2] Команда /plug")
check("/plug 1 2 -> активной камере", test_plug_binds_to_active_camera)
check("несуществующая розетка отклоняется", test_plug_unknown_rejected)

print("\n[3] Тревога и розетки камеры")
check("тревога камеры 5 -> plug2", test_alarm_uses_camera_plugs)
check("после /plug - свои розетки", test_alarm_uses_custom_plugs)

print("\n[4] Сохранение")
check("JSON roundtrip + легаси-миграция", test_persistence_roundtrip)

print("\n" + "=" * 60)
print(f"ИТОГ: {PASS} PASS, {FAIL} FAIL")
if FAILURES:
    for name, e in FAILURES:
        print(f"  ✗ {name}: {e}")
print("=" * 60)
sys.exit(1 if FAIL else 0)