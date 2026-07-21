"""Cross-platform Donna login/startup registration.

Windows: HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run
macOS:   ~/Library/LaunchAgents/com.donna.agent.plist
Linux:   ~/.config/autostart/donna.desktop

Usage:
  python -m donna.tools.setup_startup install
  python -m donna.tools.setup_startup uninstall
  python -m donna.tools.setup_startup status
"""

from __future__ import annotations

import argparse
import platform
import sys
from pathlib import Path

VALUE_NAME = "DonnaAssistant"
MACOS_LABEL = "com.donna.agent"
MACOS_PLIST_NAME = f"{MACOS_LABEL}.plist"
LINUX_DESKTOP_NAME = "donna.desktop"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def project_root() -> Path:
    from donna.paths import PROJECT_ROOT

    return PROJECT_ROOT


def _system() -> str:
    return platform.system()


def python_launcher() -> Path:
    """Prefer a windowless / venv interpreter when present."""
    root = project_root()
    system = _system()
    if system == "Windows":
        venv = root / ".venv" / "Scripts"
        for name in ("pythonw.exe", "python.exe"):
            candidate = venv / name
            if candidate.is_file():
                return candidate
    else:
        venv_bin = root / ".venv" / "bin"
        for name in ("python3", "python"):
            candidate = venv_bin / name
            if candidate.is_file():
                return candidate
    return Path(sys.executable)


def entry_script() -> Path:
    return project_root() / "run.py"


def bat_path() -> Path:
    return project_root() / "start_donna.bat"


def write_start_bat() -> Path:
    """Create ``start_donna.bat`` that launches ``run.py`` from the project venv."""
    root = project_root()
    py = python_launcher()
    entry = entry_script()
    lines = [
        "@echo off",
        f'cd /d "{root}"',
        f'start "" "{py}" "{entry}"',
        "",
    ]
    path = bat_path()
    path.write_text("\n".join(lines), encoding="utf-8", newline="\r\n")
    return path


def macos_plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / MACOS_PLIST_NAME


def linux_desktop_path() -> Path:
    return Path.home() / ".config" / "autostart" / LINUX_DESKTOP_NAME


def _write_macos_plist() -> Path:
    root = project_root()
    py = python_launcher()
    entry = entry_script()
    plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
\t<key>Label</key>
\t<string>{MACOS_LABEL}</string>
\t<key>ProgramArguments</key>
\t<array>
\t\t<string>{py}</string>
\t\t<string>{entry}</string>
\t</array>
\t<key>WorkingDirectory</key>
\t<string>{root}</string>
\t<key>RunAtLoad</key>
\t<true/>
\t<key>KeepAlive</key>
\t<false/>
</dict>
</plist>
"""
    path = macos_plist_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(plist, encoding="utf-8")
    return path


def _write_linux_desktop() -> Path:
    root = project_root()
    py = python_launcher()
    entry = entry_script()
    body = (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Version=1.0\n"
        "Name=Donna\n"
        "Comment=Donna local-first voice agent\n"
        f'Exec="{py}" "{entry}"\n'
        f"Path={root}\n"
        "Terminal=false\n"
        "X-GNOME-Autostart-enabled=true\n"
    )
    path = linux_desktop_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def _enable_windows() -> int:
    import winreg

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


def _disable_windows() -> int:
    import winreg

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


def _status_windows() -> int:
    import winreg

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


def _enable_macos() -> int:
    path = _write_macos_plist()
    print(f"[OK] Startup enabled: {path}")
    print(f"     Label: {MACOS_LABEL}")
    return 0


def _disable_macos() -> int:
    path = macos_plist_path()
    if path.is_file():
        path.unlink()
        print(f"[OK] Startup removed: {path}")
    else:
        print(f"[OK] Startup entry already absent: {path}")
    return 0


def _status_macos() -> int:
    path = macos_plist_path()
    if path.is_file():
        print(f"[ON] {path}")
        return 0
    print(f"[OFF] {path} is not present")
    return 1


def _enable_linux() -> int:
    path = _write_linux_desktop()
    print(f"[OK] Startup enabled: {path}")
    return 0


def _disable_linux() -> int:
    path = linux_desktop_path()
    if path.is_file():
        path.unlink()
        print(f"[OK] Startup removed: {path}")
    else:
        print(f"[OK] Startup entry already absent: {path}")
    return 0


def _status_linux() -> int:
    path = linux_desktop_path()
    if path.is_file():
        print(f"[ON] {path}")
        return 0
    print(f"[OFF] {path} is not present")
    return 1


def enable_startup() -> int:
    """Register Donna to launch at user login on the current OS."""
    system = _system()
    if system == "Windows":
        return _enable_windows()
    if system == "Darwin":
        return _enable_macos()
    if system == "Linux":
        return _enable_linux()
    print(f"[ERROR] Unsupported platform for startup registration: {system}", file=sys.stderr)
    return 2


def disable_startup() -> int:
    """Remove Donna from login/startup on the current OS."""
    system = _system()
    if system == "Windows":
        return _disable_windows()
    if system == "Darwin":
        return _disable_macos()
    if system == "Linux":
        return _disable_linux()
    print(f"[ERROR] Unsupported platform for startup registration: {system}", file=sys.stderr)
    return 2


def startup_status() -> int:
    """Print whether Donna is registered for login/startup (0=on, 1=off)."""
    system = _system()
    if system == "Windows":
        return _status_windows()
    if system == "Darwin":
        return _status_macos()
    if system == "Linux":
        return _status_linux()
    print(f"[ERROR] Unsupported platform for startup registration: {system}", file=sys.stderr)
    return 2


# CLI aliases (kept for existing docs / scripts).
def install() -> int:
    return enable_startup()


def uninstall() -> int:
    return disable_startup()


def status() -> int:
    return startup_status()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Add or remove Donna from user login/startup "
            "(Windows Run key, macOS LaunchAgent, or Linux autostart)."
        )
    )
    parser.add_argument(
        "action",
        choices=("install", "uninstall", "status", "enable", "disable"),
        help="install|enable / uninstall|disable / status",
    )
    args = parser.parse_args(argv)
    if args.action in ("install", "enable"):
        return enable_startup()
    if args.action in ("uninstall", "disable"):
        return disable_startup()
    return startup_status()


if __name__ == "__main__":
    raise SystemExit(main())
