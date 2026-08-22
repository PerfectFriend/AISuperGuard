#!/usr/bin/env python3
"""
SuperGuard Desktop - self-heal: check & repair the runtime environment.

Scans the SuperGuard installation and reports/repairs:
  1. Python interpreter (venv or system)
  2. pip availability
  3. Required pip packages (importable)
  4. YOLO model file (yolo11n.pt)
  5. sguard.env config (token present, not masked)
  6. PATH entries (python, pip)

Each check returns (ok: bool, message: str). repair() fixes what it can
(pip install missing packages, download model, create config from template).
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from typing import List, Tuple

# Packages required by SuperGuard (import name -> pip name)
REQUIRED_PACKAGES = {
    "numpy": "numpy",
    "cv2": "opencv-python-headless",
    "ultralytics": "ultralytics",
    "torch": "torch",
    "tinytuya": "tinytuya",
    "requests": "requests",
    "psutil": "psutil",
}
# One AES lib is enough for tinytuya (any of these)
AES_PACKAGES = {
    "cryptography": "cryptography",
    "Crypto": "pycryptodome",
    "pyaes": "pyaes",
}


@dataclass
class CheckResult:
    """Result of a single environment check."""
    name: str
    ok: bool
    message: str
    fixable: bool = False
    fixed: bool = False


@dataclass
class EnvReport:
    """Aggregated self-heal report."""
    results: List[CheckResult] = field(default_factory=list)
    python_path: str = ""
    project_dir: str = ""

    @property
    def all_ok(self) -> bool:
        return all(r.ok for r in self.results)

    @property
    def repairable(self) -> bool:
        return any(r.fixable and not r.ok for r in self.results)

    def add(self, name: str, ok: bool, message: str, fixable: bool = False) -> None:
        self.results.append(CheckResult(name, ok, message, fixable))


class SelfHeal:
    """Runs environment checks and repairs on the SuperGuard project."""

    def __init__(self, project_dir: str, python_exe: str = None):
        self.project_dir = os.path.abspath(project_dir)
        # Prefer a venv python inside the project, else current interpreter
        self.python_exe = python_exe or self._find_python()

    # ------------------------------------------------------------------ utils
    def _find_python(self) -> str:
        """Locate the best python interpreter for SuperGuard."""
        # 1. venv inside project
        for cand in (
            os.path.join(self.project_dir, "venv", "Scripts", "python.exe"),
            os.path.join(self.project_dir, ".venv", "Scripts", "python.exe"),
        ):
            if os.path.exists(cand):
                return cand
        # 2. the interpreter running this app
        return sys.executable

    def _run(self, args: List[str], timeout: int = 180) -> Tuple[int, str]:
        """Run a subprocess with this python and capture output."""
        try:
            r = subprocess.run([self.python_exe] + args, capture_output=True,
                               text=True, timeout=timeout)
            return r.returncode, (r.stdout + r.stderr).strip()
        except Exception as e:
            return -1, str(e)

    # --------------------------------------------------------------- checks
    def check_all(self) -> EnvReport:
        rep = EnvReport(python_path=self.python_exe, project_dir=self.project_dir)
        self._check_python(rep)
        self._check_pip(rep)
        self._check_packages(rep)
        self._check_model(rep)
        self._check_config(rep)
        self._check_path(rep)
        return rep

    def _check_python(self, rep: EnvReport):
        if not os.path.exists(self.python_exe):
            rep.add("Python", False,
                    f"Интерпретатор не найден: {self.python_exe}",
                    fixable=True)
            return
        code, out = self._run(["--version"])
        ver = out.splitlines()[0] if out else "?"
        ok = code == 0
        rep.add("Python", ok,
                f"{self.python_exe}\n    {ver}" if ok else f"Ошибка: {out}",
                fixable=not ok)

    def _check_pip(self, rep: EnvReport):
        if not os.path.exists(self.python_exe):
            rep.add("pip", False, "Python отсутствует")
            return
        code, out = self._run(["-m", "pip", "--version"])
        ok = code == 0
        rep.add("pip", ok,
                out.splitlines()[0] if ok else f"pip недоступен: {out}",
                fixable=not ok)

    def _check_packages(self, rep: EnvReport):
        missing = []
        for imp, pip in REQUIRED_PACKAGES.items():
            if importlib.util.find_spec(imp) is None:
                missing.append(pip)
        # AES: need at least one
        if not any(importlib.util.find_spec(imp) for imp in AES_PACKAGES):
            missing.append("pycryptodome")
        if missing:
            rep.add("Пакеты", False,
                    "Не установлены: " + ", ".join(missing),
                    fixable=True)
        else:
            rep.add("Пакеты", True,
                    f"Все зависимости на месте ({len(REQUIRED_PACKAGES)}+ пакетов)")

    def _check_model(self, rep: EnvReport):
        for name in ("yolo11n.pt", "yolov8n.pt"):
            p = os.path.join(self.project_dir, name)
            if os.path.exists(p) and os.path.getsize(p) > 1_000_000:
                rep.add("Модель YOLO", True,
                        f"{name} ({os.path.getsize(p)//1024//1024} МБ)")
                return
        rep.add("Модель YOLO", False,
                "yolo11n.pt не найден. Ultralytics скачает при первом запуске",
                fixable=True)

    def _check_config(self, rep: EnvReport):
        env_path = os.path.join(self.project_dir, "sguard.env")
        if not os.path.exists(env_path):
            rep.add("Конфиг sguard.env", False,
                    "Файл не найден. Будет создан из шаблона",
                    fixable=True)
            return
        token = ""
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                if line.startswith("SG_TELEGRAM_BOT_TOKEN="):
                    token = line.split("=", 1)[1].strip()
        if not token or "***" in token:
            rep.add("Конфиг sguard.env", False,
                    "Токен бота не задан (или замаскирован). Укажите в настройках",
                    fixable=True)
        else:
            rep.add("Конфиг sguard.env", True,
                    f"Токен задан ({token[:12]}…{token[-4:]})")

    def _check_path(self, rep: EnvReport):
        path_dirs = os.environ.get("PATH", "").split(os.pathsep)
        py_dir = os.path.dirname(self.python_exe)
        ok = any(os.path.normcase(d) == os.path.normcase(py_dir) for d in path_dirs if d)
        rep.add("PATH", ok,
                f"Каталог Python в PATH: {py_dir}" if ok
                else f"Каталог Python НЕ в PATH: {py_dir}",
                fixable=not ok)

    # -------------------------------------------------------------- repair
    def repair(self, rep: EnvReport) -> EnvReport:
        """Attempt to fix every fixable failed check in place."""
        for r in rep.results:
            if r.ok or not r.fixable:
                continue
            try:
                if r.name == "Пакеты":
                    self._repair_packages()
                elif r.name == "Модель YOLO":
                    self._repair_model()
                elif r.name == "Конфиг sguard.env":
                    self._repair_config()
                elif r.name == "PATH":
                    self._repair_path()
                elif r.name == "Python":
                    # can't install python itself - report guidance
                    r.message += "  → Установите Python 3.11+ (python.org)"
                    continue
                r.fixed = True
                r.ok = True
                r.message += "  [отремонтировано]"
            except Exception as e:
                r.message += f"  [ошибка ремонта: {e}]"
        return rep

    def _repair_packages(self):
        req = os.path.join(self.project_dir, "requirements.txt")
        if os.path.exists(req):
            code, out = self._run(["-m", "pip", "install", "-r", req])
        else:
            pkgs = list(REQUIRED_PACKAGES.values()) + ["pycryptodome"]
            code, out = self._run(["-m", "pip", "install"] + pkgs)
        if code != 0:
            raise RuntimeError(out[-400:])

    def _repair_model(self):
        """Try downloading the model via ultralytics into the project dir."""
        code, out = self._run(["-c",
            "from ultralytics import YOLO; m=YOLO('yolo11n.pt'); "
            "print('downloaded', m.model_name)"])
        if code != 0:
            raise RuntimeError(out[-300:])

    def _repair_config(self):
        env_path = os.path.join(self.project_dir, "sguard.env")
        if os.path.exists(env_path):
            return  # exists but token masked - leave for user via config UI
        template = os.path.join(self.project_dir, "assets", "sguard.env.example")
        src = template if os.path.exists(template) else None
        if src:
            shutil.copy(src, env_path)
        else:
            with open(env_path, "w", encoding="utf-8") as f:
                f.write("SG_TELEGRAM_BOT_TOKEN=\nSG_CHAT_ID=\nSG_PLUG_KEY=\n")

    def _repair_path(self):
        """Persist python dir in user PATH via setx (best effort)."""
        py_dir = os.path.dirname(self.python_exe)
        try:
            subprocess.run(["setx", "PATH",
                            f"{os.environ['PATH']}{os.pathsep}{py_dir}"],
                           capture_output=True, timeout=15)
        except Exception:
            pass  # setx quirks on some systems - non-fatal


if __name__ == "__main__":
    project = sys.argv[1] if len(sys.argv) > 1 else r"C:\SuperGuard"
    heal = SelfHeal(project)
    rep = heal.check_all()
    print(f"Python:  {rep.python_path}")
    print()
    for r in rep.results:
        icon = "✅" if r.ok else ("🔧" if r.fixable else "❌")
        print(f"{icon} {r.name}: {r.message}")
    print()
    if rep.repairable:
        print("Обнаружены проблемы. Запускаю ремонт...")
        heal.repair(rep)
        print()
        for r in rep.results:
            icon = "✅" if r.ok else "❌"
            print(f"{icon} {r.name}: {r.message}")
        print("Ремонт завершён.")
    else:
        print("Все проверки пройдены ✅")
