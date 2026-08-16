"""
SuperGuard Core - Email Notifier Plugin

Email notifications via SMTP.
Supports: Gmail, Outlook, custom SMTP servers.
"""

import asyncio
import logging
from datetime import datetime
from typing import List

import aiosmtplib
from email.message import EmailMessage

from superguard_core.core.plugins import NotifierPlugin, NotificationPayload, PluginConfig


logger = logging.getLogger(__name__)


class EmailNotifierPlugin(NotifierPlugin):
    """Email notifier via SMTP."""

    name = "email"
    version = "1.0.0"
    plugin_type = "notifier"
    description = "Email notifications via SMTP"
    author = "SuperGuard Team"

    def __init__(self, config: PluginConfig, event_bus):
        super().__init__(config, event_bus)
        self._smtp_host: str = ""
        self._smtp_port: int = 587
        self._username: str = ""
        self._password: str = ""
        self._from_email: str = ""
        self._use_tls: bool = True

    async def initialize(self) -> None:
        self._smtp_host = self.config.get("smtp_host", "")
        self._smtp_port = self.config.get("smtp_port", 587)
        self._username = self.config.get("smtp_user", "")
        self._password = self.config.get("smtp_password", "")
        self._from_email = self.config.get("from_email", self._username)
        self._use_tls = self.config.get("use_tls", True)

        if not self._smtp_host:
            raise ValueError("Email notifier requires smtp_host")

        await self._set_status(self.PluginStatus.LOADED)
        self._initialized = True
        logger.info(f"Email notifier initialized: {self._smtp_host}:{self._smtp_port}")

    async def send(self, payload: NotificationPayload, targets: List[str]) -> bool:
        """Send email to targets (list of email addresses)."""
        if not targets:
            logger.warning("No email targets provided")
            return False

        try:
            message = EmailMessage()
            message["From"] = self._from_email
            message["To"] = ", ".join(targets)
            message["Subject"] = f"[SuperGuard] {payload.title}"

            body = f"""
SuperGuard Alarm Notification
=============================

{payload.message}

Priority: {payload.priority}
Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

---
SuperGuard Alarm System
"""
            if payload.media_urls:
                body += "\n\nMedia URLs:\n" + "\n".join(payload.media_urls)

            if payload.metadata:
                body += "\n\nMetadata:\n"
                for k, v in payload.metadata.items():
                    body += f"  {k}: {v}\n"

            message.set_content(body)

            await aiosmtplib.send(
                message,
                hostname=self._smtp_host,
                port=self._smtp_port,
                username=self._username,
                password=self._password,
                use_tls=self._use_tls,
            )

            logger.info(f"Email sent to {len(targets)} recipients: {payload.title}")
            return True

        except Exception as e:
            logger.error(f"Email send failed: {e}")
            return False

    async def test(self, target: str) -> bool:
        """Send test email."""
        test_payload = NotificationPayload(
            title="SuperGuard Test Notification",
            message="This is a test notification from SuperGuard.",
            priority="normal",
        )
        return await self.send(test_payload, [target])

    @property
    def supported_targets(self) -> List[str]:
        return ["email"]

    async def shutdown(self) -> None:
        await self._set_status(self.PluginStatus.UNLOADED)