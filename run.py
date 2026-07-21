"""Root entry point for Donna.

Always resolves the repo root onto ``sys.path`` and as the process cwd so
``python run.py`` works from any working directory.
"""

from __future__ import annotations

import os
import sys

_ROOT = os.path.abspath(os.path.dirname(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
try:
    os.chdir(_ROOT)
except OSError:
    pass

# Ensure workspace dirs exist + migrate legacy artifacts before agent boot.
try:
    from donna.workspace import ensure_donna_workspace

    ensure_donna_workspace(migrate=True)
except Exception as exc:  # noqa: BLE001
    print(f"[Workspace] WARNING: ensure_donna_workspace failed: {exc}", file=sys.stderr)

# Held for process lifetime so the OS releases the bind only on exit.
_DONNA_INSTANCE_LOCK_SOCK = None
# Dedicated loopback port — not the telemetry dashboard (47474).
_DONNA_INSTANCE_LOCK_PORT = 47473


def _acquire_single_instance_lock() -> bool:
    """Bind a loopback TCP socket; False if another Donna already holds it."""
    global _DONNA_INSTANCE_LOCK_SOCK
    import socket

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        # Exclusive bind (no SO_REUSEADDR) — second instance must fail.
        sock.bind(("127.0.0.1", _DONNA_INSTANCE_LOCK_PORT))
        sock.listen(1)
    except OSError:
        try:
            sock.close()
        except OSError:
            pass
        return False
    _DONNA_INSTANCE_LOCK_SOCK = sock
    return True


if __name__ == "__main__":
    if not _acquire_single_instance_lock():
        print(
            "[Main] ERROR: Another instance of Donna is already running. "
            "Aborting to protect execution jail.",
            flush=True,
        )
        sys.exit(1)

    # Defer core_agent import until launch so torch/transformers/YOLO stay off
    # the interpreter's critical path during ``run.py`` module load.
    from donna.core_agent import main  # noqa: E402

    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        # Closing the GUI / Ctrl+C should exit quietly (workers log "Stopped.").
        try:
            from donna.core_agent import _shutdown_agent_threads

            _shutdown_agent_threads(join_timeout=5.0)
        except Exception:
            pass
        raise SystemExit(130)
