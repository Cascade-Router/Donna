"""Lazy YOLOv8 singleton — weights load on first vision use only."""

from __future__ import annotations

import threading
from typing import Any, Optional

_yolo_lock = threading.Lock()
_yolo_model: Optional[Any] = None
_yolo_weights: Optional[str] = None


def yolo_is_loaded() -> bool:
    """True once ``YOLO(weights)`` has succeeded at least once."""
    return _yolo_model is not None


def get_yolo_model(weights: str) -> Any:
    """Return the shared YOLOv8 model, loading ``weights`` on first call only.

    Import of ``ultralytics`` and disk load of ``yolov8n.pt`` are deferred until
    Vision mode is active or a frame is explicitly processed for detection.
    """
    global _yolo_model, _yolo_weights
    if _yolo_model is not None:
        return _yolo_model
    with _yolo_lock:
        if _yolo_model is not None:
            return _yolo_model
        from ultralytics import YOLO

        _yolo_model = YOLO(weights)
        _yolo_weights = weights
        return _yolo_model


def reset_yolo_model() -> None:
    """Drop the cached model (tests / forced reload)."""
    global _yolo_model, _yolo_weights
    with _yolo_lock:
        _yolo_model = None
        _yolo_weights = None
