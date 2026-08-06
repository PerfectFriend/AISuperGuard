#!/usr/bin/env python3
"""SuperGuard PANIC MODE v4 - standalone alarm bot token (no Hermes gateway conflict).
- Reads TOKEN from sguard.env (own file, NOT hermes .env) - no 409 poll conflicts.
- msg A: trigger frame (what YOLO reacted to) - NEVER edited, kept for audit
- msg B: live frame - updated every 2s during alarm
- cancel button on both msgs (manual mode): plug OFF + clear chat
- AUTO mode toggle button (control msg): plug OFF automatically when yellow
  vehicle leaves the frame (threat resolved), chat NOT cleared, updates stop.
"""
import os, time, json, threading, hashlib, re
import requests
import cv2
import numpy as np
import tinytuya
from ultralytics import YOLO

# ---------------- config ----------------
BASE = os.path.dirname(os.path.abspath(__file__))

def load_env(path):
    env = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()
    return env

env = load_env(os.path.join(BASE, "sguard.env"))
TOKEN = env.get("SG_TELEGRAM_BOT_TOKEN")
CHAT_ID = int(env.get("SG_CHAT_ID", "143293811"))
PLUG_IP = env.get("SG_PLUG_IP", "192.168.137.109")
PLUG_ID = env.get("SG_PLUG_ID", "bfd23bfc0bdd93b6904c3s")
PLUG_KEY = env.get("SG_PLUG_KEY")
if not TOKEN:
    raise SystemExit("SG_TELEGRAM_BOT_TOKEN not set in sguard.env")
if not PLUG_KEY:
    raise SystemExit("SG_PLUG_KEY not set in sguard.env")

CAM_URL = env.get("SG_CAM_URL", "https://atcs.banjarkota.go.id:5443/LiveApp/streams/Ptzparungsari.m3u8")
UPDATE_EVERY = float(env.get("SG_UPDATE_EVERY", "2.0"))
DETECT_EVERY = float(env.get("SG_DETECT_EVERY", "1.5"))
YELLOW_MIN_FRACTION = float(env.get("SG_YELLOW_MIN_FRACTION", "0.15"))
MIN_CONF = float(env.get("SG_MIN_CONF", "0.35"))
MIN_YELLOW_VEHICLES = int(env.get("SG_MIN_YELLOW_VEHICLES", "1"))
REQUIRE_FRAMES = int(env.get("SG_REQUIRE_FRAMES", "2"))
AUTO_RESOLVE_FRAMES = int(env.get("SG_AUTO_RESOLVE_FRAMES", "5"))
VEHICLE_CLASSES = {2: "car", 5: "bus", 7: "truck"}

