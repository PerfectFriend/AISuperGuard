#!/usr/bin/env python3
"""
SuperGuard Monitor - System Tray Application
Автозагружаемый GUI монитор для SuperGuard системы.
- Появляется в трее с иконкой "глаз"
- Меню: Start/Stop SuperGuard, Settings, Open Dashboard, Test Alarm, Exit
- Автозапуск SuperGuard после ребута (настраивается в конфиге)
- Напоминание если SuperGuard не запущен
"""

import os
import sys
import json
import time
import threading
import subprocess
import signal
import logging
from pathlib import Path
from typing import Optional, Callable, Dict, Any
from dataclasses import dataclass, asdict
from pathlib import Path

# GUI imports
try:
    import pystray
    from PIL import Image, ImageDraw
except ImportError:
    print("Installing required packages...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pystray", "pillow"])
    import pystray
    from PIL import Image, ImageDraw

# ─── Константы и пути ──────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
CONFIG_DIR = Path.home() / ".config" / "superguard-monitor"
CONFIG_FILE = CONFIG_DIR / "config.json"
LOG_FILE = CONFIG_DIR / "monitor.log"
PID_FILE = CONFIG_DIR / "superguard.pid"

# Пути к SuperGuard
SUPERGUARD_ROOT = BASE_DIR
API_DIR = SUPERGUARD_ROOT / "superguard-api"
DASHBOARD_DIR = SUPERGUARD_ROOT / "web-dashboard"
BOT_DIR = SUPERGUARD_ROOT / "superguard"

# Debug: print paths on startup
print(f"[DEBUG] BASE_DIR: {BASE_DIR}")
print(f"[DEBUG] SUPERGUARD_ROOT: {SUPERGUARD_ROOT}")
print(f"[DEBUG] API_DIR: {API_DIR} (exists: {API_DIR.exists()})")
print(f"[DEBUG] DASHBOARD_DIR: {DASHBOARD_DIR} (exists: {DASHBOARD_DIR.exists()})")
print(f"[DEBUG] BOT_DIR: {BOT_DIR} (exists: {BOT_DIR.exists()})")

# ─── Конфигурация по умолчанию ─────────────────────────────────
DEFAULT_CONFIG = {
    "auto_start": True,           # Автозапуск SuperGuard при старте монитора
    "check_interval": 30,         # Интервал проверки статуса (секунды)
    "notify_on_down": True,       # Уведомления когда SuperGuard упал
    "api_port": 8080,
    "dashboard_port": 5173,
    "dashboard_url": "http://localhost:5173",
    "api_url": "http://localhost:8080",
    "bot_module": "superguard.main",
    "api_cmd": ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"],
    "dashboard_cmd": ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"],
    "bot_cmd": ["python", "-m", "superguard.main"],
    "working_dir": str(SUPERGUARD_ROOT),
    "api_working_dir": str(API_DIR),
    "dashboard_working_dir": str(DASHBOARD_DIR),
    "bot_working_dir": str(BOT_DIR),
    "bot_env_pythonpath": str(SUPERGUARD_ROOT),
}

