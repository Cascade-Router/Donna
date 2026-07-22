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
    donna._tts_barge.end_playback()
    donna._tts_barge.begin_playback(interruptible=True)
    donna.speech_queue.put_nowait(("chunk-a", True))
    donna.speech_queue.put_nowait(("chunk-b", True))
    donna.tts_busy.set()

    dropped = trigger_tts_barge_in(reason="unit-test")

    assert donna.tts_interrupt_event.is_set()
    assert dropped >= 2
    assert donna.speech_queue.empty()
    donna._tts_barge.end_playback()
    print("[PASS] interrupt flushes spool + latches barge-in event")


def test_uninterruptible_ux_ack_ignores_barge_in() -> None:
    donna._bind_tts_barge_controller()
    donna.tts_interrupt_event.clear()
    donna.speech_queue.put_nowait(("Yes?", False))
    donna._tts_barge.begin_playback(interruptible=False)
    donna.tts_busy.set()

    dropped = trigger_tts_barge_in(reason="self-bleed")

    assert dropped == 0
    assert not donna.tts_interrupt_event.is_set()
    assert not donna.speech_queue.empty()
    donna._tts_barge.end_playback()
    donna.flush_tts_queue()
    donna.tts_busy.clear()
    print("[PASS] uninterruptible UX ack ignores barge-in")


def test_tts_worker_skips_chunk_when_barge_latched() -> None:
    worker = TtsWorker()
    worker.interrupt(reason="prelatch")
    assert worker.consume_if_set() is True
    assert worker.is_set() is False
    assert worker.consume_if_set() is False
    print("[PASS] barge latch consume/clear for next spool item")


def test_playback_grace_suppresses_onset_window() -> None:
    """First 400ms after begin_playback must report in_playback_grace."""
    worker = TtsWorker()
    worker.begin_playback(interruptible=True)
    assert worker.in_playback_grace(grace_s=0.4) is True
    time.sleep(0.45)
    assert worker.in_playback_grace(grace_s=0.4) is False
    worker.end_playback()
    assert worker.in_playback_grace(grace_s=0.4) is False
    assert donna.BARGE_IN_SILERO_THRESHOLD == 0.85
    assert donna.BARGE_IN_SILERO_CONSEC_FRAMES == 4
    assert donna.BARGE_IN_PLAYBACK_GRACE_MS == 400.0
    print("[PASS] playback grace + hardened Silero barge thresholds")


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