# ---------------- i18n (RU/EN/ES) ----------------
# Current interface language. /setlocal button switches it at runtime.
LANG = "ru"
L = {
    "ru": {
        "alert": "\u26a0\ufe0f ВНИМАНИЕ! ТРЕВОГА! СИГНАЛИЗАЦИЯ ВКЛЮЧЕНА!\n"
                 "ОТКЛЮЧЕНИЕ — КОМАНДА /togglealarm ИЗ МЕНЮ",
        "mode_title": "\u2699\ufe0f РЕЖИМ РАБОТЫ",
        "current_mode": "Текущий режим",
        "mode_auto": "\u2705 АВТОМАТИЧЕСКИЙ",
        "mode_manual": "\U0001F6AB РУЧНОЙ",
        "zone_search": "Зона поиска",
        "target_search": "Цель поиска",
        "whole_frame": "весь кадр",
        "row_col": "строка {r}, столбец {c}",
        "control_hint": "Управление: меню рядом со скрепкой \u2192 /autoguard, /togglealarm, /zone, /target",
        "auto_on": "\u2705 АВТОРЕЖИМ ВКЛЮЧЁН",
        "auto_off": "\U0001F6AB АВТОРЕЖИМ ВЫКЛЮЧЕН — РУЧНОЙ РЕЖИМ",
        "auto_on_detail": "Розетка отключится автоматически, когда цель покинет зону "
                          "({n} чистых кадров). Ручное отключение — /togglealarm.",
        "manual_only": "Тревогу можно отключить только командой /togglealarm из меню.",
        "alarm_on_manual": "\U0001F6A8 Тревога включена вручную (команда /togglealarm). "
                          "Отключение — повторная команда /togglealarm.",
        "alarm_off_manual": "\U0001F6A8 Сигнализация выключена вручную (команда /togglealarm).",
        "cam_unavailable": "\u26a0\ufe0f Камера недоступна — не могу включить тревогу.",
        "force_alarm": "\U0001F6A8 ПРИНУДИТЕЛЬНАЯ ТРЕВОГА (вручную)",
        "looking_for": "Ищем",
        "zone": "Зона",
        "trigger_frame": "\U0001F4F7 кадр срабатывания",
        "live_frame": "\U0001F4FA живой кадр",
        "yellow_found": "\U0001F697 ОБНАРУЖЕНА ЦЕЛЬ!",
        "threat_gone": "Угроза устранена: цель покинула зону поиска",
        "alarm_off": "\U0001F6A8 Сигнализация отключена.",
        "auto_active": "\u2705 АВТОРЕЖИМ АКТИВЕН",
        "manual_active": "\U0001F6AB РУЧНОЙ РЕЖИМ АКТИВЕН",
        "zone_set": "Зона поиска установлена",
        "zone_off": "Зона поиска: ВЕСЬ КАДР (зона выключена).",
        "zone_help": "Формат: /zone N3x4 C9\n"
                     "\u2022 N{'{'}строк{'}'}x{'{'}столбцов{'}'} — разбиение кадра (1x2, 2x2, 2x3, 3x3, 3x4...)\n"
                     "\u2022 C{'{'}номер{'}'} — ячейка слева направо, сверху вниз (C01..C12)\n"
                     "\u2022 N9 C5 — квадратное разбиение 3x3, ячейка 5\n"
                     "\u2022 /zone off — весь кадр",
        "zone_bad": "Не понял формат «{arg}». Пример: /zone N3x4 C9 (левая нижняя ячейка при 3 строках, 4 столбцах).",
        "target_current": "Текущая цель поиска",
        "target_set": "Цель поиска обновлена",
        "target_hint": "Задать: /target человек в положении стоя",
        "target_not_set": "не задана (умолчание: жёлтый транспорт)",
        "target_filter": "Фильтр поиска",
        "target_filter_kept": "Не распознал цвет/класс — фильтр не менялся",
        "any_color": "любой цвет",
        "color_filter": "цветовой фильтр",
        "lang_title": "\U0001F310 Язык интерфейса / Interface language / Idioma de la interfaz",
        "lang_set": "Язык интерфейса: {lang}",
        "cb_cancel": "Сигнализация отключена",
        "cb_auto": "Режим переключён",
        "menu_autoguard": "Авторежим: вкл/выкл",
        "menu_togglealarm": "Тревога вкл/выкл вручную",
        "menu_zone": "Зона поиска: /zone N3x4 C9",
        "menu_target": "Цель поиска: /target текст",
        "menu_lang": "Язык: EN/ES/RU",
    },
    "en": {
        "alert": "\u26a0\ufe0f WARNING! ALARM! SIGNALING IS ON!\n"
                 "TURN OFF VIA /togglealarm FROM THE MENU",
        "mode_title": "\u2699\ufe0f OPERATING MODE",
        "current_mode": "Current mode",
        "mode_auto": "\u2705 AUTOMATIC",
        "mode_manual": "\U0001F6AB MANUAL",
        "zone_search": "Search zone",
        "target_search": "Search target",
        "whole_frame": "whole frame",
        "row_col": "row {r}, column {c}",
        "control_hint": "Control: menu next to the clip \u2192 /autoguard, /togglealarm, /zone, /target",
        "auto_on": "\u2705 AUTO MODE ON",
        "auto_off": "\U0001F6AB AUTO MODE OFF — MANUAL MODE",
        "auto_on_detail": "The plug will turn off automatically when the target leaves the zone "
                          "({n} clean frames). Manual off — /togglealarm.",
        "manual_only": "The alarm can be turned off only with /togglealarm from the menu.",
        "alarm_on_manual": "\U0001F6A8 Alarm turned ON manually (/togglealarm). "
                          "Turn off — /togglealarm again.",
        "alarm_off_manual": "\U0001F6A8 Alarm turned OFF manually (/togglealarm).",
        "cam_unavailable": "\u26a0\ufe0f Camera unavailable — can't turn on the alarm.",
        "force_alarm": "\U0001F6A8 FORCED ALARM (manual)",
        "looking_for": "Looking for",
        "zone": "Zone",
        "trigger_frame": "\U0001F4F7 trigger frame",
        "live_frame": "\U0001F4FA live frame",
        "yellow_found": "\U0001F697 TARGET DETECTED!",
        "threat_gone": "Threat resolved: target left the search zone",
        "alarm_off": "\U0001F6A8 Alarm turned off.",
        "auto_active": "\u2705 AUTO MODE ACTIVE",
        "manual_active": "\U0001F6AB MANUAL MODE ACTIVE",
        "zone_set": "Search zone set",
        "zone_off": "Search zone: WHOLE FRAME (zone off).",
        "zone_help": "Format: /zone N3x4 C9\n"
                     "\u2022 N{'{'}rows{'}'}x{'{'}cols{'}'} — frame split (1x2, 2x2, 2x3, 3x3, 3x4...)\n"
                     "\u2022 C{'{'}num{'}'} — cell left-to-right, top-to-bottom (C01..C12)\n"
                     "\u2022 N9 C5 — square 3x3 grid, cell 5\n"
                     "\u2022 /zone off — whole frame",
        "zone_bad": "Couldn't understand format «{arg}». Example: /zone N3x4 C9 (bottom-left cell in a 3-row, 4-column grid).",
        "target_current": "Current search target",
        "target_set": "Search target updated",
        "target_hint": "Set: /target person standing",
        "target_not_set": "not set (default: yellow vehicle)",
        "target_filter": "Search filter",
        "target_filter_kept": "Couldn't recognize color/class - filter kept",
        "any_color": "any color",
        "color_filter": "color filter",
        "lang_title": "\U0001F310 Язык интерфейса / Interface language / Idioma de la interfaz",
        "lang_set": "Interface language: {lang}",
        "cb_cancel": "Alarm off",
        "cb_auto": "Mode switched",
        "menu_autoguard": "Auto mode: on/off",
        "menu_togglealarm": "Alarm on/off manually",
        "menu_zone": "Search zone: /zone N3x4 C9",
        "menu_target": "Search target: /target text",
        "menu_lang": "Language: EN/ES/RU",
    },
    "es": {
        "alert": "\u26a0\ufe0f ¡ATENCIÓN! ¡ALARMA! ¡ALARMA ACTIVADA!\n"
                 "APAGAR CON /togglealarm DESDE EL MENÚ",
        "mode_title": "\u2699\ufe0f MODO DE FUNCIONAMIENTO",
        "current_mode": "Modo actual",
        "mode_auto": "\u2705 AUTOMÁTICO",
        "mode_manual": "\U0001F6AB MANUAL",
        "zone_search": "Zona de búsqueda",
        "target_search": "Objetivo de búsqueda",
        "whole_frame": "todo el cuadro",
        "row_col": "fila {r}, columna {c}",
        "control_hint": "Control: menú junto al clip \u2192 /autoguard, /togglealarm, /zone, /target",
        "auto_on": "\u2705 MODO AUTO ACTIVADO",
        "auto_off": "\U0001F6AB MODO AUTO DESACTIVADO — MODO MANUAL",
        "auto_on_detail": "El enchufe se apagará automáticamente cuando el objetivo salga de la zona "
                          "({n} cuadros limpios). Apagado manual — /togglealarm.",
        "manual_only": "La alarma solo se puede apagar con /togglealarm desde el menú.",
        "alarm_on_manual": "\U0001F6A8 Alarma activada manualmente (/togglealarm). "
                          "Para apagar — /togglealarm de nuevo.",
        "alarm_off_manual": "\U0001F6A8 Alarma apagada manualmente (/togglealarm).",
        "cam_unavailable": "\u26a0\ufe0f Cámara no disponible — no puedo activar la alarma.",
        "force_alarm": "\U0001F6A8 ALARMA FORZADA (manual)",
        "looking_for": "Buscando",
        "zone": "Zona",
        "trigger_frame": "\U0001F4F7 cuadro de disparo",
        "live_frame": "\U0001F4FA cuadro en vivo",
        "yellow_found": "\U0001F697 ¡OBJETIVO DETECTADO!",
        "threat_gone": "Amenaza resuelta: el objetivo salió de la zona de búsqueda",
        "alarm_off": "\U0001F6A8 Alarma apagada.",
        "auto_active": "\u2705 MODO AUTO ACTIVO",
        "manual_active": "\U0001F6AB MODO MANUAL ACTIVO",
        "zone_set": "Zona de búsqueda configurada",
        "zone_off": "Zona de búsqueda: TODO EL CUADRO (zona desactivada).",
        "zone_help": "Formato: /zone N3x4 C9\n"
                     "\u2022 N{'{'}filas{'}'}x{'{'}columnas{'}'} — división del cuadro (1x2, 2x2, 2x3, 3x3, 3x4...)\n"
                     "\u2022 C{'{'}número{'}'} — celda de izquierda a derecha, arriba a abajo (C01..C12)\n"
                     "\u2022 N9 C5 — cuadrícula cuadrada 3x3, celda 5\n"
                     "\u2022 /zone off — todo el cuadro",
        "zone_bad": "No entiendo el formato «{arg}». Ejemplo: /zone N3x4 C9 (celda inferior izquierda en una cuadrícula de 3 filas y 4 columnas).",
        "target_current": "Objetivo de búsqueda actual",
        "target_set": "Objetivo de búsqueda actualizado",
        "target_hint": "Configurar: /target persona de pie",
        "target_not_set": "no configurado (por defecto: vehículo amarillo)",
        "target_filter": "Filtro de búsqueda",
        "target_filter_kept": "No reconocí color/clase - filtro sin cambios",
        "any_color": "cualquier color",
        "color_filter": "filtro de color",
        "lang_title": "\U0001F310 Язык интерфейса / Interface language / Idioma de la interfaz",
        "lang_set": "Idioma de la interfaz: {lang}",
        "cb_cancel": "Alarma apagada",
        "cb_auto": "Modo cambiado",
        "menu_autoguard": "Modo auto: on/off",
        "menu_togglealarm": "Alarma on/off manual",
        "menu_zone": "Zona: /zone N3x4 C9",
        "menu_target": "Objetivo: /target texto",
        "menu_lang": "Idioma: EN/ES/RU",
    },
}

