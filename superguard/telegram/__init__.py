#!/usr/bin/env python3
"""
SuperGuard Alarm - Telegram Bot Layer

Provides:
- TelegramClient: HTTP wrapper with retry, rate limiting
- CommandRouter: Command parsing and dispatch
- CallbackHandler: Inline button callbacks
- MenuManager: setMyCommands per-language
- SuperGuardBot: Main application wiring all components

Architecture:
- Poll loop (long-poll getUpdates) in background thread
- Detection loop (YOLO processing) in main thread
- Per-camera alarm update loops (spawned per trigger)
- All state persisted to JSON (SettingsStore + legacy settings file)
- Desktop bridge via status.json + alarm_live.jpg

Key protocols:
- Concurrent per-camera alarms (AlarmManager + CameraAlarmState)
- Single alarm message per camera (trigger frame -> live updates -> restore on cancel)
- Manual trigger forces manual mode for that alarm; manual cancel restores global auto_mode
- Annotated frames (YOLO boxes) sent to Telegram, not raw frames
"""

import json
import time
import threading
import requests
import numpy as np
import cv2
from typing import Dict, Optional, Any, Callable, List
from dataclasses import dataclass
from functools import wraps

from ..config import SuperGuardConfig, TelegramConfig, CameraConfig
from ..models import Alarm, AlarmManager, CameraAlarmState, CameraSettings, Zone, Target, parse_zone_spec, parse_target_text
from ..cameras import CameraManager
from ..actuators import ActuatorManager
from ..detectors import create_pipeline_from_config, ProcessedFrame


# ============================================================================
# TELEGRAM CLIENT (with retry & rate limiting)
# ============================================================================

class TelegramClient:
    """Telegram Bot API client with retry logic and rate limiting.

    Handles:
    - Rate limiting (20 calls/sec max via _min_interval)
    - Automatic retry with exponential backoff
    - Special handling for getUpdates long-poll (timeout > poll timeout)
    - 429 rate limit handling (honors Retry-After header)
    - Multipart file upload for photos

    Thread-safe: rate limiting uses simple timestamp check.
    """

    def __init__(self, config: TelegramConfig):
        """Initialize client with bot token.

        Args:
            config: TelegramConfig with token and chat_id
        """
        self.config = config
        self.api_url = f"https://api.telegram.org/bot{config.token}"
        self.session = requests.Session()
        self._last_call = 0
        self._min_interval = 0.05  # 20 calls/sec max

    def _rate_limit(self):
        """Enforce minimum interval between API calls.

        Simple sleep-based rate limiter. Not token-bucket but sufficient
        for our low-volume bot (few calls per second max).
        """
        elapsed = time.time() - self._last_call
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)

    def call(self, method: str, max_retries: int = 3, **kwargs) -> Optional[Dict]:
        """Call Telegram API method with retry logic.

        Args:
            method: API method name (e.g., "sendMessage", "getUpdates")
            max_retries: Maximum retry attempts
            **kwargs: Method parameters

        Returns:
            API result dict or None on failure
        """
        self._rate_limit()

        # getUpdates long-poll: requests timeout must EXCEED the poll timeout,
        # otherwise every poll is torn down at 20s < 25s and updates are delayed.
        req_timeout = kwargs.get("timeout", 20)
        if method == "getUpdates":
            req_timeout = (req_timeout or 25) + 15  # 40s for a 25s long-poll

        for attempt in range(max_retries):
            try:
                if "files" in kwargs:
                    files = kwargs.pop("files")
                    r = self.session.post(f"{self.api_url}/{method}", files=files, data=kwargs, timeout=req_timeout)
                else:
                    r = self.session.post(f"{self.api_url}/{method}", json=kwargs, timeout=req_timeout)

                self._last_call = time.time()

                if r.status_code == 200:
                    j = r.json()
                    if j.get("ok"):
                        return j.get("result")
                    # API error
                    if j.get("error_code") == 429:  # Rate limited
                        retry_after = j.get("parameters", {}).get("retry_after", 1)
                        time.sleep(retry_after)
                        continue
                    print(f"  TG {method} error: {j.get('description')}")
                    return None
                elif r.status_code == 429:
                    retry_after = int(r.headers.get("Retry-After", 1))
                    time.sleep(retry_after)
                    continue
                else:
                    print(f"  TG {method} HTTP {r.status_code}: {r.text}")

            except requests.Timeout:
                print(f"  TG {method} timeout (attempt {attempt + 1})")
            except Exception as e:
                print(f"  TG {method} err: {e}")

            if attempt < max_retries - 1:
                time.sleep(1 * (attempt + 1))  # Exponential backoff

        return None

    # Convenience methods for common API calls

    def send_message(self, chat_id: int, text: str, reply_markup: str = None, parse_mode: str = "HTML") -> Optional[Dict]:
        """Send text message."""
        data = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
        if reply_markup:
            data["reply_markup"] = reply_markup
        return self.call("sendMessage", **data)

    def send_photo(self, chat_id: int, photo_bytes: bytes, caption: str = "",
                   reply_markup: str = None, parse_mode: str = "HTML") -> Optional[Dict]:
        """Send photo with optional caption and inline keyboard."""
        files = {"photo": ("frame.jpg", photo_bytes, "image/jpeg")}
        data = {"chat_id": chat_id, "caption": caption, "parse_mode": parse_mode}
        if reply_markup:
            data["reply_markup"] = reply_markup
        return self.call("sendPhoto", files=files, **data)

    def edit_message_text(self, chat_id: int, message_id: int, text: str,
                          parse_mode: str = "HTML") -> Optional[Dict]:
        """Edit text of existing message."""
        return self.call("editMessageText", chat_id=chat_id, message_id=message_id,
                        text=text, parse_mode=parse_mode)

    def edit_message_media(self, chat_id: int, message_id: int, photo_bytes: bytes,
                           caption: str = "", parse_mode: str = "HTML") -> Optional[Dict]:
        """Edit media (photo) of existing message.

        Uses attach://photo protocol: media JSON references the file via attach://.
        """
        media = json.dumps({"type": "photo", "media": "attach://photo",
                            "caption": caption, "parse_mode": parse_mode})
        files = {"photo": ("frame.jpg", photo_bytes, "image/jpeg")}
        return self.call("editMessageMedia", files=files,
                         chat_id=chat_id, message_id=message_id, media=media)

    def delete_message(self, chat_id: int, message_id: int) -> bool:
        """Delete message. Returns True on success."""
        result = self.call("deleteMessage", chat_id=chat_id, message_id=message_id)
        return result is not None

    def answer_callback_query(self, callback_query_id: str, text: str) -> bool:
        """Answer callback query (inline button press)."""
        result = self.call("answerCallbackQuery", callback_query_id=callback_query_id, text=text)
        return result is not None

    def set_my_commands(self, commands: List[Dict], language_code: str) -> bool:
        """Set bot commands menu for a language."""
        result = self.call("setMyCommands", commands=commands, language_code=language_code)
        return result is not None

    def delete_my_commands(self, language_code: str) -> bool:
        """Delete bot commands menu for a language."""
        result = self.call("deleteMyCommands", language_code=language_code)
        return result is not None

    def get_updates(self, offset: int, timeout: int = 25) -> Optional[Dict]:
        """Long-poll getUpdates.

        Returns dict with "result": list of updates (never None).
        """
        result = self.call("getUpdates", offset=offset, timeout=timeout)
        if isinstance(result, list):
            return {"result": result}
        return {"result": []}


