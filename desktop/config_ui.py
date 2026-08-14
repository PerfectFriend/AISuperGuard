#!/usr/bin/env python3
"""
SuperGuard Desktop - configuration UI (tkinter).

Full-stack config editor for sguard.env:
  - Telegram: bot token, chat id
  - Paths: project dir, python interpreter
  - Cameras: SG_CAM_URL + SG_CAM{N}_URL/NAME (2..32)
  - Plugs: SG_ACTUATORS (JSON)
  - Detection: 7 tuning parameters

Saves atomically (temp + rename). Pure helper functions are GUI-free
and unit-testable.
"""
import json
import os
import sys
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

# ---------------------------------------------------------------------------
# GUI-free helpers (unit-testable)
# ---------------------------------------------------------------------------

def parse_cameras_text(text: str) -> dict:
    """Parse multi-line camera editor text into {cam_id: (url, name)}.

    Line format:  N=url|name   (name optional). Skips blank/# lines.
    """
    cams = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        n_str, rest = line.split("=", 1)
        try:
            n = int(n_str.strip())
        except ValueError:
            continue
        url, _, name = rest.partition("|")
        cams[n] = (url.strip(), name.strip())
    return cams


def cameras_to_text(cams: dict) -> str:
    """Reverse of parse_cameras_text: dict -> editor text."""
    lines = []
    for n in sorted(cams):
        url, name = cams[n]
        lines.append(f"{n}={url}|{name}" if name else f"{n}={url}")
    return "\n".join(lines)


def validate_actuators_json(text: str) -> tuple:
    """Validate SG_ACTUATORS JSON. Returns (ok, data_or_error)."""
    text = text.strip()
    if not text:
        return True, []
    try:
        data = json.loads(text)
        if not isinstance(data, list):
            return False, "SG_ACTUATORS должен быть JSON-массивом"
        for item in data:
            if not isinstance(item, dict) or "name" not in item:
                return False, "Каждый элемент должен иметь поле 'name'"
        return True, data
    except json.JSONDecodeError as e:
        return False, f"JSON ошибка: {e}"


def build_env_content(env: dict, cameras: dict, actuator_text: str) -> str:
    """Build full sguard.env content from a settings dict.

    env: parsed existing env keys (raw strings).
    cameras: {cam_id: (url, name)} -> SG_CAM{N}_URL / SG_CAM{N}_NAME.
    actuator_text: validated SG_ACTUATORS JSON text (or '' to keep existing).
    """
    lines = []
    lines.append("# SuperGuard standalone config - NOT the hermes .env")
    lines.append(f"SG_TELEGRAM_BOT_TOKEN={env.get('SG_TELEGRAM_BOT_TOKEN', '')}")
    lines.append(f"SG_CHAT_ID={env.get('SG_CHAT_ID', '')}")
    lines.append(f"SG_PLUG_IP={env.get('SG_PLUG_IP', '')}")
    lines.append(f"SG_PLUG_ID={env.get('SG_PLUG_ID', '')}")
    lines.append(f"SG_PLUG_KEY={env.get('SG_PLUG_KEY', '')}")
    lines.append(f"SG_CAM_URL={env.get('SG_CAM_URL', '')}")
    lines.append(f"SG_UPDATE_EVERY={env.get('SG_UPDATE_EVERY', '2.0')}")
    lines.append(f"SG_DETECT_EVERY={env.get('SG_DETECT_EVERY', '1.5')}")
    lines.append(f"SG_YELLOW_MIN_FRACTION={env.get('SG_YELLOW_MIN_FRACTION', '0.15')}")
    lines.append(f"SG_MIN_CONF={env.get('SG_MIN_CONF', '0.35')}")
    lines.append(f"SG_MIN_YELLOW_VEHICLES={env.get('SG_MIN_YELLOW_VEHICLES', '1')}")
    lines.append(f"SG_REQUIRE_FRAMES={env.get('SG_REQUIRE_FRAMES', '2')}")
    lines.append(f"SG_AUTO_RESOLVE_FRAMES={env.get('SG_AUTO_RESOLVE_FRAMES', '5')}")
    lines.append("")
    # cameras 2..32
    for n in sorted(cameras):
        url, name = cameras[n]
        if n == 1:
            continue  # cam 1 uses SG_CAM_URL
        if url:
            lines.append(f"SG_CAM{n}_URL={url}")
        if name:
            lines.append(f"SG_CAM{n}_NAME={name}")
    lines.append("")
    # actuators
    if actuator_text.strip():
        lines.append(f"SG_ACTUATORS={actuator_text.strip()}")
    lines.append("")
    # tuya cloud (keep if present)
    for k in ("TUYA_ACCESS_ID", "TUYA_ACCESS_SECRET", "TUYA_REGION", "TUYA_SCHEMA"):
        if env.get(k):
            lines.append(f"{k}={env[k]}")
    return "\n".join(lines) + "\n"


