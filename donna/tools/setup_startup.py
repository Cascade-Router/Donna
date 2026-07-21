"""Register / unregister Donna to start with Windows (HKCU Run).

Usage:
  python -m donna.tools.setup_startup install
  python -m donna.tools.setup_startup uninstall
  python -m donna.tools.setup_startup status
"""

from __future__ import annotations

import argparse
import sys
import winreg
from pathlib import Path

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "DonnaAssistant"


def project_root() -> Path:
    from donna.paths import PROJECT_ROOT

    return PROJECT_ROOT


def bat_path() -> Path:
    return project_root() / "start_donna.bat"


def python_launcher() -> Path:
    """Prefer pythonw.exe so startup is windowless; fall back to python.exe."""
    venv = project_root() / ".venv" / "Scripts"
    for name in ("pythonw.exe", "python.exe"):
        candidate = venv / name
        if candidate.is_file():
            return candidate
    return Path(sys.executable)


def write_start_bat() -> Path:
    """Create ``start_donna.bat`` that launches ``run.py`` from the project venv."""
    root = project_root()
    py = python_launcher()
    entry = root / "run.py"
    # /d so `cd` works across drives; quoted paths for spaces.
    # Always use run.py (never `python donna/core_agent.py`) so sys.path is the
    # repo root and ``import donna`` / root modules keep working.
    lines = [
        "@echo off",
        f'cd /d "{root}"',
        f'start "" "{py}" "{entry}"',
        "",
    ]
    path = bat_path()
    path.write_text("\n".join(lines), encoding="utf-8", newline="\r\n")
    return path


def install() -> int:
    bat = write_start_bat()
    command = f'"{bat}"'
    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE
    ) as key:
        winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, command)
    print(f"[OK] Startup enabled: HKCU\\...\\Run\\{VALUE_NAME}")
    print(f"     Command: {command}")
    print(f"     Launcher: {bat}")
    return 0


def uninstall() -> int:
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.DeleteValue(key, VALUE_NAME)
        print(f"[OK] Startup removed: {VALUE_NAME}")
        return 0
    except FileNotFoundError:
        print(f"[OK] Startup entry already absent: {VALUE_NAME}")
        return 0


def status() -> int:
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ
        ) as key:
            value, regtype = winreg.QueryValueEx(key, VALUE_NAME)
        print(f"[ON] {VALUE_NAME} = {value} (type={regtype})")
        return 0
    except FileNotFoundError:
        print(f"[OFF] {VALUE_NAME} is not in HKCU Run")
        return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Add or remove Donna from Windows startup (Current User Run key)."
    )
    parser.add_argument(
        "action",
        choices=("install", "uninstall", "status"),
        help="install / uninstall / status",
    )
    args = parser.parse_args(argv)
    if args.action == "install":
        return install()
    if args.action == "uninstall":
        return uninstall()
    return status()


if __name__ == "__main__":
    raise SystemExit(main())