def tr(key, **kw):
    """Translate key into current LANG; falls back to ru; formats with **kw."""
    txt = L[LANG].get(key) or L["ru"].get(key, key)
    if kw:
        try:
            txt = txt.format(**kw)
        except (KeyError, IndexError):
            pass
    return txt

LANG_NAMES = {"ru": "\U0001F1F7\U0001F1FA Русский", "en": "\U0001F1EC\U0001F1E7 English", "es": "\U0001F1EA\U0001F1F8 Español"}

def lang_keyboard():
    """Inline buttons EN / ES / RU to switch interface language."""
    return json.dumps({"inline_keyboard": [[
        {"text": "\U0001F1EC\U0001F1E7 EN", "callback_data": "set_lang:en"},
        {"text": "\U0001F1EA\U0001F1F8 ES", "callback_data": "set_lang:es"},
        {"text": "\U0001F1F7\U0001F1FA RU", "callback_data": "set_lang:ru"}]]})

def set_lang(code):
    """Switch interface language, refresh mode message and bot menu.
    ONLY the language is persisted here - target/zone/auto are never touched
    by a language switch (a stale process memory used to overwrite the target
    in settings.json whenever the language changed)."""
    global LANG
    if code not in L:
        return
    LANG = code
    print(f"  LANG -> {code}", flush=True)
    save_settings(persist_target=False)
    set_bot_menu_async()
    _refresh_control_msg()
    send_text(tr("lang_set", lang=LANG_NAMES[code]))

# ---------------- zone targeting (grid) ----------------
# ZONE = (rows, cols, cell_num) e.g. (3, 4, 9) = N3x4 C9 -> left-bottom corner.
# None = whole frame. Cell numbering: left->right, top->bottom, C01..C12.
ZONE = None
TARGET_DESC = ""   # empty = not set by user yet; detection defaults to yellow vehicle

def target_label():
    """Current target or localized 'not set' placeholder (never hardcoded)."""
    return TARGET_DESC if TARGET_DESC.strip() else tr("target_not_set")

def parse_zone(spec):
    """Parse 'N3x4 C9' / 'N9 C5' (square grids) / '3x4 c9' -> (rows, cols, cell) or None."""
    if not spec:
        return None
    s = spec.strip().lower().replace("х", "x").replace(" ", "").replace("_", "")
    m = re.fullmatch(r"n?(\d+)x(\d+)c(\d+)", s)
    if m:
        rows, cols, cell = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if cell < 1 or cell > rows * cols:
            return None
        return (rows, cols, cell)
    m = re.fullmatch(r"n(\d+)c(\d+)", s)   # N9 C5 -> 3x3 grid, cell 5
    if m:
        total, cell = int(m.group(1)), int(m.group(2))
        side = int(total ** 0.5)
        if side * side == total and 1 <= cell <= total:
            return (side, side, cell)
    return None

def in_zone(zone, box, W, H):
    """True if object center falls inside the zone cell (normalized grid)."""
    if zone is None:
        return True
    rows, cols, cell = zone
    r, c = divmod(cell - 1, cols)
    x1, y1, x2, y2 = box
    cx = (x1 + x2) / 2 / W
    cy = (y1 + y2) / 2 / H
    return (c / cols <= cx <= (c + 1) / cols and
            r / rows <= cy <= (r + 1) / rows)

def zone_label(zone):
    if zone is None:
        return tr("whole_frame")
    rows, cols, cell = zone
    r = (cell - 1) // cols + 1
    c = (cell - 1) % cols + 1
    return f"N{rows}x{cols} C{cell:02d} ({tr('row_col', r=r, c=c)})"

