#!/usr/bin/env python3
"""Tests for SelfHeal (environment check & repair)."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from self_heal import SelfHeal, EnvReport  # noqa: E402

PASS = FAIL = 0

def check(name, fn):
    global PASS, FAIL
    try:
        fn()
        PASS += 1
        print(f"  ✓ {name}")
    except Exception as e:
        FAIL += 1
        print(f"  ✗ {name}: {type(e).__name__}: {e}")

def make_proj(env_with_token=True):
    """Create a temp project dir with optional sguard.env."""
    tmp = tempfile.mkdtemp(prefix="sg-heal-")
    if env_with_token:
        with open(os.path.join(tmp, "sguard.env"), "w", encoding="utf-8") as f:
            f.write("SG_TELEGRAM_BOT_TOKEN=123456:ABCdef123456\nSG_CHAT_ID=42\nSG_PLUG_KEY=k\n")
    return tmp

def test_real_project():
    """Real C:\\SuperGuard: all checks pass (packages, model, config)."""
    heal = SelfHeal(r"C:\SuperGuard")
    rep = heal.check_all()
    assert rep.python_path, "python not found"
    by_name = {r.name: r for r in rep.results}
    assert by_name["Python"].ok
    assert by_name["pip"].ok
    assert by_name["Пакеты"].ok, by_name["Пакеты"].message
    assert by_name["Модель YOLO"].ok, by_name["Модель YOLO"].message
    assert by_name["Конфиг sguard.env"].ok, by_name["Конфиг sguard.env"].message
    print(f"    python={rep.python_path}")

def test_config_token_masked():
    """Masked token must be reported as broken + fixable."""
    tmp = make_proj()
    with open(os.path.join(tmp, "sguard.env"), "w", encoding="utf-8") as f:
        f.write("SG_TELEGRAM_BOT_TOKEN=123:***\n")
    heal = SelfHeal(tmp)
    rep = heal.check_all()
    cfg = [r for r in rep.results if r.name == "Конфиг sguard.env"][0]
    assert not cfg.ok, "masked token should fail"
    assert cfg.fixable

def test_config_missing_repairs():
    """Missing sguard.env -> repair creates it from template."""
    tmp = make_proj(env_with_token=False)
    heal = SelfHeal(tmp)
    rep = heal.check_all()
    cfg = [r for r in rep.results if r.name == "Конфиг sguard.env"][0]
    assert not cfg.ok and cfg.fixable
    heal.repair(rep)
    assert os.path.exists(os.path.join(tmp, "sguard.env")), "repair did not create env"

def test_report_flags():
    rep = EnvReport()
    rep.add("a", True, "ok")
    rep.add("b", False, "bad", fixable=True)
    assert rep.all_ok is False
    assert rep.repairable is True

def test_find_python_venv_preferred():
    tmp = make_proj()
    os.makedirs(os.path.join(tmp, "venv", "Scripts"), exist_ok=True)
    open(os.path.join(tmp, "venv", "Scripts", "python.exe"), "w").close()
    heal = SelfHeal(tmp)
    assert "venv" in heal.python_exe, heal.python_exe

print("SELF-HEAL TESTS")
check("реальный проект C:\\SuperGuard", test_real_project)
check("замаскированный токен = проблема", test_config_token_masked)
check("нет sguard.env -> repair создаёт", test_config_missing_repairs)
check("флаги отчёта", test_report_flags)
check("venv предпочтительнее", test_find_python_venv_preferred)
print(f"ИТОГ: {PASS} PASS, {FAIL} FAIL")
sys.exit(1 if FAIL else 0)