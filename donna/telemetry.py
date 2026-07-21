"""Live telemetry dashboard — CAMGRASPER/dashboard.md.

A daemon thread refreshes the markdown table every ~45 seconds while Donna runs.
The Cursor monitor tick can also call ``write_dashboard`` on demand.
"""

from __future__ import annotations

import os
import threading
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any

from donna.paths import DASHBOARD_PATH, DONNA_WORKSPACE

_LOCK = threading.Lock()
_STATUS = "Healthy"
_PID = os.getpid()
_RECENT_TOOLS: deque[str] = deque(maxlen=3)
_CASCADE_LAT_MS: float | None = None
_CASCADE_MODEL: str = ""
_CASCADE_OVER_THRESHOLD: bool = False
_DASHBOARD_THREAD: threading.Thread | None = None
_DASHBOARD_STOP = threading.Event()
DASHBOARD_INTERVAL_SEC = 45.0


def cascade_latency_threshold_ms() -> float:
    """Warn when a high-complexity DeepSeek call exceeds this many ms."""
    try:
        return max(
            1000.0,
            float(os.environ.get("DONNA_CASCADE_LATENCY_THRESHOLD_MS", "120000") or "120000"),
        )
    except ValueError:
        return 120000.0


def note_cascade_latency(latency_ms: float, *, model: str = "") -> None:
    """Record last high-complexity DeepSeek latency for ``dashboard.md``."""
    global _CASCADE_LAT_MS, _CASCADE_MODEL, _CASCADE_OVER_THRESHOLD
    try:
        ms = float(latency_ms)
    except (TypeError, ValueError):
        return
    thr = cascade_latency_threshold_ms()
    with _LOCK:
        _CASCADE_LAT_MS = ms
        _CASCADE_MODEL = (model or "").strip()[:80]
        _CASCADE_OVER_THRESHOLD = ms >= thr


def set_system_status(status: str) -> None:
    """Healthy | Intercepting | Restarting"""
    global _STATUS
    with _LOCK:
        _STATUS = (status or "Healthy").strip() or "Healthy"


def note_tool_event(label: str) -> None:
    text = (label or "").strip()
    if not text:
        return
    with _LOCK:
        _RECENT_TOOLS.appendleft(text[:120])


def _bug_counts() -> tuple[int, int]:
    try:
        from donna.bug_tracker import PENDING_STATUS, load_bug_tracker

        bugs = load_bug_tracker()
        pending = 0
        patched = 0
        for entry in bugs:
            st = str(entry.get("status") or PENDING_STATUS).upper()
            if st in ("PENDING", "OPEN"):
                pending += 1
            elif st == "PATCHED":
                patched += 1
        return pending, patched
    except Exception:  # noqa: BLE001
        return 0, 0


def _resolve_donna_pid(explicit: int | None = None) -> int:
    if explicit:
        return int(explicit)
    # Prefer the live singleton listener on :47474 over this process (monitor scripts
    # may call write_dashboard from a short-lived Python and must not overwrite PID).
    try:
        import socket

        # Windows: query via PowerShell-less netstat parse is heavy; use psutil if present.
        try:
            import psutil  # type: ignore

            for conn in psutil.net_connections(kind="inet"):
                if (
                    conn.laddr
                    and getattr(conn.laddr, "port", None) == 47474
                    and conn.status == "LISTEN"
                    and conn.pid
                ):
                    return int(conn.pid)
        except Exception:  # noqa: BLE001
            pass
    except Exception:  # noqa: BLE001
        pass
    with _LOCK:
        return int(_PID or os.getpid())


def write_dashboard(
    *,
    status: str | None = None,
    pid: int | None = None,
) -> str:
    """Overwrite ``CAMGRASPER/dashboard.md`` with a clean status table."""
    DONNA_WORKSPACE.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        cur_status = status or _STATUS
        recent = list(_RECENT_TOOLS)
        cascade_ms = _CASCADE_LAT_MS
        cascade_model = _CASCADE_MODEL
        cascade_over = _CASCADE_OVER_THRESHOLD
    cur_pid = _resolve_donna_pid(pid)
    pending, patched = _bug_counts()
    tools_cell = ", ".join(recent) if recent else "—"
    thr = cascade_latency_threshold_ms()
    if cascade_ms is None:
        cascade_cell = "—"
    else:
        flag = " OVER THRESHOLD" if cascade_over else ""
        model_bit = f" `{cascade_model}`" if cascade_model else ""
        cascade_cell = f"{cascade_ms:.0f} ms{model_bit} (threshold {thr:.0f} ms){flag}"
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    body = (
        "# Donna Live Telemetry\n\n"
        f"_Updated: {stamp}_\n\n"
        "| Field | Value |\n"
        "| --- | --- |\n"
        f"| System Status | {cur_status} |\n"
        f"| Active PID | `{cur_pid}` |\n"
        f"| Last 3 tools (executed / forged) | {tools_cell} |\n"
        f"| Last high-complexity DeepSeek latency | {cascade_cell} |\n"
        f"| Bugs PENDING | {pending} |\n"
        f"| Bugs PATCHED | {patched} |\n"
    )
    tmp = DASHBOARD_PATH.with_suffix(".tmp")
    tmp.write_text(body, encoding="utf-8")
    tmp.replace(DASHBOARD_PATH)
    return str(DASHBOARD_PATH)


def _dashboard_loop() -> None:
    while not _DASHBOARD_STOP.wait(DASHBOARD_INTERVAL_SEC):
        try:
            write_dashboard()
        except Exception:  # noqa: BLE001
            pass


def start_dashboard_thread() -> None:
    """Start the 45s dashboard writer (idempotent)."""
    global _DASHBOARD_THREAD, _PID
    _PID = os.getpid()
    set_system_status("Healthy")
    try:
        write_dashboard()
    except Exception:  # noqa: BLE001
        pass
    if _DASHBOARD_THREAD is not None and _DASHBOARD_THREAD.is_alive():
        return
    _DASHBOARD_STOP.clear()
    _DASHBOARD_THREAD = threading.Thread(
        target=_dashboard_loop,
        name="DonnaDashboard",
        daemon=True,
    )
    _DASHBOARD_THREAD.start()


def stop_dashboard_thread() -> None:
    _DASHBOARD_STOP.set()


def snapshot() -> dict[str, Any]:
    with _LOCK:
        return {
            "status": _STATUS,
            "pid": _PID,
            "recent_tools": list(_RECENT_TOOLS),
            "cascade_latency_ms": _CASCADE_LAT_MS,
            "cascade_model": _CASCADE_MODEL,
            "cascade_over_threshold": _CASCADE_OVER_THRESHOLD,
        }
