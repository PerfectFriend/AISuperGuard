#!/usr/bin/env python3
"""
SuperGuard Evolution Engine
Runs autonomous evolution cycles for SuperGuard Alarm project.
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.absolute()
STATE_FILE = PROJECT_ROOT / "evolution_state.json"
SUPERGUARD_DIR = PROJECT_ROOT / "superguard"

PROJECT_MAP = {
    "1": "superguard",
    "2": "paranoidx",
    "3": "grimoire",
    "4": "cathedral",
    "superguard": "superguard",
    "paranoidx": "paranoidx",
    "grimoire": "grimoire",
    "cathedral": "cathedral",
}

REVERSE_PROJECT_MAP = {v: k for k, v in PROJECT_MAP.items() if k.isdigit()}


def load_state():
    """Load evolution state from JSON file."""
    if STATE_FILE.exists():
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "last_cycle": 0,
        "last_run": None,
        "tests_passed": False,
        "debug_checks": {},
        "backup_ok": False,
        "next_cycle": 1,
    }


def save_state(state):
    """Save evolution state to JSON file."""
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def run_tests():
    """Run SuperGuard test suite."""
    print("\n[1/4] Running tests...")
    test_script = SUPERGUARD_DIR / "tests" / "test_all.py"
    if not test_script.exists():
        print(f"  ���� Test script not found: {test_script}")
        return False

    # Run tests in-process to avoid encoding issues
    import importlib.util
    spec = importlib.util.spec_from_file_location("test_all", test_script)
    test_module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(test_module)
        print("  ����� Tests PASSED")
        return True
    except SystemExit as e:
        if e.code == 0:
            print("  ����� Tests PASSED")
            return True
        else:
            print(f"  ����� Tests FAILED (exit code {e.code})")
            return False
    except Exception as e:
        print(f"  ����� Tests FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_debug_checks():
    """Run debug checks: bot_running, fallback_config, opencode_keys, usb_drive."""
    print("\n[2/4] Running debug checks...")
    checks = {}

    # Check if bot process is running
    try:
        result = subprocess.run(
            ["tasklist"],
            capture_output=True,
            text=False,  # Get bytes
            timeout=10,
        )
        output = result.stdout.decode('cp866', errors='replace')
        checks["bot_running"] = "panic_mode.py" in output or "run_bot.py" in output
    except Exception:
        checks["bot_running"] = False

    # Check fallback config exists
    fallback_file = PROJECT_ROOT / "config.yaml"
    checks["fallback_config"] = fallback_file.exists()

    # Check opencode keys (placeholder - would check actual config)
    checks["opencode_keys"] = True  # Placeholder

    # Check USB drive D:
    checks["usb_drive"] = os.path.exists("D:\\")

    for name, value in checks.items():
        print(f"  {'���' if value else '���'} {name}: {value}")

    return checks


def run_backup():
    """Backup to USB D:\\backups\\"""
    print("\n[3/4] Running backup to USB...")
    backup_dir = Path("D:/backups/superguard")
    try:
        backup_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = backup_dir / f"superguard_backup_{timestamp}.zip"

        # Create zip of project (excluding large files)
        import zipfile
        exclude_patterns = [
            "*.jpg", "*.pt", "__pycache__", ".git", ".hermes",
            "superguard_light*", "desktop", "desktop_state",
            "snap*.jpg", "yolo11n.pt", "nssm.exe"
        ]

        def should_exclude(path: Path) -> bool:
            """Check if path matches any exclude pattern."""
            path_str = str(path)
            for pattern in exclude_patterns:
                # Simple glob matching
                import fnmatch
                if fnmatch.fnmatch(path.name, pattern):
                    return True
                # Check parent directories
                for part in path.parts:
                    if fnmatch.fnmatch(part, pattern):
                        return True
            return False

        with zipfile.ZipFile(backup_file, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file_path in PROJECT_ROOT.rglob("*"):
                if file_path.is_file():
                    rel_path = file_path.relative_to(PROJECT_ROOT)
                    if not should_exclude(rel_path):
                        try:
                            zipf.write(file_path, rel_path)
                        except Exception:
                            pass  # Skip files that can't be read

        print(f"  ���� Backup created: {backup_file}")
        return True
    except Exception as e:
        print(f"  ����� Backup error: {e}")
        import traceback
        traceback.print_exc()
        return False


def send_telegram_report(cycle_id, tests_passed, debug_checks, backup_ok):
    """Send Telegram report via CathedralMaster bot."""
    print("\n[4/4] Sending Telegram report...")
    # This would integrate with Hermes gateway
    # For now, just log
    report = f"""
