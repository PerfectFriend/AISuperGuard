"""
SuperGuard Core - Уведомители Plugins Package
"""

from superguard_core.plugins.notifiers.telegram import TelegramNotifierPlugin
from superguard_core.plugins.notifiers.webhook import WebhookNotifierPlugin

# Реестр плагинов
NOTIFIER_PLUGINS = {
    "telegram": TelegramNotifierPlugin,
    "webhook": WebhookNotifierPlugin,
}

__all__ = [
    "TelegramNotifierPlugin",
    "WebhookNotifierPlugin",
    "NOTIFIER_PLUGINS",
]