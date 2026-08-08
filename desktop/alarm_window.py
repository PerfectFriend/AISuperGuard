#!/usr/bin/env python3
"""
SuperGuard Desktop - fullscreen alarm window (tkinter).

On alarm: shows a fullscreen red-bordered window with the live camera
frame, alarm info (camera / zone / target / plugs) and actions:
  - "Снять тревогу" -> on_cancel callback (sends /togglealarm via bot API)
  - Esc / "Свернуть" -> hide back to tray
The frame is refreshed on each new alarm_live.jpg.
"""
import os
import threading
import time
import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional

from bridge import Bridge, SGState


class AlarmWindow(tk.Toplevel):
    """Fullscreen alarm presentation window."""

    def __init__(self, master, state_dir: str, on_cancel: Optional[Callable[[], None]] = None,
                 on_close: Optional[Callable[[], None]] = None):
        super().__init__(master)
        self.state_dir = state_dir
        self.bridge = Bridge(state_dir)
        self.on_cancel = on_cancel
        self.on_close = on_close

        self.title("🚨 ТРЕВОГА")
        self.configure(bg="#1a0000")
        self.attributes("-fullscreen", True)
        self.attributes("-topmost", True)

        self._pulse = False
        self._last_frame_path = ""

        self._build()
        self.protocol("WM_DELETE_WINDOW", self.hide_to_tray)
        self.bind("<Escape>", lambda e: self.hide_to_tray())

        self.withdraw()  # hidden until alarm

    # ------------------------------------------------------------- widgets
    def _build(self):
        self.top = tk.Frame(self, bg="#2a0000")
        self.top.pack(fill="both", expand=True)

        self.lbl_title = tk.Label(self.top, text="🚨 ТРЕВОГА 🚨",
                                  font=("Segoe UI", 40, "bold"),
                                  fg="#ff2b2b", bg="#2a0000")
        self.lbl_title.pack(pady=(18, 4))

        self.lbl_info = tk.Label(self.top, text="",
                                 font=("Segoe UI", 13),
                                 fg="#ffeaea", bg="#2a0000", justify="left")
        self.lbl_info.pack(pady=4)

        # live frame
        self.lbl_frame = tk.Label(self.top, bg="#2a0000")
        self.lbl_frame.pack(pady=8)

        btns = tk.Frame(self.top, bg="#2a0000")
        btns.pack(pady=10)
        ttk.Button(btns, text="⛔ Снять тревогу", command=self._cancel,
                   style="Accent.TButton").pack(side="left", padx=8)
        ttk.Button(btns, text="Свернуть в трей", command=self.hide_to_tray).pack(side="left", padx=8)

        self.lbl_time = tk.Label(self.top, text="", font=("Segoe UI", 10),
                                 fg="#aaa", bg="#2a0000")
        self.lbl_time.pack(side="bottom", pady=6)

    # -------------------------------------------------------------- actions
    def show_alarm(self, state: SGState):
        """Display the alarm with the given state (idempotent)."""
        self._update_info(state)
        self._refresh_frame()
        self.deiconify()
        self.lift()
        self.attributes("-topmost", True)
        self._pulse_loop()

    def _update_info(self, state: SGState):
        lines = [
            f"📷 Камера:  {state.alarm_camera_name} (id {state.alarm_camera})",
            f"📍 Зона:    {state.zone or 'весь кадр'}",
            f"🎯 Цель:    {state.target or 'жёлтый транспорт'}",
            f"🔌 Розетки: {', '.join(state.plugs) if state.plugs else '—'}",
            f"⚙️ Режим:   {'АВТО' if state.auto_mode else 'РУЧНОЙ'}",
        ]
        self.lbl_info.config(text="\n".join(lines))

    def refresh_frame(self):
        """Called by monitor when a new alarm frame arrives."""
        if self.winfo_viewable():
            self._refresh_frame()

    def _refresh_frame(self):
        data = self.bridge.read_alarm_frame()
        if not data:
            return
        path = os.path.join(self.state_dir, "alarm_live.jpg")
        if path == self._last_frame_path and not self.bridge.has_new_frame():
            pass
        self._last_frame_path = path
        try:
            import io
            from PIL import Image, ImageTk
            img = Image.open(io.BytesIO(data))
            # fit to screen while keeping aspect
            sw = self.winfo_screenwidth()
            sh = self.winfo_screenheight()
            img.thumbnail((int(sw * 0.7), int(sh * 0.45)), Image.LANCZOS)
            self._tk_img = ImageTk.PhotoImage(img)
            self.lbl_frame.config(image=self._tk_img)
        except Exception as e:
            print(f"[alarm] frame render error: {e}")

    def _cancel(self):
        if self.on_cancel:
            threading.Thread(target=self.on_cancel, daemon=True).start()
        self.hide_to_tray()

    def hide_to_tray(self):
        self.withdraw()
        self._pulse = False

    def _pulse_loop(self):
        """Red border pulse while alarm is visible."""
        if not self.winfo_viewable():
            return
        self._pulse = not self._pulse
        bg = "#3d0000" if self._pulse else "#2a0000"
        self.top.config(bg=bg)
        self.lbl_title.config(bg=bg)
        self.lbl_info.config(bg=bg)
        self.lbl_frame.config(bg=bg)
        self.lbl_time.config(text=time.strftime("%H:%M:%S"))
        self.after(500, self._pulse_loop)


if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()
    win = AlarmWindow(root, r"C:\SuperGuard\desktop_state")
    st = SGState(alarm_active=True, alarm_camera=2, zone="N3x4 C9",
                 target="red car", plugs=["plug1"], auto_mode=True,
                 camera_names={2: "Revotech"})
    win.show_alarm(st)
    root.mainloop()
