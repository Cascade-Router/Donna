"""Barge-in interrupt plumbing tests (no live mic/speaker required)."""

from __future__ import annotations

import threading
import time

import numpy as np

import donna.core_agent as donna


def test_flush_speech_queue() -> None:
    donna.flush_speech_queue()
    donna.speech_queue.put_nowait("one")
    donna.speech_queue.put_nowait("two")
    assert donna.flush_speech_queue() == 2
    assert donna.speech_queue.empty()
    print("[PASS] flush_speech_queue")


def test_play_pcm_respects_interrupt_event() -> None:
    donna.tts_interrupt_event.clear()
    # ~1s of silence @ 16 kHz — interrupt after 80ms.
    audio = np.zeros(16000, dtype=np.float32)

    def _trip() -> None:
        time.sleep(0.08)
        donna.tts_interrupt_event.set()

    threading.Thread(target=_trip, daemon=True).start()
    t0 = time.perf_counter()
    interrupted = donna._play_pcm_interruptible(audio, 16000, None)
    elapsed = time.perf_counter() - t0
    donna.tts_interrupt_event.clear()
    assert interrupted is True
    assert elapsed < 0.6, f"playback did not abort quickly ({elapsed:.2f}s)"
    print(f"[PASS] interruptible playback aborted in {elapsed:.2f}s")


def test_tts_interrupt_event_exists() -> None:
    assert isinstance(donna.tts_interrupt_event, threading.Event)
    print("[PASS] tts_interrupt_event is a threading.Event")


if __name__ == "__main__":
    test_tts_interrupt_event_exists()
    test_flush_speech_queue()
    test_play_pcm_respects_interrupt_event()
    print("OK")
