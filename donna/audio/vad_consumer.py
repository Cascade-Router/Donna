"""VAD / wake-word onset hooks that trigger TTS barge-in."""

from __future__ import annotations

from donna.audio.tts_worker import get_tts_worker


def trigger_tts_barge_in(*, reason: str = "vad_onset") -> int:
    """Invoke when valid speech / wake-word is detected while TTS is playing.

    Safe to call from the barge-in watcher or ``record_utterance`` VAD path.
    Returns the number of flushed TTS spool items.
    """
    return get_tts_worker().interrupt(reason=reason, set_listening=True)
