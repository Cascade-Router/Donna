"""Thread-safe TTS barge-in controller (flush spool + hard-stop playback)."""

from __future__ import annotations

import logging
import threading
from typing import Any, Callable

_log = logging.getLogger("donna.audio.tts")

_FlushFn = Callable[[], int]
_StopFn = Callable[..., None]
_UiFn = Callable[[str], None]
_ResetStreamFn = Callable[[], None]


class TtsWorker:
    """Owns the barge-in flag and coordinates queue flush + hardware stop.

    Playback code registers the active ``OutputStream`` so ``interrupt()`` can
    ``abort()`` it without waiting on the writer’s ``playback_lock`` (avoids the
    race where ``sd.stop`` was deferred while a chunk write held the lock).
    """

    def __init__(self, *, barge_in_event: threading.Event | None = None) -> None:
        self._barge_in_event = barge_in_event or threading.Event()
        self._stream_lock = threading.Lock()
        self._active_stream: Any | None = None
        self._flush_fn: _FlushFn | None = None
        self._sd_stop_fn: _StopFn | None = None
        self._set_ui_fn: _UiFn | None = None
        self._reset_stream_fn: _ResetStreamFn | None = None
        self._busy_fn: Callable[[], bool] | None = None

    @property
    def barge_in_event(self) -> threading.Event:
        return self._barge_in_event

    def bind(
        self,
        *,
        flush_fn: _FlushFn | None = None,
        sd_stop_fn: _StopFn | None = None,
        set_ui_fn: _UiFn | None = None,
        reset_stream_fn: _ResetStreamFn | None = None,
        busy_fn: Callable[[], bool] | None = None,
    ) -> None:
        """Inject core_agent callbacks (keeps this module free of PortAudio imports)."""
        if flush_fn is not None:
            self._flush_fn = flush_fn
        if sd_stop_fn is not None:
            self._sd_stop_fn = sd_stop_fn
        if set_ui_fn is not None:
            self._set_ui_fn = set_ui_fn
        if reset_stream_fn is not None:
            self._reset_stream_fn = reset_stream_fn
        if busy_fn is not None:
            self._busy_fn = busy_fn

    def register_output_stream(self, stream: Any) -> None:
        with self._stream_lock:
            self._active_stream = stream

    def unregister_output_stream(self, stream: Any | None = None) -> None:
        with self._stream_lock:
            if stream is None or self._active_stream is stream:
                self._active_stream = None

    def is_set(self) -> bool:
        return self._barge_in_event.is_set()

    def clear(self) -> None:
        self._barge_in_event.clear()

    def interrupt(self, *, reason: str = "", set_listening: bool = True) -> int:
        """Hard barge-in: flag → flush spool → abort stream → stop device."""
        self._barge_in_event.set()

        dropped = 0
        if self._flush_fn is not None:
            try:
                dropped = int(self._flush_fn() or 0)
            except Exception as exc:  # noqa: BLE001
                _log.debug("TTS flush failed during interrupt: %s", exc)

        # Drop any LangGraph stream sentence fragments still coalescing into TTS.
        if self._reset_stream_fn is not None:
            try:
                self._reset_stream_fn()
            except Exception as exc:  # noqa: BLE001
                _log.debug("stream TTS reset failed during interrupt: %s", exc)

        stream = None
        with self._stream_lock:
            stream = self._active_stream
        if stream is not None:
            for meth in ("abort", "stop", "close"):
                fn = getattr(stream, meth, None)
                if not callable(fn):
                    continue
                try:
                    fn()
                    break
                except Exception:  # noqa: BLE001
                    continue

        if self._sd_stop_fn is not None:
            try:
                self._sd_stop_fn(where=f"barge_in:{reason or 'interrupt'}", blocking=False)
            except TypeError:
                try:
                    self._sd_stop_fn()
                except Exception as exc:  # noqa: BLE001
                    _log.debug("sd.stop failed during interrupt: %s", exc)
            except Exception as exc:  # noqa: BLE001
                _log.debug("sd.stop failed during interrupt: %s", exc)

        if set_listening and self._set_ui_fn is not None:
            try:
                self._set_ui_fn("listening")
            except Exception as exc:  # noqa: BLE001
                _log.debug("UI listening transition failed: %s", exc)

        if reason:
            _log.info("TTS barge-in (%s); flushed=%s", reason, dropped)
        return dropped

    def consume_if_set(self) -> bool:
        """If barge-in latched, clear it and return True (skip next spool item)."""
        if not self._barge_in_event.is_set():
            return False
        self._barge_in_event.clear()
        return True

    def is_tts_busy(self) -> bool:
        if self._busy_fn is None:
            return False
        try:
            return bool(self._busy_fn())
        except Exception:  # noqa: BLE001
            return False


_CONTROLLER: TtsWorker | None = None
_CONTROLLER_LOCK = threading.Lock()


def get_tts_worker(*, barge_in_event: threading.Event | None = None) -> TtsWorker:
    """Process-wide TTS barge-in controller (lazy singleton)."""
    global _CONTROLLER
    with _CONTROLLER_LOCK:
        if _CONTROLLER is None:
            _CONTROLLER = TtsWorker(barge_in_event=barge_in_event)
        elif barge_in_event is not None and _CONTROLLER.barge_in_event is not barge_in_event:
            # Keep a single shared Event object with core_agent.
            _CONTROLLER._barge_in_event = barge_in_event
        return _CONTROLLER
