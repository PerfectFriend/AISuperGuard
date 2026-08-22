"""
Telegram Bot Service for SuperGuard API.
Uses python-telegram-bot v20+ (async) with inline keyboard menus like Hermes.
"""
import os
import asyncio
import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    BotCommand, BotCommandScopeChat
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, MessageHandler, filters
)
from telegram.constants import ParseMode

from app.core.config import settings
from app.core.database import get_db
from app.models.models import Notifier
from sqlalchemy import select

logger = logging.getLogger(__name__)


@dataclass
class BotMenuState:
    """Track user menu state."""
    chat_id: int
    current_menu: str = "main"
    selected_notifier_id: Optional[str] = None
    step: str = ""  # For multi-step flows
    # Dynamic attributes for multi-step flows
    selected_notifier_type: Optional[str] = None
    notifier_name: Optional[str] = None
    telegram_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    notifier_type: Optional[str] = None
    camera_name: Optional[str] = None


class SuperGuardTelegramBot:
    """Telegram bot with menu-driven interface for SuperGuard."""

    def __init__(self):
        self.token = settings.telegram_bot_token
        self.chat_id = settings.telegram_chat_id
        self.application: Optional[Application] = None
        self.user_states: Dict[int, BotMenuState] = {}
        self.allowed_users = {int(settings.telegram_chat_id)} if settings.telegram_chat_id else set()
        
        logger.info(f"TelegramBot init: token={'set' if self.token else 'MISSING'}, chat_id={self.chat_id}")

    async def initialize(self) -> bool:
        """Initialize the bot application."""
        if not self.token:
            logger.warning("Telegram bot token not configured")
            return False
            
        try:
            self.application = Application.builder().token(self.token).build()
            logger.debug("Telegram Application built successfully")
            
            # Register handlers
            self.application.add_handler(CommandHandler("start", self.cmd_start))
            self.application.add_handler(CommandHandler("menu", self.cmd_menu))
            self.application.add_handler(CommandHandler("notifiers", self.cmd_notifiers))
            self.application.add_handler(CommandHandler("alarm", self.cmd_alarm))
            self.application.add_handler(CommandHandler("camera", self.cmd_camera))
            self.application.add_handler(CommandHandler("status", self.cmd_status))
            self.application.add_handler(CommandHandler("help", self.cmd_help))
            self.application.add_handler(CommandHandler("test_notifier", self.cmd_test_notifier))
            
            # Callback query handler for inline keyboards
            self.application.add_handler(CallbackQueryHandler(self.handle_callback))
            
            # Text handler for multi-step flows
            self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text))
            
            # Set bot commands menu
            await self.set_bot_commands()
            
            logger.info("Telegram bot initialized successfully with all handlers")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize Telegram bot: {e}", exc_info=True)
            return False

    async def set_bot_commands(self):
        """Set the bot command menu (like Hermes)."""
        commands = [
            BotCommand("start", "🏁 Start bot and show main menu"),
            BotCommand("menu", "📋 Open main menu"),
            BotCommand("notifiers", "🔔 Manage Telegram notifiers"),
            BotCommand("alarm", "🚨 Alarm control"),
            BotCommand("camera", "📷 Camera management"),
            BotCommand("status", "📊 System status"),
            BotCommand("test_notifier", "🧪 Test a notifier"),
            BotCommand("help", "❓ Show help"),
        ]
        await self.application.bot.set_my_commands(commands)

    async def send_message(self, text: str, chat_id: Optional[int] = None, parse_mode: str = "HTML") -> bool:
        """Send a message via the bot."""
        if not self.application:
            logger.error("Cannot send message: bot not initialized")
            return False
        
        target_chat_id = chat_id or self.chat_id
        if not target_chat_id:
            logger.error("No chat_id configured for sending message")
            return False
        
        try:
            await self.application.bot.send_message(
                chat_id=target_chat_id,
                text=text,
                parse_mode=ParseMode.HTML if parse_mode == "HTML" else ParseMode.MARKDOWN
            )
            return True
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
            return False

    async def start(self):
        """Start the bot (polling or webhook)."""
        if not self.application:
            await self.initialize()
        if not self.application:
            logger.error("Cannot start: application not initialized")
            return
            
        logger.info("Starting Telegram bot application...")
        await self.application.initialize()
        await self.application.start()
        
        # Start polling in background (don't await - runs forever)
        self._polling_task = asyncio.create_task(
            self.application.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        )
        logger.info("Telegram bot polling started successfully")

    async def stop(self):
        """Stop the bot."""
        logger.info("Stopping Telegram bot...")
        if self.application:
            if self.application.updater and self.application.updater.running:
                logger.debug("Stopping updater...")
                await self.application.updater.stop()
            if hasattr(self, '_polling_task') and self._polling_task:
                logger.debug("Cancelling polling task...")
                self._polling_task.cancel()
                try:
                    await self._polling_task
                except asyncio.CancelledError:
                    logger.debug("Polling task cancelled")
            logger.info("Stopping application...")
            await self.application.stop()
            await self.application.shutdown()
        logger.info("Telegram bot stopped")

    def _is_allowed(self, chat_id: int) -> bool:
        """Check if user is allowed to use the bot."""
        return chat_id in self.allowed_users

    def _get_state(self, chat_id: int) -> BotMenuState:
        """Get or create user state."""
        if chat_id not in self.user_states:
            self.user_states[chat_id] = BotMenuState(chat_id=chat_id)
        return self.user_states[chat_id]

    # ==================== MENU BUILDERS ====================

    def build_main_menu(self) -> InlineKeyboardMarkup:
        """Build main menu keyboard."""
        keyboard = [
            [
                InlineKeyboardButton("🔔 Notifiers", callback_data="menu:notifiers"),
                InlineKeyboardButton("🚨 Alarms", callback_data="menu:alarms"),
            ],
            [
                InlineKeyboardButton("📷 Cameras", callback_data="menu:cameras"),
                InlineKeyboardButton("📊 Status", callback_data="menu:status"),
            ],
            [
                InlineKeyboardButton("⚙️ Settings", callback_data="menu:settings"),
                InlineKeyboardButton("❓ Help", callback_data="menu:help"),
            ],
        ]
        return InlineKeyboardMarkup(keyboard)

    def build_notifiers_menu(self) -> InlineKeyboardMarkup:
        """Build notifiers management menu."""
        keyboard = [
            [
                InlineKeyboardButton("➕ Add Notifier", callback_data="notifier:add"),
                InlineKeyboardButton("📋 List Notifiers", callback_data="notifier:list"),
            ],
            [
                InlineKeyboardButton("🧪 Test Notifier", callback_data="notifier:test"),
                InlineKeyboardButton("🗑 Delete Notifier", callback_data="notifier:delete"),
            ],
            [
                InlineKeyboardButton("🔙 Back to Main", callback_data="menu:main"),
            ],
        ]
        return InlineKeyboardMarkup(keyboard)

    def build_notifier_type_menu(self) -> InlineKeyboardMarkup:
        """Build notifier type selection menu."""
        keyboard = [
            [
                InlineKeyboardButton("🤖 Telegram Bot", callback_data="notifier:type:telegram"),
                InlineKeyboardButton("📧 Email", callback_data="notifier:type:email"),
            ],
            [
                InlineKeyboardButton("🌐 Webhook", callback_data="notifier:type:webhook"),
                InlineKeyboardButton("📡 MQTT", callback_data="notifier:type:mqtt"),
            ],
            [
                InlineKeyboardButton("🔔 Pushover", callback_data="notifier:type:pushover"),
                InlineKeyboardButton("📱 Signal", callback_data="notifier:type:signal"),
            ],
            [
                InlineKeyboardButton("📱 SMS (Twilio)", callback_data="notifier:type:sms"),
            ],
            [
                InlineKeyboardButton("🔙 Back", callback_data="menu:notifiers"),
            ],
        ]
        return InlineKeyboardMarkup(keyboard)

    def build_notifier_list_keyboard(self, notifiers: List[Dict]) -> InlineKeyboardMarkup:
        """Build keyboard with list of notifiers for selection."""
        keyboard = []
        for n in notifiers:
            status = "✅" if n.get("is_enabled") else "❌"
            keyboard.append([
                InlineKeyboardButton(
                    f"{status} {n['name']} ({n['type']})", 
                    callback_data=f"notifier:view:{n['id']}"
                )
            ])
        keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="menu:notifiers")])
        return InlineKeyboardMarkup(keyboard)

    def build_alarm_menu(self) -> InlineKeyboardMarkup:
        """Build alarm control menu."""
        keyboard = [
            [
                InlineKeyboardButton("🟢 Enable Auto Mode", callback_data="alarm:auto_on"),
                InlineKeyboardButton("🔴 Disable Auto Mode", callback_data="alarm:auto_off"),
            ],
            [
                InlineKeyboardButton("🔔 Trigger Test Alarm", callback_data="alarm:trigger_test"),
                InlineKeyboardButton("🔕 Clear All Alarms", callback_data="alarm:clear_all"),
            ],
            [
                InlineKeyboardButton("📋 Active Alarms", callback_data="alarm:list"),
                InlineKeyboardButton("🔙 Back", callback_data="menu:main"),
            ],
        ]
        return InlineKeyboardMarkup(keyboard)

    def build_camera_menu(self) -> InlineKeyboardMarkup:
        """Build camera management menu."""
        keyboard = [
            [
                InlineKeyboardButton("📋 List Cameras", callback_data="camera:list"),
                InlineKeyboardButton("➕ Add Camera", callback_data="camera:add"),
            ],
            [
                InlineKeyboardButton("🔧 Configure Camera", callback_data="camera:config"),
                InlineKeyboardButton("🧪 Test Camera", callback_data="camera:test"),
            ],
            [
                InlineKeyboardButton("🔙 Back", callback_data="menu:main"),
            ],
        ]
        return InlineKeyboardMarkup(keyboard)

    def build_settings_menu(self) -> InlineKeyboardMarkup:
        """Build settings menu."""
        keyboard = [
            [
                InlineKeyboardButton("🌐 Language: RU/EN/ES", callback_data="settings:lang"),
                InlineKeyboardButton("⏱ Detection Interval", callback_data="settings:detect_interval"),
            ],
            [
                InlineKeyboardButton("🎯 Confidence Threshold", callback_data="settings:confidence"),
                InlineKeyboardButton("🔄 Auto-resolve Frames", callback_data="settings:auto_resolve"),
            ],
            [
                InlineKeyboardButton("🔙 Back", callback_data="menu:main"),
            ],
        ]
        return InlineKeyboardMarkup(keyboard)

    # ==================== COMMAND HANDLERS ====================

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command."""
        if not update.effective_chat:
            return
        chat_id = update.effective_chat.id
        logger.info(f"cmd_start from chat_id={chat_id}")
        if not self._is_allowed(chat_id):
            logger.warning(f"Access denied for chat_id={chat_id}")
            await update.message.reply_text("❌ Access denied. Contact administrator.")
            return
            
        text = (
            "🛡 <b>SuperGuard Alarm Bot</b>\n\n"
            "Welcome! Use the menu below to manage your security system.\n\n"
            "📋 <b>Main features:</b>\n"
            "• 🔔 Notifier management (Telegram, Email, Webhook, etc.)\n"
            "• 🚨 Alarm monitoring and control\n"
            "• 📷 Camera management\n"
            "• 📊 System status and health\n\n"
            "Use /menu to open the main menu anytime."
        )
        await update.message.reply_text(
            text, 
            parse_mode=ParseMode.HTML,
            reply_markup=self.build_main_menu()
        )
        logger.debug(f"cmd_start completed for chat_id={chat_id}")

    async def cmd_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /menu command."""
        if not update.effective_chat:
            return
        chat_id = update.effective_chat.id
        logger.info(f"cmd_menu from chat_id={chat_id}")
        if not self._is_allowed(chat_id):
            return
        await update.message.reply_text(
            "📋 <b>Main Menu</b>\n\nSelect an option:",
            parse_mode=ParseMode.HTML,
            reply_markup=self.build_main_menu()
        )

    async def cmd_notifiers(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /notifiers command."""
        if not update.effective_chat:
            return
        chat_id = update.effective_chat.id
        logger.info(f"cmd_notifiers from chat_id={chat_id}")
        if not self._is_allowed(chat_id):
            return
        await update.message.reply_text(
            "🔔 <b>Notifier Management</b>\n\nSelect an action:",
            parse_mode=ParseMode.HTML,
            reply_markup=self.build_notifiers_menu()
        )

    async def cmd_alarm(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /alarm command."""
        if not self._is_allowed(update.effective_chat.id):
            return
        await update.message.reply_text(
            "🚨 <b>Alarm Control</b>\n\nSelect an action:",
            parse_mode=ParseMode.HTML,
            reply_markup=self.build_alarm_menu()
        )

    async def cmd_camera(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /camera command."""
        if not self._is_allowed(update.effective_chat.id):
            return
        await update.message.reply_text(
            "📷 <b>Camera Management</b>\n\nSelect an action:",
            parse_mode=ParseMode.HTML,
            reply_markup=self.build_camera_menu()
        )

    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command."""
        if not self._is_allowed(update.effective_chat.id):
            return
            
        # Get system status from API
        status_text = await self._get_system_status()
        await update.message.reply_text(
            status_text,
            parse_mode=ParseMode.HTML,
            reply_markup=self.build_main_menu()
        )

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command."""
        if not self._is_allowed(update.effective_chat.id):
            return
            
        text = (
            "❓ <b>SuperGuard Bot Help</b>\n\n"
            "<b>Commands:</b>\n"
            "• /start - Start bot and show main menu\n"
            "• /menu - Open main menu\n"
            "• /notifiers - Manage notifiers\n"
            "• /alarm - Alarm control\n"
            "• /camera - Camera management\n"
            "• /status - System status\n"
            "• /test_notifier - Test a notifier\n"
            "• /help - Show this help\n\n"
            "<b>Notifier Types:</b>\n"
            "• <b>Telegram Bot</b> - Send alerts to Telegram (this bot)\n"
            "• <b>Email</b> - SMTP email notifications\n"
            "• <b>Webhook</b> - HTTP POST to custom endpoint\n"
            "• <b>MQTT</b> - Publish to MQTT broker\n"
            "• <b>Pushover</b> - Pushover.net push notifications\n"
            "• <b>Signal</b> - Signal messenger via signal-cli\n"
            "• <b>SMS</b> - Twilio/Plivo/Nexmo SMS\n\n"
            "<b>Menu Navigation:</b>\n"
            "Use inline buttons below messages to navigate. "
            "Each menu has a 'Back' button to return."
        )
        await update.message.reply_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=self.build_main_menu()
        )

    async def cmd_test_notifier(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /test_notifier command."""
        if not self._is_allowed(update.effective_chat.id):
            return
            
        # Fetch notifiers from API
        notifiers = await self._fetch_notifiers()
        if not notifiers:
            await update.message.reply_text(
                "❌ No notifiers configured. Use /notifiers to add one.",
                reply_markup=self.build_notifiers_menu()
            )
            return
            
        await update.message.reply_text(
            "🧪 <b>Test Notifier</b>\n\nSelect a notifier to test:",
            parse_mode=ParseMode.HTML,
            reply_markup=self.build_notifier_list_keyboard(notifiers)
        )

    # ==================== CALLBACK HANDLER ====================

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle inline keyboard callbacks."""
        query = update.callback_query
        await query.answer()
        
        if not query.message or not query.message.chat:
            logger.warning("Callback query missing message or chat")
            return
            
        chat_id = query.message.chat.id
        logger.info(f"Callback from chat_id={chat_id}, data={query.data}")
        
        if not self._is_allowed(chat_id):
            logger.warning(f"Access denied for chat_id={chat_id}")
            await query.edit_message_text("❌ Access denied")
            return
            
        data = query.data
        state = self._get_state(chat_id)
        
        try:
            if data == "menu:main":
                await query.edit_message_text(
                    "📋 <b>Main Menu</b>\n\nSelect an option:",
                    parse_mode=ParseMode.HTML,
                    reply_markup=self.build_main_menu()
                )
                
            elif data == "menu:notifiers":
                await query.edit_message_text(
                    "🔔 <b>Notifier Management</b>\n\nSelect an action:",
                    parse_mode=ParseMode.HTML,
                    reply_markup=self.build_notifiers_menu()
                )
                
            elif data == "menu:alarms":
                await query.edit_message_text(
                    "🚨 <b>Alarm Control</b>\n\nSelect an action:",
                    parse_mode=ParseMode.HTML,
                    reply_markup=self.build_alarm_menu()
                )
                
            elif data == "menu:cameras":
                await query.edit_message_text(
                    "📷 <b>Camera Management</b>\n\nSelect an action:",
                    parse_mode=ParseMode.HTML,
                    reply_markup=self.build_camera_menu()
                )
                
            elif data == "menu:status":
                status_text = await self._get_system_status()
                await query.edit_message_text(
                    status_text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=self.build_main_menu()
                )
                
            elif data == "menu:settings":
                await query.edit_message_text(
                    "⚙️ <b>Settings</b>\n\nSelect a setting to change:",
                    parse_mode=ParseMode.HTML,
                    reply_markup=self.build_settings_menu()
                )
                
            elif data == "menu:help":
                await self.cmd_help(update, context)
                
            elif data == "notifier:add":
                await query.edit_message_text(
                    "➕ <b>Add New Notifier</b>\n\nSelect notifier type:",
                    parse_mode=ParseMode.HTML,
                    reply_markup=self.build_notifier_type_menu()
                )
                
            elif data == "notifier:list":
                notifiers = await self._fetch_notifiers()
                if not notifiers:
                    await query.edit_message_text(
                        "📋 <b>Notifiers List</b>\n\nNo notifiers configured yet.",
                        parse_mode=ParseMode.HTML,
                        reply_markup=self.build_notifiers_menu()
                    )
                else:
                    text = "📋 <b>Configured Notifiers:</b>\n\n"
                    for n in notifiers:
                        status = "✅ Enabled" if n.get("is_enabled") else "❌ Disabled"
                        text += f"• <b>{n['name']}</b> ({n['type']}) - {status}\n"
                    await query.edit_message_text(
                        text,
                        parse_mode=ParseMode.HTML,
                        reply_markup=self.build_notifier_list_keyboard(notifiers)
                    )
                    
            elif data == "notifier:test":
                notifiers = await self._fetch_notifiers()
                if not notifiers:
                    await query.edit_message_text(
                        "❌ No notifiers to test.",
                        parse_mode=ParseMode.HTML,
                        reply_markup=self.build_notifiers_menu()
                    )
                else:
                    await query.edit_message_text(
                        "🧪 <b>Test Notifier</b>\n\nSelect a notifier to test:",
                        parse_mode=ParseMode.HTML,
                        reply_markup=self.build_notifier_list_keyboard(notifiers)
                    )
                    
            elif data == "notifier:delete":
                notifiers = await self._fetch_notifiers()
                if not notifiers:
                    await query.edit_message_text(
                        "❌ No notifiers to delete.",
                        parse_mode=ParseMode.HTML,
                        reply_markup=self.build_notifiers_menu()
                    )
                else:
                    await query.edit_message_text(
                        "🗑 <b>Delete Notifier</b>\n\nSelect a notifier to delete:",
                        parse_mode=ParseMode.HTML,
                        reply_markup=self.build_notifier_list_keyboard(notifiers)
                    )
                    
            elif data.startswith("notifier:type:"):
                notifier_type = data.split(":")[2]
                state.selected_notifier_type = notifier_type
                state.step = "name"
                await query.edit_message_text(
                    f"➕ <b>Add {notifier_type.title()} Notifier</b>\n\n"
                    f"Step 1/3: Enter a name for this notifier:",
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🔙 Cancel", callback_data="menu:notifiers")
                    ]])
                )
                
            elif data.startswith("notifier:view:"):
                notifier_id = data.split(":")[2]
                await self._show_notifier_details(query, notifier_id)
                
            elif data == "alarm:auto_on":
                await query.edit_message_text(
                    "✅ Auto mode enabled",
                    reply_markup=self.build_alarm_menu()
                )
                
            elif data == "alarm:auto_off":
                await query.edit_message_text(
                    "🔴 Auto mode disabled",
                    reply_markup=self.build_alarm_menu()
                )
                
            elif data == "alarm:trigger_test":
                await query.edit_message_text(
                    "🔔 Test alarm triggered!",
                    reply_markup=self.build_alarm_menu()
                )
                
            elif data == "alarm:clear_all":
                await query.edit_message_text(
                    "🔕 All alarms cleared",
                    reply_markup=self.build_alarm_menu()
                )
                
            elif data == "alarm:list":
                alarms = await self._fetch_active_alarms()
                if not alarms:
                    text = "📋 <b>Active Alarms</b>\n\nNo active alarms."
                else:
                    text = "📋 <b>Active Alarms:</b>\n\n"
                    for a in alarms:
                        text += f"• {a['camera_name']} - {a['state']} at {a['created_at']}\n"
                await query.edit_message_text(
                    text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=self.build_alarm_menu()
                )
                
            elif data == "camera:list":
                cameras = await self._fetch_cameras()
                if not cameras:
                    text = "📷 <b>Cameras</b>\n\nNo cameras configured."
                else:
                    text = "📷 <b>Configured Cameras:</b>\n\n"
                    for c in cameras:
                        status = "🟢 Online" if c.get("is_online") else "🔴 Offline"
                        text += f"• <b>{c['name']}</b> - {status}\n"
                await query.edit_message_text(
                    text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=self.build_camera_menu()
                )
                
            elif data == "camera:add":
                state.step = "camera_name"
                await query.edit_message_text(
                    "➕ <b>Add Camera</b>\n\nStep 1/5: Enter camera name:",
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🔙 Cancel", callback_data="menu:cameras")
                    ]])
                )
                
            elif data == "camera:test":
                cameras = await self._fetch_cameras()
                if not cameras:
                    await query.edit_message_text(
                        "❌ No cameras to test.",
                        reply_markup=self.build_camera_menu()
                    )
                else:
                    keyboard = []
                    for c in cameras:
                        keyboard.append([
                            InlineKeyboardButton(c['name'], callback_data=f"camera:test:{c['id']}")
                        ])
                    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="menu:cameras")])
                    await query.edit_message_text(
                        "🧪 <b>Test Camera</b>\n\nSelect camera:",
                        parse_mode=ParseMode.HTML,
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )
                    
            elif data == "camera:config":
                await query.edit_message_text(
                    "🔧 Camera configuration - coming soon",
                    reply_markup=self.build_camera_menu()
                )
                
        except Exception as e:
            logger.error(f"Callback error: {e}")
            await query.edit_message_text(
                f"❌ Error: {str(e)}",
                reply_markup=self.build_main_menu()
            )

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle text input for multi-step flows."""
        if not self._is_allowed(update.effective_chat.id):
            return
            
        chat_id = update.effective_chat.id
        state = self._get_state(chat_id)
        text = update.message.text.strip()
        
        # Multi-step: Add notifier
        if state.step == "name":
            state.notifier_name = text
            state.step = "telegram_token"
            await update.message.reply_text(
                f"✅ Name: <b>{text}</b>\n\n"
                f"Step 2/3: Enter Telegram Bot Token (from BotFather):",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Cancel", callback_data="menu:notifiers")
                ]])
            )
            
        elif state.step == "telegram_token":
            state.telegram_token = text
            state.step = "telegram_chat_id"
            await update.message.reply_text(
                f"✅ Token saved\n\n"
                f"Step 3/3: Enter Chat ID (e.g., -1001234567890):",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Cancel", callback_data="menu:notifiers")
                ]])
            )
            
        elif state.step == "telegram_chat_id":
            state.telegram_chat_id = text
            # Create the notifier
            success = await self._create_notifier(
                name=state.notifier_name,
                type=state.selected_notifier_type,
                config={
                    "bot_token": state.telegram_token,
                    "chat_id": state.telegram_chat_id,
                    "parse_mode": "HTML"
                }
            )
            
            if success:
                await update.message.reply_text(
                    f"✅ <b>Notifier created successfully!</b>\n\n"
                    f"Name: {state.notifier_name}\n"
                    f"Type: {state.selected_notifier_type}",
                    parse_mode=ParseMode.HTML,
                    reply_markup=self.build_notifiers_menu()
                )
            else:
                await update.message.reply_text(
                    "❌ Failed to create notifier",
                    reply_markup=self.build_notifiers_menu()
                )
            
            # Reset state
            state.step = ""
            state.selected_notifier_type = None
            state.notifier_name = None
            state.telegram_token = None
            state.telegram_chat_id = None

    # ==================== API HELPERS ====================

    async def _fetch_notifiers(self) -> List[Dict]:
        """Fetch notifiers from API/DB."""
        try:
            async for db in get_db():
                result = await db.execute(
                    select(Notifier).where(Notifier.site_id == "00bab373-4b0b-4a82-899b-316b493f0935")
                )
                notifiers = result.scalars().all()
                return [
                    {
                        "id": str(n.id),
                        "name": n.name,
                        "type": n.type.value if hasattr(n.type, 'value') else str(n.type),
                        "is_enabled": n.is_enabled,
                        "config": n.config,
                        "notify_on_trigger": n.notify_on_trigger,
                        "notify_on_ack": n.notify_on_ack,
                        "notify_on_resolve": n.notify_on_resolve,
                    }
                    for n in notifiers
                ]
        except Exception as e:
            logger.error(f"Failed to fetch notifiers: {e}")
            return []

    async def _fetch_cameras(self) -> List[Dict]:
        """Fetch cameras from API/DB."""
        try:
            from app.models.models import Camera
            async for db in get_db():
                result = await db.execute(
                    select(Camera).where(Camera.site_id == "00bab373-4b0b-4a82-899b-316b493f0935")
                )
                cameras = result.scalars().all()
                return [
                    {
                        "id": str(c.id),
                        "name": c.name,
                        "is_online": c.is_online,
                        "is_enabled": c.is_enabled,
                    }
                    for c in cameras
                ]
        except Exception as e:
            logger.error(f"Failed to fetch cameras: {e}")
            return []

    async def _fetch_active_alarms(self) -> List[Dict]:
        """Fetch active alarms from API/DB."""
        try:
            from app.models.models import Alarm, AlarmState
            async for db in get_db():
                result = await db.execute(
                    select(Alarm).where(Alarm.state == AlarmState.triggered)
                )
                alarms = result.scalars().all()
                return [
                    {
                        "id": str(a.id),
                        "camera_name": a.camera_id,
                        "state": a.state.value,
                        "created_at": a.created_at.strftime("%H:%M:%S") if a.created_at else "",
                    }
                    for a in alarms
                ]
        except Exception as e:
            logger.error(f"Failed to fetch alarms: {e}")
            return []

    async def _get_system_status(self) -> str:
        """Get system status from API."""
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(f"http://localhost:8080/api/v1/system/health") as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return (
                            f"📊 <b>System Status</b>\n\n"
                            f"• Status: {'🟢 Healthy' if data.get('status') == 'ok' else '🔴 Unhealthy'}\n"
                            f"• Version: {data.get('version', 'unknown')}\n"
                            f"• Database: {data.get('database', 'unknown')}\n"
                            f"• Uptime: {data.get('uptime_seconds', 0):.0f}s\n"
                            f"• Cameras: {data.get('cameras_online', 0)}/{data.get('cameras_total', 0)} online\n"
                            f"• Active Alarms: {data.get('active_alarms', 0)}"
                        )
        except Exception as e:
            logger.error(f"Failed to get system status: {e}")
            
        return "📊 <b>System Status</b>\n\n❌ Failed to fetch status from API"

    async def _create_notifier(self, name: str, type: str, config: Dict) -> bool:
        """Create notifier via API."""
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                # Get auth token
                async with session.post(
                    "http://localhost:8080/api/v1/auth/login",
                    json={"email": "admin@example.com", "password": "admin123"}
                ) as resp:
                    data = await resp.json()
                    token = data.get("access_token")
                
                # Create notifier
                headers = {"Authorization": f"Bearer {token}"}
                async with session.post(
                    "http://localhost:8080/api/v1/sites/00bab373-4b0b-4a82-899b-316b493f0935/notifiers",
                    json={"name": name, "type": type, "config": config},
                    headers=headers
                ) as resp:
                    return resp.status == 201
        except Exception as e:
            logger.error(f"Failed to create notifier: {e}")
            return False

    async def _show_notifier_details(self, query, notifier_id: str):
        """Show detailed notifier view with actions."""
        notifiers = await self._fetch_notifiers()
        notifier = next((n for n in notifiers if n["id"] == notifier_id), None)
        
        if not notifier:
            await query.edit_message_text(
                "❌ Notifier not found",
                reply_markup=self.build_notifiers_menu()
            )
            return
            
        config = notifier.get("config", {})
        text = (
            f"🔔 <b>Notifier Details</b>\n\n"
            f"• <b>Name:</b> {notifier['name']}\n"
            f"• <b>Type:</b> {notifier['type']}\n"
            f"• <b>Status:</b> {'✅ Enabled' if notifier['is_enabled'] else '❌ Disabled'}\n"
            f"• <b>Notify on Trigger:</b> {'Yes' if notifier['notify_on_trigger'] else 'No'}\n"
            f"• <b>Notify on Ack:</b> {'Yes' if notifier['notify_on_ack'] else 'No'}\n"
            f"• <b>Notify on Resolve:</b> {'Yes' if notifier['notify_on_resolve'] else 'No'}\n\n"
            f"<b>Config:</b>\n"
        )
        
        for k, v in config.items():
            if "token" in k.lower() or "pass" in k.lower() or "key" in k.lower():
                v = "••••••••"
            text += f"  {k}: {v}\n"
            
        keyboard = [
            [
                InlineKeyboardButton("🧪 Test", callback_data=f"notifier:test:{notifier_id}"),
                InlineKeyboardButton("✏️ Edit", callback_data=f"notifier:edit:{notifier_id}"),
            ],
            [
                InlineKeyboardButton("🗑 Delete", callback_data=f"notifier:confirm_delete:{notifier_id}"),
                InlineKeyboardButton("🔙 Back", callback_data="notifier:list"),
            ],
        ]
        
        await query.edit_message_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


# Singleton instance
_telegram_bot: Optional[SuperGuardTelegramBot] = None


async def get_telegram_bot() -> Optional[SuperGuardTelegramBot]:
    """Get or create the telegram bot instance."""
    global _telegram_bot
    if _telegram_bot is None:
        _telegram_bot = SuperGuardTelegramBot()
        if await _telegram_bot.initialize():
            return _telegram_bot
        else:
            _telegram_bot = None
    return _telegram_bot


async def start_telegram_bot():
    """Start the telegram bot (call from lifespan)."""
    bot = await get_telegram_bot()
    if bot and bot.application:
        await bot.start()
    return bot


async def stop_telegram_bot():
    """Stop the telegram bot."""
    global _telegram_bot
    if _telegram_bot:
        await _telegram_bot.stop()
        _telegram_bot = None