# ============================================================================
# COMMAND ROUTER
# ============================================================================

@dataclass
class CommandContext:
    """Context passed to command handlers.

    Attributes:
        text: Full message text
        args: Text after command prefix
        message_id: Telegram message ID
        chat_id: Chat ID
        user_id: User ID
    """
    text: str
    args: str
    message_id: int
    chat_id: int
    user_id: int


class CommandRouter:
    """Routes commands to handlers based on text prefix.

    Matching order:
    1. Exact match (text == prefix)
    2. Prefix + space (text.startswith(prefix + " "))
    3. Prefix + @ (for bot mentions: /cmd@botname)
    4. Prefix match (text.startswith(prefix))
    5. Default handler

    Thread-unsafe: register() should be called before routing starts.
    """

    def __init__(self):
        self.handlers: Dict[str, Callable[[CommandContext], None]] = {}
        self.default_handler: Optional[Callable[[CommandContext], None]] = None

    def register(self, prefix: str, handler: Callable[[CommandContext], None]):
        """Register handler for command prefix (e.g., '/zone')."""
        self.handlers[prefix.lower()] = handler

    def set_default(self, handler: Callable[[CommandContext], None]):
        """Set default handler for unmatched commands."""
        self.default_handler = handler

    def route(self, ctx: CommandContext):
        """Route command to appropriate handler."""
        text_lower = ctx.text.lower().strip()

        # Exact matches first
        for prefix, handler in self.handlers.items():
            if text_lower == prefix or text_lower.startswith(prefix + " ") or text_lower.startswith(prefix + "@"):
                handler(ctx)
                return

        # Prefix matches
        for prefix, handler in self.handlers.items():
            if text_lower.startswith(prefix):
                handler(ctx)
                return

        # Default
        if self.default_handler:
            self.default_handler(ctx)


# ============================================================================
# BOT APPLICATION (Main wiring)
# ============================================================================

