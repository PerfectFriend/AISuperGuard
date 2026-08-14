import os
import asyncio
import json
import time
import cv2
import numpy as np
from typing import Dict, Optional, Any, Callable, List
from dataclasses import dataclass
from functools import wraps
from telethon import TelegramClient, events, Button
from telethon.tl.types import InputPeerUser, InputPeerChannel
from telethon.errors import FloodWaitError
from ..config import SuperGuardConfig, TelegramConfig
from ..models import Alarm, AlarmManager, CameraAlarmState, CameraSettings, Zone, Target, parse_zone_spec, parse_target_text
from ..cameras import CameraManager
from ..actuators import ActuatorManager
from ..detectors import create_pipeline_from_config

class TelethonClient:

    def __init__(self, config: TelegramConfig):
        self.config = config
        self.api_id = config.api_id
        self.api_hash = config.api_hash
        self.bot_token = config.token
        self.chat_id = config.chat_id
        session_path = os.path.join(os.path.dirname(__file__), '..', '..', 'telethon_session')
        self.client = TelegramClient(session_path, self.api_id, self.api_hash)
        self._handlers: Dict[str, Callable] = {}
        self._callback_handlers: Dict[str, Callable] = {}
        self._default_handler: Optional[Callable] = None
        self._me = None

    async def start(self):
        await self.client.start(bot_token=self.bot_token)
        self._me = await self.client.get_me()
        print(f'Telethon bot started: @{self._me.username} (id: {self._me.id})')
        self.client.add_event_handler(self._handle_new_message, events.NewMessage)
        self.client.add_event_handler(self._handle_callback, events.CallbackQuery)

    async def stop(self):
        await self.client.disconnect()

    def register(self, prefix: str, handler: Callable):
        self._handlers[prefix.lower()] = handler

    def set_default(self, handler: Callable):
        self._default_handler = handler

    def register_callback(self, data_prefix: str, handler: Callable):
        self._callback_handlers[data_prefix] = handler

    async def _handle_new_message(self, event):
        if event.is_private and event.chat_id == self.chat_id:
            text = event.raw_text.strip()
            if text:
                await self._route_command(event, text)

    async def _handle_callback(self, event):
        data = event.data.decode() if event.data else ''
        for prefix, handler in self._callback_handlers.items():
            if data.startswith(prefix):
                await handler(event, data)
                return

    async def _route_command(self, event, text: str):
        text_lower = text.lower().strip()
        parts = text.split(maxsplit=1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ''
        ctx = CommandContext(text=text, args=args, message_id=event.id, chat_id=event.chat_id, user_id=event.sender_id, event=event)
        for prefix, handler in self._handlers.items():
            if text_lower == prefix or text_lower.startswith(prefix + ' ') or text_lower.startswith(prefix + '@'):
                try:
                    await handler(ctx)
                except Exception as e:
                    print(f'Handler error: {e}')
                return
        for prefix, handler in self._handlers.items():
            if text_lower.startswith(prefix):
                try:
                    await handler(ctx)
                except Exception as e:
                    print(f'Handler error: {e}')
                return
        if self._default_handler:
            try:
                await self._default_handler(ctx)
            except Exception as e:
                print(f'Default handler error: {e}')

    async def send_message(self, chat_id: int, text: str, buttons=None, parse_mode='html') -> Any:
        try:
            return await self.client.send_message(chat_id, text, buttons=buttons, parse_mode=parse_mode)
        except FloodWaitError as e:
            print(f'Flood wait: {e.seconds}s')
            await asyncio.sleep(e.seconds)
            return await self.client.send_message(chat_id, text, buttons=buttons, parse_mode=parse_mode)

    async def send_file(self, chat_id: int, file_bytes: bytes, caption: str='', buttons=None, parse_mode='html') -> Any:
        try:
            from io import BytesIO
            file = BytesIO(file_bytes)
            file.name = 'frame.jpg'
            return await self.client.send_file(chat_id, file, caption=caption, buttons=buttons, parse_mode=parse_mode)
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds)
            from io import BytesIO
            file = BytesIO(file_bytes)
            file.name = 'frame.jpg'
            return await self.client.send_file(chat_id, file, caption=caption, buttons=buttons, parse_mode=parse_mode)

    async def edit_message(self, chat_id: int, message_id: int, text: str=None, file_bytes: bytes=None, buttons=None, parse_mode='html') -> Any:
        try:
            if file_bytes:
                from io import BytesIO
                file = BytesIO(file_bytes)
                file.name = 'frame.jpg'
                return await self.client.edit_message(chat_id, message_id, file=file, text=text or '', buttons=buttons, parse_mode=parse_mode)
            else:
                return await self.client.edit_message(chat_id, message_id, text=text, buttons=buttons, parse_mode=parse_mode)
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds)
            if file_bytes:
                from io import BytesIO
                file = BytesIO(file_bytes)
                file.name = 'frame.jpg'
                return await self.client.edit_message(chat_id, message_id, file=file, text=text or '', buttons=buttons, parse_mode=parse_mode)
            else:
                return await self.client.edit_message(chat_id, message_id, text=text, buttons=buttons, parse_mode=parse_mode)

    async def delete_message(self, chat_id: int, message_id: int) -> bool:
        try:
            await self.client.delete_messages(chat_id, message_id)
            return True
        except Exception as e:
            print(f'Delete error: {e}')
            return False

    async def answer_callback(self, callback_query, text: str, alert: bool=False):
        try:
            await callback_query.answer(text, alert=alert)
        except Exception as e:
            print(f'Callback answer error: {e}')

    def run_until_disconnected(self):
        self.client.run_until_disconnected()

