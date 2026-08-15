"""
SuperGuard Core - Telegram Notifier Plugin

Telegram bot notifications with inline keyboards and media support.
"""

import asyncio
import logging
from typing import Optional, List, Dict, Any

import aiohttp

from superguard_core.core.plugins import NotifierPlugin, PluginConfig
from superguard_core.core.events import EventBus, Event, Streams
from superguard_core.core.database import Alarm, AlarmStatus


logger = logging.getLogger(__name__)


class TelegramNotifierPlugin(NotifierPlugin):
    """Telegram bot notifier with rich formatting and inline keyboards."""
    
    name = "telegram"
    version = "1.0.0"
    plugin_type = "notifier"
    description = "Telegram bot notifications with inline controls"
    author = "SuperGuard Team"
    
    def __init__(self, config: PluginConfig, event_bus: EventBus):
        super().__init__(config, event_bus)
        self._bot_token: str = ""
        self._allowed_users: List[int] = []
        self._session: Optional[aiohttp.ClientSession] = None
        self._api_url: str = ""
        self._site_id: int = 0
        
        # Rate limiting
        self._last_send: float = 0
        self._min_interval: float = 0.5  # 2 messages/sec max
        
        # Command handlers
        self._command_handlers = {
            "/start": self._handle_start,
            "/help": self._handle_help,
            "/alarm": self._handle_alarm_list,
            "/cameras": self._handle_cameras,
            "/actuators": self._handle_actuators,
        }
    
    async def initialize(self, site_id: int) -> None:
        """Initialize Telegram bot."""
        self._site_id = site_id
        
        self._bot_token = self.config.get("bot_token", "")
        self._allowed_users = self.config.get("allowed_users", [])
        
        if not self._bot_token:
            raise ValueError("Telegram notifier requires bot_token")
        
        self._api_url = f"https://api.telegram.org/bot{self._bot_token}"
        
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
        )
        
        # Test bot
        async with self._session.get(f"{self._api_url}/getMe") as resp:
            if resp.status != 200:
                raise RuntimeError("Invalid bot token")
            data = await resp.json()
            logger.info(f"Telegram bot connected: @{data['result']['username']}")
        
        # Start polling for updates
        self._polling_task = asyncio.create_task(self._poll_updates())
        
        # Subscribe to alarm events
        await self._event_bus.subscribe(
            Streams.ALARMS_EVENTS,
            self._on_alarm_event,
            group=f"telegram-alarms-{site_id}"
        )
        
        await self._set_status(self.PluginStatus.LOADED)
        self._initialized = True
        
        logger.info(f"Telegram notifier initialized for site {site_id}")
    
    async def _poll_updates(self) -> None:
        """Long polling for Telegram updates."""
        offset = 0
        
        while self._initialized:
            try:
                params = {
                    "offset": offset + 1,
                    "timeout": 30,
                    "allowed_updates": ["message", "callback_query"],
                }
                
                async with self._session.get(f"{self._api_url}/getUpdates", params=params) as resp:
                    if resp.status != 200:
                        await asyncio.sleep(5)
                        continue
                    
                    data = await resp.json()
                    
                    for update in data.get("result", []):
                        offset = update["update_id"]
                        
                        if "message" in update:
                            await self._handle_message(update["message"])
                        elif "callback_query" in update:
                            await self._handle_callback(update["callback_query"])
                            
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Telegram polling error: {e}")
                await asyncio.sleep(5)
    
    async def _handle_message(self, message: dict) -> None:
        """Handle incoming message."""
        user_id = message.get("from", {}).get("id")
        chat_id = message.get("chat", {}).get("id")
        text = message.get("text", "")
        
        # Check authorization
        if self._allowed_users and user_id not in self._allowed_users:
            await self._send_message(chat_id, "��� Unauthorized")
            return
        
        # Handle commands
        if text.startswith("/"):
            cmd = text.split()[0].lower()
            handler = self._command_handlers.get(cmd)
            if handler:
                await handler(chat_id, user_id, message)
            else:
                await self._send_message(chat_id, f"Unknown command: {cmd}. Use /help")
    
    async def _handle_callback(self, callback: dict) -> None:
        """Handle inline keyboard callback."""
        user_id = callback.get("from", {}).get("id")
        chat_id = callback.get("message", {}).get("chat", {}).get("id")
        data = callback.get("data", "")
        callback_id = callback.get("id")
        
        # Check authorization
        if self._allowed_users and user_id not in self._allowed_users:
            await self._answer_callback(callback_id, "��� Unauthorized", show_alert=True)
            return
        
        # Handle callback data
        if data.startswith("alarm_ack_"):
            alarm_id = int(data.replace("alarm_ack_", ""))
            await self._acknowledge_alarm(chat_id, callback_id, alarm_id, user_id)
        elif data.startswith("alarm_resolve_"):
            alarm_id = int(data.replace("alarm_resolve_", ""))
            await self._resolve_alarm(chat_id, callback_id, alarm_id, user_id, "resolved")
        elif data.startswith("alarm_fp_"):
            alarm_id = int(data.replace("alarm_fp_", ""))
            await self._resolve_alarm(chat_id, callback_id, alarm_id, user_id, "false_positive")
        elif data.startswith("actuator_on_"):
            actuator_id = int(data.replace("actuator_on_", ""))
            await self._control_actuator(chat_id, callback_id, actuator_id, "on")
        elif data.startswith("actuator_off_"):
            actuator_id = int(data.replace("actuator_off_", ""))
            await self._control_actuator(chat_id, callback_id, actuator_id, "off")
        elif data == "refresh_alarms":
            await self._handle_alarm_list(chat_id, user_id, {})
        elif data == "refresh_cameras":
            await self._handle_cameras(chat_id, user_id, {})
        elif data == "refresh_actuators":
            await self._handle_actuators(chat_id, user_id, {})
        else:
            await self._answer_callback(callback_id, "Unknown action")
    
    async def _send_message(
        self,
        chat_id: int,
        text: str,
        parse_mode: str = "HTML",
        reply_markup: dict = None,
    ) -> bool:
        """Send message to Telegram."""
        # Rate limiting
        now = asyncio.get_event_loop().time()
        if now - self._last_send < self._min_interval:
            await asyncio.sleep(self._min_interval - (now - self._last_send))
        
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }
        
        if reply_markup:
            payload["reply_markup"] = reply_markup
        
        try:
            async with self._session.post(f"{self._api_url}/sendMessage", json=payload) as resp:
                self._last_send = asyncio.get_event_loop().time()
                return resp.status == 200
        except Exception as e:
            logger.error(f"Telegram send failed: {e}")
            return False
    
    async def _send_photo(
        self,
        chat_id: int,
        photo_bytes: bytes,
        caption: str = "",
        parse_mode: str = "HTML",
        reply_markup: dict = None,
    ) -> bool:
        """Send photo to Telegram."""
        try:
            data = aiohttp.FormData()
            data.add_field("chat_id", str(chat_id))
            data.add_field("photo", photo_bytes, filename="frame.jpg", content_type="image/jpeg")
            if caption:
                data.add_field("caption", caption)
                data.add_field("parse_mode", parse_mode)
            if reply_markup:
                import json
                data.add_field("reply_markup", json.dumps(reply_markup))
            
            async with self._session.post(f"{self._api_url}/sendPhoto", data=data) as resp:
                return resp.status == 200
        except Exception as e:
            logger.error(f"Telegram photo send failed: {e}")
            return False
    
    async def _answer_callback(self, callback_id: str, text: str, show_alert: bool = False) -> bool:
        """Answer callback query."""
        try:
            async with self._session.post(
                f"{self._api_url}/answerCallbackQuery",
                json={"callback_query_id": callback_id, "text": text, "show_alert": show_alert}
            ) as resp:
                return resp.status == 200
        except Exception:
            return False
    
    # Command handlers
    
    async def _handle_start(self, chat_id: int, user_id: int, message: dict) -> None:
        """Handle /start command."""
        await self._send_message(chat_id, 
            "���� <b>SuperGuard Alarm Bot</b>\n\n"
            "Welcome! I'll notify you about security events.\n\n"
            "Commands:\n"
            "/alarm - Active alarms\n"
            "/cameras - Camera status\n"
            "/actuators - Actuator control\n"
            "/help - This message"
        )
    
    async def _handle_help(self, chat_id: int, user_id: int, message: dict) -> None:
        """Handle /help command."""
        await self._send_message(chat_id,
            "���� <b>SuperGuard Commands</b>\n\n"
            "/alarm - List active alarms with actions\n"
            "/cameras - Camera status and snapshots\n"
            "/actuators - Manual actuator control\n"
            "/help - This help"
        )
    
    async def _handle_alarm_list(self, chat_id: int, user_id: int, message: dict) -> None:
        """Handle /alarm command."""
        # Get active alarms from event bus or database
        from superguard_core.services.alarm_engine import get_alarm_engine
        from superguard_core.core.plugins import PluginManager
        
        try:
            pm = PluginManager()
            await pm.discover_plugins()
            ae = await get_alarm_engine(self._site_id, self._event_bus)
            alarms = await ae.get_active_alarms()
        except Exception:
            alarms = []
        
        if not alarms:
            await self._send_message(chat_id, "��� No active alarms")
            return
        
        text = "���� <b>Active Alarms</b>\n\n"
        keyboard = {"inline_keyboard": []}
        
        for alarm in alarms:
            text += f"���� <b>Alarm #{alarm.id}</b>\n"
            text += f"  Camera: {alarm.camera_id}\n"
            text += f"  Started: {alarm.started_at.strftime('%H:%M:%S')}\n"
            text += f"  Class: {alarm.trigger_data.get('class_name', 'unknown')}\n"
            text += f"  Confidence: {alarm.trigger_data.get('confidence', 0):.2f}\n\n"
            
            row = [
                {"text": "��� Acknowledge", "callback_data": f"alarm_ack_{alarm.id}"},
                {"text": "��� Resolve", "callback_data": f"alarm_resolve_{alarm.id}"},
                {"text": "��� False Positive", "callback_data": f"alarm_fp_{alarm.id}"},
            ]
            keyboard["inline_keyboard"].append(row)
        
        keyboard["inline_keyboard"].append([{"text": "���� Refresh", "callback_data": "refresh_alarms"}])
        
        await self._send_message(chat_id, text, reply_markup=keyboard)
    
    async def _handle_cameras(self, chat_id: int, user_id: int, message: dict) -> None:
        """Handle /cameras command."""
        text = "���� <b>Cameras</b>\n\n"
        text += "Use web interface for live view and snapshots.\n\n"
        
        keyboard = {"inline_keyboard": [[{"text": "���� Refresh", "callback_data": "refresh_cameras"}]]}
        
        await self._send_message(chat_id, text, reply_markup=keyboard)
    
    async def _handle_actuators(self, chat_id: int, user_id: int, message: dict) -> None:
        """Handle /actuators command."""
        text = "���� <b>Actuators</b>\n\n"
        text += "Manual control:\n"
        
        keyboard = {"inline_keyboard": []}
        
        # Get actuators from database
        try:
            from superguard_core.core.database import get_session_factory, Actuator
            from sqlalchemy import select
            
            factory = get_session_factory()
            if factory:
                async with factory() as session:
                    result = await session.execute(
                        select(Actuator).where(Actuator.site_id == self._site_id, Actuator.is_enabled == True)
                    )
                    actuators = result.scalars().all()
                    
                    for act in actuators:
                        state_emoji = "����" if act.last_state and act.last_state.get("is_on") else "����"
                        keyboard["inline_keyboard"].append([
                            {"text": f"{state_emoji} {act.name} ON", "callback_data": f"actuator_on_{act.id}"},
                            {"text": f"��� {act.name} OFF", "callback_data": f"actuator_off_{act.id}"},
                        ])
        except Exception:
            pass
        
        keyboard["inline_keyboard"].append([{"text": "���� Refresh", "callback_data": "refresh_actuators"}])
        
        await self._send_message(chat_id, text, reply_markup=keyboard)
    
    # Callback handlers
    
    async def _acknowledge_alarm(self, chat_id: int, callback_id: str, alarm_id: int, user_id: int) -> None:
        """Acknowledge alarm via callback."""
        try:
            from superguard_core.services.alarm_engine import get_alarm_engine
            from superguard_core.core.plugins import PluginManager
            
            pm = PluginManager()
            await pm.discover_plugins()
            ae = await get_alarm_engine(self._site_id, self._event_bus)
            
            from superguard_core.core.database import get_session_factory
            factory = get_session_factory()
            if factory:
                ae.set_session_factory(factory)
                await ae.acknowledge_alarm(alarm_id, user_id)
                
                await self._answer_callback(callback_id, "��� Alarm acknowledged")
                await self._handle_alarm_list(chat_id, user_id, {})
        except Exception as e:
            await self._answer_callback(callback_id, f"Error: {e}", show_alert=True)
    
    async def _resolve_alarm(self, chat_id: int, callback_id: str, alarm_id: int, user_id: int, reason: str) -> None:
        """Resolve alarm via callback."""
        try:
            from superguard_core.services.alarm_engine import get_alarm_engine
            from superguard_core.core.plugins import PluginManager
            
            pm = PluginManager()
            await pm.discover_plugins()
            ae = await get_alarm_engine(self._site_id, self._event_bus)
            
            from superguard_core.core.database import get_session_factory
            factory = get_session_factory()
            if factory:
                ae.set_session_factory(factory)
                await ae.resolve_alarm(alarm_id, user_id, reason)
                
                await self._answer_callback(callback_id, f"��� Alarm {reason}")
                await self._handle_alarm_list(chat_id, user_id, {})
        except Exception as e:
            await self._answer_callback(callback_id, f"Error: {e}", show_alert=True)
    
    async def _control_actuator(self, chat_id: int, callback_id: str, actuator_id: int, action: str) -> None:
        """Control actuator via callback."""
        try:
            from superguard_core.services.actuator_engine import get_actuator_engine
            from superguard_core.core.plugins import PluginManager
            
            pm = PluginManager()
            await pm.discover_plugins()
            ae = await get_actuator_engine(self._site_id, self._event_bus)
            
            from superguard_core.core.database import get_session_factory
            factory = get_session_factory()
            if factory:
                ae.set_session_factory(factory)
                cmd = "turn_on" if action == "on" else "turn_off"
                await ae.manual_command(actuator_id, cmd)
                
                await self._answer_callback(callback_id, f"��� Actuator {action.upper()}")
                await self._handle_actuators(chat_id, 0, {})
        except Exception as e:
            await self._answer_callback(callback_id, f"Error: {e}", show_alert=True)
    
    # Event handlers
    
    async def _on_alarm_event(self, event: Event) -> None:
        """Handle alarm events from event bus."""
        if event.type in ["alarm_created", "alarm_acknowledged", "alarm_resolved"]:
            # Send notification to all allowed users
            for user_id in self._allowed_users:
                await self._notify_alarm(user_id, event)
    
    async def _notify_alarm(self, chat_id: int, event: Event) -> None:
        """Send alarm notification."""
        payload = event.payload
        
        if event.type == "alarm_created":
            text = "���� <b>NEW ALARM</b>\n\n"
            text += f"Camera: {payload.get('camera_id')}\n"
            text += f"Class: {payload.get('class_name', 'unknown')}\n"
            text += f"Confidence: {payload.get('confidence', 0):.2f}\n"
            text += f"Time: {payload.get('timestamp', '')}\n"
            
            keyboard = {
                "inline_keyboard": [
                    [
                        {"text": "��� Acknowledge", "callback_data": f"alarm_ack_{payload.get('alarm_id')}"},
                        {"text": "��� False Positive", "callback_data": f"alarm_fp_{payload.get('alarm_id')}"},
                    ]
                ]
            }
            
            # Send photo if available
            if payload.get("frame_base64"):
                import base64
                photo_bytes = base64.b64decode(payload["frame_base64"])
                await self._send_photo(chat_id, photo_bytes, caption=text, reply_markup=keyboard)
            else:
                await self._send_message(chat_id, text, reply_markup=keyboard)
        
        elif event.type == "alarm_acknowledged":
            text = f"��� Alarm #{payload.get('alarm_id')} acknowledged by {payload.get('acknowledged_by')}"
            await self._send_message(chat_id, text)
        
        elif event.type == "alarm_resolved":
            reason = payload.get("reason", "resolved")
            text = f"{'���' if reason == 'resolved' else '���'} Alarm #{payload.get('alarm_id')} {reason}"
            await self._send_message(chat_id, text)
    
    async def send_notification(self, event: Event) -> bool:
        """Send notification for any event (interface method)."""
        if event.stream == Streams.ALARMS_EVENTS:
            for user_id in self._allowed_users:
                await self._notify_alarm(user_id, event)
            return True
        return False
    
    async def shutdown(self) -> None:
        """Shutdown plugin."""
        self._initialized = False
        
        if hasattr(self, '_polling_task'):
            self._polling_task.cancel()
            try:
                await self._polling_task
            except asyncio.CancelledError:
                pass
        
        if self._session:
            await self._session.close()
        
        await self._set_status(self.PluginStatus.UNLOADED)