"""
Ядро системы видеонаблюдения: захват RTSP, YOLO-детекция, зоны, тревоги в Telegram.
Работает полностью локально (ffmpeg + ultralytics + requests к Telegram API).
"""
import os
import sys
import time
import json
import logging
import threading
import subprocess
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO
import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(Path(__file__).parent / "logs" / "surveillance.log", encoding="utf-8"),
    ],
)
log = logging.getLogger("surveillance")

# ── Telegram ──────────────────────────────────────────────────────────────
def load_telegram_config():
    """Читает токен из .env Hermes (единственный источник правды)."""
    env_path = Path(os.environ.get("HERMES_HOME", Path.home() / "AppData/Local/hermes")) / ".env"
    token = None
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("TELEGRAM_BOT_TOKEN="):
                token = line.split("=", 1)[1].strip()
    if not token:
        # fallback: переменная окружения
        token = os.environ.get("TELEGRAM_BOT_TOKEN")
    return token

def send_telegram_photo(token, chat_id, photo_path, caption=""):
    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    with open(photo_path, "rb") as f:
        r = requests.post(url, data={"chat_id": chat_id, "caption": caption}, files={"photo": f}, timeout=30)
    return r.ok

def send_telegram_video(token, chat_id, video_path, caption=""):
    url = f"https://api.telegram.org/bot{token}/sendVideo"
    with open(video_path, "rb") as f:
        r = requests.post(url, data={"chat_id": chat_id, "caption": caption}, files={"video": f}, timeout=120)
    return r.ok

def send_telegram_text(token, chat_id, text):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    r = requests.post(url, data={"chat_id": chat_id, "text": text}, timeout=30)
    return r.ok

# ── Зоны ──────────────────────────────────────────────────────────────────
class Zone:
    """Многоугольная зона интереса в нормализованных координатах."""

    def __init__(self, name: str, polygon: list):
        self.name = name
        self.polygon = np.array(polygon, dtype=np.float32)  # [[x,y],...] 0-1

    def contains(self, point: tuple, frame_w: int, frame_h: int) -> bool:
        """Точка (центр бокса) внутри зоны?"""
        px, py = point[0] * frame_w, point[1] * frame_h
        poly = self.polygon * np.array([frame_w, frame_h])
        return cv2.pointPolygonTest(poly.astype(np.int32), (float(px), float(py)), False) >= 0