def read_env(path: str) -> dict:
    """Read sguard.env into {KEY: value} (raw strings)."""
    env = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if s and not s.startswith("#") and "=" in s:
                    k, v = s.split("=", 1)
                    env[k.strip()] = v.strip()
    return env


def write_env(path: str, content: str) -> None:
    """Atomic env write: temp file + os.replace."""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(content)
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------

class ConfigWindow(tk.Toplevel):
    """Modal configuration editor window."""

    def __init__(self, master, project_dir: str, on_saved=None):
        super().__init__(master)
        self.project_dir = project_dir
        self.env_path = os.path.join(project_dir, "sguard.env")
        self.on_saved = on_saved
        self.env = read_env(self.env_path)

        self.title("⚙️ SuperGuard — Настройки")
        self.geometry("720x560")
        self.resizable(True, True)
        self.transient(master)
        self.grab_set()

        # rebuild camera list from env
        self.cameras = {}
        for k, v in self.env.items():
            if k.startswith("SG_CAM") and k.endswith("_URL"):
                try:
                    n = int(k[6:-4])
                except ValueError:
                    continue
                name = self.env.get(f"SG_CAM{n}_NAME", "")
                self.cameras[n] = (v, name)

        self._build()
        self.protocol("WM_DELETE_WINDOW", self.destroy)

    # ------------------------------------------------------------- widgets
    def _build(self):
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=8, pady=8)

        self.tab_tg = ttk.Frame(nb)
        self.tab_paths = ttk.Frame(nb)
        self.tab_cams = ttk.Frame(nb)
        self.tab_plugs = ttk.Frame(nb)
        self.tab_det = ttk.Frame(nb)
        nb.add(self.tab_tg, text="Telegram")
        nb.add(self.tab_paths, text="Пути")
        nb.add(self.tab_cams, text="Камеры")
        nb.add(self.tab_plugs, text="Розетки")
        nb.add(self.tab_det, text="Детекция")

        self._build_telegram()
        self._build_paths()
        self._build_cameras()
        self._build_plugs()
        self._build_detection()

        btns = ttk.Frame(self)
        btns.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Button(btns, text="💾 Сохранить", command=self._save).pack(side="left", padx=4)
        ttk.Button(btns, text="Отмена", command=self.destroy).pack(side="left", padx=4)
        self.status = ttk.Label(self, text="")
        self.status.pack(side="right", padx=8)

    def _build_telegram(self):
        f = self.tab_tg
        pad = dict(padx=10, pady=6)
        ttk.Label(f, text="Токен бота (от @BotFather):").grid(row=0, column=0, sticky="w", **pad)
        self.var_token = tk.StringVar(value=self.env.get("SG_TELEGRAM_BOT_TOKEN", ""))
        ttk.Entry(f, textvariable=self.var_token, width=50).grid(row=0, column=1, sticky="we", **pad)
        ttk.Label(f, text="Chat ID:").grid(row=1, column=0, sticky="w", **pad)
        self.var_chat = tk.StringVar(value=self.env.get("SG_CHAT_ID", ""))
        ttk.Entry(f, textvariable=self.var_chat, width=20).grid(row=1, column=1, sticky="w", **pad)
        ttk.Label(f, text="Ключ розетки Tuya (SG_PLUG_KEY):").grid(row=2, column=0, sticky="w", **pad)
        self.var_plugkey = tk.StringVar(value=self.env.get("SG_PLUG_KEY", ""))
        ttk.Entry(f, textvariable=self.var_plugkey, width=40, show="*").grid(row=2, column=1, sticky="we", **pad)
        f.columnconfigure(1, weight=1)

    def _build_paths(self):
        f = self.tab_paths
        pad = dict(padx=10, pady=6)
        ttk.Label(f, text="Папка проекта (SuperGuard):").grid(row=0, column=0, sticky="w", **pad)
        self.var_proj = tk.StringVar(value=self.project_dir)
        ttk.Entry(f, textvariable=self.var_proj, width=50).grid(row=0, column=1, sticky="we", **pad)
        ttk.Button(f, text="Обзор…", command=self._browse_proj).grid(row=0, column=2, **pad)
        ttk.Label(f, text="Python интерпретатор:").grid(row=1, column=0, sticky="w", **pad)
        self.var_py = tk.StringVar(value=sys.executable)
        ttk.Entry(f, textvariable=self.var_py, width=50).grid(row=1, column=1, sticky="we", **pad)
        ttk.Button(f, text="Обзор…", command=self._browse_py).grid(row=1, column=2, **pad)
        f.columnconfigure(1, weight=1)

    def _build_cameras(self):
        f = self.tab_cams
        pad = dict(padx=10, pady=4)
        ttk.Label(f, text="Камера 1 (SG_CAM_URL, HLS):").grid(row=0, column=0, sticky="w", **pad)
        self.var_cam1 = tk.StringVar(value=self.env.get("SG_CAM_URL", ""))
        ttk.Entry(f, textvariable=self.var_cam1, width=70).grid(row=0, column=1, sticky="we", **pad)
        ttk.Label(f, text="Камеры 2–32 (строка:  N=url|имя):").grid(row=1, column=0, sticky="nw", **pad)
        self.txt_cams = tk.Text(f, width=70, height=16)
        self.txt_cams.grid(row=1, column=1, sticky="nsew", **pad)
        others = {n: v for n, v in self.cameras.items() if n != 1}
        self.txt_cams.insert("1.0", cameras_to_text(others))
        f.rowconfigure(1, weight=1)
        f.columnconfigure(1, weight=1)

    def _build_plugs(self):
        f = self.tab_plugs
        pad = dict(padx=10, pady=4)
        ttk.Label(f, text="SG_ACTUATORS (JSON-массив):").grid(row=0, column=0, sticky="nw", **pad)
        self.txt_plugs = tk.Text(f, width=70, height=14)
        self.txt_plugs.grid(row=0, column=1, sticky="nsew", **pad)
        self.txt_plugs.insert("1.0", self.env.get("SG_ACTUATORS", ""))
        ttk.Label(f, text="Пример:\n[{\"name\": \"plug1\", \"type\": \"tuya\", \"cameras\": [1,2,3,4], \"ip\": \"192.168.1.50\", \"device_id\": \"…\", \"local_key\": \"…\", \"version\": 3.4, \"port\": 6668}]",
                  foreground="gray").grid(row=1, column=1, sticky="w", **pad)
        f.rowconfigure(0, weight=1)
        f.columnconfigure(1, weight=1)

    def _build_detection(self):
        f = self.tab_det
        pad = dict(padx=10, pady=5)
        fields = [
            ("SG_UPDATE_EVERY", "Интервал кадров / live (с)"),
            ("SG_DETECT_EVERY", "Интервал детекции (с)"),
            ("SG_MIN_CONF", "Мин. уверенность YOLO"),
            ("SG_YELLOW_MIN_FRACTION", "Мин. доля цвета в боксе"),
            ("SG_MIN_YELLOW_VEHICLES", "Мин. совпадений для хита"),
            ("SG_REQUIRE_FRAMES", "Кадров подряд для тревоги"),
            ("SG_AUTO_RESOLVE_FRAMES", "Чистых кадров для автоснятия"),
        ]
        self.det_vars = {}
        for i, (key, label) in enumerate(fields):
            ttk.Label(f, text=f"{label} ({key}):").grid(row=i, column=0, sticky="w", **pad)
            var = tk.StringVar(value=self.env.get(key, ""))
            self.det_vars[key] = var
            ttk.Entry(f, textvariable=var, width=14).grid(row=i, column=1, sticky="w", **pad)

    # ------------------------------------------------------------- actions
    def _browse_proj(self):
        d = filedialog.askdirectory(initialdir=self.project_dir)
        if d:
            self.var_proj.set(d)

    def _browse_py(self):
        f = filedialog.askopenfilename(
            title="Python interpreter",
            filetypes=[("python.exe", "python.exe")])
        if f:
            self.var_py.set(f)

    def _save(self):
        proj = self.var_proj.get().strip()
        if not os.path.isdir(proj):
            messagebox.showerror("Ошибка", "Папка проекта не существует")
            return
        self.project_dir = proj
        self.env_path = os.path.join(proj, "sguard.env")

        # cameras from editor
        try:
            cams = parse_cameras_text(self.txt_cams.get("1.0", "end"))
        except Exception as e:
            messagebox.showerror("Ошибка камер", str(e))
            return
        if self.var_cam1.get().strip():
            cams[1] = (self.var_cam1.get().strip(), self.env.get("SG_CAM1_NAME", ""))

        # plugs JSON validation
        plugs_text = self.txt_plugs.get("1.0", "end").strip()
        ok, res = validate_actuators_json(plugs_text)
        if not ok:
            messagebox.showerror("Ошибка розеток", str(res))
            return

        env = dict(self.env)
        env["SG_TELEGRAM_BOT_TOKEN"] = self.var_token.get().strip()
        env["SG_CHAT_ID"] = self.var_chat.get().strip()
        env["SG_PLUG_KEY"] = self.var_plugkey.get().strip()
        for key, var in self.det_vars.items():
            env[key] = var.get().strip()

        content = build_env_content(env, cams, plugs_text)
        write_env(self.env_path, content)
        self.status.config(text="✅ Сохранено")
        if self.on_saved:
            self.on_saved(self.env_path)
        self.after(800, self.destroy)


def open_config(master, project_dir: str, on_saved=None) -> ConfigWindow:
    """Open the config window (blocking modal)."""
    return ConfigWindow(master, project_dir, on_saved)


if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()
    open_config(root, r"C:\SuperGuard")
    root.mainloop()
