"""Register Donna in the current user's Windows Startup (HKCU Run key).

Run once:
  python register_startup.py

Removes the need to launch Donna manually after login. Uses ``pythonw.exe``
so no console window appears at logon.
"""

from __future__ import annotations

import os
import sys


def main() -> int:
    if sys.platform != "win32":
        print("[Startup] ERROR: Windows-only (winreg).", file=sys.stderr)
        return 1

    import winreg

    root = os.path.abspath(os.path.dirname(__file__))
    run_py = os.path.join(root, "run.py")
    if not os.path.isfile(run_py):
        print(f"[Startup] ERROR: run.py not found at {run_py}", file=sys.stderr)
        return 1

    # Prefer venv pythonw next to this repo; fall back to sibling of sys.executable.
    candidates = [
        os.path.join(root, ".venv", "Scripts", "pythonw.exe"),
        os.path.join(os.path.dirname(sys.executable), "pythonw.exe"),
        sys.executable.replace("python.exe", "pythonw.exe"),
    ]
    pythonw = next((p for p in candidates if os.path.isfile(p)), None)
    if not pythonw:
        print("[Startup] ERROR: pythonw.exe not found.", file=sys.stderr)
        return 1

    # Quote paths for the Run key (spaces-safe).
    value = f'"{os.path.abspath(pythonw)}" "{os.path.abspath(run_py)}"'
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        key_path,
        0,
        winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE,
    ) as key:
        winreg.SetValueEx(key, "DonnaVoiceAgent", 0, winreg.REG_SZ, value)

    print(f"[Startup] Registered HKCU\\...\\Run\\DonnaVoiceAgent")
    print(f"[Startup] Command: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