@dataclass
class CommandContext:
    text: str
    args: str
    message_id: int
    chat_id: int
    user_id: int
    event: Any

class SuperGuardTelethonBot:

    def __init__(self, config: SuperGuardConfig):
        self.config = config
        self.tg = TelethonClient(config.telegram)
        self.alarm = AlarmManager()
        self.camera_manager = CameraManager(config)
        self.actuator_manager = ActuatorManager(config)
        self.camera_settings: Dict[int, CameraSettings] = {}
        self.lang = 'ru'
        self._load_i18n()
        self._register_commands()
        self.frame_dir = self.config.frame_dir
        os.makedirs(self.frame_dir, exist_ok=True)

    @property
    def active_camera_id(self) -> int:
        return self.alarm.active_camera_id

    @active_camera_id.setter
    def active_camera_id(self, value: int):
        self.alarm.active_camera_id = value

    def _load_i18n(self):
        self.L = {'ru': {'alert': '⚠️ ВНИМАНИЕ! ТРЕВОГА! СИГНАЛИЗАЦИЯ ВКЛЮЧЕНА!\nОТКЛЮЧЕНИЕ — КОМАНДА /togglealarm ИЗ МЕНЮ', 'mode_title': '⚙️ РЕЖИМ РАБОТЫ', 'current_mode': 'Текущий режим', 'mode_auto': '✅ АВТОМАТИЧЕСКИЙ', 'mode_manual': '🚫 РУЧНОЙ', 'zone_search': 'Зона поиска', 'target_search': 'Цель поиска', 'whole_frame': 'весь кадр', 'row_col': 'строка {r}, столбец {c}', 'control_hint': 'Управление: меню → /autoguard, /togglealarm, /zone, /target, /cam', 'auto_on': '✅ АВТОРЕЖИМ ВКЛЮЧЁН', 'auto_off': '🚫 АВТОРЕЖИМ ВЫКЛЮЧЕН — РУЧНОЙ РЕЖИМ', 'auto_on_detail': 'Розетка отключится автоматически, когда цель покинет зону ({n} чистых кадров). Ручное отключение — /togglealarm.', 'manual_only': 'Тревогу можно отключить только командой /togglealarm из меню.', 'alarm_on_manual': '🚨 Тревога включена вручную (/togglealarm). Отключение — повторная команда /togglealarm.', 'alarm_off_manual': '🚨 Сигнализация выключена вручную (/togglealarm).', 'cam_unavailable': '⚠️ Камера недоступна — не могу включить тревогу.', 'force_alarm': '🚨 ПРИНУДИТЕЛЬНАЯ ТРЕВОГА (вручную)', 'looking_for': 'Ищем', 'zone': 'Зона', 'trigger_frame': '📷 кадр срабатывания', 'live_frame': '📺 живой кадр', 'camera': 'Камера', 'yellow_found': '🚗 ОБНАРУЖЕНА ЦЕЛЬ!', 'threat_gone': 'Угроза устранена: цель покинула зону поиска', 'alarm_off': '🚨 Сигнализация отключена.', 'auto_active': '✅ АВТОРЕЖИМ АКТИВЕН', 'manual_active': '🚫 РУЧНОЙ РЕЖИМ АКТИВЕН', 'zone_set': 'Зона поиска установлена', 'zone_off': 'Зона поиска: ВЕСЬ КАДР (зона выключена).', 'zone_help': 'Формат: /zone N3x4 C9\nN{rows}x{cols} — разбиение кадра\nC{num} — ячейка\n/zone off — весь кадр', 'zone_bad': 'Не понял формат «{arg}». Пример: /zone N3x4 C9', 'target_current': 'Текущая цель поиска', 'target_set': 'Цель поиска обновлена', 'target_hint': 'Задать: /target человек в положении стоя', 'target_not_set': 'не задана (умолчание: жёлтый транспорт)', 'target_filter': 'Фильтр поиска', 'target_filter_kept': 'Не распознал цвет/класс — фильтр не менялся', 'any_color': 'любой цвет', 'color_filter': 'цветовой фильтр', 'lang_title': '🌐 Язык интерфейса / Interface language / Idioma de la interfaz', 'lang_set': 'Язык интерфейса: {lang}', 'cb_cancel': 'Сигнализация отключена', 'cb_auto': 'Режим переключён', 'menu_autoguard': 'Авторежим: вкл/выкл', 'menu_togglealarm': 'Тревога вкл/выкл вручную', 'menu_zone': 'Зона поиска: /zone N3x4 C9', 'menu_target': 'Цель поиска: /target текст', 'menu_plug': 'Розетки: /plug', 'menu_lang': 'Язык: EN/ES/RU', 'menu_cam': 'Камера: /cam имя', 'cam_status': 'Камера: {status}'}, 'en': {'alert': '⚠️ WARNING! ALARM! SIGNALING IS ON!\nTURN OFF VIA /togglealarm FROM THE MENU', 'mode_title': '⚙️ OPERATING MODE', 'current_mode': 'Current mode', 'mode_auto': '✅ AUTOMATIC', 'mode_manual': '🚫 MANUAL', 'zone_search': 'Search zone', 'target_search': 'Search target', 'whole_frame': 'whole frame', 'row_col': 'row {r}, column {c}', 'control_hint': 'Control: menu → /autoguard, /togglealarm, /zone, /target, /cam', 'auto_on': '✅ AUTO MODE ON', 'auto_off': '🚫 AUTO MODE OFF — MANUAL MODE', 'auto_on_detail': 'The plug will turn off automatically when the target leaves the zone ({n} clean frames). Manual off — /togglealarm.', 'manual_only': 'The alarm can be turned off only with /togglealarm from the menu.', 'alarm_on_manual': '🚨 Alarm turned ON manually (/togglealarm). Turn off — /togglealarm again.', 'alarm_off_manual': '🚨 Alarm turned OFF manually (/togglealarm).', 'cam_unavailable': "⚠️ Camera unavailable — can't turn on the alarm.", 'force_alarm': '🚨 FORCED ALARM (manual)', 'looking_for': 'Looking for', 'zone': 'Zone', 'trigger_frame': '📷 trigger frame', 'live_frame': '📺 live frame', 'camera': 'Camera', 'yellow_found': '🚗 TARGET DETECTED!', 'threat_gone': 'Threat resolved: target left the search zone', 'alarm_off': '🚨 Alarm turned off.', 'auto_active': '✅ AUTO MODE ACTIVE', 'manual_active': '🚫 MANUAL MODE ACTIVE', 'zone_set': 'Search zone set', 'zone_off': 'Search zone: WHOLE FRAME (zone off).', 'zone_help': 'Format: /zone N3x4 C9\nN{rows}x{cols} — frame split\nC{num} — cell\n/zone off — whole frame', 'zone_bad': "Couldn't understand format «{arg}». Example: /zone N3x4 C9", 'target_current': 'Current search target', 'target_set': 'Search target updated', 'target_hint': 'Set: /target person standing', 'target_not_set': 'not set (default: yellow vehicle)', 'target_filter': 'Search filter', 'target_filter_kept': "Couldn't recognize color/class - filter kept", 'any_color': 'any color', 'color_filter': 'color filter', 'lang_title': '🌐 Interface language / Idioma de la interfaz', 'lang_set': 'Interface language: {lang}', 'cb_cancel': 'Alarm off', 'cb_auto': 'Mode switched', 'menu_autoguard': 'Auto mode: on/off', 'menu_togglealarm': 'Alarm on/off manually', 'menu_zone': 'Search zone: /zone N3x4 C9', 'menu_target': 'Search target: /target text', 'menu_plug': 'Plugs: /plug', 'menu_lang': 'Language: EN/ES/RU', 'menu_cam': 'Camera: /cam name', 'cam_status': 'Camera: {status}'}, 'es': {'alert': '⚠️ ¡ATENCIÓN! ¡ALARMA! ¡ALARMA ACTIVADA!\nAPAGAR CON /togglealarm DESDE EL MENÚ', 'mode_title': '⚙️ MODO DE FUNCIONAMIENTO', 'current_mode': 'Modo actual', 'mode_auto': '✅ AUTOMÁTICO', 'mode_manual': '🚫 MANUAL', 'zone_search': 'Zona de búsqueda', 'target_search': 'Objetivo de búsqueda', 'whole_frame': 'todo el cuadro', 'row_col': 'fila {r}, columna {c}', 'control_hint': 'Control: menú → /autoguard, /togglealarm, /zone, /target, /cam', 'auto_on': '✅ MODO AUTO ACTIVADO', 'auto_off': '🚫 MODO AUTO DESACTIVADO — MODO MANUAL', 'auto_on_detail': 'El enchufe se apagará automáticamente cuando el objetivo salga de la zona ({n} cuadros limpios). Apagado manual — /togglealarm.', 'manual_only': 'La alarma solo se puede apagar con /togglealarm desde el menú.', 'alarm_on_manual': '🚨 Alarma activada manualmente (/togglealarm). Para apagar — /togglealarm de nuevo.', 'alarm_off_manual': '🚨 Alarma apagada manualmente (/togglealarm).', 'cam_unavailable': '⚠️ Cámara no disponible — no puedo activar la alarma.', 'force_alarm': '🚨 ALARMA FORZADA (manual)', 'looking_for': 'Buscando', 'zone': 'Zona', 'trigger_frame': '📷 cuadro de disparo', 'live_frame': '📺 cuadro en vivo', 'camera': 'Cámara', 'yellow_found': '🚗 ¡OBJETIVO DETECTADO!', 'threat_gone': 'Amenaza resuelta: el objetivo salió de la zona de búsqueda', 'alarm_off': '🚨 Alarma apagada.', 'auto_active': '✅ MODO AUTO ACTIVO', 'manual_active': '🚫 MODO MANUAL ACTIVO', 'zone_set': 'Zona de búsqueda configurada', 'zone_off': 'Zona de búsqueda: TODO EL CUADRO (zona desactivada).', 'zone_help': 'Formato: /zone N3x4 C9\nN{rows}x{cols} — división del cuadro\nC{num} — celда\n/zone off — todo el cuadro', 'zone_bad': 'No entiendo el formato «{arg}». Ejemplo: /zone N3x4 C9', 'target_current': 'Objetivo de búsqueda actual', 'target_set': 'Objetivo de búsqueda actualizado', 'target_hint': 'Configurar: /target persona de pie', 'target_not_set': 'no configurado (por defecto: vehículo amarillo)', 'target_filter': 'Filtro de búsqueda', 'target_filter_kept': 'No reconocí color/clase - filtro sin cambios', 'any_color': 'cualquier цвет', 'color_filter': 'filtro de color', 'lang_title': '🌐 Язык интерфейса / Interface language / Idioma de la interfaz', 'lang_set': 'Idioma de la interfaz: {lang}', 'cb_cancel': 'Alarma apagada', 'cb_auto': 'Modo cambiado', 'menu_autoguard': 'Modo auto: on/off', 'menu_togglealarm': 'Alarma on/off manual', 'menu_zone': 'Zona: /zone N3x4 C9', 'menu_target': 'Objetivo: /target texto', 'menu_plug': 'Enchufes: /plug', 'menu_lang': 'Idioma: EN/ES/RU', 'menu_cam': 'Cámara: /cam nombre', 'cam_status': 'Cámara: {status}'}}

    def tr(self, key: str, **kw) -> str:
        txt = self.L[self.lang].get(key) or self.L['ru'].get(key, key)
        if kw:
            try:
                txt = txt.format(**kw)
            except (KeyError, IndexError):
                pass
        return txt

    def _register_commands(self):
        self.tg.register('/autoguard', self.cmd_autoguard)
        self.tg.register('/togglealarm', self.cmd_togglealarm)
        self.tg.register('/zone', self.cmd_zone)
        self.tg.register('/target', self.cmd_target)
        self.tg.register('/cam', self.cmd_cam)
        self.tg.register('/plug', self.cmd_plug)
        self.tg.register('/setlocal', self.cmd_setlocal)
        self.tg.set_default(self.cmd_default)
        self.tg.register_callback('set_lang:', self.cb_set_lang)
        self.tg.register_callback('cancel_alarm', self.cb_cancel_alarm)
        self.tg.register_callback('auto_toggle', self.cb_auto_toggle)

    async def cmd_autoguard(self, ctx: CommandContext):
        await self.toggle_auto()

    async def cmd_togglealarm(self, ctx: CommandContext):
        args = ctx.args.strip()
        if args:
            try:
                cam_id = int(args)
                if 1 <= cam_id <= 8:
                    await self.toggle_alarm(cam_id)
                    return
            except ValueError:
                pass
        await self.toggle_alarm()

    async def cmd_zone(self, ctx: CommandContext):
        arg = ctx.args.strip()
        if not arg or arg.lower() in ('?', 'help', 'справка', 'ayuda'):
            await self.tg.send_message(ctx.chat_id, f"📍 {self.tr('zone_search')}: {self.zone_label()}\n\n{self.tr('zone_help')}")
            return
        if arg.lower() in ('off', 'none', 'всё', 'все', '0', 'todo', 'toda', 'nada', 'desactivar'):
            await self.set_zone(None)
            return
        zone = parse_zone_spec(arg)
        if zone is None:
            await self.tg.send_message(ctx.chat_id, f"⚠️ {self.tr('zone_bad', arg=arg)}")
            return
        await self.set_zone(zone)

    async def cmd_target(self, ctx: CommandContext):
        arg = ctx.args.strip()
        if not arg or arg.lower() in ('?', 'help', 'справка', 'ayuda'):
            await self.tg.send_message(ctx.chat_id, f"🔍 {self.tr('target_current')}: {self.target_label()}\n{self.tr('target_hint')}")
            return
        await self.set_target(arg)

    async def cmd_cam(self, ctx: CommandContext):
        arg = ctx.args.strip()
        if not arg or arg.lower() in ('?', 'list', 'список', 'lista'):
            lines = []
            for cid in range(1, 9):
                cam = self.camera_manager.get(cid)
                status = '🟢' if cam and cam.alive else '🔴'
                marker = ' ← ACTIVE' if cid == self.active_camera_id else ''
                name = self.config.cameras.get(cid, CameraConfig(cam_id=cid, name=f'Camera {cid}', url='')).name
                lines.append(f'{status} {name} ({cid}){marker}')
            await self.tg.send_message(ctx.chat_id, 'Доступные камеры (1-8):\n' + '\n'.join(lines))
            return
        if arg.lower() in ('status', 'статус', 'estado'):
            lines = []
            for cid in range(1, 9):
                cam = self.camera_manager.get(cid)
                status = '🟢 alive' if cam and cam.alive else '🔴 dead'
                name = self.config.cameras.get(cid, CameraConfig(cam_id=cid, name=f'Camera {cid}', url='')).name
                lines.append(f'{name} ({cid}): {status}')
            await self.tg.send_message(ctx.chat_id, 'Статус камер:\n' + '\n'.join(lines))
            return
        try:
            num = int(arg)
            if 1 <= num <= 8:
                await self.switch_camera(num)
                return
        except ValueError:
            pass
        await self.tg.send_message(ctx.chat_id, f"Камера '{arg}' не найдена. Используйте номер 1-8. /cam ? для списка.")

    async def cmd_plug(self, ctx: CommandContext):
        arg = ctx.args.strip()
        if not arg or arg.lower() in ('?', 'help', 'справка', 'ayuda', 'list', 'список', 'lista'):
            await self.list_plugs()
            return
        if arg.lower() == 'test':
            await self.test_plugs()
            return
        numbers = []
        for token in arg.split():
            try:
                numbers.append(int(token))
            except ValueError:
                await self.tg.send_message(ctx.chat_id, f"❌ Не понял номер розетки: '{token}'. Пример: /plug 1 2 3")
                return
        plug_names = [f'plug{n}' for n in numbers]
        await self.set_active_camera_plugs(plug_names)

    async def cmd_setlocal(self, ctx: CommandContext):
        buttons = [[Button.inline('🇬🇧 EN', 'set_lang:en'), Button.inline('🇪🇸 ES', 'set_lang:es'), Button.inline('🇷🇺 RU', 'set_lang:ru')]]
        await self.tg.send_message(ctx.chat_id, self.tr('lang_title'), buttons=buttons)

    async def cmd_default(self, ctx: CommandContext):
        await self.tg.delete_message(ctx.chat_id, ctx.message_id)

    async def cb_set_lang(self, event, data):
        code = data.split(':', 1)[1]
        await self.tg.answer_callback(event, self.tr('lang_set', lang=code))
        await self.set_language(code)

    async def cb_cancel_alarm(self, event, data):
        await self.tg.answer_callback(event, self.tr('cb_cancel'))
        await self.cancel_alarm()

    async def cb_auto_toggle(self, event, data):
        await self.tg.answer_callback(event, self.tr('cb_auto'))
        await self.toggle_auto()

    async def set_language(self, code: str):
        if code not in self.L:
            return
        self.lang = code
        self.save_settings()
        await self.set_bot_menu()
        self.refresh_control_msg()
        await self.tg.send_message(self.config.telegram.chat_id, self.tr('lang_set', lang=code))

    async def toggle_auto(self):
        self.alarm.auto_mode = not self.alarm.auto_mode
        self.save_settings()
        self.refresh_control_msg()
        await self.tg.send_message(self.config.telegram.chat_id, self.tr('auto_on') if self.alarm.auto_mode else self.tr('auto_off'))
        if self.alarm.auto_mode:
            await self.tg.send_message(self.config.telegram.chat_id, self.tr('auto_on_detail', n=self.config.detection.auto_resolve_frames))

    async def toggle_alarm(self, cam_id: Optional[int]=None):
        if cam_id is None:
            cam_id = self.active_camera_id
        state = self.alarm.get(cam_id)
        if state.is_active:
            await self.cancel_alarm(cam_id=cam_id, note=self.tr('alarm_off_manual'))
        else:
            cam = self.camera_manager.get(cam_id)
            if not cam or not cam.alive:
                await self.tg.send_message(self.config.telegram.chat_id, self.tr('cam_unavailable'))
                return
            frame = getattr(self, '_annotated_frames', {}).get(cam_id)
            if frame is not None:
                frame = frame.annotated
            else:
                frame = cam.latest
            if frame is None:
                await self.tg.send_message(self.config.telegram.chat_id, self.tr('cam_unavailable'))
                return
            await self.trigger_alarm(self.tr('force_alarm'), frame, cam_id=cam_id, manual=True)

    async def cancel_alarm(self, cam_id: Optional[int]=None, note: str=''):
        if cam_id is None:
            cams = self.alarm.active_cameras()
            cam_id = cams[-1] if cams else self.alarm.alarm_camera_id
        if cam_id is None:
            return
        state = self.alarm.get(cam_id)
        if not state.is_active:
            return
        if state.msg_id and state.first_frame is not None:
            try:
                ok, buf = cv2.imencode('.jpg', state.first_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
                if ok:
                    cam_name = self.config.cameras.get(cam_id, CameraConfig(cam_id=cam_id, name=f'Camera {cam_id}', url='')).name
                    caption = f"{self.tr('alert')}\n\n📅 {time.strftime('%H:%M:%S')}\n📷 {self.tr('camera')}: {cam_name}\n\n📷 {self.tr('trigger_frame')}"
                    await self.tg.edit_message(self.config.telegram.chat_id, state.msg_id, file_bytes=buf.tobytes(), caption=caption)
            except Exception as e:
                print(f'  Restore first frame error: {e}')
        self.set_actuators(False, cam_id)
        result = self.alarm.deactivate(cam_id, keep_trigger=True)
        if result.get('already_inactive'):
            return
        self.write_status()
        for mid in result.get('delete_msg_ids', []):
            await self.tg.delete_message(self.config.telegram.chat_id, mid)
        if note:
            await self.tg.send_message(self.config.telegram.chat_id, note)
        await self.tg.send_message(self.config.telegram.chat_id, self.tr('alarm_off'))
        self.refresh_control_msg()

    async def set_zone(self, zone: Optional[Zone]):
        settings = self.get_active_settings()
        settings.zone = zone
        self.save_camera_settings()
        self.refresh_control_msg()
        await self.tg.send_message(self.config.telegram.chat_id, f"📍 {self.tr('zone_set')}: {self.zone_label()}" if zone else f"📍 {self.tr('zone_off')}")

    async def set_target(self, text: str):
        target = parse_target_text(text)
        settings = self.get_active_settings()
        settings.target = target
        self.save_camera_settings()
        self.refresh_control_msg()
        if not target.classes and (not target.color_ranges):
            await self.tg.send_message(self.config.telegram.chat_id, f"🔍 {self.tr('target_set')}: {text}\n{self.tr('target_filter_kept')}: {target.filter_label()}")
        else:
            await self.tg.send_message(self.config.telegram.chat_id, f"🔍 {self.tr('target_set')}: {text}\n🔍 {self.tr('target_filter')}: {target.filter_label()}")

    async def switch_camera(self, cam_id: int):
        self.alarm.active_camera_id = cam_id
        self.camera_manager.set_active(cam_id)
        self.load_camera_settings()
        self.save_settings()
        self.refresh_control_msg()
        self.write_status()
        name = self.config.cameras.get(cam_id, CameraConfig(cam_id=cam_id, name=f'Camera {cam_id}', url='')).name
        await self.tg.send_message(self.config.telegram.chat_id, f'Камера переключена: {name}')

    async def list_plugs(self):
        plugs = self.actuator_manager.list_all()
        cam_id = self.active_camera_id
        active_bindings = self.actuator_manager.camera_bindings.get(cam_id, [])
        lines = [f'🔌 Розетки. Активная камера: {cam_id}']
        lines.append(f"   → привязаны: {(', '.join(active_bindings) if active_bindings else 'нет')}")
        lines.append('')
        lines.append('Список розеток:')
        for p in plugs:
            cam_list = ', '.join((f'cam{c}' for c in p['cameras'])) if p['cameras'] else 'нет'
            lines.append(f"  {p['status_icon']} {p['name']} ({p['type']}): {p['status']} | cameras: {cam_list}")
        lines.append('')
        lines.append('Задать: /plug 1 2 3 — розетки для активной камеры')
        await self.tg.send_message(self.config.telegram.chat_id, '\n'.join(lines))

    async def test_plugs(self):
        results = self.actuator_manager.test_all()
        lines = ['🔌 Тестирование розеток...']
        for r in results:
            icon = '🟢' if r['status'] in ('OK', 'RECONNECTED') else '🔴'
            recon = ' (переподключено)' if r.get('reconnected') else ''
            lines.append(f"  {icon} {r['name']}: {r['status']}{recon}")
        await self.tg.send_message(self.config.telegram.chat_id, '\n'.join(lines))

    async def set_active_camera_plugs(self, plug_names: List[str]):
        available = [p['name'] for p in self.actuator_manager.list_all()]
        unknown = [n for n in plug_names if n not in available]
        if unknown:
            await self.tg.send_message(self.config.telegram.chat_id, f"❌ Розетки не найдены: {', '.join(unknown)}. Доступные: {', '.join(available)}")
            return
        cam_id = self.active_camera_id
        self.actuator_manager.set_camera_bindings(cam_id, plug_names)
        settings = self.get_camera_settings(cam_id)
        settings.actuator = plug_names
        self.save_camera_settings()
        cam_name = self.config.cameras.get(cam_id, CameraConfig(cam_id=cam_id, name=f'Camera {cam_id}', url='')).name
        plugs_str = ', '.join(plug_names) if plug_names else 'нет'
        await self.tg.send_message(self.config.telegram.chat_id, f'✅ Камера {cam_id} ({cam_name}) → розетки: {plugs_str}')

    async def trigger_alarm(self, desc: str, frame: np.ndarray, cam_id: Optional[int]=None, manual: bool=False):
        cam_id = cam_id or self.alarm.active_camera_id
        state = self.alarm.get(cam_id)
        if not self.alarm.activate(cam_id, auto=self.alarm.auto_mode, manual=manual):
            return
        self.alarm.active_camera_id = cam_id
        self.active_camera_id = cam_id
        self.camera_manager.set_active(cam_id)
        self.load_camera_settings()
        self.set_actuators(True, cam_id)
        state.first_frame = frame.copy()
        state.frame_pool = [frame]
        self.write_status()
        self.write_alarm_frame(frame)
        ok, buf = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
        frame_bytes = buf.tobytes()
        cam_name = self.config.cameras.get(cam_id, CameraConfig(cam_id=cam_id, name=f'Camera {cam_id}', url='')).name
        caption = f"{self.tr('alert')}\n\n📅 {time.strftime('%H:%M:%S')}\n{desc}\n\n🔍 {self.tr('looking_for')}: {self.target_label()}\n📍 {self.tr('zone')}: {self.zone_label()}\n📷 {self.tr('camera')}: {cam_name}\n\n📷 {self.tr('trigger_frame')}"
        buttons = [[Button.inline('🚨 Отключить тревогу', 'cancel_alarm')]]
        res = await self.tg.send_file(self.config.telegram.chat_id, frame_bytes, caption, buttons=buttons)
        if not res:
            await self.cancel_alarm(cam_id=cam_id)
            return
        state.msg_id = res.id
        state.known_msg_ids.add(res.id)
        self.save_local(frame_bytes)
        asyncio.create_task(self._update_loop(cam_id))
        if manual:
            await self.tg.send_message(self.config.telegram.chat_id, self.tr('alarm_on_manual') + '\n' + self.tr('manual_only'))

    async def _update_loop(self, cam_id: int):
        state = self.alarm.get(cam_id)
        last_sent_hash = None
        while True:
            await asyncio.sleep(self.config.detection.update_every)
            if not state.is_active:
                return
            mid = state.msg_id
            if mid is None:
                continue
            processed = getattr(self, '_annotated_frames', {}).get(cam_id)
            if processed is None or processed.annotated is None:
                continue
            frame = processed.annotated
            frame_hash = hash(frame.tobytes())
            if last_sent_hash is not None and frame_hash == last_sent_hash:
                continue
            state.frame_pool.append(frame)
            if len(state.frame_pool) > 60:
                state.frame_pool.pop(0)
            ok, buf = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
            if not ok:
                continue
            caption = f"{self.tr('alert')}\n\n📅 {time.strftime('%H:%M:%S')}\n📺 {self.tr('live_frame')}"
            try:
                if await self.tg.edit_message(self.config.telegram.chat_id, mid, file_bytes=buf.tobytes(), caption=caption):
                    self.save_local(buf.tobytes())
                    self.write_alarm_frame(frame)
                    last_sent_hash = frame_hash
            except Exception as e:
                print(f'  Live frame update error: {e}')

    def set_actuators(self, on: bool, cam_id: int):
        actuators = self.actuator_manager.get_for_camera(cam_id)
        if not actuators:
            print(f"  PLUG {('ON' if on else 'OFF')} FAILED: No actuators for cam={cam_id}")
            return False
        results = []
        for act in actuators:
            try:
                result = act.turn_on() if on else act.turn_off()
                results.append(result)
                print(f"  Actuator '{act.name}' {('ON' if on else 'OFF')}: {('success' if result else 'failed')}")
            except Exception as e:
                print(f'  Actuator error: {e}')
                results.append(False)
        return any(results)

    def get_active_settings(self) -> CameraSettings:
        return self.get_camera_settings(self.active_camera_id)

    def get_camera_settings(self, cam_id: int) -> CameraSettings:
        if cam_id not in self.camera_settings:
            self.camera_settings[cam_id] = CameraSettings()
        return self.camera_settings[cam_id]

    def save_camera_settings(self):
        import os, json
        data = {'camera_settings': {}, 'active_camera': self.active_camera_id, 'lang': self.lang}
        try:
            with open(self.config.settings_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            pass
        for cam_id, settings in self.camera_settings.items():
            data['camera_settings'][str(cam_id)] = settings.to_dict()
        data['active_camera'] = self.active_camera_id
        data['lang'] = self.lang
        with open(self.config.settings_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def save_settings(self):
        self.save_camera_settings()

    def load_settings(self):
        import os, json
        if not os.path.exists(self.config.settings_file):
            return
        try:
            with open(self.config.settings_file, encoding='utf-8') as f:
                data = json.load(f)
            self.lang = data.get('lang', 'ru')
            self.alarm.auto_mode = data.get('auto', False)
            self.active_camera_id = data.get('active_camera', 1)
            self.camera_manager.set_active(self.active_camera_id)
            for cam_key, cs_data in data.get('camera_settings', {}).items():
                cam_id = int(cam_key)
                settings = CameraSettings.from_dict(cs_data)
                self.camera_settings[cam_id] = settings
                if settings.actuator:
                    self.actuator_manager.set_camera_bindings(cam_id, settings.actuator)
            print(f'Settings loaded: cam={self.active_camera_id} lang={self.lang} auto={self.alarm.auto_mode}')
        except Exception as e:
            print(f'Settings load error: {e}')

    def zone_label(self) -> str:
        settings = self.get_active_settings()
        if settings.zone is None:
            return self.tr('whole_frame')
        return str(settings.zone) + f" ({self.tr('row_col', r=settings.zone.row, c=settings.zone.col)})"

    def target_label(self) -> str:
        settings = self.get_active_settings()
        if settings.target and settings.target.description:
            return settings.target.description
        return self.tr('target_not_set')

    def refresh_control_msg(self):
        if self.alarm.control_msg_id:
            self.tg.edit_message(self.config.telegram.chat_id, self.alarm.control_msg_id, text=self.control_text())

    def control_text(self) -> str:
        mode = self.tr('mode_auto') if self.alarm.auto_mode else self.tr('mode_manual')
        cam_name = self.config.cameras.get(self.active_camera_id, CameraConfig(cam_id=self.active_camera_id, name=f'Camera {self.active_camera_id}', url='')).name
        plugs = self.actuator_manager.camera_bindings.get(self.active_camera_id, [])
        plugs_str = ', '.join(plugs) if plugs else '—'
        return f"⚙️ {self.tr('mode_title')}\n\n📌 {self.tr('current_mode')}: {mode}\n🎯 {self.tr('target_search')}: {self.target_label()}\n📍 {self.tr('zone_search')}: {self.zone_label()}\n🔌 Розетки: {plugs_str}\n📷 {self.tr('camera')}: {cam_name}\n\n💡 {self.tr('control_hint')}"

    async def set_bot_menu(self):
        pass

    def save_local(self, frame_bytes: bytes):
        ts = time.strftime('%Y%m%d_%H%M%S')
        import hashlib, os
        path = os.path.join(self.frame_dir, f'panic_{ts}_{hashlib.md5(frame_bytes).hexdigest()[:6]}.jpg')
        with open(path, 'wb') as f:
            f.write(frame_bytes)

    def _state_dir(self) -> str:
        import os
        d = os.path.join(os.path.dirname(self.config.base_dir), 'desktop_state')
        os.makedirs(d, exist_ok=True)
        return d

    def write_status(self, alarm_active: bool=None):
        import os, json
        d = self._state_dir()
        settings = self.get_active_settings()
        plugs = self.actuator_manager.camera_bindings.get(self.alarm.active_camera_id, [])
        active_cams = self.alarm.active_cameras()
        state = {'active_camera': self.alarm.active_camera_id, 'auto_mode': bool(self.alarm.auto_mode), 'alarm_active': self.alarm.any_active() if alarm_active is None else alarm_active, 'alarm_camera': self.alarm.alarm_camera_id, 'active_alarm_cameras': active_cams, 'zone': str(settings.zone) if settings.zone else '', 'target': settings.target.description if settings.target and settings.target.description else '', 'plugs': list(plugs), 'camera_names': {str(k): v.name for k, v in self.config.cameras.items()}, 'timestamp': time.time()}
        tmp = os.path.join(d, 'status.json.tmp')
        try:
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(state, f, ensure_ascii=False)
            os.replace(tmp, os.path.join(d, 'status.json'))
        except Exception as e:
            print(f'  status write error: {e}')

    def write_alarm_frame(self, frame):
        import os
        try:
            ok, buf = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
            if not ok:
                return
            with open(os.path.join(self._state_dir(), 'alarm_live.jpg'), 'wb') as f:
                f.write(buf.tobytes())
        except Exception as e:
            print(f'  alarm frame write error: {e}')

    async def detection_loop(self):
        from ..detectors import create_pipeline_from_config, ProcessedFrame
        streak = {cid: 0 for cid in range(1, 9)}
        clean = {cid: 0 for cid in range(1, 9)}
        annotated_frames: Dict[int, ProcessedFrame] = {}
        while True:
            await asyncio.sleep(self.config.detection.detect_every)
            for cam_id in range(1, 9):
                cam = self.camera_manager.get(cam_id)
                if not cam or not cam.alive:
                    continue
                if cam_id == 2 and hasattr(cam, 'get_downscaled_frame'):
                    frame = cam.get_downscaled_frame(max_width=1280)
                else:
                    frame = cam.latest
                if frame is None:
                    continue
                settings = self.get_camera_settings(cam_id)
                zone = settings.zone
                target = settings.target or Target()
                pipeline = create_pipeline_from_config(self.config, target, zone)
                processed = pipeline.process(frame, zone)
                processed.camera_id = cam_id
                annotated_frames[cam_id] = processed
                matches = processed.matches
                all_dets = processed.all_detections
                if len(matches) >= self.config.detection.min_yellow_vehicles:
                    streak[cam_id] += 1
                    clean[cam_id] = 0
                else:
                    streak[cam_id] = 0
                    clean[cam_id] += 1
                status = f'[cam {cam_id}] hit={len(matches)}/{self.config.detection.min_yellow_vehicles} streak={streak[cam_id]}/{self.config.detection.require_frames} clean={clean[cam_id]}/{self.config.detection.auto_resolve_frames} zone={self.zone_label()} | ' + ', '.join((f'{d.name} c={d.confidence:.2f} y={d.color_fraction * 100:.0f}%' for d in all_dets)) or 'empty'
                print(status, flush=True)
                if streak[cam_id] >= self.config.detection.require_frames and (not self.alarm.is_cam_active(cam_id)):
                    m = matches[0]
                    desc = f"{self.tr('yellow_found')}\n({m.name} conf={m.confidence:.2f}, color={m.color_fraction * 100:.0f}%)"
                    await self.trigger_alarm(desc, processed.annotated, cam_id=cam_id)
                    streak[cam_id] = 0
            for alarm_cam in list(self.alarm.active_cameras()):
                state = self.alarm.get(alarm_cam)
                if state.auto_mode and clean.get(alarm_cam, 0) >= self.config.detection.auto_resolve_frames:
                    await self.cancel_alarm(cam_id=alarm_cam, note=self.tr('threat_gone'))
            self.write_status()
        self._annotated_frames = annotated_frames

async def main():
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    base_dir = os.path.dirname(os.path.abspath(__file__))
    config = load_config(base_dir)
    bot = SuperGuardTelethonBot(config)
    bot.load_settings()
    await bot.tg.start()
    print('Bot started with Telethon (MTProto)')
    await bot.detection_loop()
if __name__ == '__main__':
    import os
    asyncio.run(main())