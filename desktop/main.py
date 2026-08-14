#!/usr/bin/env python3
"""
SuperGuard Desktop - autonomous launcher & monitor.

Startup sequence:
  1. Self-heal: check Python/pip/packages/model/config/PATH, repair what's broken
  2. If config is broken (no token) -> open configuration window
  3. Launch SuperGuard service (subprocess, project venv python)
  4. Run in tray; on alarm -> fullscreen alarm window with live frame
  5. Cancel alarm via Telegram bot API (/togglealarm message)

Build: pyinstaller --onefile --windowed --icon=assets/icon.ico main.py
"""
import os
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox

# allow running from any cwd
BASE = os.path.dirname(os.path.abspath(__file__))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

from self_heal import SelfHeal  # noqa: E402
from monitor import Monitor  # noqa: E402
from tray import Tray  # noqa: E402
from alarm_window import AlarmWindow  # noqa: E402
import config_ui  # noqa: E402
import requests  # noqa: E402

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


class DesktopApp:
    def __init__(self, project_dir: str):
        self.project_dir = os.path.abspath(project_dir)
        self.state_dir = os.path.join(self.project_dir, "desktop_state")
        os.makedirs(self.state_dir, exist_ok=True)

        self.heal = SelfHeal(self.project_dir)
        self.report = None
        self.sg_process: subprocess.Popen = None
        self.monitor: Monitor = None
        self.tray = Tray()
        self.alarm_win: AlarmWindow = None

        self.root = tk.Tk()
        self.root.title("SuperGuard Desktop")
        self.root.geometry("640x420")
        self.root.minsize(560, 360)
        try:
            from PIL import Image, ImageTk
            img = Image.open(os.path.join(BASE, "assets", "icon.png")).resize((64, 64), Image.LANCZOS)
            self.root.iconphoto(True, ImageTk.PhotoImage(img))
        except Exception:
            pass

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._hide_to_tray)

        self._wire_tray()
        self.monitor = Monitor(self.state_dir, interval=1.0)
        self.monitor.on_alarm_on = self._on_alarm_on
        self.monitor.on_alarm_off = self._on_alarm_off
        self.monitor.on_frame = self._on_frame

        self.alarm_win = AlarmWindow(self.root, self.state_dir,
                                     on_cancel=self.cancel_alarm_via_bot)

    # ---------------------------------------------------------------- UI
    def _build_ui(self):
        pad = dict(padx=10, pady=4)
        top = ttk.Frame(self.root)
        top.pack(fill="x", padx=8, pady=6)

        ttk.Label(top, text=f"SuperGuard Desktop — {self.project_dir}",
                  font=("Segoe UI", 12, "bold")).pack(side="left")

        self.lbl_svc = ttk.Label(top, text="● сервис не запущен", foreground="gray")
        self.lbl_svc.pack(side="right")

        # self-heal report area
        box = ttk.LabelFrame(self.root, text="🩺 Проверка окружения")
        box.pack(fill="both", expand=True, padx=8, pady=4)
        self.txt_report = tk.Text(box, height=10, font=("Consolas", 10), state="disabled")
        self.txt_report.pack(fill="both", expand=True, padx=6, pady=6)

        btns = ttk.Frame(self.root)
        btns.pack(fill="x", padx=8, pady=6)
        self.btn_start = ttk.Button(btns, text="▶️ Запустить сервис", command=self.start_service)
        self.btn_start.pack(side="left", padx=4)
        self.btn_stop = ttk.Button(btns, text="⏹ Остановить", command=self.stop_service, state="disabled")
        self.btn_stop.pack(side="left", padx=4)
        ttk.Button(btns, text="⚙️ Настройки", command=self.open_settings).pack(side="left", padx=4)
        ttk.Button(btns, text="🩺 Проверить ещё раз", command=self._rerun_heal).pack(side="left", padx=4)

        self.var_autostart = tk.BooleanVar(value=self._autostart_enabled())
        ttk.Checkbutton(btns, text="Автозапуск при входе",
                        variable=self.var_autostart, command=self._toggle_autostart).pack(side="left", padx=8)

        self.lbl_status = ttk.Label(self.root, text="Готов", foreground="gray")
        self.lbl_status.pack(fill="x", padx=8, pady=(0, 6))

        # initial heal
        self._rerun_heal()

    def _log(self, text: str):
        self.txt_report.config(state="normal")
        self.txt_report.insert("end", text + "\n")
        self.txt_report.see("end")
        self.txt_report.config(state="disabled")

    # ---------------------------------------------------------- self-heal
    def _rerun_heal(self):
        self._log("→ Проверка окружения…")
        self.report = self.heal.check_all()
        self._render_report()
        if not self.report.all_ok and self.report.repairable:
            self._log("→ Обнаружены проблемы. Ремонт…")
            self.heal.repair(self.report)
            self.report = self.heal.check_all()
            self._render_report()

    def _render_report(self):
        for r in self.report.results:
            icon = "✅" if r.ok else ("🔧" if r.fixable else "❌")
            self._log(f"{icon} {r.name}: {r.message}")
        if self.report.all_ok:
            self._log("✅ ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ\n")
            self.lbl_status.config(text="Окружение в порядке — можно запускать", foreground="green")
        else:
            self._log("⚠️ Есть проблемы (🔧 — ремонтируемо)\n")
            self.lbl_status.config(text="Требуется настройка/ремонт", foreground="orange")

    # ------------------------------------------------------------ service
    def start_service(self):
        if self.sg_process and self.sg_process.poll() is None:
            return
        if not self.report or not self.report.all_ok:
            if not messagebox.askyesno("Внимание",
                                       "Есть непройденные проверки. Всё равно запустить?"):
                return
        main_py = os.path.join(self.project_dir, "superguard", "main.py")
        if not os.path.exists(main_py):
            messagebox.showerror("Ошибка", f"Не найден: {main_py}")
            return
        python = self.heal.python_exe
        self._log(f"→ Запуск SuperGuard: {python} {main_py}")
        try:
            self.sg_process = subprocess.Popen(
                [python, main_py],
                cwd=self.project_dir,
                creationflags=CREATE_NO_WINDOW,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except Exception as e:
            messagebox.showerror("Ошибка запуска", str(e))
            return
        self.btn_start.config(state="disabled")
        self.btn_stop.config(state="normal")
        self.lbl_svc.config(text="● сервис работает", foreground="green")
        self.monitor.start()
        threading.Thread(target=self._watch_process, daemon=True).start()

    def stop_service(self):
        if self.sg_process and self.sg_process.poll() is None:
            self.sg_process.terminate()
            try:
                self.sg_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.sg_process.kill()
        self.sg_process = None
        self.monitor.stop()
        self.btn_start.config(state="normal")
        self.btn_stop.config(state="disabled")
        self.lbl_svc.config(text="● сервис остановлен", foreground="gray")
        self._log("⏹ Сервис остановлен")

    def _watch_process(self):
        while self.sg_process and self.sg_process.poll() is None:
            import time
            time.sleep(2)
        if self.sg_process:
            self.root.after(0, self._service_exited)

    def _service_exited(self):
        self.sg_process = None
        self.monitor.stop()
        self.btn_start.config(state="normal")
        self.btn_stop.config(state="disabled")
        self.lbl_svc.config(text="● сервис завершился", foreground="red")
        self._log("⚠️ Сервис SuperGuard завершился")

    # ----------------------------------------------------------- monitoring
    def _on_alarm_on(self, state):
        self.root.after(0, lambda: self.alarm_win.show_alarm(state))
        self.tray.notify("🚨 ТРЕВОГА", f"Камера {state.alarm_camera_name}")

    def _on_alarm_off(self, state):
        self.root.after(0, self.alarm_win.hide_to_tray)
        self.tray.notify("✅ Тревога снята", "Цель устранена / отключено")

    def _on_frame(self):
        self.root.after(0, self.alarm_win.refresh_frame)

    def cancel_alarm_via_bot(self):
        """Send /togglealarm to the bot via Telegram API (desktop-initiated cancel)."""
        env = config_ui.read_env(os.path.join(self.project_dir, "sguard.env"))
        token = env.get("SG_TELEGRAM_BOT_TOKEN", "")
        chat = env.get("SG_CHAT_ID", "")
        if not token or "***" in token or not chat:
            print("[cancel] токен/chat не настроены")
            return
        try:
            requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                          json={"chat_id": int(chat), "text": "/togglealarm"},
                          timeout=10)
        except Exception as e:
            print(f"[cancel] error: {e}")

    # --------------------------------------------------------------- misc
    def open_settings(self):
        config_ui.open_config(self.root, self.project_dir,
                              on_saved=lambda p: self._log(f"✅ Конфиг сохранён: {p}"))

    def _hide_to_tray(self):
        self.root.withdraw()

    def show_main(self):
        self.root.deiconify()
        self.root.lift()

    def _wire_tray(self):
        self.tray.on_show = self.show_main
        self.tray.on_settings = self.open_settings
        self.tray.on_test_alarm = self._test_alarm
        self.tray.on_exit = self._exit

    def _test_alarm(self):
        """Simulate alarm for admin testing (fullscreen window)."""
        from bridge import SGState
        st = SGState(alarm_active=True, alarm_camera=2, zone="N3x4 C9",
                     target="red car", plugs=["plug1"], auto_mode=True,
                     camera_names={2: "Тест"})
        self.root.after(0, lambda: self.alarm_win.show_alarm(st))

    def _autostart_enabled(self) -> bool:
        try:
            r = subprocess.run(["schtasks", "/Query", "/TN", "SuperGuardDesktop"],
                               capture_output=True, timeout=10)
            return r.returncode == 0
        except Exception:
            return False

    def _toggle_autostart(self):
        if self.var_autostart.get():
            exe = sys.executable
            args = f'"{exe}"'
            if "python" in os.path.basename(exe).lower():
                args += f' "{os.path.join(BASE, "main.py")}"'
            try:
                subprocess.run(["schtasks", "/Create", "/TN", "SuperGuardDesktop",
                                "/TR", args, "/SC", "ONLOGON", "/RL", "HIGHEST",
                                "/F"], capture_output=True, timeout=15)
                self._log("✅ Автозапуск включён (при входе в Windows)")
            except Exception as e:
                messagebox.showerror("Автозапуск", str(e))
        else:
            try:
                subprocess.run(["schtasks", "/Delete", "/TN", "SuperGuardDesktop",
                                "/F"], capture_output=True, timeout=15)
                self._log("Автозапуск выключен")
            except Exception as e:
                messagebox.showerror("Автозапуск", str(e))

    def _exit(self):
        self.stop_service()
        self.tray.stop()
        self.root.after(100, self.root.destroy)

    def run(self):
        self.tray.start()
        self.root.mainloop()


def main():
    project = sys.argv[1] if len(sys.argv) > 1 else r"C:\SuperGuard"
    DesktopApp(project).run()


if __name__ == "__main__":
    main()