Y_LOW = np.array([15, 60, 80])    # HSV yellow range (OpenCV H:0-180)
Y_HIGH = np.array([40, 255, 255])

# ---------------- target parsing: color + class ---------------- 
# /target text now drives REAL detection: color words -> HSV filter,
# class words -> YOLO classes (person/car/bus/truck). No hardcoding.
TARGET_CLASSES = set(VEHICLE_CLASSES.keys())   # default: car/bus/truck
COLOR_RANGES = [(Y_LOW.tolist(), Y_HIGH.tolist())]  # default: yellow filter

COLOR_MAP = {   # color name -> list of (low, high) HSV PAIRS
    "yellow": [((15, 60, 80), (40, 255, 255))],
    "red":    [((0, 100, 80), (10, 255, 255)), ((170, 100, 80), (180, 255, 255))],
    "orange": [((10, 100, 80), (25, 255, 255))],
    "green":  [((40, 60, 60), (85, 255, 255))],
    "cyan":   [((85, 60, 60), (100, 255, 255))],
    "blue":   [((100, 100, 60), (130, 255, 255))],
    "purple": [((130, 60, 60), (160, 255, 255))],
    "pink":   [((160, 60, 60), (175, 255, 255))],
    "white":  [((0, 0, 180), (180, 30, 255))],
    "gray":   [((0, 0, 60), (180, 30, 200))],
    "black":  [((0, 0, 0), (180, 255, 60))],
}
COLOR_SYN = {   # words (ru/en/es) that select a color
    "yellow": {"жёлтый", "желтый", "жёлтая", "желтая", "жёлтое", "желтое", "жёлтые", "желтые", "yellow", "amarillo"},
    "red":    {"красный", "красная", "красное", "красные", "красного", "red", "rojo", "roja", "rojos", "rojas"},
    "orange": {"оранжевый", "оранжевая", "orange", "naranja"},
    "green":  {"зелёный", "зеленый", "зелёная", "зеленая", "green", "verde"},
    "cyan":   {"голубой", "голубая", "cyan", "ciano"},
    "blue":   {"синий", "синяя", "синее", "синие", "blue", "azul", "azules"},
    "purple": {"фиолетовый", "фиолетовая", "purple", "violeta", "morado"},
    "pink":   {"розовый", "розовая", "pink", "rosa"},
    "white":  {"белый", "белая", "белое", "белые", "white", "blanco", "blanca", "blancos"},
    "gray":   {"серый", "серая", "серые", "grey", "gray", "gris", "grises"},
    "black":  {"чёрный", "черный", "чёрная", "черная", "чёрные", "черные", "black", "negro", "negra", "negros"},
}
CLASS_MAP = {0: "person", 2: "car", 5: "bus", 7: "truck"}
CLASS_SYN = {   # words (ru/en/es) that select a YOLO class
    0: {"человек", "человека", "люди", "мужчина", "мужчину", "женщина", "женщину",
        "стоя", "стоящий", "стоящая", "идущий", "идущая", "person", "people", "persona", "hombre", "mujer"},
    2: {"машина", "машину", "автомобиль", "автомобиля", "легковой", "авто", "автомобили",
        "car", "cars", "coche", "coches", "auto", "autos", "automóvil", "carro", "carros"},
    5: {"автобус", "автобуса", "bus", "buses", "autobús", "autobus"},
    7: {"грузовик", "грузовика", "грузовики", "truck", "trucks", "camión", "camion", "camiones"},
}

def parse_target(text):
    """Extract (classes, color_ranges) from free text.
    Returns (None, None) if nothing recognizable (keep current filter)."""
    toks = set(re.split(r"[^a-zа-яё0-9]+", text.lower()))
    classes = {cls for cls, syns in CLASS_SYN.items() if toks & syns}
    colors = [c for c, syns in COLOR_SYN.items() if toks & syns]
    if not classes and not colors:
        return None, None
    if not classes:
        classes = set(VEHICLE_CLASSES.keys())   # color only -> all vehicles
    if not colors:
        return classes, None                    # class only -> no color filter
    ranges = []
    for c in colors:
        ranges.extend(COLOR_MAP[c])
    return classes, ranges

def _ranges_color_name(ranges):
    """Best-effort: which color name the active HSV ranges correspond to."""
    for cname, pairs in COLOR_MAP.items():
        if sorted(ranges) == sorted(pairs):
            return cname
    return None

def target_filter_label():
    """Human-readable filter description, localized (classes + color)."""
    if not TARGET_CLASSES:
        return tr("target_not_set")
    names = ", ".join(sorted(CLASS_MAP.get(c, str(c)) for c in TARGET_CLASSES))
    cname = _ranges_color_name(COLOR_RANGES) if COLOR_RANGES else None
    if cname:
        return f"{cname} {names}"
    if COLOR_RANGES:
        return f"{names} ({tr('color_filter')})"
    return f"{names} ({tr('any_color')})"

FRAME_DIR = os.path.join(BASE, "panic_frames")
os.makedirs(FRAME_DIR, exist_ok=True)

API = f"https://api.telegram.org/bot{TOKEN}"

# ---------------- telegram ----------------
def tg(method, **kwargs):
    r = requests.post(f"{API}/{method}", timeout=8, **kwargs)
    j = r.json()
    if not j.get("ok"):
        print(f"  TG ERROR {method}: {j}", flush=True)
    return j.get("result")

def cancel_keyboard():
    # NOTE: inline cancel button is NOT used anymore - commands live in the
    # bot menu button (setChatMenuButton) next to the attach clip. Kept for refs.
    return json.dumps({"inline_keyboard": [[
        {"text": "\U0001F6A8  ОТКЛЮЧИТЬ СИГНАЛИЗАЦИЮ  \U0001F6A8", "callback_data": "cancel_alarm"}]]})

def _commands_payload(lang):
    return json.dumps([
        {"command": "autoguard", "description": L[lang]["menu_autoguard"]},
        {"command": "togglealarm", "description": L[lang]["menu_togglealarm"]},
        {"command": "zone", "description": L[lang]["menu_zone"]},
        {"command": "target", "description": L[lang]["menu_target"]},
        {"command": "setlocal", "description": L[lang]["menu_lang"]}])

