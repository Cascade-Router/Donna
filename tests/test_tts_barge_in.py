"""Unit tests for VAD-triggered TTS barge-in (no live mic/speakers)."""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock

import numpy as np

import donna.core_agent as donna
from donna.audio.tts_worker import TtsWorker, get_tts_worker
from donna.audio.vad_consumer import trigger_tts_barge_in


def test_interrupt_flushes_queue_and_sets_event() -> None:
    donna._bind_tts_barge_controller()
    donna.tts_interrupt_event.clear()
    donna.speech_queue.put_nowait("chunk-a")
    donna.speech_queue.put_nowait("chunk-b")
    donna.tts_busy.set()

    dropped = trigger_tts_barge_in(reason="unit-test")

    assert donna.tts_interrupt_event.is_set()
    assert dropped >= 2
    assert donna.speech_queue.empty()
    print("[PASS] interrupt flushes spool + latches barge-in event")


def test_tts_worker_skips_chunk_when_barge_latched() -> None:
    worker = TtsWorker()
    worker.interrupt(reason="prelatch")
    assert worker.consume_if_set() is True
    assert worker.is_set() is False
    assert worker.consume_if_set() is False
    print("[PASS] barge latch consume/clear for next spool item")


def test_active_stream_abort_on_interrupt() -> None:
    stream = MagicMock()
    worker = get_tts_worker(barge_in_event=donna.tts_interrupt_event)
    donna._bind_tts_barge_controller()
    donna.tts_interrupt_event.clear()
    worker.register_output_stream(stream)

    worker.interrupt(reason="abort-stream")

    stream.abort.assert_called()
    worker.unregister_output_stream(stream)
    print("[PASS] interrupt aborts registered OutputStream")


def test_play_pcm_respects_barge_in_quickly() -> None:
    """Simulate long PCM; interrupt from another thread mid-playback."""
    donna._bind_tts_barge_controller()
    donna.tts_interrupt_event.clear()
    donna.stop_event.clear()

    # ~2s of silence @ 16 kHz — interrupt should cut well before full duration.
    audio = np.zeros(32000, dtype=np.float32)
    t0 = time.perf_counter()

    def _barge() -> None:
        time.sleep(0.05)
        trigger_tts_barge_in(reason="sim-barge")

    threading.Thread(target=_barge, daemon=True).start()
    # Use fallback path if OutputStream unavailable in CI — still checks event.
    interrupted = donna._play_pcm_interruptible(audio, 16000, None)
    elapsed = time.perf_counter() - t0

    assert interrupted is True
    assert elapsed < 1.5, f"barge-in too slow ({elapsed:.2f}s)"
    print(f"[PASS] playback aborted on barge-in ({elapsed:.2f}s)")
