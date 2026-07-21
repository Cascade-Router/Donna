"""TTS timeout / deadlock recovery tests (no live Piper or speakers)."""

from __future__ import annotations

import threading
import time
from unittest.mock import patch

import donna.core_agent as donna


def test_reset_tts_audio_state_releases_wake_word_gates() -> None:
    donna.speech_queue.put_nowait("stale")
    donna.tts_busy.set()
    donna.speech_idle.clear()
    donna.vad_capture_active.set()

    dropped = donna.reset_tts_audio_state("unit test", ui_state="idle")

    assert dropped == 1
    assert donna.speech_queue.empty()
    assert not donna.tts_busy.is_set()
    assert donna.speech_idle.is_set()
    assert not donna.vad_capture_active.is_set()
    print("[PASS] reset_tts_audio_state releases gates")


def test_wait_for_speech_idle_timeout_resets_state() -> None:
    donna.tts_busy.set()
    donna.speech_idle.clear()
    donna.speech_queue.put_nowait("orphaned")

    t0 = time.perf_counter()
    donna.wait_for_speech_idle(timeout=0.15)
    elapsed = time.perf_counter() - t0

    assert elapsed < 1.0
    assert donna.speech_idle.is_set()
    assert not donna.tts_busy.is_set()
    assert donna.speech_queue.empty()
    print(f"[PASS] wait_for_speech_idle timeout recovery ({elapsed:.2f}s)")


def test_speak_with_timeout_aborts_hung_utterance() -> None:
    hang = threading.Event()

    def _hang_forever(_text: str, _device: object) -> bool:
        hang.wait(timeout=5.0)
        return False

    donna.tts_interrupt_event.clear()
    with patch.object(donna, "speak_text", side_effect=_hang_forever):
        t0 = time.perf_counter()
        interrupted = donna._speak_with_timeout("test", None, max_seconds=0.2)
        elapsed = time.perf_counter() - t0

    hang.set()
    assert interrupted is True
    assert elapsed < 1.5, f"timeout wrapper too slow ({elapsed:.2f}s)"
    print(f"[PASS] _speak_with_timeout aborted hung utterance ({elapsed:.2f}s)")


def test_portaudio_fault_signals_main_soft_restart() -> None:
    donna.audio_hardware_fault.clear()
    donna.consume_audio_hardware_fault()

    class _PaErr(Exception):
        pass

    _PaErr.__name__ = "PortAudioError"
    exc = _PaErr("Device unavailable [PaErrorCode -9999]")
    donna.report_audio_hardware_fault(exc, where="unit-test")

    assert donna.audio_hardware_fault.is_set()
    detail = donna.consume_audio_hardware_fault()
    assert "PaErrorCode" in detail or "PortAudioError" in detail
    assert not donna.audio_hardware_fault.is_set()

    # Soft recover should clear TTS gates without raising.
    donna.tts_busy.set()
    donna.speech_idle.clear()
    donna.soft_recover_audio_hardware(detail)
    assert donna.speech_idle.is_set()
    assert not donna.tts_busy.is_set()
    print("[PASS] PortAudio fault propagates to Main soft-restart")


if __name__ == "__main__":
    test_reset_tts_audio_state_releases_wake_word_gates()
    test_wait_for_speech_idle_timeout_resets_state()
    test_speak_with_timeout_aborts_hung_utterance()
    test_portaudio_fault_signals_main_soft_restart()
    print("OK")
