"""
demo_prototype.py — сквозной прототип охранной системы «Вор-электрик».

Полный цикл:
  кадр (RTSP/файл/тест-стенд)
    → YOLO person-детекция
    → electrician_detector (штанга УКН + каска + жилет)
    → подтверждение на N кадрах
    → Telegram: фото с разметкой + текст
    → WiFi-актуатор: прожектор + сирена (ESP32 / webhook / sim)

Запуск:
  python demo_prototype.py                          # тест-стенд (синтетический вор)
  python demo_prototype.py --source test.mp4        # видеофайл
  python demo_prototype.py --source rtsp://...      # RTSP-камера
  python demo_prototype.py --no-telegram --no-act   # без внешних эффектов
  python demo_prototype.py --actuator sim|esp32|webhook
"""

import argparse
import json
import logging
import threading
import time
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO

import electrician_detector as ed
from actuator import Actuator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(Path(__file__).parent / "logs" / "prototype.log", encoding="utf-8"),
    ],
)
log = logging.getLogger("prototype")

BASE = Path(__file__).parent


# ── Telegram ──────────────────────────────────────────────────────────────
def load_telegram_config():
    import os
    env_path = Path(os.environ.get("HERMES_HOME", Path.home() / "AppData/Local/hermes")) / ".env"
    token = None
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("TELEGRAM_BOT_TOKEN="):
                token = line.split("=", 1)[1].strip()
    return token or os.environ.get("TELEGRAM_BOT_TOKEN")


def tg_send_photo(token, chat_id, photo_path, caption=""):
    import requests
    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    with open(photo_path, "rb") as f:
        r = requests.post(url, data={"chat_id": chat_id, "caption": caption},
                          files={"photo": f}, timeout=30)
    return r.ok


def tg_send_text(token, chat_id, text):
    import requests
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    r = requests.post(url, data={"chat_id": chat_id, "text": text}, timeout=30)
    return r.ok


# ── Синтетический тест-стенд: «вор-электрик» ─────────────────────────────
def synth_thief_frame(size=(640, 480), seed=42, add_helmet=True, add_vest=True, add_pole=True):
    """Генерирует кадр: тёмный фон, силуэт человека с каской/жилетом и штангой УКН."""
    rng = np.random.default_rng(seed)
    frame = np.full((size[1], size[0], 3), (40, 45, 50), dtype=np.uint8)  # сумерки

    # фон — лёгкий шум
    noise = rng.integers(-8, 8, frame.shape, dtype=np.int16)
    frame = np.clip(frame.astype(np.int16) + noise, 0, 255).astype(np.uint8)

    # горизонт/стена
    cv2.rectangle(frame, (0, 350), (size[0], size[1]), (30, 35, 40), -1)

    # кабель вверху (кабельная зона)
    cv2.line(frame, (0, 120), (size[0], 120), (0, 0, 0), 3)

    # человек: тёмная одежда
    cx = 320
    body_top, body_bot = 260, 460
    cv2.rectangle(frame, (cx - 40, body_top), (cx + 40, body_bot), (25, 25, 30), -1)  # торс
    cv2.rectangle(frame, (cx - 15, body_bot), (cx + 15, body_bot + 50), (20, 20, 25), -1)  # ноги
    cv2.circle(frame, (cx, body_top - 25), 22, (30, 30, 35), -1)  # голова

    if add_helmet:
        cv2.circle(frame, (cx, body_top - 28), 24, (0, 200, 255), -1)   # жёлтая каска
        cv2.rectangle(frame, (cx - 26, body_top - 30), (cx + 26, body_top - 20), (0, 180, 230), -1)
    if add_vest:
        cv2.rectangle(frame, (cx - 38, body_top + 15), (cx + 38, body_top + 75), (0, 220, 255), -1)  # жилет

    if add_pole:
        # штанга УКН: от рук до кабеля (тонкая вертикальная линия)
        pole_x = cx + 55
        cv2.line(frame, (pole_x, 430), (pole_x, 118), (200, 200, 200), 3)   # тело штанги
        cv2.circle(frame, (pole_x, 118), 5, (160, 160, 160), -1)             # контактная головка у кабеля

    return frame