# ─── Логирование ───────────────────────────────────────────────
def setup_logging():
    """Настройка логирования с UTF-8."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    
    # Удаляем старые хендлеры
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)
    
    # Форматтер
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    # File handler с UTF-8
    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.DEBUG)
    
    # Console handler с UTF-8
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)
    
    # Root logger
    logging.root.setLevel(logging.DEBUG)
    logging.root.addHandler(file_handler)
    logging.root.addHandler(console_handler)
    
    # Отключаем propagation для сторонних логгеров
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("pystray").setLevel(logging.WARNING)
    
    return logging.getLogger("SuperGuardMonitor")

logger = setup_logging()

# ─── Утилиты ───────────────────────────────────────────────────
def load_config() -> Dict[str, Any]:
    """Загружает конфиг, создаёт дефолтный если нет."""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return {**DEFAULT_CONFIG, **json.load(f)}
        except Exception as e:
            logger.warning(f"Failed to load config: {e}, using defaults")
    return DEFAULT_CONFIG.copy()

def save_config(config: Dict[str, Any]):
    """Сохраняет конфиг."""
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Failed to save config: {e}")

def is_process_running(pid: int) -> bool:
    """Проверяет, жив ли процесс с данным PID."""
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False

def get_superguard_pids() -> Dict[str, int]:
    """Находит PID запущенных процессов SuperGuard."""
    pids = {}
    try:
        # Ищем процессы по командной строке
        result = subprocess.run(
            ["pgrep", "-f", "superguard"],
            capture_output=True, text=True
        )
        for line in result.stdout.strip().split("\n"):
            if line.strip():
                pid = int(line)
                try:
                    cmd = subprocess.run(
                        ["ps", "-p", str(pid), "-o", "cmd="],
                        capture_output=True, text=True
                    ).stdout.lower()
                    # Проверяем в порядке специфичности
                    if "superguard.main" in cmd:
                        pids["bot"] = pid
                    elif "vite" in cmd or "npm" in cmd:
                        pids["dashboard"] = pid
                    elif "uvicorn" in cmd and "app.main:app" in cmd:
                        pids["api"] = pid
                except:
                    pass
    except Exception as e:
        logger.debug(f"Error finding pids: {e}")
    return pids

# ─── Генерация иконки (глаз с молнией) ─────────────────────────
from PIL import Image, ImageDraw, ImageFilter
def generate_monitor_icon(size: int = 64) -> Image.Image:
    """Генерирует иконку монитора (глаз с молнией) в памяти."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx = cy = size / 2
    s = size / 64.0

    # Цвета (темная тема)
    BG_DARK = (10, 20, 45, 255)
    BG_DARKER = (5, 10, 25, 255)
    EYE_WHITE = (235, 242, 255, 255)
    EYE_LINE = (15, 25, 55, 255)
    PUPIL = (12, 16, 38, 255)
    BOLT = (255, 213, 0, 255)
    BOLT_GLOW = (255, 236, 120, 255)
    HIGHLIGHT = (255, 255, 255, 255)

    # Радиальный градиент фона
    for i in range(60, 0, -1):
        t = i / 60
        rad = size / 2 * (1.0 - (1.0 - t) * 0.12)
        col = tuple(int(BG_DARK[k] * t + BG_DARKER[k] * (1 - t)) for k in range(3)) + (255,)
        d.ellipse([cx - rad, cy - rad, cx + rad, cy + rad], fill=col)

    # Маска для скругления
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse([2, 2, size - 2, size - 2], fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(size / 64))
    img.putalpha(mask)

    # Глаз (линза)
    rx, ry = 95 * s, 50 * s
    almond = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ad = ImageDraw.Draw(almond)
    ad.ellipse([cx - rx, cy - ry, cx + rx * 0.55, cy + ry], fill=EYE_WHITE)
    ad.ellipse([cx - rx * 0.55, cy - ry, cx + rx, cy + ry], fill=EYE_WHITE)
    almond = almond.filter(ImageFilter.GaussianBlur(size / 96))
    img.alpha_composite(almond)

    # Контур века
    d.ellipse([cx - rx, cy - ry, cx + rx * 0.55, cy + ry], outline=EYE_LINE, width=max(2, int(6 * s)))
    d.ellipse([cx - rx * 0.55, cy - ry, cx + rx, cy + ry], outline=EYE_LINE, width=max(2, int(6 * s)))

    # Зрачок
    pr = 40 * s
    d.ellipse([cx - pr, cy - pr, cx + pr, cy + pr], fill=PUPIL, outline=EYE_LINE, width=max(1, int(3 * s)))

    # Молния
    def bolt_points(cx, cy, r):
        return [
            (cx + 0.28 * r, cy - 0.95 * r),
            (cx - 0.18 * r, cy + 0.10 * r),
            (cx - 0.05 * r, cy + 0.10 * r),
            (cx - 0.30 * r, cy + 0.95 * r),
            (cx + 0.26 * r, cy - 0.08 * r),
            (cx + 0.12 * r, cy - 0.08 * r),
            (cx + 0.42 * r, cy - 0.95 * r),
        ]
    d.polygon(bolt_points(cx, cy, pr * 0.95), fill=BOLT)
    d.polygon(bolt_points(cx, cy - pr * 0.06, pr * 0.55), fill=BOLT_GLOW)

    # Блик на глазу
    d.ellipse([cx - rx * 0.55, cy - ry * 0.45, cx - rx * 0.15, cy - ry * 0.05], fill=HIGHLIGHT)

    return img