def set_bot_menu():
    """Menu button next to the paperclip: commands for auto mode, alarm control,
    zone targeting, target description and interface language.
    Menu follows the bot language chosen via /setlocal (NOT the Telegram
    client language), so language_code variants are removed first.
    Runs in its own thread - Telegram calls here must NEVER block the poll
    loop (a slow network used to freeze the bot for up to 75s)."""
    # drop any per-client-language command sets previously registered
    for lc in ("ru", "es", "en"):
        try:
            tg("deleteMyCommands", data={"language_code": lc})
        except Exception as e:
            print(f"  delMyCommands {lc} err: {e}", flush=True)
    # single default set in the bot's current language
    try:
        tg("setMyCommands", data={"commands": _commands_payload(LANG)})
    except Exception as e:
        print(f"  setMyCommands err: {e}", flush=True)
    try:
        tg("setChatMenuButton", data={"chat_id": CHAT_ID,
                                      "menu_button": json.dumps({"type": "commands"})})
    except Exception as e:
        print(f"  setMenuButton err: {e}", flush=True)

def set_bot_menu_async():
    threading.Thread(target=set_bot_menu, daemon=True).start()

def auto_keyboard(auto_on):
    label = "\u23f8\ufe0f АВТО ВЫКЛ" if auto_on else "\u23f5\ufe0f АВТО ВКЛ"
    return json.dumps({"inline_keyboard": [[
        {"text": label, "callback_data": "auto_toggle"}]]})

def send_photo(frame_bytes, caption):
    files = {"photo": ("frame.jpg", frame_bytes, "image/jpeg")}
    data = {"chat_id": CHAT_ID, "caption": caption}
    return tg("sendPhoto", files=files, data=data)

def control_text(auto_on):
    """Current mode + live zone/target data in one message (localized)."""
    mode = tr("mode_auto") if auto_on else tr("mode_manual")
    txt = (f"{tr('mode_title')}\n\n"
           f"\U0001F4CC {tr('current_mode')}: {mode}\n"
           f"\U0001F4CD {tr('zone_search')}: {zone_label(ZONE)}\n"
           f"\U0001F50D {tr('target_search')}: {target_label()}\n\n"
           f"\U0001F4A1 {tr('control_hint')}")
    return txt

def send_control_msg(auto_on):
    return tg("sendMessage", data={"chat_id": CHAT_ID, "text": control_text(auto_on)})

def edit_control_msg(msg_id, auto_on):
    return tg("editMessageText", data={"chat_id": CHAT_ID, "message_id": msg_id,
                                       "text": control_text(auto_on)})

def edit_photo(frame_bytes, message_id, caption):
    fname = f"frame_{int(time.time()*1000)}.jpg"
    files = {fname: frame_bytes}
    media = {"type": "photo", "media": f"attach://{fname}", "caption": caption}
    return tg("editMessageMedia", files=files,
              data={"chat_id": CHAT_ID, "message_id": message_id,
                    "media": json.dumps(media)})

def delete_msg(mid):
    return tg("deleteMessage", data={"chat_id": CHAT_ID, "message_id": mid})

def send_text(text):
    return tg("sendMessage", data={"chat_id": CHAT_ID, "text": text})

# ---------------- plug ----------------
def plug_set(on):
    d = tinytuya.Device(PLUG_ID, PLUG_IP, PLUG_KEY, version=3.4)
    d.set_socketTimeout(5)
    r = d.set_status(bool(on), 1)
    print(f"  PLUG {'ON' if on else 'OFF'}: ack={r.get('dps') if isinstance(r, dict) else r}", flush=True)
    return r

# ---------------- camera: continuous bg capture ----------------
class Camera:
    def __init__(self, url):
        self.url = url
        self.lock = threading.Lock()
        self.frame = None
        self.alive = False
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        while True:
            try:
                cap = cv2.VideoCapture(self.url)
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                while True:
                    ok, f = cap.read()
                    if not ok:
                        break
                    with self.lock:
                        self.frame = f.copy()
                        self.alive = True
            except Exception:
                pass
            with self.lock:
                self.alive = False
            time.sleep(2)

    def latest(self):
        with self.lock:
            return None if self.frame is None else self.frame.copy()

CAM = Camera(CAM_URL)
MODEL = YOLO("yolo11n.pt")