# ── Ядро прототипа ───────────────────────────────────────────────────────
class Prototype:
    def __init__(self, source, detector, alert_cfg, tg, actuator, out_dir):
        self.source = source
        self.detector = detector
        self.alert_cfg = alert_cfg
        self.tg = tg
        self.actuator = actuator
        self.out_dir = out_dir
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.last_alert_ts = 0
        self.pending_confirms = 0

    def run(self):
        if self.source == "synth":
            self._run_synth()
        else:
            self._run_stream()

    def _run_synth(self):
        """Прогон на синтетических кадрах: вор появляется/исчезает."""
        log.info("🧪 Тест-стенд: синтетический вор-электрик (5 кадров с вором, 3 без)")
        for i in range(8):
            thief = i < 5
            frame = synth_thief_frame(seed=42 + i, add_helmet=thief, add_vest=thief, add_pole=thief)
            if not thief:
                # обычный прохожий без атрибутов
                frame = synth_thief_frame(seed=100 + i, add_helmet=False, add_vest=False, add_pole=False)
            self._process_frame(frame, is_synth=True, frame_idx=i)
            time.sleep(0.8)

    def _run_stream(self):
        cap = cv2.VideoCapture(self.source)
        if not cap.isOpened():
            log.error(f"Не удалось открыть {self.source}")
            return
        log.info(f"▶ Поток: {self.source}")
        n = 0
        while True:
            ok, frame = cap.read()
            if not ok:
                log.warning("Конец потока / потеря кадра")
                break
            n += 1
            if n % 3 != 0:
                continue
            self._process_frame(frame, is_synth=False, frame_idx=n)
            time.sleep(0.1)
        cap.release()

    def _process_frame(self, frame, is_synth=False, frame_idx=0):
        if getattr(self, "direct_boxes", None):
            # режим --direct: YOLO не видит примитивную синтетику,
            # используем заранее известный бокс человека
            results = [(x1, y1, x2, y2, "person", 0.85) for (x1, y1, x2, y2) in self.direct_boxes]
        else:
            results = self.detector.predict(frame)
        alerts = ed.analyze_frame(frame, results)
        now = time.time()

        if alerts:
            self.pending_confirms += 1
            need = self.alert_cfg.get("require_frames", 2)
            cooldown = self.alert_cfg.get("cooldown_seconds", 60)
            if self.pending_confirms >= need and (now - self.last_alert_ts > cooldown):
                self._fire(frame, alerts, results, frame_idx)
                self.last_alert_ts = now
                self.pending_confirms = 0
        else:
            self.pending_confirms = 0

        # снапшот каждого N-го кадра в debug/ (для наглядности демо)
        if is_synth or frame_idx % 10 == 0:
            marked = ed.draw_alerts(frame.copy(), alerts)
            dbg = self.out_dir / "debug"
            dbg.mkdir(exist_ok=True)
            cv2.imwrite(str(dbg / f"frame_{frame_idx:04d}.jpg"), marked)

    def _fire(self, frame, alerts, detections, frame_idx):
        a = alerts[0]
        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

        # размеченный снапшот
        marked = ed.draw_alerts(frame.copy(), alerts)
        snap = self.out_dir / f"alert_{ts}.jpg"
        cv2.imwrite(str(snap), marked)
        log.warning(f"🚨 ОБНАРУЖЕН ВОР-ЭЛЕКТРИК: {snap.name} (conf={a['confidence']})")

        # Telegram
        if self.tg.get("token") and self.tg.get("chat_id"):
            text = (
                "🚨 ВОР-ЭЛЕКТРИК В ЗОНЕ!\n"
                f"• Штанга УКН: {'ДА, достаёт кабель' if a['pole_in_cable'] else 'есть'}\n"
                f"• Каска: {'ДА' if a['helmet'] else 'нет'}\n"
                f"• Жилет: {'ДА' if a['vest'] else 'нет'}\n"
                f"• Уверенность: {a['confidence']:.0%}\n"
                f"• Время: {datetime.now().strftime('%H:%M:%S')}"
            )
            tg_send_text(self.tg["token"], self.tg["chat_id"], text)
            tg_send_photo(self.tg["token"], self.tg["chat_id"], str(snap), caption="🚨 Кадр с камеры")
            log.info("📸 Фото + текст отправлены в Telegram")

        # WiFi-актуатор
        if self.actuator:
            res = self.actuator.trigger(reason=f"вор-электрик (conf={a['confidence']})")
            log.info(f"🔦 Актуатор: {json.dumps(res, ensure_ascii=False)}")


