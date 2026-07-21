"""Convert free-form execution_jail/input.txt batches into task_queue.json.

Split tasks on blank lines (paragraphs), append as pending queue objects,
then clear input.txt so the same batch is not ingested twice.

Empty / missing ``input.txt`` is silent (no log churn). Callers that poll in a
loop should pass ``empty_sleep`` (e.g. 0.75) to back off when there is nothing
to queue.
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
INPUT_FILE = _ROOT / "execution_jail" / "input.txt"
QUEUE_FILE = _ROOT / "execution_jail" / "task_queue.json"

# Default idle back-off for dedicated watch loops (seconds).
EMPTY_POLL_SLEEP_S = 0.75


def ingest_text_to_queue(*, empty_sleep: float = 0.0) -> int:
    """Ingest non-empty ``input.txt`` into ``task_queue.json``.

    Returns the number of tasks queued. Missing/empty files log nothing and
    optionally sleep ``empty_sleep`` seconds to avoid busy-poll CPU churn.
    """
    # 1. Check if input file exists and read it
    if not INPUT_FILE.is_file():
        if empty_sleep > 0:
            time.sleep(empty_sleep)
        return 0

    raw_text = INPUT_FILE.read_text(encoding="utf-8").strip()
    if not raw_text:
        if empty_sleep > 0:
            time.sleep(empty_sleep)
        return 0

    # 2. Split tasks by blank lines (tolerate Windows \r\n)
    raw_tasks = [
        task.strip()
        for task in re.split(r"\r?\n\s*\r?\n", raw_text)
        if task.strip()
    ]
    if not raw_tasks:
        if empty_sleep > 0:
            time.sleep(empty_sleep)
        return 0

    # 3. Load the existing queue so we don't overwrite pending tasks
    queue: list = []
    if QUEUE_FILE.is_file():
        try:
            loaded = json.loads(QUEUE_FILE.read_text(encoding="utf-8"))
            if isinstance(loaded, list):
                queue = loaded
        except json.JSONDecodeError:
            # If the file is corrupted or empty, start fresh
            queue = []

    # 4. Generate structured JSON objects for each task (10s dedupe + pending/running).
    try:
        from donna.tools.task_queue import (
            normalize_command_key,
            shadow_backup_before_write,
            try_record_command,
        )
    except Exception:  # noqa: BLE001
        normalize_command_key = lambda c: " ".join((c or "").strip().lower().split())  # noqa: E731
        try_record_command = lambda c: True  # noqa: E731
        shadow_backup_before_write = None

    existing_keys = {
        normalize_command_key(str(t.get("command") or ""))
        for t in queue
        if isinstance(t, dict) and t.get("status") in ("pending", "running")
    }
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    added = 0
    for i, text_command in enumerate(raw_tasks):
        key = normalize_command_key(text_command)
        if not key or key in existing_keys:
            continue
        if not try_record_command(text_command):
            continue
        queue.append(
            {
                "id": f"input_{timestamp}_{added + 1}",
                "status": "pending",
                "command": text_command,
            }
        )
        existing_keys.add(key)
        added += 1

    # 5. Always clear input.txt so the same batch cannot be re-read.
    INPUT_FILE.write_text("", encoding="utf-8")
    if added <= 0:
        return 0

    QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        if shadow_backup_before_write is not None:
            shadow_backup_before_write(QUEUE_FILE)
    except Exception:
        pass
    QUEUE_FILE.write_text(
        json.dumps(queue, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"[Ingest] Successfully added {added} task(s) to the queue.")
    print("[Ingest] Cleared input.txt")
    return added


def watch_input_txt(*, empty_sleep: float = EMPTY_POLL_SLEEP_S) -> None:
    """Poll ``input.txt`` forever; silent sleep when empty, log only on success."""
    while True:
        n = ingest_text_to_queue(empty_sleep=0.0)
        if n <= 0:
            time.sleep(max(0.1, float(empty_sleep)))


if __name__ == "__main__":
    watch_input_txt()
