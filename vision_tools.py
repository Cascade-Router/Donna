"""
On-demand vision capture agents for Jarvis.

ScreenAgent  - mss primary-monitor grab
VideoAgent   - cv2 webcam grab (MSMF/DSHOW resilient)

Both expose .get_frame() -> Optional[np.ndarray] (BGR, 640x480).
Frames are captured only when get_frame() is called (no background loops).
"""

from __future__ import annotations

import threading
import time
from typing import Optional

import cv2
import mss
import numpy as np

FRAME_SIZE = (640, 480)  # (width, height)


class ScreenAgent:
    """Lazy mss screen capture. Grabs only when get_frame() is called."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sct: Optional[mss.MSS] = None
        self._monitor: Optional[dict] = None
        self._fail_streak = 0

    def _ensure_open(self) -> bool:
        if self._sct is not None and self._monitor is not None:
            return True
        try:
            self._sct = mss.MSS()
            if len(self._sct.monitors) < 2:
                self._sct = None
                self._monitor = None
                return False
            self._monitor = self._sct.monitors[1]  # primary
            return True
        except Exception:
            self._sct = None
            self._monitor = None
            return False

    def get_frame(self) -> Optional[np.ndarray]:
        """Capture one primary-monitor frame resized to 640x480 BGR."""
        with self._lock:
            if not self._ensure_open():
                return None
            assert self._sct is not None and self._monitor is not None
            try:
                shot = self._sct.grab(self._monitor)
                frame = np.asarray(shot, dtype=np.uint8)
                if frame.ndim == 3 and frame.shape[2] == 4:
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                elif not (frame.ndim == 3 and frame.shape[2] == 3):
                    raise ValueError(f"Unexpected screen frame shape: {frame.shape}")

                w, h = FRAME_SIZE
                if frame.shape[1] != w or frame.shape[0] != h:
                    frame = cv2.resize(frame, FRAME_SIZE, interpolation=cv2.INTER_AREA)

                self._fail_streak = 0
                return frame
            except Exception:
                self._fail_streak += 1
                # Recreate mss handle after repeated failures.
                if self._fail_streak >= 5:
                    self.release()
                return None

    def release(self) -> None:
        with self._lock:
            self._sct = None
            self._monitor = None


class VideoAgent:
    """Lazy webcam capture via OpenCV. Handles Windows MSMF lock failures."""

    def __init__(self, camera_index: int = 0) -> None:
        self._lock = threading.Lock()
        self._camera_index = camera_index
        self._cap: Optional[cv2.VideoCapture] = None
        self._backend_name = "none"
        self._fail_streak = 0
        self._last_warn = 0.0

    def _open_backends(self) -> list[tuple[str, int]]:
        """Prefer DirectShow on Windows; fall back to MSMF then default."""
        backends: list[tuple[str, int]] = []
        if hasattr(cv2, "CAP_DSHOW"):
            backends.append(("DSHOW", cv2.CAP_DSHOW))
        if hasattr(cv2, "CAP_MSMF"):
            backends.append(("MSMF", cv2.CAP_MSMF))
        backends.append(("ANY", cv2.CAP_ANY if hasattr(cv2, "CAP_ANY") else 0))
        return backends

    def _ensure_open(self) -> bool:
        if self._cap is not None and self._cap.isOpened():
            return True
        self._close_unlocked()

        for name, backend in self._open_backends():
            try:
                cap = cv2.VideoCapture(self._camera_index, backend)
                if not cap.isOpened():
                    cap.release()
                    continue
                # Warm up / verify a readable frame (MSMF often opens then fails).
                ok, _ = cap.read()
                if not ok:
                    cap.release()
                    continue
                # Prefer a modest capture size close to our output.
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_SIZE[0])
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_SIZE[1])
                self._cap = cap
                self._backend_name = name
                self._fail_streak = 0
                return True
            except Exception:
                continue
        return False

    def _close_unlocked(self) -> None:
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:
                pass
            self._cap = None
            self._backend_name = "none"

    def get_frame(self) -> Optional[np.ndarray]:
        """Capture one webcam frame resized to 640x480 BGR. Safe on MSMF lock fail."""
        with self._lock:
            if not self._ensure_open():
                now = time.monotonic()
                if now - self._last_warn > 5.0:
                    self._last_warn = now
                return None
            assert self._cap is not None
            try:
                ok, frame = self._cap.read()
                if not ok or frame is None:
                    self._fail_streak += 1
                    # MSMF lock / device busy: release and retry next call.
                    if self._fail_streak >= 3:
                        self._close_unlocked()
                    return None

                w, h = FRAME_SIZE
                if frame.shape[1] != w or frame.shape[0] != h:
                    frame = cv2.resize(frame, FRAME_SIZE, interpolation=cv2.INTER_AREA)

                self._fail_streak = 0
                return frame
            except Exception:
                self._fail_streak += 1
                if self._fail_streak >= 3:
                    self._close_unlocked()
                return None

    def release(self) -> None:
        with self._lock:
            self._close_unlocked()
            self._fail_streak = 0