def main():
    ap = argparse.ArgumentParser(description="Охранный прототип «Вор-электрик»")
    ap.add_argument("--source", default="synth", help="synth | видеофайл | rtsp://...")
    ap.add_argument("--actuator", default="sim", choices=["sim", "esp32", "webhook"], help="режим актуатора")
    ap.add_argument("--no-telegram", action="store_true", help="отключить Telegram")
    ap.add_argument("--no-act", action="store_true", help="отключить актуатор")
    ap.add_argument("--direct", action="store_true", help="режим демо: бокс человека вручную (синтетика)")
    ap.add_argument("--chat-id", default=None, help="Telegram chat_id (переопределяет config)")
    args = ap.parse_args()

    # конфиг
    import yaml
    cfg_path = BASE / "config.yaml"
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) if cfg_path.exists() else {}

    detector = DetectorWrapper(cfg.get("detection", {}))

    # Telegram
    tg = {"token": load_telegram_config(), "chat_id": args.chat_id}
    if not tg["chat_id"]:
        tg["chat_id"] = cfg.get("alert", {}).get("telegram_channel")
    if args.no_telegram:
        tg = {"token": None, "chat_id": None}

    # актуатор
    actuator = None
    if not args.no_act:
        act_cfg = cfg.get("actuator", {})
        act_cfg["mode"] = args.actuator
        actuator = Actuator(act_cfg, log_dir=BASE / "logs")

    alert_cfg = {
        "require_frames": cfg.get("alert", {}).get("require_frames", 2),
        "cooldown_seconds": cfg.get("alert", {}).get("cooldown_seconds", 60),
    }

    proto = Prototype(args.source, detector, alert_cfg, tg, actuator, BASE / "alerts")
    if args.direct:
        # бокс человека на синтетическом стенде (640x480)
        proto.direct_boxes = [(280, 235, 360, 460)]
        log.info("🎯 Режим --direct: бокс человека задан вручную (YOLO не видит примитив)")
    proto.run()


# ── Детектор (обёртка над YOLO, чтобы не тянуть весь surveillance.py) ───
class DetectorWrapper:
    def __init__(self, cfg):
        from ultralytics import YOLO
        model_path = cfg.get("model", "yolo11n.pt")
        self.model = YOLO(model_path if Path(model_path).exists() else BASE / "yolo11n.pt")
        self.conf = cfg.get("conf_threshold", 0.4)
        self.iou = cfg.get("iou_threshold", 0.45)
        self.imgsz = cfg.get("imgsz", 640)

    def predict(self, frame):
        detections = []
        results = self.model.predict(frame, conf=self.conf, iou=self.iou,
                                     imgsz=self.imgsz, verbose=False)
        for r in results:
            names = r.names
            for box in r.boxes:
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                conf = float(box.conf[0])
                cls = int(box.cls[0])
                detections.append((x1, y1, x2, y2, names[cls], conf))
        return detections


if __name__ == "__main__":
    main()