class CameraWatcher(threading.Thread):
    """Наблюдатель одной камеры: RTSP → кадры → YOLO → зоны → тревога."""

    def __init__(self, name, url, zones, detector, alert_cfg, tg_cfg, stop_event):
        super().__init__(daemon=True)
        self.name = name
        self.url = url
        self.zones = [Zone(z["name"], z["polygon"]) for z in zones]
        self.detector = detector
        self.alert_cfg = alert_cfg
        self.tg_cfg = tg_cfg
        self.stop_event = stop_event
        self.last_alert_ts = 0
        self.pending_confirms = {}  # zone -> count

    def _grab_frame(self, cap):
        ok, frame = cap.read()
        if not ok:
            return None
        return frame

    def _point_in_zone(self, bbox, frame_w, frame_h):
        """Центр бокса YOLO (xyxy) в нормализованных координатах."""
        x1, y1, x2, y2 = bbox
        cx = ((x1 + x2) / 2) / frame_w
        cy = ((y1 + y2) / 2) / frame_h
        return cx, cy

    def _draw(self, frame, detections):
        """Рисует боксы и зоны (для снапшота)."""
        for z in self.zones:
            poly = (z.polygon * np.array([frame.shape[1], frame.shape[0]])).astype(np.int32)
            cv2.polylines(frame, [poly], True, (0, 255, 0), 2)
            cv2.putText(frame, z.name, tuple(poly[0]), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
        for det in detections:
            x1, y1, x2, y2, label, conf = det
            cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), (0, 0, 255), 2)
            cv2.putText(frame, f"{label} {conf:.0%}", (int(x1), int(y1) - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
        return frame

    def run(self):
        log.info(f"[{self.name}] запуск наблюдения: {self.url}")
        cap = cv2.VideoCapture(self.url)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if not cap.isOpened():
            log.error(f"[{self.name}] НЕ удалось открыть поток")
            return

        frame_count = 0
        interval = self.detector.frame_interval
        while not self.stop_event.is_set():
            frame = self._grab_frame(cap)
            if frame is None:
                log.warning(f"[{self.name}] потеря кадра, переподключение...")
                cap.release()
                time.sleep(3)
                cap = cv2.VideoCapture(self.url)
                continue

            frame_count += 1
            if frame_count % interval != 0:
                continue

            h, w = frame.shape[:2]
            results = self.detector.predict(frame)

            # Детекции в зонах
            alerts = []
            for det in results:
                x1, y1, x2, y2, label, conf = det
                if label not in self.alert_cfg.get("classes", ["person"]):
                    continue
                cx, cy = self._point_in_zone((x1, y1, x2, y2), w, h)
                for zone in self.zones:
                    if zone.contains((cx, cy), w, h):
                        alerts.append((label, conf, zone))

            # Подтверждение на N кадрах
            now = time.time()
            cooldown = self.alert_cfg.get("cooldown_seconds", 300)
            if alerts and (now - self.last_alert_ts > cooldown):
                # подтверждение
                for label, conf, zone in alerts:
                    key = f"{zone.name}:{label}"
                    self.pending_confirms[key] = self.pending_confirms.get(key, 0) + 1
                triggered = [a for a in alerts
                             if self.pending_confirms.get(f"{a[2].name}:{a[0]}", 0)
                                >= self.alert_cfg.get("require_frames", 2)]
                if triggered:
                    label, conf, zone = triggered[0]
                    self._fire_alert(frame, detections=results, label=label, conf=conf, zone=zone)
                    self.last_alert_ts = now
                    self.pending_confirms.clear()
            else:
                self.pending_confirms.clear()

        cap.release()
        log.info(f"[{self.name}] остановлен")

    def _fire_alert(self, frame, detections, label, conf, zone):
        """Тревога: снапшот + видео → Telegram."""
        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        out_dir = Path(__file__).parent / "alerts" / self.name
        out_dir.mkdir(parents=True, exist_ok=True)

        # Снапшот с разметкой
        annotated = self._draw(frame.copy(), detections)
        snap_path = out_dir / f"snapshot_{ts}.jpg"
        cv2.imwrite(str(snap_path), annotated)

        event_text = (self.alert_cfg.get("message_template", "🚨 ТРЕВОГА: {event}") .format(
            event=f"{label} в зоне '{zone.name}'", camera=self.name, zone=zone.name,
            label=label, conf=conf, time=datetime.now().strftime("%H:%M:%S")))
        log.warning(f"[{self.name}] 🚨 {event_text}")

        if not self.tg_cfg.get("token"):
            log.warning("Нет Telegram-токена — только локальный снапшот")
            return

        chat_id = self.tg_cfg.get("chat_id")
        send_telegram_text(self.tg_cfg["token"], chat_id, event_text)
        if self.alert_cfg.get("send_snapshot", True):
            send_telegram_photo(self.tg_cfg["token"], chat_id, str(snap_path), caption=event_text)

        # Видео (последние N секунд через ffmpeg ring buffer — упрощённо: 30 сек с текущего момента)
        if self.alert_cfg.get("send_video", True):
            secs = self.alert_cfg.get("video_seconds", 30)
            vid_path = out_dir / f"clip_{ts}.mp4"
            self._capture_clip(vid_path, secs)
            if vid_path.exists():
                send_telegram_video(self.tg_cfg["token"], chat_id, str(vid_path), caption=event_text)

    def _capture_clip(self, out_path, seconds):
        """Запись клипа с RTSP через ffmpeg."""
        cmd = [
            "ffmpeg", "-y", "-rtsp_transport", "tcp",
            "-i", self.url, "-t", str(seconds),
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "28",
            "-an", str(out_path),
        ]
        try:
            subprocess.run(cmd, capture_output=True, timeout=seconds + 30, check=False)
        except Exception as e:
            log.error(f"ffmpeg: {e}")


class Detector:
    """YOLO-детектор (базовая модель + кастомная на клещи)."""

    def __init__(self, cfg):
        self.model = YOLO(cfg.get("model", "yolo11n.pt"))
        self.custom = None
        custom_path = cfg.get("model_custom")
        if custom_path and Path(custom_path).exists():
            self.custom = YOLO(custom_path)
            log.info(f"Кастомная модель загружена: {custom_path}")
        self.conf = cfg.get("conf_threshold", 0.45)
        self.iou = cfg.get("iou_threshold", 0.45)
        self.imgsz = cfg.get("imgsz", 640)
        self.frame_interval = cfg.get("frame_interval", 3)

    def predict(self, frame):
        detections = []
        for model in (self.model, self.custom):
            if model is None:
                continue
            results = model.predict(frame, conf=self.conf, iou=self.iou,
                                    imgsz=self.imgsz, verbose=False)
            for r in results:
                names = r.names
                for box in r.boxes:
                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    conf = float(box.conf[0])
                    cls = int(box.cls[0])
                    detections.append((x1, y1, x2, y2, names[cls], conf))
        # дедупликация базовой и кастомной
        return detections


# ── Главный ───────────────────────────────────────────────────────────────
def main():
    cfg_path = Path(__file__).parent / "config.yaml"
    import yaml
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))

    tg_token = load_telegram_config()
    tg_cfg = {"token": tg_token, "chat_id": None}
    chat_id = cfg.get("alert", {}).get("telegram_channel")
    if chat_id:
        tg_cfg["chat_id"] = chat_id

    detector = Detector(cfg.get("detection", {}))
    alert_cfg = cfg.get("alert", {})
    alert_cfg["classes"] = cfg.get("alert_classes", ["person"])

    stop_event = threading.Event()
    watchers = []
    for cam in cfg.get("camera", {}).get("streams", []):
        if not cam.get("enabled"):
            log.info(f"[{cam['name']}] отключена (включи в config.yaml)")
            continue
        w = CameraWatcher(cam["name"], cam["url"], cam.get("zones", []),
                          detector, alert_cfg, tg_cfg, stop_event)
        w.start()
        watchers.append(w)

    if not watchers:
        log.warning("Нет включённых камер. Добавь RTSP-URL в config.yaml и enabled: true")
        log.info("Тестовый режим: синтетический поток для проверки...")
        # тестовый поток
        cam = cfg["camera"]["streams"][0]
        w = CameraWatcher("test-cam", "testsrc", cam.get("zones", []),
                          detector, alert_cfg, tg_cfg, stop_event)
        watchers.append(w)

    try:
        while not stop_event.is_set():
            time.sleep(1)
    except KeyboardInterrupt:
        log.info("Остановка...")
        stop_event.set()


if __name__ == "__main__":
    main()
