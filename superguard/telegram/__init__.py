"""
SuperGuard Alarm - Telegram Bot Layer

Provides:
- TelegramClient: HTTP wrapper with retry, rate limiting
- CommandRouter: Command parsing and dispatch
- CallbackHandler: Inline button callbacks
- MenuManager: setMyCommands per-language
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
from ..models import Alarm, CameraSettings, Zone, Target, parse_zone_spec, parse_target_text
from ..cameras import CameraManager
from ..actuators import ActuatorManager
from ..detectors import create_pipeline_from_config


# ============================================================================
# TELEGRAM CLIENT (with retry & rate limiting)
# ============================================================================

class TelegramClient:
    """Telegram Bot API client with retry logic and rate limiting."""
    
    def __init__(self, config: TelegramConfig):
        self.config = config
        self.api_url = f"https://api.telegram.org/bot{config.token}"
        self.session = requests.Session()
        self._last_call = 0
        self._min_interval = 0.05  # 20 calls/sec max
    
    def _rate_limit(self):
        """Enforce minimum interval between calls."""
        elapsed = time.time() - self._last_call
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
    
    def call(self, method: str, max_retries: int = 3, **kwargs) -> Optional[Dict]:
        """Call Telegram API method with retry logic."""
        self._rate_limit()
        
        for attempt in range(max_retries):
            try:
                if "files" in kwargs:
                    files = kwargs.pop("files")
                    r = self.session.post(f"{self.api_url}/{method}", files=files, data=kwargs, timeout=20)
                else:
                    r = self.session.post(f"{self.api_url}/{method}", json=kwargs, timeout=20)
                
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
    
    # Convenience methods
    def send_message(self, chat_id: int, text: str, reply_markup: str = None, parse_mode: str = "HTML") -> Optional[Dict]:
        data = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
        if reply_markup:
            data["reply_markup"] = reply_markup
        return self.call("sendMessage", **data)
    
    def send_photo(self, chat_id: int, photo_bytes: bytes, caption: str = "", 
                   reply_markup: str = None, parse_mode: str = "HTML") -> Optional[Dict]:
        files = {"photo": ("frame.jpg", photo_bytes, "image/jpeg")}
        data = {"chat_id": chat_id, "caption": caption, "parse_mode": parse_mode}
        if reply_markup:
            data["reply_markup"] = reply_markup
        return self.call("sendPhoto", files=files, **data)
    
    def edit_message_text(self, chat_id: int, message_id: int, text: str, 
                          parse_mode: str = "HTML") -> Optional[Dict]:
        return self.call("editMessageText", chat_id=chat_id, message_id=message_id, 
                        text=text, parse_mode=parse_mode)
    
    def edit_message_media(self, chat_id: int, message_id: int, photo_bytes: bytes, 
                           caption: str = "", parse_mode: str = "HTML") -> Optional[Dict]:
        # media = JSON string (form field) referencing attach://photo (actual file)
        media = json.dumps({"type": "photo", "media": "attach://photo", 
                            "caption": caption, "parse_mode": parse_mode})
        files = {"photo": ("frame.jpg", photo_bytes, "image/jpeg")}
        return self.call("editMessageMedia", files=files, 
                         chat_id=chat_id, message_id=message_id, media=media)
    
    def delete_message(self, chat_id: int, message_id: int) -> bool:
        result = self.call("deleteMessage", chat_id=chat_id, message_id=message_id)
        return result is not None
    
    def answer_callback_query(self, callback_query_id: str, text: str) -> bool:
        result = self.call("answerCallbackQuery", callback_query_id=callback_query_id, text=text)
        return result is not None
    
    def set_my_commands(self, commands: List[Dict], language_code: str) -> bool:
        result = self.call("setMyCommands", commands=commands, language_code=language_code)
        return result is not None
    
    def delete_my_commands(self, language_code: str) -> bool:
        result = self.call("deleteMyCommands", language_code=language_code)
        return result is not None
    
    def get_updates(self, offset: int, timeout: int = 25) -> Optional[Dict]:
        return self.call("getUpdates", offset=offset, timeout=timeout)


# ============================================================================
# COMMAND ROUTER
# ============================================================================

@dataclass
class CommandContext:
    """Context passed to command handlers."""
    text: str
    args: str
    message_id: int
    chat_id: int
    user_id: int


class CommandRouter:
    """Routes commands to handlers based on text prefix."""
    
    def __init__(self):
        self.handlers: Dict[str, Callable[[CommandContext], None]] = {}
        self.default_handler: Optional[Callable[[CommandContext], None]] = None
    
    def register(self, prefix: str, handler: Callable[[CommandContext], None]):
        """Register handler for command prefix (e.g., '/zone')."""
        self.handlers[prefix.lower()] = handler
    
    def set_default(self, handler: Callable[[CommandContext], None]):
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
    """Main bot application - wires all components together."""
    
    def __init__(self, config: SuperGuardConfig):
        self.config = config
        
        # Core components
        self.tg = TelegramClient(config.telegram)
        self.alarm = Alarm()
        self.camera_manager = CameraManager(config)
        self.actuator_manager = ActuatorManager(config)
        
        # Per-camera settings (loaded from disk)
        self.camera_settings: Dict[int, CameraSettings] = {}
        self.active_camera_id = 1
        
        # Localization
        self.lang = "ru"
        self._load_i18n()
        
        # Command router
        self.router = CommandRouter()
        self._register_commands()
        
        # Frame directory
        self.frame_dir = config.frame_dir
        import os
        os.makedirs(self.frame_dir, exist_ok=True)
    
    def _load_i18n(self):
        """Load translation dictionaries."""
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
        """Translate key into current language."""
        txt = self.L[self.lang].get(key) or self.L["ru"].get(key, key)
        if kw:
            try:
                txt = txt.format(**kw)
            except (KeyError, IndexError):
                pass
        return txt
    
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
    
    # ----- Command Handlers -----
    
    def cmd_autoguard(self, ctx: CommandContext):
        self.toggle_auto()
    
    def cmd_togglealarm(self, ctx: CommandContext):
        self.toggle_alarm()
    
    def cmd_zone(self, ctx: CommandContext):
        arg = ctx.args.strip()
        if not arg or arg.lower() in ("?", "help", "справка", "ayuda"):
            self.tg.send_message(ctx.chat_id, f"📍 {self.tr('zone_search')}: {self.zone_label()}\n\n{self.tr('zone_help')}")
            return
        
        if arg.lower() in ("off", "none", "всё", "все", "0", "todo", "toda", "nada", "desactivar"):
            self.set_zone(None)
            return
        
        zone = parse_zone_spec(arg)
        if zone is None:
            self.tg.send_message(ctx.chat_id, f"⚠️ {self.tr('zone_bad', arg=arg)}")
            return
        
        self.set_zone(zone)
    
    def cmd_target(self, ctx: CommandContext):
        arg = ctx.args.strip()
        if not arg or arg.lower() in ("?", "help", "справка", "ayuda"):
            self.tg.send_message(ctx.chat_id, f"🔍 {self.tr('target_current')}: {self.target_label()}\n{self.tr('target_hint')}")
            return
        
        self.set_target(arg)
    
    def cmd_cam(self, ctx: CommandContext):
        arg = ctx.args.strip()
        if not arg or arg.lower() in ("?", "list", "список", "lista"):
            lines = []
            for cid in range(1, 9):
                cam = self.camera_manager.get(cid)
                status = "🟢" if cam and cam.alive else "🔴"
                marker = " ← ACTIVE" if cid == self.active_camera_id else ""
                name = self.config.cameras.get(cid, CameraConfig(cam_id=cid, name=f"Camera {cid}", url="")).name
                lines.append(f"{status} {name} ({cid}){marker}")
            self.tg.send_message(ctx.chat_id, "Доступные камеры (1-8):\n" + "\n".join(lines))
            return
        
        if arg.lower() in ("status", "статус", "estado"):
            lines = []
            for cid in range(1, 9):
                cam = self.camera_manager.get(cid)
                status = "🟢 alive" if cam and cam.alive else "🔴 dead"
                name = self.config.cameras.get(cid, CameraConfig(cam_id=cid, name=f"Camera {cid}", url="")).name
                lines.append(f"{name} ({cid}): {status}")
            self.tg.send_message(ctx.chat_id, "Статус камер:\n" + "\n".join(lines))
            return
        
        try:
            num = int(arg)
            if 1 <= num <= 8:
                self.switch_camera(num)
                return
        except ValueError:
            pass
        
        self.tg.send_message(ctx.chat_id, f"Камера '{arg}' не найдена. Используйте номер 1-8. /cam ? для списка.")
    
    def cmd_plug(self, ctx: CommandContext):
        """Configure plugs for the ACTIVE camera.
        
        Usage:
          /plug              - show plugs bound to the active camera
          /plug 1 2 3        - bind plugs plug1, plug2, plug3 to the active camera
          /plug test         - test all plugs
        """
        arg = ctx.args.strip()
        
        if not arg or arg.lower() in ("?", "help", "справка", "ayuda", "list", "список", "lista"):
            self.list_plugs()
            return
        
        if arg.lower() == "test":
            self.test_plugs()
            return
        
        # Parse plug numbers: "/plug 1 2 3" -> ["plug1", "plug2", "plug3"]
        numbers = []
        for token in arg.split():
            try:
                numbers.append(int(token))
            except ValueError:
                self.tg.send_message(ctx.chat_id,
                                     f"❌ Не понял номер розетки: '{token}'. Пример: /plug 1 2 3")
                return
        
        plug_names = [f"plug{n}" for n in numbers]
        self.set_active_camera_plugs(plug_names)
    
    def set_active_camera_plugs(self, plug_names: List[str]):
        """Bind a list of plugs to the active camera and persist the binding."""
        available = [p["name"] for p in self.actuator_manager.list_all()]
        unknown = [n for n in plug_names if n not in available]
        if unknown:
            self.tg.send_message(self.config.telegram.chat_id,
                                 f"❌ Розетки не найдены: {', '.join(unknown)}. Доступные: {', '.join(available)}")
            return
        
        cam_id = self.active_camera_id
        self.actuator_manager.set_camera_bindings(cam_id, plug_names)
        
        # Persist in camera settings
        settings = self.get_camera_settings(cam_id)
        settings.actuator = plug_names
        self.save_camera_settings()
        
        cam_name = self.config.cameras.get(cam_id, CameraConfig(cam_id=cam_id, name=f"Camera {cam_id}", url="")).name
        plugs_str = ", ".join(plug_names) if plug_names else "нет"
        self.tg.send_message(self.config.telegram.chat_id,
                             f"✅ Камера {cam_id} ({cam_name}) → розетки: {plugs_str}")
    
    def cmd_setlocal(self, ctx: CommandContext):
        keyboard = json.dumps({"inline_keyboard": [[
            {"text": "🇬🇧 EN", "callback_data": "set_lang:en"},
            {"text": "🇪🇸 ES", "callback_data": "set_lang:es"},
            {"text": "🇷🇺 RU", "callback_data": "set_lang:ru"}]]})
        self.tg.send_message(ctx.chat_id, self.tr("lang_title"), reply_markup=keyboard)
    
    def cmd_default(self, ctx: CommandContext):
        # Delete non-command messages to keep chat clean
        self.tg.delete_message(ctx.chat_id, ctx.message_id)
    
    # ----- Callback Handlers -----
    
    def handle_callback(self, callback_query: Dict):
        data = callback_query.get("data")
        cb_id = callback_query["id"]
        
        if data and data.startswith("set_lang:"):
            code = data.split(":", 1)[1]
            self.tg.answer_callback_query(cb_id, self.tr("lang_set", lang=code))
            self.set_language(code)
        elif data == "cancel_alarm":
            self.tg.answer_callback_query(cb_id, self.tr("cb_cancel"))
            self.cancel_alarm()
        elif data == "auto_toggle":
            self.tg.answer_callback_query(cb_id, self.tr("cb_auto"))
            self.toggle_auto()
    
    # ----- Core Logic -----
    
    def set_language(self, code: str):
        if code not in self.L:
            return
        self.lang = code
        self.save_settings()
        self.set_bot_menu()
        self.refresh_control_msg()
        self.tg.send_message(self.config.telegram.chat_id, self.tr("lang_set", lang=code))
    
    def toggle_auto(self):
        self.alarm.auto_mode = not self.alarm.auto_mode
        self.save_settings()
        self.refresh_control_msg()
        self.tg.send_message(self.config.telegram.chat_id, 
                            self.tr("auto_on") if self.alarm.auto_mode else self.tr("auto_off"))
        if self.alarm.auto_mode:
            self.tg.send_message(self.config.telegram.chat_id, 
                                self.tr("auto_on_detail", n=self.config.detection.auto_resolve_frames))
    
    def toggle_alarm(self):
        if self.alarm.is_active:
            self.cancel_alarm(note=self.tr("alarm_off_manual"))
        else:
            cam = self.camera_manager.get_active()
            if not cam or not cam.alive:
                self.tg.send_message(self.config.telegram.chat_id, self.tr("cam_unavailable"))
                return
            frame = cam.latest
            if frame is None:
                self.tg.send_message(self.config.telegram.chat_id, self.tr("cam_unavailable"))
                return
            # Manual trigger duplicates the automatic alarm behavior:
            self.trigger_alarm(self.tr("force_alarm"), frame)
            if self.alarm.auto_mode:
                # Auto mode: alarm will cancel itself when the target leaves the zone
                self.tg.send_message(self.config.telegram.chat_id,
                                     self.tr("alarm_on_manual") + "\n" +
                                     self.tr("auto_on_detail", n=self.config.detection.auto_resolve_frames))
            else:
                # Manual mode: alarm waits for manual /togglealarm
                self.tg.send_message(self.config.telegram.chat_id,
                                     self.tr("alarm_on_manual") + "\n" + self.tr("manual_only"))
    
    def cancel_alarm(self, note: str = ""):
        # Save the alarm camera BEFORE deactivate() (it resets alarm_camera_id)
        cam_id = self.alarm.alarm_camera_id
        result = self.alarm.deactivate(keep_trigger=True)
        if result.get("already_inactive"):
            return
        
        # Turn off actuators for the alarm camera
        if cam_id:
            self.set_actuators(False, cam_id)
        
        # Delete messages (except trigger)
        for mid in result.get("delete_msg_ids", []):
            self.tg.delete_message(self.config.telegram.chat_id, mid)
        
        if note:
            self.tg.send_message(self.config.telegram.chat_id, note)
        self.tg.send_message(self.config.telegram.chat_id, self.tr("alarm_off"))
        self.refresh_control_msg()
    
    def set_zone(self, zone: Optional[Zone]):
        settings = self.get_active_settings()
        settings.zone = zone
        self.save_camera_settings()
        self.refresh_control_msg()
        self.tg.send_message(self.config.telegram.chat_id, 
                            f"📍 {self.tr('zone_set')}: {self.zone_label()}" if zone 
                            else f"📍 {self.tr('zone_off')}")
    
    def set_target(self, text: str):
        target = parse_target_text(text)
        settings = self.get_active_settings()
        settings.target = target
        self.save_camera_settings()
        self.refresh_control_msg()
        
        if not target.classes and not target.color_ranges:
            self.tg.send_message(self.config.telegram.chat_id, 
                                f"🔍 {self.tr('target_set')}: {text}\n{self.tr('target_filter_kept')}: {target.filter_label()}")
        else:
            self.tg.send_message(self.config.telegram.chat_id, 
                                f"🔍 {self.tr('target_set')}: {text}\n🔍 {self.tr('target_filter')}: {target.filter_label()}")
    
    def switch_camera(self, cam_id: int):
        if self.alarm.is_active:
            self.alarm.alarm_camera_id = cam_id
        
        self.active_camera_id = cam_id
        self.camera_manager.set_active(cam_id)
        
        # Load settings for new camera
        self.load_camera_settings()
        self.save_settings()
        self.refresh_control_msg()
        
        name = self.config.cameras.get(cam_id, CameraConfig(cam_id=cam_id, name=f"Camera {cam_id}", url="")).name
        self.tg.send_message(self.config.telegram.chat_id, f"Камера переключена: {name}")
    
    def list_plugs(self):
        plugs = self.actuator_manager.list_all()
        cam_id = self.active_camera_id
        active_bindings = self.actuator_manager.camera_bindings.get(cam_id, [])
        
        lines = [f"🔌 Розетки. Активная камера: {cam_id}"]
        lines.append(f"   → привязаны: {', '.join(active_bindings) if active_bindings else 'нет'}")
        lines.append("")
        lines.append("Список розеток:")
        for p in plugs:
            cam_list = ", ".join(f"cam{c}" for c in p["cameras"]) if p["cameras"] else "нет"
            lines.append(f"  {p['status_icon']} {p['name']} ({p['type']}): {p['status']} | cameras: {cam_list}")
        lines.append("")
        lines.append("Задать: /plug 1 2 3 — розетки для активной камеры")
        self.tg.send_message(self.config.telegram.chat_id, "\n".join(lines))
    
    def test_plugs(self):
        results = self.actuator_manager.test_all()
        lines = ["🔌 Тестирование розеток..."]
        for r in results:
            icon = "🟢" if r["status"] in ("OK", "RECONNECTED") else "🔴"
            recon = " (переподключено)" if r.get("reconnected") else ""
            lines.append(f"  {icon} {r['name']}: {r['status']}{recon}")
        self.tg.send_message(self.config.telegram.chat_id, "\n".join(lines))
    
    # ----- Alarm Trigger & Updates -----
    
    def trigger_alarm(self, desc: str, frame: np.ndarray, cam_id: Optional[int] = None):
        # Use the camera that triggered the alarm (from detection loop) or active camera (manual)
        cam_id = cam_id or self.active_camera_id
        # Manual trigger duplicates automatic alarm: preserve the current auto_mode.
        # auto_mode=True  -> alarm auto-cancels when the target leaves the zone
        # auto_mode=False -> alarm stays until manual /togglealarm
        if not self.alarm.activate(cam_id, auto=self.alarm.auto_mode):
            return
        
        # The triggering camera BECOMES the active camera and stays active
        # until another camera becomes active (via alarm or /cam command).
        if self.active_camera_id != cam_id:
            self.active_camera_id = cam_id
            self.camera_manager.set_active(cam_id)
            self.load_camera_settings()
        
        # Turn on actuators for the triggering camera
        self.set_actuators(True, cam_id)
        
        # Send trigger frame (msg A)
        ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
        frame_bytes = buf.tobytes()
        
        cam_name = self.config.cameras.get(cam_id, CameraConfig(cam_id=cam_id, name=f"Camera {cam_id}", url="")).name
        caption = (f"{self.tr('alert')}\n\n📅 {time.strftime('%H:%M:%S')}\n{desc}\n"
                   f"\n🔍 {self.tr('looking_for')}: {self.target_label()}\n"
                   f"📍 {self.tr('zone')}: {self.zone_label()}\n"
                   f"📷 {self.tr('camera')}: {cam_name}\n\n"
                   f"📷 {self.tr('trigger_frame')}")
        
        res = self.tg.send_photo(self.config.telegram.chat_id, frame_bytes, caption)
        if not res:
            self.cancel_alarm()
            return
        
        self.alarm.trigger_msg_id = res["message_id"]
        self.alarm.known_msg_ids.add(res["message_id"])
        self.save_local(frame_bytes)
        
        # Send live frame (msg B) after 1 second
        threading.Thread(target=self._send_live_after_delay, daemon=True).start()
    
    def _send_live_after_delay(self):
        """Send the first live frame (msg B) ~1s after trigger, then start the update loop."""
        try:
            time.sleep(1.0)
            cam_id = self.alarm.alarm_camera_id
            cam = self.camera_manager.get(cam_id) if cam_id else None
            live = cam.latest if cam else None
            
            if live is None:
                return
            
            ok, buf = cv2.imencode(".jpg", live, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
            if not ok:
                return
            
            cam_name = self.config.cameras.get(cam_id, CameraConfig(cam_id=cam_id, name=f"Camera {cam_id}", url="")).name
            caption = (f"{self.tr('alert')}\n\n📅 {time.strftime('%H:%M:%S')}\n"
                       f"📺 {self.tr('live_frame')}\n"
                       f"📷 {self.tr('camera')}: {cam_name}")
            
            res = self.tg.send_photo(self.config.telegram.chat_id, buf.tobytes(), caption)
            if res:
                self.alarm.live_msg_id = res["message_id"]
                self.alarm.known_msg_ids.add(res["message_id"])
                self.save_local(buf.tobytes())
                # Start update loop
                threading.Thread(target=self._update_loop, daemon=True).start()
        except Exception as e:
            print(f"  Live frame send error: {e}")
    
    def _update_loop(self):
        """Update the live frame (msg B) every update_every seconds while alarm is active."""
        while True:
            time.sleep(self.config.detection.update_every)
            if not self.alarm.is_active:
                return
            
            mid = self.alarm.live_msg_id
            cam_id = self.alarm.alarm_camera_id
            if mid is None or cam_id is None:
                continue
            
            cam = self.camera_manager.get(cam_id)
            if not cam:
                continue
            
            frame = cam.latest
            if frame is None:
                continue
            
            ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
            if not ok:
                continue
            
            caption = f"{self.tr('alert')}\n\n📅 {time.strftime('%H:%M:%S')}\n📺 {self.tr('live_frame')}"
            try:
                if self.tg.edit_message_media(self.config.telegram.chat_id, mid, buf.tobytes(), caption):
                    self.save_local(buf.tobytes())
            except Exception as e:
                print(f"  Live frame update error: {e}")
    
    def set_actuators(self, on: bool, cam_id: int):
        actuators = self.actuator_manager.get_for_camera(cam_id)
        if not actuators:
            print(f"  PLUG {'ON' if on else 'OFF'} FAILED: No actuators for cam={cam_id}")
            return False
        
        results = []
        for act in actuators:
            try:
                result = act.turn_on() if on else act.turn_off()
                results.append(result)
                print(f"  Actuator '{act.name}' {'ON' if on else 'OFF'}: {'success' if result else 'failed'}")
            except Exception as e:
                print(f"  Actuator error: {e}")
                results.append(False)
        
        return any(results)
    
    # ----- Settings Persistence -----
    
    def get_active_settings(self) -> CameraSettings:
        return self.get_camera_settings(self.active_camera_id)
    
    def get_camera_settings(self, cam_id: int) -> CameraSettings:
        if cam_id not in self.camera_settings:
            self.camera_settings[cam_id] = CameraSettings()
        return self.camera_settings[cam_id]
    
    def load_camera_settings(self):
        """Load settings for active camera from persisted data."""
        settings = self.get_active_settings()
        if settings.zone:
            # Zone already loaded from disk
            pass
        if settings.target:
            # Target already loaded
            pass
    
    def save_camera_settings(self):
        """Save active camera settings to disk."""
        import os, json
        data = {"camera_settings": {}, "active_camera": self.active_camera_id, "lang": self.lang}
        
        # Load existing
        try:
            with open(self.config.settings_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            pass
        
        # Update
        cam_key = str(self.active_camera_id)
        settings = self.get_active_settings()
        data["camera_settings"][cam_key] = settings.to_dict()
        data["active_camera"] = self.active_camera_id
        data["lang"] = self.lang
        
        with open(self.config.settings_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def save_settings(self):
        """Save global settings (lang, auto, active_camera)."""
        self.save_camera_settings()
    
    def load_settings(self):
        """Load all settings from disk."""
        import os, json
        if not os.path.exists(self.config.settings_file):
            return
        
        try:
            with open(self.config.settings_file, encoding="utf-8") as f:
                data = json.load(f)
            
            self.lang = data.get("lang", "ru")
            self.alarm.auto_mode = data.get("auto", False)
            self.active_camera_id = data.get("active_camera", 1)
            self.camera_manager.set_active(self.active_camera_id)
            
            # Load per-camera settings
            for cam_key, cs_data in data.get("camera_settings", {}).items():
                cam_id = int(cam_key)
                settings = CameraSettings.from_dict(cs_data)
                self.camera_settings[cam_id] = settings
                # Apply persisted plug bindings to the actuator manager
                if settings.actuator:
                    self.actuator_manager.set_camera_bindings(cam_id, settings.actuator)
            
            print(f"Settings loaded: cam={self.active_camera_id} lang={self.lang} auto={self.alarm.auto_mode}")
        except Exception as e:
            print(f"Settings load error: {e}")
    
    # ----- Helpers -----
    
    def tr(self, key: str, **kw) -> str:
        txt = self.L[self.lang].get(key) or self.L["ru"].get(key, key)
        if kw:
            try:
                txt = txt.format(**kw)
            except (KeyError, IndexError):
                pass
        return txt
    
    def zone_label(self) -> str:
        settings = self.get_active_settings()
        if settings.zone is None:
            return self.tr("whole_frame")
        return str(settings.zone) + f" ({self.tr('row_col', r=settings.zone.row, c=settings.zone.col)})"
    
    def target_label(self) -> str:
        settings = self.get_active_settings()
        if settings.target and settings.target.description:
            return settings.target.description
        return self.tr("target_not_set")
    
    def refresh_control_msg(self):
        if self.alarm.control_msg_id:
            self.tg.edit_message_text(
                self.config.telegram.chat_id,
                self.alarm.control_msg_id,
                self.control_text()
            )
    
    def control_text(self) -> str:
        mode = self.tr("mode_auto") if self.alarm.auto_mode else self.tr("mode_manual")
        cam_name = self.config.cameras.get(self.active_camera_id, CameraConfig(cam_id=self.active_camera_id, name=f"Camera {self.active_camera_id}", url="")).name
        plugs = self.actuator_manager.camera_bindings.get(self.active_camera_id, [])
        plugs_str = ", ".join(plugs) if plugs else "—"
        return (f"⚙️ {self.tr('mode_title')}\n\n"
                f"📌 {self.tr('current_mode')}: {mode}\n"
                f"🎯 {self.tr('target_search')}: {self.target_label()}\n"
                f"📍 {self.tr('zone_search')}: {self.zone_label()}\n"
                f"🔌 Розетки: {plugs_str}\n"
                f"📷 {self.tr('camera')}: {cam_name}\n\n"
                f"💡 {self.tr('control_hint')}")
    
    def set_bot_menu(self):
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
        ts = time.strftime("%Y%m%d_%H%M%S")
        import hashlib, os
        path = os.path.join(self.frame_dir, f"panic_{ts}_{hashlib.md5(frame_bytes).hexdigest()[:6]}.jpg")
        with open(path, "wb") as f:
            f.write(frame_bytes)
    
    # ----- Poll Loop -----
    
    def poll_loop(self):
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
        if "callback_query" in upd:
            self.handle_callback(upd["callback_query"])
        elif "message" in upd:
            m = upd["message"]
            mid = m.get("message_id")
            if mid:
                self.alarm.known_msg_ids.add(mid)
            
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
        """Monitor ALL cameras simultaneously with per-camera settings."""
        from ..detectors import create_pipeline_from_config
        
        streak = {cid: 0 for cid in range(1, 9)}
        clean = {cid: 0 for cid in range(1, 9)}
        
        while True:
            time.sleep(self.config.detection.detect_every)
            
            for cam_id in range(1, 9):
                cam = self.camera_manager.get(cam_id)
                if not cam or not cam.alive:
                    continue
                
                frame = cam.latest
                if frame is None:
                    continue
                
                # Get camera-specific settings
                settings = self.get_camera_settings(cam_id)
                zone = settings.zone
                target = settings.target or Target()
                
                # Create pipeline for this camera
                pipeline = create_pipeline_from_config(self.config, target, zone)
                matches, all_dets = pipeline.process(frame, zone)
                
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
                
                # Trigger alarm (pass the camera that triggered it!)
                if streak[cam_id] >= self.config.detection.require_frames and not self.alarm.is_active:
                    m = matches[0]
                    desc = (f"{self.tr('yellow_found')}\n"
                            f"({m.name} conf={m.confidence:.2f}, color={m.color_fraction*100:.0f}%)")
                    self.trigger_alarm(desc, frame, cam_id=cam_id)
                    break
            
            # Auto-resolve
            if self.alarm.is_active and self.alarm.auto_mode:
                alarm_cam = self.alarm.alarm_camera_id
                if clean.get(alarm_cam, 0) >= self.config.detection.auto_resolve_frames:
                    self.cancel_alarm(note=self.tr("threat_gone"))


# ============================================================================
# ENTRY POINT
# ============================================================================

def main():
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    
    base_dir = os.path.dirname(os.path.abspath(__file__))
    config = load_config(base_dir)
    
    # Kill other instances
    # ... (zombie killer from original)
    
    bot = SuperGuardBot(config)
    bot.load_settings()
    bot.set_bot_menu()
    
    # Start poll loop in background
    threading.Thread(target=bots.poll_loop, daemon=True).start()
    
    # Start detection loop
    bot.detection_loop()


if __name__ == "__main__":
    main()