def create_tray_icon_image() -> Image.Image:
    """Создает иконку для трея (64x64)."""
    return generate_monitor_icon(64)


# ─── SuperGuard Process Manager ────────────────────────────────
class SuperGuardManager:
    """Управляет запуском/остановкой компонентов SuperGuard."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.processes: Dict[str, subprocess.Popen] = {}
        self._lock = threading.Lock()

    def start_api(self) -> bool:
        """Запускает API сервер."""
        with self._lock:
            if "api" in self.processes and self.processes["api"].poll() is None:
                logger.info("API уже запущен")
                return True

            try:
                logger.info("Запуск API сервера...")
                proc = subprocess.Popen(
                    self.config["api_cmd"],
                    cwd=self.config.get("api_working_dir", self.config["working_dir"]),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    start_new_session=True,
                )
                self.processes["api"] = proc
                # Ждём готовность
                time.sleep(3)
                if self.check_health():
                    logger.info("API сервер запущен успешно")
                    return True
                else:
                    logger.error("API не ответил на health check")
                    return False
            except Exception as e:
                logger.error(f"Ошибка запуска API: {e}")
                return False

    def start_dashboard(self) -> bool:
        """Запускает дашборд (Vite dev server)."""
        with self._lock:
            if "dashboard" in self.processes and self.processes["dashboard"].poll() is None:
                logger.info("Dashboard уже запущен")
                return True

            try:
                logger.info("Запуск Dashboard...")
                proc = subprocess.Popen(
                    self.config["dashboard_cmd"],
                    cwd=self.config.get("dashboard_working_dir", str(DASHBOARD_DIR)),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    start_new_session=True,
                )
                self.processes["dashboard"] = proc
                logger.info("Dashboard запущен")
                return True
            except Exception as e:
                logger.error(f"Ошибка запуска Dashboard: {e}")
                return False

    def start_bot(self) -> bool:
        """Запускает SuperGuard бота."""
        with self._lock:
            if "bot" in self.processes and self.processes["bot"].poll() is None:
                logger.info("Бот уже запущен")
                return True

            try:
                logger.info("Запуск SuperGuard бота...")
                env = os.environ.copy()
                env["PYTHONPATH"] = self.config.get("bot_env_pythonpath", str(SUPERGUARD_ROOT))
                # Force CPU-only PyTorch for AMD 780M (ROCm not supported on consumer iGPU)
                env["CUDA_VISIBLE_DEVICES"] = ""
                env["ROC_VISIBLE_DEVICES"] = ""
                proc = subprocess.Popen(
                    self.config["bot_cmd"],
                    cwd=self.config.get("bot_working_dir", str(BOT_DIR)),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    start_new_session=True,
                    env=env,
                )
                self.processes["bot"] = proc
                # Wait a bit and check if it's still alive
                time.sleep(2)
                if proc.poll() is None:
                    logger.info("Бот запущен")
                    return True
                else:
                    # Process died, read stderr
                    stdout, stderr = proc.communicate(timeout=2)
                    logger.error(f"Бот завершился с кодом {proc.returncode}")
                    if stderr:
                        logger.error(f"Bot stderr: {stderr.decode('utf-8', errors='replace')[:500]}")
                    return False
            except Exception as e:
                logger.error(f"Ошибка запуска бота: {e}")
                return False

    def start_all(self) -> Dict[str, bool]:
        """Запускает все компоненты."""
        results = {}
        results["api"] = self.start_api()
        time.sleep(1)
        results["dashboard"] = self.start_dashboard()
        time.sleep(1)
        results["bot"] = self.start_bot()
        return results

    def stop_all(self):
        """Останавливает все процессы."""
        with self._lock:
            for name, proc in self.processes.items():
                if proc.poll() is None:
                    logger.info(f"Остановка {name} (PID: {proc.pid})...")
                    try:
                        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                        proc.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                    except Exception as e:
                        logger.warning(f"Ошибка остановки {name}: {e}")
                    logger.info(f"{name} остановлен")
            self.processes.clear()

    def check_health(self) -> bool:
        """Проверяет health API."""
        try:
            import urllib.request
            with urllib.request.urlopen(f"{self.config['api_url']}/health", timeout=5) as resp:
                return resp.status == 200
        except:
            return False

    def get_status(self) -> Dict[str, Any]:
        """Возвращает статус всех компонентов (менеджер + внешние процессы)."""
        # Статус от менеджера (процессы, запущенные нами)
        manager_status = {"api": False, "dashboard": False, "bot": False}
        with self._lock:
            for name, proc in self.processes.items():
                manager_status[name] = proc.poll() is None
            # Доп. проверка API
            if manager_status["api"]:
                manager_status["api"] = self.check_health()
        
        # Дополнительно проверяем через pgrep (на случай если процессы запущены извне)
        pids = get_superguard_pids()
        external_status = {
            "api": "api" in pids and is_process_running(pids["api"]),
            "dashboard": "dashboard" in pids and is_process_running(pids["dashboard"]),
            "bot": "bot" in pids and is_process_running(pids["bot"]),
        }
        
        # Объединяем: running если есть в менеджере ИЛИ найден через pgrep
        return {
            "api": manager_status.get("api", False) or external_status.get("api", False),
            "dashboard": manager_status.get("dashboard", False) or external_status.get("dashboard", False),
            "bot": manager_status.get("bot", False) or external_status.get("bot", False),
        }


# ─── Settings Window ───────────────────────────────────────────
class SettingsWindow:
    """Окно настроек (tkinter)."""

    def __init__(self, config: Dict[str, Any], on_save: Callable[[Dict], None]):
        self.config = config
        self.on_save = on_save
        self.window = None

    def show(self):
        import tkinter as tk
        from tkinter import ttk, messagebox

        if self.window and self.window.winfo_exists():
            self.window.lift()
            return

        self.window = tk.Toplevel()
        self.window.title("SuperGuard Monitor - Настройки")
        self.window.geometry("500x450")
        self.window.resizable(False, False)

        # Центрирование
        self.window.update_idletasks()
        x = (self.window.winfo_screenwidth() - 500) // 2
        y = (self.window.winfo_screenheight() - 450) // 2
        self.window.geometry(f"+{x}+{y}")

        # Переменные
        self.vars = {}
        for key, default in [
            ("auto_start", True),
            ("check_interval", 30),
            ("notify_on_down", True),
            ("api_port", 8080),
            ("dashboard_port", 5173),
        ]:
            self.vars[key] = tk.BooleanVar(value=self.config.get(key, default)) if isinstance(default, bool) else tk.IntVar(value=self.config.get(key, default))

        # UI
        main_frame = ttk.Frame(self.window, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(main_frame, text="⚙️ SuperGuard Monitor Settings", font=("Segoe UI", 14, "bold")).pack(pady=(0, 20))

        # Auto start
        ttk.Checkbutton(main_frame, text="Автозапуск SuperGuard при старте монитора",
                       variable=self.vars["auto_start"]).pack(anchor="w", pady=5)

        # Notify on down
        ttk.Checkbutton(main_frame, text="Уведомлять когда SuperGuard не запущен",
                       variable=self.vars["notify_on_down"]).pack(anchor="w", pady=5)

        # Check interval
        frame = ttk.Frame(main_frame)
        frame.pack(fill="x", pady=5)
        ttk.Label(frame, text="Интервал проверки (сек):").pack(side="left")
        ttk.Spinbox(frame, from_=10, to=300, textvariable=self.vars["check_interval"], width=10).pack(side="right")

        # API port
        frame = ttk.Frame(main_frame)
        frame.pack(fill="x", pady=5)
        ttk.Label(frame, text="API порт:").pack(side="left")
        ttk.Spinbox(frame, from_=1000, to=65535, textvariable=self.vars["api_port"], width=10).pack(side="right")

        # Dashboard port
        frame = ttk.Frame(main_frame)
        frame.pack(fill="x", pady=5)
        ttk.Label(frame, text="Dashboard порт:").pack(side="left")
        ttk.Spinbox(frame, from_=1000, to=65535, textvariable=self.vars["dashboard_port"], width=10).pack(side="right")

        # Buttons
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill="x", pady=(20, 0))
        ttk.Button(btn_frame, text="💾 Сохранить", command=self._save).pack(side="right", padx=5)
        ttk.Button(btn_frame, text="❌ Отмена", command=self.window.destroy).pack(side="right")

    def _save(self):
        new_config = {**self.config}
        for key, var in self.vars.items():
            new_config[key] = var.get()
        self.on_save(new_config)
        self.window.destroy()


# ─── Tray Menu Application ─────────────────────────────────────
class SuperGuardMonitor:
    """Главное приложение монитора в трее."""

    def __init__(self):
        self.config = load_config()
        self.manager = SuperGuardManager(self.config)
        self.tray: Optional[pystray.Icon] = None
        self.icon_image = create_tray_icon_image()
        self._running = True
        self._check_thread: Optional[threading.Thread] = None
        self._last_status = {}
        self._was_down_notified = False

    def _create_menu(self):
        """Создаёт меню трея."""
        status = self.manager.get_status()
        any_running = any(status.values())
        all_running = all(status.values())
        
        menu_items = []
        
        # Header
        menu_items.append(pystray.MenuItem("👁 SuperGuard Monitor", None, enabled=False))
        menu_items.append(pystray.Menu.SEPARATOR)
        
        # Start/Stop items with dynamic enable/disable based on current status
        menu_items.append(pystray.MenuItem("▶ Запустить SuperGuard", self._action_start_all, enabled=not all_running))
        menu_items.append(pystray.MenuItem("⏹ Остановить SuperGuard", self._action_stop_all, enabled=any_running))
        menu_items.append(pystray.Menu.SEPARATOR)
        
        # Other items
        menu_items.append(pystray.MenuItem("🌐 Открыть Dashboard", self._action_open_dashboard))
        menu_items.append(pystray.MenuItem("📊 Статус API", self._action_check_api))
        menu_items.append(pystray.MenuItem("🚨 Тест-тревога", self._action_test_alarm))
        menu_items.append(pystray.Menu.SEPARATOR)
        menu_items.append(pystray.MenuItem("⚙️ Настройки", self._action_settings))
        menu_items.append(pystray.MenuItem("📋 Логи монитора", self._action_show_logs))
        menu_items.append(pystray.Menu.SEPARATOR)
        menu_items.append(pystray.MenuItem("❌ Выход", self._action_exit))
        
        return pystray.Menu(*menu_items)

    def _update_tooltip(self):
        """Обновляет tooltip трея с текущим статусом."""
        status = self.manager.get_status()
        running = sum(status.values())
        total = len(status)
        if running == total:
            text = f"SuperGuard Monitor - All running ({total}/{total})"
        elif running == 0:
            text = f"SuperGuard Monitor - Stopped (0/{total})"
        else:
            text = f"SuperGuard Monitor - Partial ({running}/{total})"
        if self.tray:
            self.tray.title = text

    def _update_menu_state(self):
        """Принудительно обновляет меню (пересоздаёт с новыми enabled состояниями)."""
        try:
            status = self.manager.get_status()
            any_running = any(status.values())
            all_running = all(status.values())
            
            if self.tray:
                # Пересоздаём меню с актуальными состояниями
                self.tray.menu = self._create_menu()
        except Exception as e:
            logger.debug(f"Menu update error: {e}")

    def _action_start_all(self, icon=None, item=None):
        logger.info("Запуск всех компонентов SuperGuard...")
        results = self.manager.start_all()
        self._update_tooltip()
        self._update_menu_state()
        success = all(results.values())
        if self.tray:
            self.tray.notify("SuperGuard", "Все компоненты запущены" if success else "Некоторые компоненты не запустились")

    def _action_stop_all(self, icon=None, item=None):
        logger.info("Остановка всех компонентов SuperGuard...")
        self.manager.stop_all()
        self._update_tooltip()
        self._update_menu_state()
        if self.tray:
            self.tray.notify("SuperGuard", "Все компоненты остановлены")

    def _action_open_dashboard(self, icon=None, item=None):
        import webbrowser
        webbrowser.open(self.config["dashboard_url"])
        logger.info("Открыт Dashboard в браузере")

    def _action_check_api(self, icon=None, item=None):
        healthy = self.manager.check_health()
        msg = "API работает ✅" if healthy else "API недоступен ❌"
        logger.info(msg)
        if self.tray:
            self.tray.notify("API Status", msg)

    def _action_test_alarm(self, icon=None, item=None):
        logger.info("Тест-тревога...")
        if self.tray:
            self.tray.notify("🚨 Test Alarm", "Тестовая тревога срабатывает!")

    def _action_settings(self, icon=None, item=None):
        import tkinter as tk
        from tkinter import ttk

        # Создаем скрытый root если не существует
        root = getattr(self, '_tk_root', None)
        if root is None:
            root = tk.Tk()
            root.withdraw()
            self._tk_root = root

        def on_save(new_config):
            self.config = new_config
            save_config(new_config)
            self.manager.config = new_config
            logger.info("Настройки сохранены")

        win = SettingsWindow(self.config, on_save)
        win.show()
        root.mainloop()

    def _action_show_logs(self, icon=None, item=None):
        import subprocess
        try:
            subprocess.Popen(["xdg-open", str(LOG_FILE)])
        except:
            try:
                subprocess.Popen(["notepad", str(LOG_FILE)])
            except:
                logger.error("Не удалось открыть логи")

    def _action_exit(self, icon=None, item=None):
        logger.info("Выход из монитора...")
        self._running = False
        if self._check_thread:
            self._check_thread.join(timeout=5)
        self.manager.stop_all()
        if self.tray:
            self.tray.stop()

    def _status_check_loop(self):
        """Фоновая проверка статуса SuperGuard."""
        while self._running:
            try:
                # Получаем статус от менеджера (процессы, запущенные нами)
                manager_status = self.manager.get_status()
                
                # Дополнительно проверяем через pgrep (на случай если процессы запущены извне)
                pids = get_superguard_pids()
                external_status = {
                    "api": "api" in pids and is_process_running(pids["api"]),
                    "dashboard": "dashboard" in pids and is_process_running(pids["dashboard"]),
                    "bot": "bot" in pids and is_process_running(pids["bot"]),
                }
                
                # Объединяем: running если есть в менеджере ИЛИ найден через pgrep
                status = {
                    "api": manager_status.get("api", False) or external_status.get("api", False),
                    "dashboard": manager_status.get("dashboard", False) or external_status.get("dashboard", False),
                    "bot": manager_status.get("bot", False) or external_status.get("bot", False),
                }
                
                running_count = sum(status.values())
                total = len(status)

                # Обновляем tooltip
                if status != self._last_status:
                    self._update_tooltip()
                    self._update_menu_state()
                    self._last_status = status.copy()

                # Проверка на падение
                if self.config.get("notify_on_down", True):
                    if running_count < total and not self._was_down_notified:
                        logger.warning(f"SuperGuard partially stopped: {running_count}/{total}")
                        if self.tray:
                            self.tray.notify(
                                "SuperGuard Alert",
                                f"Components stopped: {running_count}/{total} running"
                            )
                        self._was_down_notified = True
                    elif running_count == total:
                        self._was_down_notified = False

            except Exception as e:
                # Ensure error message can be logged without encoding issues
                error_msg = str(e).encode('ascii', 'replace').decode('ascii')
                logger.error(f"Ошибка в проверке статуса: {error_msg}")

            time.sleep(self.config.get("check_interval", 30))

    def run(self):
        """Запускает монитор."""
        logger.info("=" * 50)
        logger.info("SuperGuard Monitor starting...")
        logger.info(f"Config: {self.config}")

        # Автозапуск если включен
        if self.config.get("auto_start", True):
            logger.info("Auto-start enabled, launching SuperGuard...")
            self.manager.start_all()

        # Запускаем поток проверки
        self._check_thread = threading.Thread(target=self._status_check_loop, daemon=True)
        self._check_thread.start()

        # Создаем иконку трея
        self.icon_image = create_tray_icon_image()

        self.tray = pystray.Icon(
            "SuperGuardMonitor",
            self.icon_image,
            "SuperGuard Monitor",
            self._create_menu()
        )

        logger.info("Tray icon created, starting main loop...")

        # Запуск в главном потоке (блокирует до выхода)
        self.tray.run()

        logger.info("SuperGuard Monitor stopped")


# ─── Entry Point ───────────────────────────────────────────────
def main():
    print("🛡️ SuperGuard Monitor")
    print("=" * 50)

    # Проверка зависимостей
    try:
        import pystray
        from PIL import Image, ImageDraw, ImageFilter
    except ImportError:
        print("Installing dependencies...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pystray", "pillow"])
        import pystray
        from PIL import Image, ImageDraw, ImageFilter

    # Запуск монитора
    monitor = SuperGuardMonitor()
    monitor.run()


if __name__ == "__main__":
    main()