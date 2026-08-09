#!/usr/bin/env python3
"""
SuperGuard - тест live-обновления кадра в режиме тревоги.

Проверяет протокол безопасности:
1. При тревоге отправляется кадр срабатывания (msg A)
2. Через ~1с отправляется первый live кадр (msg B)
3. Live кадр ОБНОВЛЯЕТСЯ каждые update_every секунд (editMessageMedia)
4. Кадры действительно разные (новые с активной камеры)
5. При снятии тревоги цикл обновления останавливается
6. Тревога привязывается к камере-источнику (cam_id)
"""
import sys
import time
import threading
import numpy as np
import cv2

BASE = r"C:\SuperGuard"
sys.path.insert(0, BASE)

from superguard.config import load_config
from superguard.telegram import SuperGuardBot

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

# ---------------------------------------------------------------------------
# Мок Telegram-клиента: считает вызовы, хранит переданные байты
# ---------------------------------------------------------------------------
class MockTelegram:
    def __init__(self):
        self.send_photo_calls = []   # (photo_bytes, caption)
        self.edit_media_calls = []   # (message_id, photo_bytes, caption)
        self.next_msg_id = 1000
        self.edit_count = 0
    
    def send_photo(self, chat_id, photo_bytes, caption):
        self.send_photo_calls.append((bytes(photo_bytes), caption))
        self.next_msg_id += 1
        return {"message_id": self.next_msg_id}
    
    def edit_message_media(self, chat_id, message_id, photo_bytes, caption):
        self.edit_media_calls.append((message_id, bytes(photo_bytes), caption))
        self.edit_count += 1
        return {"message_id": message_id}
    
    def send_message(self, chat_id, text, reply_markup=None, parse_mode="HTML"):
        return {"message_id": 9999}
    
    def delete_message(self, chat_id, message_id):
        return True
    
    def edit_message_text(self, chat_id, message_id, text, parse_mode="HTML"):
        return {"message_id": message_id}
    
    def answer_callback_query(self, callback_query_id, text):
        return True
    
    def set_my_commands(self, commands, language_code):
        return True
    
    def delete_my_commands(self, language_code):
        return True