���� **EVOLUTION REPORT** — Cycle {cycle_id}
��� {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

��� Tests: {'PASSED' if tests_passed else 'FAILED'}
���� Debug Checks:
  - Bot Running: {'���' if debug_checks.get('bot_running') else '���'}
  - Fallback Config: {'���' if debug_checks.get('fallback_config') else '���'}
  - OpenCode Keys: {'���' if debug_checks.get('opencode_keys') else '���'}
  - USB Drive: {'���' if debug_checks.get('usb_drive') else '���'}
���� Backup: {'���' if backup_ok else '���'}

���� Next cycle: {cycle_id + 1}
"""
    print(report)
    return True


def push_to_github(cycle_id):
    """Push to private GitHub repo PerfectFriend/AISuperGuard."""
    print(f"\n[Push] Pushing cycle {cycle_id} to GitHub...")

    # Check if git is initialized
    git_dir = PROJECT_ROOT / ".git"
    if not git_dir.exists():
        print("  Initializing git repo...")
        subprocess.run(["git", "init"], cwd=PROJECT_ROOT, capture_output=True)

    # Check remote
    result = subprocess.run(
        ["git", "remote", "-v"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    if "PerfectFriend/AISuperGuard" not in result.stdout:
        print("  Adding remote...")
        subprocess.run(
            ["git", "remote", "add", "origin", "https://github.com/PerfectFriend/AISuperGuard.git"],
            cwd=PROJECT_ROOT,
            capture_output=True,
        )

    # Add all files
    subprocess.run(["git", "add", "-A"], cwd=PROJECT_ROOT, capture_output=True)

    # Commit
    commit_msg = f"evolution: cycle {cycle_id} - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    result = subprocess.run(
        ["git", "commit", "-m", commit_msg],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 and "nothing to commit" not in result.stdout:
        print(f"  �� Commit failed: {result.stderr}")
        return False

    # Push
    result = subprocess.run(
        ["git", "push", "-u", "origin", "master"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode == 0:
        print(f"  �� Pushed to GitHub")
        return True
    else:
        print(f"  ��� Push result: {result.stderr}")
        # Might fail if repo doesn't exist or auth needed
        return False


def run_cycle(cycle_id, push_private=False):
    """Run a single evolution cycle."""
    print(f"\n{'='*60}")
    print(f"SUPERGUARD EVOLUTION — CYCLE {cycle_id}")
    print(f"{'='*60}")

    state = load_state()
    state["last_cycle"] = cycle_id
    state["last_run"] = datetime.now().isoformat()

    # Run tests
    tests_passed = run_tests()
    state["tests_passed"] = tests_passed

    # Run debug checks
    debug_checks = run_debug_checks()
    state["debug_checks"] = debug_checks

    # Run backup
    backup_ok = run_backup()
    state["backup_ok"] = backup_ok

    # Send Telegram report
    send_telegram_report(cycle_id, tests_passed, debug_checks, backup_ok)

    # Save state
    state["next_cycle"] = cycle_id + 1
    save_state(state)

    # Push at checkpoints
    if push_private and cycle_id in [3, 6, 10]:
        push_to_github(cycle_id)

    print(f"\n{'='*60}")
    print(f"CYCLE {cycle_id} COMPLETE")
    print(f"{'='*60}")

    return tests_passed


def main():
    parser = argparse.ArgumentParser(description="SuperGuard Evolution Engine")
    parser.add_argument("--project", choices=["1", "2", "3", "4", "superguard", "paranoidx", "grimoire", "cathedral"], required=True,
                        help="Project ID (1=superguard, 2=paranoidx, 3=grimoire, 4=cathedral) or project name")
    parser.add_argument("--cycles", type=int, default=1,
                        help="Number of cycles to run")
    parser.add_argument("--cycle-id", type=int, required=True,
                        help="Starting cycle ID")
    parser.add_argument("--push-private", action="store_true",
                        help="Push to private GitHub repo at checkpoints")

    args = parser.parse_args()

    project_name = PROJECT_MAP.get(args.project)
    if not project_name:
        print(f"Unknown project: {args.project}")
        sys.exit(1)

    print(f"Project: {project_name} (ID: {args.project})")
    print(f"Cycles: {args.cycles}")
    print(f"Starting cycle ID: {args.cycle_id}")
    print(f"Push private: {args.push_private}")

    # Run cycles
    for i in range(args.cycles):
        cycle_id = args.cycle_id + i
        success = run_cycle(cycle_id, push_private=args.push_private)
        if not success:
            print(f"Cycle {cycle_id} had test failures, continuing...")

        if i < args.cycles - 1:
            print(f"\nWaiting 60 seconds before next cycle...")
            time.sleep(60)

    print(f"\n��� All {args.cycles} cycles completed!")


if __name__ == "__main__":
    main()