class SuperGuardBot:
    """Main bot application - wires all components together.

    Responsibilities:
    - Initialize all subsystems (cameras, detectors, actuators, alarms)
    - Handle Telegram updates (poll loop + callbacks)
    - Run detection loop (YOLO processing on all cameras)
    - Manage per-camera settings persistence
    - Publish status for desktop monitor (status.json + alarm_live.jpg)
    - Localization (RU/EN/ES)

    Threading model:
    - Main thread: detection_loop()
    - Background thread: poll_loop()
    - Per-alarm threads: _update_loop(cam_id) - one per active camera
    """

    def __init__(self, config: SuperGuardConfig):
        self.config = config

        # Core components
        self.tg = TelegramClient(config.telegram)
        self.alarm = AlarmManager()  # per-camera concurrent alarms
        self.camera_manager = CameraManager(config)
        self.actuator_manager = ActuatorManager(config)

        # Per-camera settings (loaded from disk)
        self.camera_settings: Dict[int, CameraSettings] = {}

        # Active camera (command target). Delegates to AlarmManager.
        # Using property for backward compatibility with legacy code.

    @property
    def active_camera_id(self) -> int:
        return self.alarm.active_camera_id

    @active_camera_id.setter
    def active_camera_id(self, value: int):
        self.alarm.active_camera_id = value

        # Localization
        self.lang = "ru"
        self._load_i18n()

        # Command router
        self.router = CommandRouter()
        self._register_commands()

        # Frame directory
        self.frame_dir = self.config.frame_dir
        import os
        os.makedirs(self.frame_dir, exist_ok=True)

    def _load_i18n(self):
        """Load translation dictionaries for RU/EN/ES.

        Contains all user-facing strings. Uses simple key-value dict per language.
        tr() method handles formatting with **kw.
        """
        # Import from existing panic_mode or define here
        # For brevity, using minimal set - full dict in i18n.py
        self.L = {
            "ru": {
                "alert": "⚠️ ВНИМАНИЕ! ТРЕВОГА! СИГНАЛИЗАЦИЯ ВКЛЮЧЕНА!\nОТКЛЮЧЕНИЕ — КОМАНДА /togglealarm ИЗ МЕНЮ",
                "mode_title": "⚙️ РЕЖИМ РАБОТЫ",
                "current_mode": "Текущий режим",
                "mode_auto": "✅ АВТОМАТИЧЕСКИЙ",
                "mode_manual": "🚫 РУЧНОЙ",
                "zone_search": "Зона поиска",
                "target_search": "Цель поиска",
                "whole_frame": "весь кадр",
                "row_col": "строка {r}, столбец {c}",
                "control_hint": "Управление: меню → /autoguard, /togglealarm, /zone, /target, /cam",
                "auto_on": "✅ АВТОРЕЖИМ ВКЛЮЧЁН",
                "auto_off": "🚫 АВТОРЕЖИМ ВЫКЛЮЧЕН — РУЧНОЙ РЕЖИМ",
                "auto_on_detail": "Розетка отключится автоматически, когда цель покинет зону ({n} чистых кадров). Ручное отключение — /togglealarm.",
                "manual_only": "Тревогу можно отключить только командой /togglealarm из меню.",
                "alarm_on_manual": "🚨 Тревога включена вручную (/togglealarm). Отключение — повторная команда /togglealarm.",
                "alarm_off_manual": "🚨 Сигнализация выключена вручную (/togglealarm).",
                "cam_unavailable": "⚠️ Камера недоступна — не могу включить тревогу.",
                "force_alarm": "🚨 ПРИНУДИТЕЛЬНАЯ ТРЕВОГА (вручную)",
                "looking_for": "Ищем",
                "zone": "Зона",
                "trigger_frame": "📷 кадр срабатывания",
                "live_frame": "📺 живой кадр",
                "camera": "Камера",
                "yellow_found": "🚗 ОБНАРУЖЕНА ЦЕЛЬ!",
                "threat_gone": "Угроза устранена: цель покинула зону поиска",
                "alarm_off": "🚨 Сигнализация отключена.",
                "auto_active": "✅ АВТОРЕЖИМ АКТИВЕН",
                "manual_active": "🚫 РУЧНОЙ РЕЖИМ АКТИВЕН",
                "zone_set": "Зона поиска установлена",
                "zone_off": "Зона поиска: ВЕСЬ КАДР (зона выключена).",
                "zone_help": "Формат: /zone N3x4 C9\nN{rows}x{cols} — разбиение кадра\nC{num} — ячейка\n/zone off — весь кадр",
                "zone_bad": "Не понял формат «{arg}». Пример: /zone N3x4 C9",
                "target_current": "Текущая цель поиска",
                "target_set": "Цель поиска обновлена",
                "target_hint": "Задать: /target человек в положении стоя",
                "target_not_set": "не задана (умолчание: жёлтый транспорт)",
                "target_filter": "Фильтр поиска",
                "target_filter_kept": "Не распознал цвет/класс — фильтр не менялся",
                "any_color": "любой цвет",
                "color_filter": "цветовой фильтр",
                "lang_title": "🌐 Язык интерфейса / Interface language / Idioma de la interfaz",
                "lang_set": "Язык интерфейса: {lang}",
                "cb_cancel": "Сигнализация отключена",
                "cb_auto": "Режим переключён",
                "menu_autoguard": "Авторежим: вкл/выкл",
                "menu_togglealarm": "Тревога вкл/выкл вручную",
                "menu_zone": "Зона поиска: /zone N3x4 C9",
                "menu_target": "Цель поиска: /target текст",
                "menu_plug": "Розетки: /plug",
                "menu_lang": "Язык: EN/ES/RU",
                "menu_cam": "Камера: /cam имя",
                "cam_status": "Камера: {status}",
            },
            "en": {
                "alert": "⚠️ WARNING! ALARM! SIGNALING IS ON!\nTURN OFF VIA /togglealarm FROM THE MENU",
                "mode_title": "⚙️ OPERATING MODE",
                "current_mode": "Current mode",
                "mode_auto": "✅ AUTOMATIC",
                "mode_manual": "🚫 MANUAL",
                "zone_search": "Search zone",
                "target_search": "Search target",
                "whole_frame": "whole frame",
                "row_col": "row {r}, column {c}",
                "control_hint": "Control: menu → /autoguard, /togglealarm, /zone, /target, /cam",
                "auto_on": "✅ AUTO MODE ON",
                "auto_off": "🚫 AUTO MODE OFF — MANUAL MODE",
                "auto_on_detail": "The plug will turn off automatically when the target leaves the zone ({n} clean frames). Manual off — /togglealarm.",
                "manual_only": "The alarm can be turned off only with /togglealarm from the menu.",
                "alarm_on_manual": "🚨 Alarm turned ON manually (/togglealarm). Turn off — /togglealarm again.",
                "alarm_off_manual": "🚨 Alarm turned OFF manually (/togglealarm).",
                "cam_unavailable": "⚠️ Camera unavailable — can't turn on the alarm.",
                "force_alarm": "🚨 FORCED ALARM (manual)",
                "looking_for": "Looking for",
                "zone": "Zone",
                "trigger_frame": "📷 trigger frame",
                "live_frame": "📺 live frame",
                "camera": "Camera",
                "yellow_found": "🚗 TARGET DETECTED!",
                "threat_gone": "Threat resolved: target left the search zone",
                "alarm_off": "🚨 Alarm turned off.",
                "auto_active": "✅ AUTO MODE ACTIVE",
                "manual_active": "🚫 MANUAL MODE ACTIVE",
                "zone_set": "Search zone set",
                "zone_off": "Search zone: WHOLE FRAME (zone off).",
                "zone_help": "Format: /zone N3x4 C9\nN{rows}x{cols} — frame split\nC{num} — cell\n/zone off — whole frame",
                "zone_bad": "Couldn't understand format «{arg}». Example: /zone N3x4 C9",
                "target_current": "Current search target",
                "target_set": "Search target updated",
                "target_hint": "Set: /target person standing",
                "target_not_set": "not set (default: yellow vehicle)",
                "target_filter": "Search filter",
                "target_filter_kept": "Couldn't recognize color/class - filter kept",
                "any_color": "any color",
                "color_filter": "color filter",
                "lang_title": "🌐 Язык интерфейса / Interface language / Idioma de la interfaz",
                "lang_set": "Interface language: {lang}",
                "cb_cancel": "Alarm off",
                "cb_auto": "Mode switched",
                "menu_autoguard": "Auto mode: on/off",
                "menu_togglealarm": "Alarm on/off manually",
                "menu_zone": "Search zone: /zone N3x4 C9",
                "menu_target": "Search target: /target text",
                "menu_plug": "Plugs: /plug",
                "menu_lang": "Language: EN/ES/RU",
                "menu_cam": "Camera: /cam name",
                "cam_status": "Camera: {status}",
            },
            "es": {
                "alert": "⚠️ ¡ATENCIÓN! ¡ALARMA! ¡ALARMA ACTIVADA!\nAPAGAR CON /togglealarm DESDE EL MENÚ",
                "mode_title": "⚙️ MODO DE FUNCIONAMIENTO",
                "current_mode": "Modo actual",
                "mode_auto": "✅ AUTOMÁTICO",
                "mode_manual": "🚫 MANUAL",
                "zone_search": "Zona de búsqueda",
                "target_search": "Objetivo de búsqueda",
                "whole_frame": "todo el cuadro",
                "row_col": "fila {r}, columna {c}",
                "control_hint": "Control: menú → /autoguard, /togglealarm, /zone, /target, /cam",
                "auto_on": "✅ MODO AUTO ACTIVADO",
                "auto_off": "🚫 MODO AUTO DESACTIVADO — MODO MANUAL",
                "auto_on_detail": "El enchufe se apagará automáticamente cuando el objetivo salga de la zona ({n} cuadros limpios). Apagado manual — /togglealarm.",
                "manual_only": "La alarma solo se puede apagar con /togglealarm desde el menú.",
                "alarm_on_manual": "🚨 Alarma activada manualmente (/togglealarm). Para apagar — /togglealarm de nuevo.",
                "alarm_off_manual": "🚨 Alarma apagada manualmente (/togglealarm).",
                "cam_unavailable": "⚠️ Cámara no disponible — no puedo activar la alarma.",
                "force_alarm": "🚨 ALARMA FORZADA (manual)",
                "looking_for": "Buscando",
                "zone": "Zona",
                "trigger_frame": "📷 cuadro de disparo",
                "live_frame": "📺 cuadro en vivo",
                "camera": "Cámara",
                "yellow_found": "🚗 ¡OBJETIVO DETECTADO!",
                "threat_gone": "Amenaza resuelta: el objetivo salió de la zona de búsqueda",
                "alarm_off": "🚨 Alarma apagada.",
                "auto_active": "✅ MODO AUTO ACTIVO",
                "manual_active": "🚫 MODO MANUAL ACTIVO",
                "zone_set": "Zona de búsqueda configurada",
                "zone_off": "Zona de búsqueda: TODO EL CUADRO (zona desactivada).",
                "zone_help": "Formato: /zone N3x4 C9\nN{rows}x{cols} — división del cuadro\nC{num} — celda\n/zone off — todo el cuadro",
                "zone_bad": "No entiendo el formato «{arg}». Ejemplo: /zone N3x4 C9",
                "target_current": "Objetivo de búsqueda actual",
                "target_set": "Objetivo de búsqueda actualizado",
                "target_hint": "Configurar: /target persona de pie",
                "target_not_set": "no configurado (por defecto: vehículo amarillo)",
                "target_filter": "Filtro de búsqueda",
                "target_filter_kept": "No reconocí color/clase - filtro sin cambios",
                "any_color": "cualquier color",
                "color_filter": "filtro de color",
                "lang_title": "🌐 Язык интерфейса / Interface language / Idioma de la interfaz",
                "lang_set": "Idioma de la interfaz: {lang}",
                "cb_cancel": "Alarma apagada",
                "cb_auto": "Modo cambiado",
                "menu_autoguard": "Modo auto: on/off",
                "menu_togglealarm": "Alarma on/off manual",
                "menu_zone": "Zona: /zone N3x4 C9",
                "menu_target": "Objetivo: /target texto",
                "menu_plug": "Enchufes: /plug",
                "menu_lang": "Idioma: EN/ES/RU",
                "menu_cam": "Cámara: /cam nombre",
                "cam_status": "Cámara: {status}",
            },
        }

    def tr(self, key: str, **kw) -> str:
        """Translate key for current language with optional formatting."""
        return self.L.get(self.lang, self.L["ru"]).get(key, key).format(**kw)

    def _register_commands(self):
        """Register all command handlers."""
        self.router.register("/autoguard", self.cmd_autoguard)
        self.router.register("/togglealarm", self.cmd_togglealarm)
        self.router.register("/zone", self.cmd_zone)
        self.router.register("/target", self.cmd_target)
        self.router.register("/cam", self.cmd_cam)
        self.router.register("/plug", self.cmd_plug)
        self.router.register("/setlocal", self.cmd_setlocal)
        self.router.set_default(self.cmd_default)

    def get_camera_settings(self, cam_id: int) -> CameraSettings:
        """Get or create camera settings (lazy load from disk)."""
        if cam_id not in self.camera_settings:
            self.camera_settings[cam_id] = CameraSettings()
        return self.camera_settings[cam_id]

    def get_active_settings(self) -> CameraSettings:
        """Get settings for currently active camera."""
        return self.get_camera_settings(self.alarm.active_camera_id)

    def load_settings(self):
        """Load persisted camera settings from SettingsStore."""
        from ..storage import SettingsStore
        store = SettingsStore(self.config)
        data = store.load()
        for cam_id_str, cam_data in data.get("camera_settings", {}).items():
            cam_id = int(cam_id_str)
            self.camera_settings[cam_id] = CameraSettings.from_dict(cam_data)

    def save_settings(self):
        """Save current camera settings to SettingsStore."""
        from ..storage import SettingsStore
        store = SettingsStore(self.config)
        data = store.load()
        data["camera_settings"] = {str(k): v.to_dict() for k, v in self.camera_settings.items()}
        store.force_flush()

    def set_bot_menu(self):
        """Set Telegram bot command menu for all languages."""
        cmds = [
            {"command": "autoguard", "description": self.tr("menu_autoguard")},
            {"command": "togglealarm", "description": self.tr("menu_togglealarm")},
            {"command": "zone", "description": self.tr("menu_zone")},
            {"command": "target", "description": self.tr("menu_target")},
            {"command": "plug", "description": self.tr("menu_plug")},
            {"command": "setlocal", "description": self.tr("menu_lang")},
            {"command": "cam", "description": self.tr("menu_cam")},
        ]
        for lc in ("ru", "en", "es"):
            self.tg.delete_my_commands(lc)
            self.tg.set_my_commands(cmds, lc)

    def save_local(self, frame_bytes: bytes):
        """Save frame locally to frame_dir with timestamp + hash filename.

        Also cleans up old frames (older than 7 days) to prevent disk fill.
        """
        import os
        import hashlib
        import glob
        from datetime import datetime, timedelta

        ts = time.strftime("%Y%m%d_%H%M%S")
        path = os.path.join(self.frame_dir, f"panic_{ts}_{hashlib.md5(frame_bytes).hexdigest()[:6]}.jpg")
        with open(path, "wb") as f:
            f.write(frame_bytes)

        # Cleanup old frames (keep last 7 days)
        self._cleanup_old_frames()

    def _cleanup_old_frames(self, max_age_days: int = 7):
        """Remove frame files older than max_age_days."""
        import os
        import glob
        from datetime import datetime, timedelta

        try:
            cutoff = datetime.now() - timedelta(days=max_age_days)
            pattern = os.path.join(self.frame_dir, "panic_*.jpg")
            for filepath in glob.glob(pattern):
                try:
                    mtime = datetime.fromtimestamp(os.path.getmtime(filepath))
                    if mtime < cutoff:
                        os.remove(filepath)
                except Exception:
                    pass  # Ignore individual file errors
        except Exception:
            pass  # Ignore cleanup errors

    # ----- Desktop bridge (desktop_state/status.json + alarm_live.jpg) -----

    def _state_dir(self) -> str:
        """Shared directory the desktop app watches."""
        import os
        d = os.path.join(os.path.dirname(self.config.base_dir), "desktop_state")
        os.makedirs(d, exist_ok=True)
        return d

    def write_status(self, alarm_active: bool = None):
        """Write runtime state for the desktop monitor (atomic).

        Published to desktop_state/status.json watched by desktop UI.

        Args:
            alarm_active: Override alarm status (None = compute from AlarmManager)
        """
        import os, json
        d = self._state_dir()
        settings = self.get_active_settings()
        plugs = self.actuator_manager.camera_bindings.get(self.alarm.active_camera_id, [])
        active_cams = self.alarm.active_cameras()
        state = {
            "active_camera": self.alarm.active_camera_id,
            "auto_mode": bool(self.alarm.auto_mode),
            "alarm_active": self.alarm.any_active() if alarm_active is None else alarm_active,
            "alarm_camera": self.alarm.alarm_camera_id,
            "active_alarm_cameras": active_cams,  # concurrent alarms protocol
            "zone": str(settings.zone) if settings.zone else "",
            "target": settings.target.description if settings.target and settings.target.description else "",
            "plugs": list(plugs),
            "camera_names": {str(k): v.name for k, v in self.config.cameras.items()},
            "timestamp": time.time(),
        }
        tmp = os.path.join(d, "status.json.tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False)
            os.replace(tmp, os.path.join(d, "status.json"))
        except Exception as e:
            print(f"  status write error: {e}")

    def write_alarm_frame(self, frame):
        """Write the latest alarm frame for the desktop fullscreen window.

        Published to desktop_state/alarm_live.jpg watched by desktop UI.
        """
        import os
        try:
            ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
            if not ok:
                return
            with open(os.path.join(self._state_dir(), "alarm_live.jpg"), "wb") as f:
                f.write(buf.tobytes())
        except Exception as e:
            print(f"  alarm frame write error: {e}")

    # ----- Poll Loop -----

    def poll_loop(self):
        """Long-poll Telegram updates in background thread.

        Runs continuously, dispatching updates to handle_update().
        Handles network errors with backoff.
        """
        offset = 0
        while True:
            try:
                updates = self.tg.get_updates(offset)
                if not updates:
                    time.sleep(1)
                    continue

                for upd in updates.get("result", []):
                    offset = upd["update_id"] + 1
                    try:
                        self.handle_update(upd)
                    except Exception as e:
                        print(f"Update error: {e}")
            except Exception as e:
                print(f"Poll error: {e}")
                time.sleep(2)

    def handle_update(self, upd: Dict):
        """Dispatch update to callback or command handler."""
        if "callback_query" in upd:
            self.handle_callback(upd["callback_query"])
        elif "message" in upd:
            m = upd["message"]
            mid = m.get("message_id")
            if mid:
                # Track incoming messages so callbacks know which alarm to edit.
                # Per-camera alarms own their msg_id; here we only need to avoid
                # deleting user messages on cancel (alarms track their own ids).
                pass

            text = (m.get("text") or "").strip()
            ctx = CommandContext(
                text=text,
                args=text[len(text.split()[0]):] if text else "",
                message_id=mid or 0,
                chat_id=m.get("chat", {}).get("id", self.config.telegram.chat_id),
                user_id=m.get("from", {}).get("id", 0),
            )
            self.router.route(ctx)

    # ----- Detection Loop -----

    def detection_loop(self):
        """Monitor ALL cameras simultaneously with per-camera settings.

        YOLO processes frames -> annotates with boxes -> stores annotated frames.
        Bot consumes annotated frames for live updates and alarm triggers.

        Runs in main thread. Sleeps detect_every between cycles.

        Key data structures:
        - streak[cam_id]: consecutive frames with matches (trigger threshold)
        - clean[cam_id]: consecutive frames without matches (auto-resolve threshold)
        - annotated_frames[cam_id]: latest ProcessedFrame per camera (for live updates)

        Alarm triggering:
        - If streak >= require_frames AND camera not already in alarm -> trigger
        - Uses ANNOTATED frame (with YOLO boxes) for trigger
        - Resets streak to 0 to prevent re-trigger spam

        Auto-resolve:
        - Per camera: if auto_mode AND clean >= auto_resolve_frames -> cancel
        """
        from ..detectors import create_pipeline_from_config, ProcessedFrame

        streak = {cid: 0 for cid in range(1, 9)}
        clean = {cid: 0 for cid in range(1, 9)}

        # Per-camera annotated frame store for live updates
        annotated_frames: Dict[int, ProcessedFrame] = {}

        while True:
            time.sleep(self.config.detection.detect_every)

            for cam_id in range(1, 9):
                cam = self.camera_manager.get(cam_id)
                if not cam or not cam.alive:
                    continue

                # Use downscaled frame for YOLO on 4K cameras (Camera 2)
                if cam_id == 2 and hasattr(cam, 'get_downscaled_frame'):
                    frame = cam.get_downscaled_frame(max_width=1280)
                else:
                    frame = cam.latest
                if frame is None:
                    continue

                # Get camera-specific settings
                settings = self.get_camera_settings(cam_id)
                zone = settings.zone
                target = settings.target or Target()

                # Create pipeline for this camera
                pipeline = create_pipeline_from_config(self.config, target, zone)
                processed = pipeline.process(frame, zone)
                processed.camera_id = cam_id

                # Store annotated frame for this camera (bot will consume)
                annotated_frames[cam_id] = processed

                matches = processed.matches
                all_dets = processed.all_detections

                if len(matches) >= self.config.detection.min_yellow_vehicles:
                    streak[cam_id] += 1
                    clean[cam_id] = 0
                else:
                    streak[cam_id] = 0
                    clean[cam_id] += 1

                # Log
                status = (f"[cam {cam_id}] hit={len(matches)}/{self.config.detection.min_yellow_vehicles} "
                          f"streak={streak[cam_id]}/{self.config.detection.require_frames} "
                          f"clean={clean[cam_id]}/{self.config.detection.auto_resolve_frames} "
                          f"zone={self.zone_label()} | "
                          + ", ".join(f"{d.name} c={d.confidence:.2f} y={d.color_fraction*100:.0f}%" for d in all_dets) or "empty")
                print(status, flush=True)

                # Trigger alarm for THIS camera (concurrent, no global lock)
                # Use ANNOTATED frame for alarm trigger
                if streak[cam_id] >= self.config.detection.require_frames and not self.alarm.is_cam_active(cam_id):
                    m = matches[0]
                    desc = (f"{self.tr('yellow_found')}"
                            f"({m.name} conf={m.confidence:.2f}, color={m.color_fraction*100:.0f}%)")
                    self.trigger_alarm(desc, processed.annotated, cam_id=cam_id)
                    streak[cam_id] = 0  # prevent re-trigger spam while active

            # Auto-resolve per camera: each alarm resolves independently
            for alarm_cam in list(self.alarm.active_cameras()):
                state = self.alarm.get(alarm_cam)
                if state.auto_mode and clean.get(alarm_cam, 0) >= self.config.detection.auto_resolve_frames:
                    self.cancel_alarm(cam_id=alarm_cam, note=self.tr("threat_gone"))

            # Periodic status update for heartbeat/watchdog
            self.write_status()

        # Store reference for bot to access annotated frames
        self._annotated_frames = annotated_frames

    # ----- Command Handlers -----

    def cmd_autoguard(self, ctx: CommandContext):
        """Toggle global auto mode."""
        self.alarm.auto_mode = not self.alarm.auto_mode
        mode = self.tr("mode_auto") if self.alarm.auto_mode else self.tr("mode_manual")
        detail = self.tr("auto_on_detail", n=self.config.detection.auto_resolve_frames) if self.alarm.auto_mode else self.tr("manual_only")
        self.tg.send_message(ctx.chat_id, f"{self.tr('mode_title')}\n{self.tr('current_mode')}: {mode}\n{detail}")

    def cmd_togglealarm(self, ctx: CommandContext):
        """Manually toggle alarm for active camera."""
        cam_id = self.alarm.active_camera_id
        cam = self.camera_manager.get(cam_id)
        if not cam or not cam.alive:
            self.tg.send_message(ctx.chat_id, self.tr("cam_unavailable"))
            return

        state = self.alarm.get(cam_id)
        if state.is_active:
            # Manual cancel - deactivate
            self.alarm.deactivate(cam_id, keep_trigger=True)
            self.tg.send_message(ctx.chat_id, self.tr("alarm_off_manual"))
        else:
            # Manual trigger - activate
            self.alarm.activate(cam_id, auto=self.alarm.auto_mode, manual=True)
            # Send trigger frame
            frames = self._annotated_frames.get(cam_id)
            if frames and frames.annotated is not None:
                ok, buf = cv2.imencode(".jpg", frames.annotated, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
                if ok:
                    self.tg.send_photo(ctx.chat_id, buf.tobytes(), caption=self.tr("force_alarm"))
            self.tg.send_message(ctx.chat_id, self.tr("alarm_on_manual"))

    def cmd_zone(self, ctx: CommandContext):
        """Set or show search zone for active camera."""
        args = ctx.args.strip()
        settings = self.get_active_settings()

        if not args:
            # Show current zone
            if settings.zone:
                self.tg.send_message(ctx.chat_id, f"{self.tr('zone_search')}: {settings.zone}")
            else:
                self.tg.send_message(ctx.chat_id, self.tr("zone_off"))
            return

        if args.lower() in ("off", "none", "0"):
            settings.zone = None
            self.save_settings()
            self.tg.send_message(ctx.chat_id, self.tr("zone_off"))
            return

        zone = parse_zone_spec(args)
        if zone:
            settings.zone = zone
            self.save_settings()
            self.tg.send_message(ctx.chat_id, f"{self.tr('zone_set')}: {zone} ({zone.row}, {zone.col})")
        else:
            self.tg.send_message(ctx.chat_id, self.tr("zone_bad", arg=args))

    def cmd_target(self, ctx: CommandContext):
        """Set or show search target for active camera."""
        args = ctx.args.strip()
        settings = self.get_active_settings()

        if not args:
            # Show current target
            if settings.target and settings.target.description:
                self.tg.send_message(ctx.chat_id, f"{self.tr('target_current')}: {settings.target.filter_label()}")
            else:
                self.tg.send_message(ctx.chat_id, self.tr("target_not_set"))
            return

        target = parse_target_text(args)
        if target.color_ranges or target.classes:
            settings.target = target
            self.save_settings()
            self.tg.send_message(ctx.chat_id, f"{self.tr('target_set')}: {target.filter_label()}")
        else:
            self.tg.send_message(ctx.chat_id, self.tr("target_filter_kept"))

    def cmd_cam(self, ctx: CommandContext):
        """Switch active camera."""
        args = ctx.args.strip()
        if not args:
            cam_name = self.config.cameras.get(self.alarm.active_camera_id, CameraConfig(0, "Unknown", "")).name
            self.tg.send_message(ctx.chat_id, f"{self.tr('camera')}: {cam_name}")
            return

        # Try to find camera by name or ID
        for cam_id, cam_cfg in self.config.cameras.items():
            if args.lower() in cam_cfg.name.lower() or args == str(cam_id):
                self.alarm.active_camera_id = cam_id
                self.tg.send_message(ctx.chat_id, self.tr("cam_status", status=cam_cfg.name))
                return

        self.tg.send_message(ctx.chat_id, f"Camera '{args}' not found")

    def cmd_plug(self, ctx: CommandContext):
        """Show actuator status."""
        plugs = self.actuator_manager.list_all()
        if not plugs:
            self.tg.send_message(ctx.chat_id, "No actuators configured")
            return

        lines = ["Actuators:"]
        for name, info in plugs.items():
            if "error" in info:
                lines.append(f"  {name}: ERROR - {info['error']}")
            else:
                status = "ON" if info.get("status") else "OFF"
                power = info.get("power_w")
                power_str = f" ({power:.1f}W)" if power is not None else ""
                lines.append(f"  {name} ({info['type']}): {status}{power_str}")

        self.tg.send_message(ctx.chat_id, "\n".join(lines))

    def cmd_setlocal(self, ctx: CommandContext):
        """Set interface language."""
        args = ctx.args.strip().lower()
        if args in ("ru", "en", "es"):
            self.lang = args
            self.tg.send_message(ctx.chat_id, self.tr("lang_set", lang=args))
        else:
            # Show language menu
            kb = {"inline_keyboard": [[
                {"text": "Русский", "callback_data": "set_lang:ru"},
                {"text": "English", "callback_data": "set_lang:en"},
                {"text": "Español", "callback_data": "set_lang:es"},
            ]]}
            import json
            self.tg.send_message(ctx.chat_id, self.tr("lang_title"), reply_markup=json.dumps(kb))

    def cmd_default(self, ctx: CommandContext):
        """Default handler for unknown commands."""
        self.tg.send_message(ctx.chat_id, self.tr("control_hint"))

    def handle_callback(self, query: Dict):
        """Handle inline button callbacks."""
        data = query.get("data", "")
        qid = query.get("id")
        chat_id = query.get("message", {}).get("chat", {}).get("id", self.config.telegram.chat_id)

        if data == "cancel_alarm":
            self.cancel_alarm(note=self.tr("cb_cancel"))
            self.tg.answer_callback_query(qid, self.tr("cb_cancel"))
        elif data == "auto_toggle":
            self.alarm.auto_mode = not self.alarm.auto_mode
            self.tg.answer_callback_query(qid, self.tr("cb_auto"))
        elif data.startswith("set_lang:"):
            lang = data.split(":")[1]
            if lang in ("ru", "en", "es"):
                self.lang = lang
                self.set_bot_menu()
                self.tg.answer_callback_query(qid, self.tr("lang_set", lang=lang))
        else:
            self.tg.answer_callback_query(qid, "Unknown callback")

    def zone_label(self) -> str:
        """Human-readable zone label for current camera."""
        settings = self.get_active_settings()
        if settings.zone:
            return f"{settings.zone} (row={settings.zone.row}, col={settings.zone.col})"
        return self.tr("whole_frame")

    def trigger_alarm(self, desc: str, frame, cam_id: int):
        """Trigger alarm for a specific camera."""
        self.alarm.activate(cam_id, auto=self.alarm.auto_mode, manual=False)

        # Send trigger frame
        ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        if ok:
            caption = f"{desc}\n{self.tr('camera')}: {self.config.cameras.get(cam_id, CameraConfig(0,'','')).name}"
            result = self.tg.send_photo(chat_id=self.config.telegram.chat_id, photo_bytes=buf.tobytes(), caption=caption)
            if result:
                msg_id = result.get("message_id")
                state = self.alarm.get(cam_id)
                state.msg_id = msg_id
                state.known_msg_ids.add(msg_id)
                state.first_frame = buf.tobytes()

    def cancel_alarm(self, cam_id: int = None, note: str = None):
        """Cancel alarm for specific camera or active camera."""
        if cam_id is None:
            cam_id = self.alarm.active_camera_id

        result = self.alarm.deactivate(cam_id, keep_trigger=True)
        if note:
            self.tg.send_message(self.config.telegram.chat_id, note)
        return result

    def _update_loop(self, cam_id: int):
        """Background thread: send live frame updates for active alarm."""
        state = self.alarm.get(cam_id)
        interval = self.config.detection.update_every

        while state.is_active:
            time.sleep(interval)
            # Get latest annotated frame
            frames = self._annotated_frames.get(cam_id)
            if frames and frames.annotated is not None:
                ok, buf = cv2.imencode(".jpg", frames.annotated, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
                if ok:
                    self.tg.edit_message_media(
                        chat_id=self.config.telegram.chat_id,
                        message_id=state.msg_id,
                        photo_bytes=buf.tobytes(),
                        caption=f"{self.tr('live_frame')}\n{time.strftime('%H:%M:%S')}"
                    )
                    state.known_msg_ids.add(state.msg_id)


# ============================================================================
# ENTRY POINT
# ============================================================================

def main():
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

    base_dir = os.path.dirname(os.path.abspath(__file__))
    from ..config import load_config
    config = load_config(base_dir)

    # Kill other instances
    # ... (zombie killer from original)

    bot = SuperGuardBot(config)
    bot.load_settings()
    bot.set_bot_menu()

    # Start poll loop in background
    threading.Thread(target=bot.poll_loop, daemon=True).start()

    # Start detection loop
    bot.detection_loop()


if __name__ == "__main__":
    main()