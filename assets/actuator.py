"""
actuator.py — WiFi-исполнительное устройство: прожектор + сирена.

При тревоге отправляет HTTP-сигнал на ESP32 (или любое WiFi-реле),
которое включает прожектор и сирену на N секунд, затем выключает.

Поддерживает 3 режима:
1. esp32   — реальное устройство: HTTP GET/POST на http://<ip>/on и /off
2. webhook — любой WiFi-контроллер с JSON API (POST {"action": "alarm"})
3. sim     — симуляция для демо: печать в консоль + лог (нет железа)

Схема ESP32 (прошивка в docs/esp32_alarm.ino):
  GPIO2 -> реле 1 -> прожектор
  GPIO4 -> реле 2 -> сирена
"""

import json
import logging
import time
from datetime import datetime
from pathlib import Path

import requests

log = logging.getLogger("actuator")

DEFAULT_CONFIG = {
    "mode": "sim",                 # esp32 | webhook | sim
    "base_url": "http://192.168.1.50",   # ESP32 IP (для mode=esp32)
    "webhook_url": "http://192.168.1.60/alarm",  # для mode=webhook
    "on_path": "/on",              # ESP32: включить (GET)
    "off_path": "/off",            # ESP32: выключить (GET)
    "duration_seconds": 30,        # сколько держать прожектор+сирену
    "timeout": 5,
}


class Actuator:
    def __init__(self, cfg=None, log_dir=None):
        self.cfg = {**DEFAULT_CONFIG, **(cfg or {})}
        self.log_dir = Path(log_dir) if log_dir else Path(__file__).parent / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def _log_event(self, event: dict):
        """Запись события актуатора в JSONL (для демо/аудита)."""
        path = self.log_dir / "actuator_events.jsonl"
        event["ts"] = datetime.now().isoformat()
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

    def trigger(self, reason: str, duration=None) -> dict:
        """Включить прожектор + сирену. Возвращает результат операции."""
        duration = duration or self.cfg["duration_seconds"]
        mode = self.cfg["mode"]
        result = {"mode": mode, "reason": reason, "duration": duration, "ok": False}

        if mode == "esp32":
            result = self._trigger_esp32(reason, duration, result)
        elif mode == "webhook":
            result = self._trigger_webhook(reason, duration, result)
        else:  # sim
            log.warning(f"🚨 SIM-АКТУАТОР: прожектор ВКЛ + сирена ВКЛ на {duration}с — причина: {reason}")
            result["ok"] = True
            result["message"] = "simulated: floodlight ON + siren ON"

        self._log_event(result)
        return result

    def _trigger_esp32(self, reason, duration, result):
        base = self.cfg["base_url"].rstrip("/")
        try:
            r = requests.get(f"{base}{self.cfg['on_path']}", timeout=self.cfg["timeout"])
            result["ok"] = r.ok
            result["http"] = r.status_code
            log.info(f"🔦 ESP32 ON: {base}{self.cfg['on_path']} -> {r.status_code}")
            if r.ok:
                time.sleep(duration)
                r2 = requests.get(f"{base}{self.cfg['off_path']}", timeout=self.cfg["timeout"])
                result["off_http"] = r2.status_code
                log.info(f"🔕 ESP32 OFF: {base}{self.cfg['off_path']} -> {r2.status_code}")
        except Exception as e:
            result["error"] = str(e)
            log.error(f"ESP32 недоступен: {e}")
        return result

    def _trigger_webhook(self, reason, duration, result):
        try:
            payload = {"action": "alarm", "reason": reason, "duration": duration}
            r = requests.post(self.cfg["webhook_url"], json=payload, timeout=self.cfg["timeout"])
            result["ok"] = r.ok
            result["http"] = r.status_code
            log.info(f"🔦 WEBHOOK: {self.cfg['webhook_url']} -> {r.status_code}")
        except Exception as e:
            result["error"] = str(e)
            log.error(f"Webhook недоступен: {e}")
        return result