def color_fraction(frame, box):
    """Fraction of pixels matching ANY active color range (COLOR_RANGES)
    in central body zone. 0.0 if no color filter active."""
    if not COLOR_RANGES:
        return 0.0
    x1, y1, x2, y2 = [int(v) for v in box]
    cx = (x1 + x2) // 2
    w, h = x2 - x1, y2 - y1
    if w < 20 or h < 20:
        return 0.0
    zone = frame[max(y1, y1 + h // 4):y2, max(x1, cx - w // 5):min(x2, cx + w // 5)]
    if zone.size == 0:
        return 0.0
    hsv = cv2.cvtColor(zone, cv2.COLOR_BGR2HSV)
    mask = np.zeros(zone.shape[:2], dtype=np.uint8)
    for lo, hi in COLOR_RANGES:
        mask |= cv2.inRange(hsv, np.array(lo, dtype=np.uint8), np.array(hi, dtype=np.uint8))
    return float(mask.mean() / 255.0)

def detect_vehicles(frame):
    """Returns (yellow, all) lists of (name, conf, box, color_frac), zone-filtered.
    yellow = matches TARGET_CLASSES + active COLOR_RANGES (or all classes when
    no color filter is set)."""
    r = MODEL(frame, conf=MIN_CONF, imgsz=640, verbose=False)[0]
    H, W = frame.shape[:2]
    yellow, allv = [], []
    for b in r.boxes:
        cls = int(b.cls[0])
        if cls not in TARGET_CLASSES:
            continue
        box = b.xyxy[0].tolist()
        name = CLASS_MAP.get(cls, str(cls))
        conf = float(b.conf[0])
        if not in_zone(ZONE, box, W, H):
            continue
        cf = color_fraction(frame, box)
        item = (name, conf, box, cf)
        allv.append(item)
        if not COLOR_RANGES or cf >= YELLOW_MIN_FRACTION:
            yellow.append(item)
    return yellow, allv

# ---------------- alarm state ----------------
class Alarm:
    def __init__(self):
        self.active = False
        self.auto = False           # auto mode: plug OFF when yellow leaves frame
        self.trigger_msg_id = None  # msg A: trigger frame - NEVER edited
        self.live_msg_id = None     # msg B: live frame - updated every 2s
        self.control_msg_id = None  # mode toggle message
        self.known = set()
        self.lock = threading.Lock()

alarm = Alarm()

# ---------------- settings persistence ----------------
# zone / target / language / auto mode are saved to sguard_settings.json and
# restored on restart - they must NOT reset to defaults unless changed manually.
SETTINGS_FILE = os.path.join(BASE, "sguard_settings.json")

def kill_other_instances():
    """Kill every python.exe running panic_mode.py EXCEPT the current process.
    A zombie that survived a shell 'kill' keeps Telegram long-polling and
    answers commands with stale in-memory state - two bots on one token is
    exactly how an old target kept resurrecting. PowerShell is used (MSYS
    mangles $_ in bash); file-based so MSYS can't corrupt it."""
    import subprocess
    try:
        # Get the ACTUAL python.exe PID (not bash wrapper PID in MSYS)
        import psutil
        mypid = psutil.Process().pid
        # Build PS command in a file to avoid MSYS mangling
        ps_script = f"""$mypid = {mypid}
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
Where-Object {{ $_.CommandLine -match 'panic_mode' -and $_.ProcessId -ne \$mypid }} |
ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force; Write-Output ('killed ' + $_.ProcessId) }}
"""
        with open("kill_zombies.ps1", "w", encoding="utf-8") as f:
            f.write(ps_script)
        # Use cp866 for PowerShell stderr (Cyrillic on RU Windows), ignore errors
        r = subprocess.run(["powershell", "-NoProfile", "-File", "kill_zombies.ps1"],
                          capture_output=True, text=True, timeout=20, encoding="utf-8", errors="ignore")
        if r.stdout.strip():
            print(f"  killed stale instance(s): {r.stdout.strip()}", flush=True)
    except Exception as e:
        print(f"  zombie kill err: {e}", flush=True)

def save_settings(persist_target=True):
    """Persist zone/target/lang/auto so a restart does not reset them.
    persist_target=False keeps the ON-DISK target untouched (language switch
    must never overwrite the target with whatever is in process memory)."""
    with alarm.lock:
        auto = alarm.auto
    data = {"zone": list(ZONE) if ZONE else None,
            "target": TARGET_DESC,
            "lang": LANG,
            "auto": auto}
    if not persist_target:
        # read previous target from disk, keep it as-is
        try:
            with open(SETTINGS_FILE, encoding="utf-8") as f:
                prev = json.load(f)
            pt = prev.get("target")
            if isinstance(pt, str) and pt.strip():
                data["target"] = pt
        except Exception:
            pass
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"  settings saved: zone={zone_label(ZONE)} target={data['target'][:40]} lang={LANG} auto={auto}", flush=True)
    except Exception as e:
        print(f"  settings save err: {e}", flush=True)

def load_settings():
    """Restore zone/target/lang/auto from disk (if present)."""
    global ZONE, TARGET_DESC, TARGET_CLASSES, COLOR_RANGES, LANG
    if not os.path.exists(SETTINGS_FILE):
        print("  no settings file, defaults kept", flush=True)
        return
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            s = json.load(f)
        z = s.get("zone")
        if isinstance(z, list) and len(z) == 3:
            rows, cols, cell = int(z[0]), int(z[1]), int(z[2])
            if 1 <= cell <= rows * cols:
                ZONE = (rows, cols, cell)
        t = s.get("target")
        if isinstance(t, str) and t.strip():
            TARGET_DESC = t.strip()
            classes, ranges = parse_target(TARGET_DESC)
            if classes is not None:
                TARGET_CLASSES = classes
                COLOR_RANGES = ranges
        lg = s.get("lang")
        if lg in L:
            LANG = lg
        with alarm.lock:
            alarm.auto = bool(s.get("auto", False))
        print(f"  settings loaded: zone={zone_label(ZONE)} target={TARGET_DESC[:40]} lang={LANG} auto={alarm.auto} filter={target_filter_label()}", flush=True)
    except Exception as e:
        print(f"  settings load err: {e}", flush=True)

def annotate(frame, yellow, allv):
    out = frame.copy()
    H, W = out.shape[:2]
    if ZONE is not None:
        rows, cols, cell = ZONE
        r, c = divmod(cell - 1, cols)
        x1 = c * W // cols; x2 = (c + 1) * W // cols
        y1 = r * H // rows; y2 = (r + 1) * H // rows
        cv2.rectangle(out, (x1, y1), (x2, y2), (255, 165, 0), 2)
        cv2.putText(out, f"ZONE N{rows}x{cols} C{cell:02d}", (x1 + 4, y1 + 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 165, 0), 2)
    for name, conf, box, yf in allv:
        x1, y1, x2, y2 = [int(v) for v in box]
        is_y = any(y == box for _, _, y, _ in yellow)
        color = (0, 0, 255) if is_y else (0, 255, 0)
        cv2.rectangle(out, (x1, y1), (x2, y2), color, 2)
        cv2.putText(out, f"{name} {conf:.2f}{' YELLOW' if is_y else ''}",
                    (x1, max(15, y1 - 5)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
    cv2.putText(out, f"yellow: {len(yellow)}", (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
    return out

def trigger_alarm(desc, frame):
    with alarm.lock:
        if alarm.active:
            print("  already active, ignore", flush=True)
            return
        alarm.active = True
    print("== PANIC TRIGGER ==", flush=True)
    plug_set(True)
    # msg A: trigger frame (what YOLO reacted to) - kept as-is, NO button (clean photo)
    ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
    frame_bytes = buf.tobytes()
    caption = (f"{tr('alert')}\n\n\U0001F4C5 {time.strftime('%H:%M:%S')}\n{desc}"
               f"\n\U0001F50D {tr('looking_for')}: {target_label()}\n\U0001F4CD {tr('zone')}: {zone_label(ZONE)}\n\n"
               f"\U0001F4F7 {tr('trigger_frame')}")
    files = {"photo": ("frame.jpg", frame_bytes, "image/jpeg")}
    res = tg("sendPhoto", files=files,
             data={"chat_id": CHAT_ID, "caption": caption})
    if not res:
        alarm.active = False
        return
    alarm.trigger_msg_id = res["message_id"]
    alarm.known.add(res["message_id"])
    save_local(frame_bytes)
    print(f"  trigger photo sent, msg_id={alarm.trigger_msg_id} (no button)", flush=True)
    # msg B: fresh live frame - updated every 2s (no inline button; commands in menu)
    time.sleep(1.0)
    live = CAM.latest()
    if live is None:
        live = frame
    ok, buf = cv2.imencode(".jpg", live, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
    caption = f"{tr('alert')}\n\n\U0001F4C5 {time.strftime('%H:%M:%S')}\n\U0001F4FA {tr('live_frame')}"
    res = send_photo(buf.tobytes(), caption)
    if res:
        alarm.live_msg_id = res["message_id"]
        alarm.known.add(res["message_id"])
        save_local(buf.tobytes())
        print(f"  live photo sent, msg_id={alarm.live_msg_id}", flush=True)
        threading.Thread(target=update_loop, daemon=True).start()

def save_local(frame_bytes):
    ts = time.strftime("%Y%m%d_%H%M%S")
    path = os.path.join(FRAME_DIR, f"panic_{ts}_{hashlib.md5(frame_bytes).hexdigest()[:6]}.jpg")
    with open(path, "wb") as f:
        f.write(frame_bytes)

def update_loop():
    while True:
        time.sleep(UPDATE_EVERY)
        with alarm.lock:
            if not alarm.active:
                return
            mid = alarm.live_msg_id
        if mid is None:
            continue
        frame = CAM.latest()
        if frame is None:
            continue
        ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
        caption = f"{tr('alert')}\n\n\U0001F4C5 {time.strftime('%H:%M:%S')}\n\U0001F4FA {tr('live_frame')}"
        if edit_photo(buf.tobytes(), mid, caption):
            save_local(buf.tobytes())
            print(f"  live photo updated {time.strftime('%H:%M:%S')}", flush=True)

def stop_alarm(clear_chat, note):
    """End alarm: plug OFF, stop updates.
    Deletes all alarm msgs EXCEPT the trigger frame (msg A) - the clean photo that
    stays in history for audit. Live frame (msg B) + its button get removed.
    If note given, a text summary is sent (auto-mode)."""
    with alarm.lock:
        if not alarm.active:
            return
        alarm.active = False
        keep = alarm.trigger_msg_id
        mids = [m for m in alarm.known if m != keep]
        alarm.known.clear()
        alarm.live_msg_id = None
    plug_set(False)
    for mid in mids:
        try:
            delete_msg(mid)
            print(f"  deleted msg {mid}", flush=True)
        except Exception as e:
            print(f"  del {mid} err {e}", flush=True)
    if note:
        mode_txt = (tr("auto_active") if alarm.auto else tr("manual_active"))
        send_text(f"\u2705 {note}\n\n{tr('alarm_off')}\n"
                  f"\U0001F4CC {tr('current_mode')}: {mode_txt}\n"
                  f"\U0001F50D {tr('target_search')}: {target_label()}\n"
                  f"\U0001F4CD {tr('zone_search')}: {zone_label(ZONE)}")
        print("  plug OFF, live frame removed, trigger frame kept", flush=True)
    else:
        print(f"  chat cleaned (trigger msg {keep} kept), plug OFF", flush=True)

def toggle_alarm():
    """Force alarm ON (even without yellow detection) or OFF manually."""
    with alarm.lock:
        if alarm.active:
            active = True
        else:
            active = False
    if active:
        cancel_alarm()
        send_text(tr("alarm_off_manual"))
    else:
        frame = CAM.latest()
        if frame is None:
            send_text(tr("cam_unavailable"))
            return
        desc = tr("force_alarm")
        trigger_alarm(desc, annotate(frame, [], []))
        send_text(tr("alarm_on_manual"))

def _refresh_control_msg():
    """Keep the mode message in sync with current zone/target/auto."""
    with alarm.lock:
        cid = alarm.control_msg_id
        auto = alarm.auto
    if cid:
        edit_control_msg(cid, auto)

def _handle_zone_cmd(text):
    """/zone N3x4 C9 | /zone N9 C5 | /zone off | /zone ? — set/clear/show zone.
    Help/off words accepted in RU/EN/ES."""
    global ZONE
    arg = text[len("/zone"):].strip()
    if not arg or arg.lower() in ("?", "help", "справка", "ayuda"):
        send_text(f"\U0001F4CD {tr('zone_search')}: {zone_label(ZONE)}\n\n{tr('zone_help')}")
        return
    if arg.lower() in ("off", "none", "всё", "все", "0", "todo", "toda", "nada", "desactivar"):
        ZONE = None
        send_text(f"\U0001F4CD {tr('zone_off')}")
        save_settings()
        _refresh_control_msg()
        return
    z = parse_zone(arg)
    if z is None:
        send_text(f"\u26a0\ufe0f {tr('zone_bad', arg=arg)}")
        return
    ZONE = z
    send_text(f"\U0001F4CD {tr('zone_set')}: {zone_label(z)}.\n"
              f"\U0001F50D {tr('looking_for')}: {target_label()}")
    save_settings()
    _refresh_control_msg()

def _handle_target_cmd(text):
    """/target <desc> - what to search for. Text drives REAL detection:
    color words -> HSV filter, class words -> YOLO classes."""
    global TARGET_DESC, TARGET_CLASSES, COLOR_RANGES
    arg = text[len("/target"):].strip()
    if not arg or arg.lower() in ("?", "help", "справка", "ayuda"):
        send_text(f"\U0001F50D {tr('target_current')}: {target_label()}\n"
                  f"{tr('target_hint')}")
        return
    classes, ranges = parse_target(arg)
    TARGET_DESC = arg
    if classes is None:
        # unrecognized words: keep current detection filter, still update label
        send_text(f"\U0001F50D {tr('target_set')}: {TARGET_DESC}\n"
                  f"{tr('target_filter_kept')}: {target_filter_label()}")
    else:
        TARGET_CLASSES = classes
        COLOR_RANGES = ranges
        send_text(f"\U0001F50D {tr('target_set')}: {TARGET_DESC}\n"
                  f"\U0001F50D {tr('target_filter')}: {target_filter_label()}")
    save_settings()
    _refresh_control_msg()

def cancel_alarm():
    stop_alarm(clear_chat=True, note="")

def toggle_auto():
    with alarm.lock:
        alarm.auto = not alarm.auto
        auto = alarm.auto
        cid = alarm.control_msg_id
    print(f"  AUTO mode {'ON' if auto else 'OFF'}", flush=True)
    save_settings()
    if cid:
        edit_control_msg(cid, auto)
    # always reply with the mode that is now active
    if auto:
        send_text(f"{tr('auto_on')}\n\n"
                  f"\U0001F4CD {tr('zone_search')}: {zone_label(ZONE)}\n"
                  f"\U0001F50D {tr('target_search')}: {target_label()}\n\n"
                  f"{tr('auto_on_detail', n=AUTO_RESOLVE_FRAMES)}")
    else:
        send_text(f"{tr('auto_off')}\n\n"
                  f"\U0001F4CD {tr('zone_search')}: {zone_label(ZONE)}\n"
                  f"\U0001F50D {tr('target_search')}: {target_label()}\n\n"
                  f"{tr('manual_only')}")

# ---------------- poll loop ----------------
def poll_loop():
    offset = 0
    while True:
        try:
            j = requests.post(f"{API}/getUpdates",
                              json={"offset": offset, "timeout": 25},
                              timeout=35).json()
            if not j.get("ok"):
                print(f"  poll warn: {j.get('description')}", flush=True)
                time.sleep(1)
                continue
            for upd in j["result"]:
                offset = upd["update_id"] + 1
                try:
                    _handle_update(upd)
                except Exception as e:
                    print(f"  update err: {e}", flush=True)
        except Exception as e:
            print(f"  poll err {e}", flush=True)
            time.sleep(2)

def _handle_update(upd):
    """Process one update; called from poll loop (each update isolated so a
    network error on one command never freezes or skips the others)."""
    if "callback_query" in upd:
        cb = upd["callback_query"]
        data = cb.get("data")
        if data and data.startswith("set_lang:"):
            code = data.split(":", 1)[1]
            tg("answerCallbackQuery", data={"callback_query_id": cb["id"],
                                            "text": tr("lang_set", lang=LANG_NAMES.get(code, code))})
            set_lang(code)
        elif data == "cancel_alarm":
            tg("answerCallbackQuery", data={"callback_query_id": cb["id"],
                                            "text": tr("cb_cancel")})
            cancel_alarm()
        elif data == "auto_toggle":
            tg("answerCallbackQuery", data={"callback_query_id": cb["id"],
                                            "text": tr("cb_auto")})
            toggle_auto()
    elif "message" in upd:
        m = upd["message"]
        mid = m.get("message_id")
        if mid:
            alarm.known.add(mid)
        text = (m.get("text") or "").strip().lower()
        # commands arrive from the bot menu button (next to paperclip)
        if text == "/autoguard" or text == "/autoguard@superguard_alarm_bot":
            toggle_auto()
        elif text == "/togglealarm" or text == "/togglealarm@superguard_alarm_bot":
            toggle_alarm()
        elif text.startswith("/zone"):
            _handle_zone_cmd(text)
        elif text.startswith("/target"):
            _handle_target_cmd(text)
        elif text == "/setlocal" or text == "/setlocal@superguard_alarm_bot":
            tg("sendMessage", data={"chat_id": CHAT_ID,
                                    "text": tr("lang_title"),
                                    "reply_markup": lang_keyboard()})
        elif mid:
            # any other user message: delete to keep chat clean
            try:
                delete_msg(mid)
            except Exception:
                pass

# ---------------- main detection loop ----------------
def detection_loop():
    streak = 0
    clean = 0   # consecutive frames without yellow (auto-resolve counter)
    while True:
        time.sleep(DETECT_EVERY)
        frame = CAM.latest()
        if frame is None:
            continue
        yellow, allv = detect_vehicles(frame)
        if len(yellow) >= MIN_YELLOW_VEHICLES:
            streak += 1
            clean = 0
        else:
            streak = 0
            clean += 1
        status = (f"[{time.strftime('%H:%M:%S')}] hit={len(yellow)}/{MIN_YELLOW_VEHICLES} "
                  f"streak={streak}/{REQUIRE_FRAMES} clean={clean}/{AUTO_RESOLVE_FRAMES} "
                  f"zone={zone_label(ZONE)} filter={target_filter_label()} | "
                  + ", ".join(f"{n} c={c:.2f} y={y*100:.0f}%" for n, c, _, y in allv) or "empty")
        print(status, flush=True)
        # fire alarm
        if streak >= REQUIRE_FRAMES and not alarm.active:
            y = yellow[0]
            desc = (f"{tr('yellow_found')}\n"
                    f"({y[0]} conf={y[1]:.2f}, color={y[3]*100:.0f}%)")
            trigger_alarm(desc, annotate(frame, yellow, allv))
        # auto-resolve: threat gone while alarm active in AUTO mode
        elif alarm.active and alarm.auto and clean >= AUTO_RESOLVE_FRAMES:
            stop_alarm(clear_chat=False, note=tr("threat_gone"))

if __name__ == "__main__":
    # kill any other panic_mode instances first - a stale python.exe that
    # survives a shell kill keeps polling Telegram and answers commands with
    # OLD in-memory state (that is how a language switch resurrected an old
    # target: the zombie's save_settings() overwrote settings.json).
    kill_other_instances()
    # restore persisted zone/target/lang/auto FIRST - commands must see them
    load_settings()
    threading.Thread(target=poll_loop, daemon=True).start()
    time.sleep(2)
    # bot menu button (next to paperclip): commands - always available
    set_bot_menu()
    # control msg with current mode (no inline buttons - commands live in menu)
    res = send_control_msg(alarm.auto)
    if res:
        alarm.control_msg_id = res["message_id"]
    print(f"SuperGuard panic mode: watching for {target_filter_label()}...", flush=True)
    detection_loop()