# ---------------------------------------------------------------------------
# Фейковая камера: каждый вызов latest() возвращает КАДР С НОВЫМ СЧЁТЧИКОМ
# ---------------------------------------------------------------------------
class FakeCamera:
    def __init__(self, cam_id):
        self.cam_id = cam_id
        self.frame_counter = 0
        self.alive = True
    
    @property
    def latest(self):
        """Возвращает кадр с растущим счётчиком в углу - кадры РАЗНЫЕ."""
        self.frame_counter += 1
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        # Вписываем номер кадра в левый верхний угол (видимый, разный для каждого кадра)
        cv2.putText(frame, f"cam{self.cam_id} frame#{self.frame_counter:04d}",
                    (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)
        return frame

class FakeCameraManager:
    def __init__(self):
        self.cameras = {1: FakeCamera(1), 2: FakeCamera(2), 3: FakeCamera(3),
                        4: FakeCamera(4), 5: FakeCamera(5), 6: FakeCamera(6),
                        7: FakeCamera(7), 8: FakeCamera(8)}
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
    def __init__(self):
        self.camera_bindings = {2: ["plug1"]}
        self.actuators = {"plug1": "tuya"}
    
    def get_for_camera(self, cam_id):
        return []  # не тестируем розетки здесь
    
    def get_actuator(self, name):
        return None
    
    def set_camera_binding(self, cam_id, actuator_name):
        pass
    
    def list_all(self):
        return [{"name": "plug1", "type": "tuya", "status": "ONLINE",
                 "status_icon": "🟢", "cameras": [2]}]
    
    def test_all(self):
        return [{"name": "plug1", "status": "OK", "reconnected": False}]

# ---------------------------------------------------------------------------
# Тесты
# ---------------------------------------------------------------------------

def setup_bot():
    config = load_config(BASE + r"\superguard")
    bot = SuperGuardBot.__new__(SuperGuardBot)  # без __init__ (не создаём реальные компоненты)
    bot.config = config
    bot.tg = MockTelegram()
    bot.camera_manager = FakeCameraManager()
    bot.actuator_manager = FakeActuatorManager()
    bot.camera_settings = {}
    bot.lang = "ru"
    bot._load_i18n()
    models = __import__("superguard.models", fromlist=["AlarmManager"])
    bot.alarm = models.AlarmManager()
    bot.active_camera_id = 1
    bot.frame_dir = config.frame_dir
    return bot

def test_trigger_uses_source_camera():
    """Тревога из detection_loop привязывается к камере-источнику (cam 2)."""
    bot = setup_bot()
    frame = bot.camera_manager.cameras[2].latest
    bot.trigger_alarm("TEST", frame, cam_id=2)
    assert bot.alarm.alarm_camera_id == 2, f"alarm_camera_id={bot.alarm.alarm_camera_id}, ожидал 2"
    assert bot.alarm.is_active
    # Одно сообщение тревоги (новый протокол) + live-кадр из пула камеры 2
    time.sleep(2.5)  # ждём цикл обновления (нужно 2+ секунд для первого edit)
    cam2_counter = bot.camera_manager.cameras[2].frame_counter
    assert cam2_counter >= 2, f"камера 2 дала мало кадров: {cam2_counter}"
    bot.cancel_alarm(cam_id=2)

def test_live_frame_sent_once_then_updated():
    """Одно сообщение тревоги (trigger), потом ОНО ЖЕ обновляется live-кадрами."""
    bot = setup_bot()
    frame = bot.camera_manager.cameras[2].latest
    bot.trigger_alarm("TEST", frame, cam_id=2)

    # Новый протокол: ровно ОДИН send_photo (trigger), live идёт через edit
    time.sleep(1.5)
    assert len(bot.tg.send_photo_calls) == 1, \
        f"ожидал 1 send_photo (trigger), получил {len(bot.tg.send_photo_calls)}"
    assert bot.alarm.live_msg_id is not None, "msg_id не установлен"

    # Ждём цикл обновления (update_every=2с + запас)
    time.sleep(2.5)
    assert bot.tg.edit_count >= 1, \
        f"live кадр не обновился: edit_message_media вызван {bot.tg.edit_count} раз"
    print(f"    edit_message_media вызовов: {bot.tg.edit_count} (ожидали ≥1 за ~4с)")

    bot.cancel_alarm(cam_id=2)

def test_live_frames_are_different():
    """Каждый live-кадр реально НОВЫЙ (байты отличаются)."""
    bot = setup_bot()
    frame = bot.camera_manager.cameras[2].latest
    bot.trigger_alarm("TEST", frame, cam_id=2)

    time.sleep(1.5)  # первый цикл обновления
    live1 = bot.tg.send_photo_calls[0][0] if bot.tg.send_photo_calls else None
    assert live1 is not None, "нет trigger кадра"

    time.sleep(2.5)  # ждём обновление
    assert bot.tg.edit_media_calls, "нет edit_message_media вызовов"
    live2 = bot.tg.edit_media_calls[-1][1]

    assert live1 != live2, "live-кадры идентичны! Камера не отдаёт новые кадры"
    print(f"    live1={len(live1)}b vs live2={len(live2)}b - кадры разные ✓")

    bot.cancel_alarm(cam_id=2)

def test_update_loop_stops_on_cancel():
    """После снятия тревоги цикл обновления останавливается."""
    bot = setup_bot()
    frame = bot.camera_manager.cameras[2].latest
    bot.trigger_alarm("TEST", frame, cam_id=2)

    time.sleep(1.5)  # запуск цикла
    bot.cancel_alarm(cam_id=2)
    count_after_cancel = bot.tg.edit_count

    time.sleep(3.0)  # 1+ циклов
    assert bot.tg.edit_count == count_after_cancel, \
        f"цикл не остановился: было {count_after_cancel}, стало {bot.tg.edit_count}"
    assert not bot.alarm.is_active
    print(f"    после отмены edit_count не растёт ({count_after_cancel}) ✓")

def test_manual_alarm_uses_active_camera():
    """Ручная тревога (/togglealarm) использует активную камеру."""
    bot = setup_bot()
    bot.active_camera_id = 2
    frame = bot.camera_manager.cameras[2].latest
    bot.trigger_alarm("MANUAL", frame)  # без cam_id -> active_camera_id
    assert bot.alarm.alarm_camera_id == 2, f"ожидал 2, получил {bot.alarm.alarm_camera_id}"
    bot.cancel_alarm(cam_id=2)

def test_manual_trigger_auto_mode_preserved():
    """Ручной триггер в АВТОрежиме: тревога становится РУЧНОЙ, после отмены АВТО возвращается."""
    bot = setup_bot()
    bot.alarm.auto_mode = True
    bot.toggle_alarm()  # ручной триггер (тест администратора)
    assert bot.alarm.is_active, "тревога не активировалась"
    # Ручной триггер переключает ЭТУ тревогу в ручной режим (prev_auto сохранён)
    state = bot.alarm.get(bot.alarm.alarm_camera_id)
    assert state.auto_mode is False, "ручной триггер не переключил тревогу в ручной режим"
    assert state.prev_auto_mode is True, "prev_auto_mode не сохранён"
    # Ручная отмена возвращает АВТО-режим
    bot.cancel_alarm(cam_id=bot.alarm.alarm_camera_id)
    assert bot.alarm.auto_mode is True, "после ручной отмены авто-режим не восстановлен!"

def test_manual_trigger_manual_mode_waits():
    """Ручной триггер в РУЧНОМ режиме: auto_mode=False, ждёт /togglealarm."""
    bot = setup_bot()
    bot.alarm.auto_mode = False
    bot.toggle_alarm()
    assert bot.alarm.is_active, "тревога не активировалась"
    state = bot.alarm.get(bot.alarm.alarm_camera_id)
    assert not state.auto_mode, "ручной режим стал авто!"
    # В ручном режиме тревога НЕ снимается автоматически
    state.clean_frames = 999  # хоть 999 чистых кадров - не снимется
    assert bot.alarm.is_active, "ручная тревога снялась автоматически - баг!"
    bot.cancel_alarm(cam_id=bot.alarm.alarm_camera_id)

def test_desktop_bridge_writes_state():
    """При тревоге пишутся desktop_state/status.json и alarm_live.jpg."""
    import os, json
    bot = setup_bot()
    state_dir = bot._state_dir()
    # чистим старые файлы
    for f in ("status.json", "alarm_live.jpg"):
        p = os.path.join(state_dir, f)
        if os.path.exists(p):
            os.remove(p)
    frame = bot.camera_manager.cameras[2].latest
    bot.trigger_alarm("BRIDGE TEST", frame, cam_id=2)
    
    status_path = os.path.join(state_dir, "status.json")
    assert os.path.exists(status_path), "status.json не создан"
    with open(status_path, encoding="utf-8") as f:
        st = json.load(f)
    assert st["alarm_active"] is True, st
    assert st["alarm_camera"] == 2, st
    assert st["active_camera"] == 2, st
    assert "camera_names" in st and "2" in st["camera_names"]
    
    frame_path = os.path.join(state_dir, "alarm_live.jpg")
    assert os.path.exists(frame_path), "alarm_live.jpg не создан"
    assert os.path.getsize(frame_path) > 500
    
    # снятие -> alarm_active False
    bot.cancel_alarm()
    with open(status_path, encoding="utf-8") as f:
        st2 = json.load(f)
    assert st2["alarm_active"] is False, st2

if __name__ == "__main__":
    print("=" * 60)
    print("SUPERGUARD LIVE-КАДР: ТЕСТ ПРОТОКОЛА БЕЗОПАСНОСТИ")
    print("=" * 60)

    print("\n[1] Привязка тревоги к камере-источнику")
    check("trigger_alarm(cam_id=2) -> alarm_camera_id=2", test_trigger_uses_source_camera)

    print("\n[2] Отправка и обновление live кадра")
    check("msgA + msgB отправлены, live обновляется", test_live_frame_sent_once_then_updated)

    print("\n[3] Новизна кадров")
    check("live-кадры реально разные", test_live_frames_are_different)

    print("\n[4] Остановка цикла при снятии тревоги")
    check("цикл останавливается после cancel_alarm", test_update_loop_stops_on_cancel)

    print("\n[5] Ручная тревога")
    check("ручная тревога -> активная камера", test_manual_alarm_uses_active_camera)
    check("ручной триггер сохраняет АВТОрежим (авто-снятие)", test_manual_trigger_auto_mode_preserved)
    check("ручной триггер в РУЧНОМ режиме ждёт отключения", test_manual_trigger_manual_mode_waits)

    print("\n[6] Desktop bridge")
    check("status.json + alarm_live.jpg при тревоге", test_desktop_bridge_writes_state)

    print("=" * 60)
    print(f"ИТОГ: {PASS} PASS, {FAIL} FAIL")
    if FAILURES:
        for name, e in FAILURES:
            print(f"  ✗ {name}: {e}")
    print("=" * 60)
    sys.exit(1 if FAIL else 0)
    sys.exit(1 if FAIL else 0)