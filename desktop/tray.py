#!/usr/bin/env python3
"""
SuperGuard Desktop - system tray icon (pystray).

Menu: Show / Settings / Test alarm / Status / Exit.
Runs in a background thread; communicates with the main UI via callbacks.
"""
import os
import threading
from typing import Callable, Optional

import pystray
from PIL import Image

ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")


class Tray:
    """System tray icon with menu actions."""

    def __init__(self, icon_path: str = None):
        self.icon_path = icon_path or os.path.join(ASSETS, "icon.png")
        self.on_show: Optional[Callable[[], None]] = None
        self.on_settings: Optional[Callable[[], None]] = None
        self.on_test_alarm: Optional[Callable[[], None]] = None
        self.on_exit: Optional[Callable[[], None]] = None
        self._icon: Optional[pystray.Icon] = None
        self._thread: Optional[threading.Thread] = None

    # -------------------------------------------------------------- control
    def start(self, title: str = "SuperGuard"):
        """Start tray icon in a background thread."""
        if self._icon is not None:
            return
        image = self._load_image()
        menu = pystray.Menu(
            pystray.MenuItem("👁 Показать", lambda: self._safe(self.on_show), default=True),
            pystray.MenuItem("⚙️ Настройки", lambda: self._safe(self.on_settings)),
            pystray.MenuItem("🚨 Тест-тревога", lambda: self._safe(self.on_test_alarm)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Выход", lambda: self._safe(self.on_exit)),
        )
        self._icon = pystray.Icon("superguard", image, title, menu)
        self._thread = threading.Thread(target=self._icon.run, daemon=True)
        self._thread.start()

    def stop(self):
        if self._icon is not None:
            try:
                self._icon.stop()
            except Exception:
                pass
            self._icon = None

    def notify(self, title: str, message: str):
        """Show a tray notification (best effort)."""
        if self._icon is not None:
            try:
                self._icon.notify(message, title)
            except Exception:
                pass

    # ---------------------------------------------------------------- utils
    def _load_image(self) -> Image.Image:
        path = self.icon_path
        if not os.path.exists(path):
            # fallback: generate a simple icon on the fly
            from icon import generate_icon
            return generate_icon(64)
        return Image.open(path)

    @staticmethod
    def _safe(cb: Optional[Callable[[], None]]):
        if cb:
            try:
                cb()
            except Exception as e:
                print(f"[tray] callback error: {e}")


if __name__ == "__main__":
    tray = Tray()
    tray.on_show = lambda: print("show")
    tray.on_settings = lambda: print("settings")
    tray.on_exit = lambda: (tray.stop(), print("exit"))
    print("Трей запущен. Ctrl+C в консоли = выход (сама иконка в трее)")
    tray.start()
    import time
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        tray.stop()
