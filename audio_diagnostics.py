"""
Donna audio diagnostics — one-click mic/speaker/TTS hardware check.

Usage:
  python audio_diagnostics.py
  python audio_diagnostics.py --mic 1 --speaker 9
"""

from __future__ import annotations

import argparse
import os
import sys

import numpy as np
import sounddevice as sd
import soundfile as sf
from piper import PiperVoice


def list_devices() -> None:
    devices = sd.query_devices()
    hostapis = sd.query_hostapis()
    print("\n=== INPUT devices ===")
    print(f"{'Index':<7} {'Rate':<8} {'Ch':<4} {'HostAPI':<18} Name")
    print("-" * 72)
    for idx, dev in enumerate(devices):
        if int(dev.get("max_input_channels", 0)) < 1:
            continue
        try:
            api = str(hostapis[int(dev["hostapi"])]["name"])
        except Exception:
            api = "?"
        rate = int(round(float(dev.get("default_samplerate", 0))))
        print(
            f"{idx:<7} {rate:<8} {int(dev['max_input_channels']):<4} "
            f"{api:<18} {dev.get('name', '')}"
        )

    print("\n=== OUTPUT devices ===")
    print(f"{'Index':<7} {'Rate':<8} {'Ch':<4} {'HostAPI':<18} Name")
    print("-" * 72)
    for idx, dev in enumerate(devices):
        if int(dev.get("max_output_channels", 0)) < 1:
            continue
        try:
            api = str(hostapis[int(dev["hostapi"])]["name"])
        except Exception:
            api = "?"
        rate = int(round(float(dev.get("default_samplerate", 0))))
        print(
            f"{idx:<7} {rate:<8} {int(dev['max_output_channels']):<4} "
            f"{api:<18} {dev.get('name', '')}"
        )

    try:
        din, dout = sd.default.device
        print(f"\nDefault input:  [{din}]")
        print(f"Default output: [{dout}]")
    except Exception as exc:  # noqa: BLE001
        print(f"Could not read defaults: {exc}")


def record_and_playback(mic: int | None, speaker: int | None, seconds: float = 7.0) -> None:
    devices = sd.query_devices()
    if mic is None:
        mic = sd.default.device[0]
    if speaker is None:
        speaker = sd.default.device[1]

    mic = int(mic)
    speaker = int(speaker)
    if mic < 0 or mic >= len(devices) or int(devices[mic].get("max_input_channels", 0)) < 1:
        raise SystemExit(f"Invalid mic index: {mic}")
    if (
        speaker < 0
        or speaker >= len(devices)
        or int(devices[speaker].get("max_output_channels", 0)) < 1
    ):
        raise SystemExit(f"Invalid speaker index: {speaker}")

    rate = int(round(float(devices[mic].get("default_samplerate", 44100))))
    channels = 1
    print(f"\nRecording for {seconds:.0f} seconds... Speak now!", flush=True)
    print(f"Recording {seconds:.0f}s from mic [{mic}] @ {rate} Hz...", flush=True)
    audio = sd.rec(
        int(seconds * rate),
        samplerate=rate,
        channels=channels,
        dtype="float32",
        device=mic,
    )
    sd.wait()
    peak = float(np.max(np.abs(audio))) if audio.size else 0.0
    print(f"Capture peak amplitude: {peak:.4f}")
    if peak < 1e-4:
        print("WARNING: recording looks silent — check mic selection / permissions.")

    out_rate = int(round(float(devices[speaker].get("default_samplerate", rate))))
    print(f"Playing back through speaker [{speaker}] @ {out_rate} Hz...")
    play = audio
    if out_rate != rate and audio.size:
        # Simple linear resample for diagnostics only.
        src = audio.reshape(-1)
        dst_len = max(1, int(round(src.size * out_rate / float(rate))))
        x_old = np.linspace(0.0, 1.0, num=src.size, endpoint=False)
        x_new = np.linspace(0.0, 1.0, num=dst_len, endpoint=False)
        play = np.interp(x_new, x_old, src).astype(np.float32)
    sd.play(play, samplerate=out_rate, device=speaker, blocking=True)
    print("Playback complete.")


def tts_test(speaker: int | None) -> None:
    print("\nTTS test (piper-tts)...")
    # Reuse Donna's downloader / English voice when available.
    from donna.core_agent import PIPER_EN_ONNX, download_piper_models, synthesize_to_file

    download_piper_models()
    voice = PiperVoice.load(PIPER_EN_ONNX)
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp_reply.wav")
    try:
        synthesize_to_file(voice, "Audio diagnostics online. Donna speaker test.", path)
        audio, rate = sf.read(path, dtype="float32")
        kwargs = {"samplerate": int(rate), "blocking": True}
        if speaker is not None:
            kwargs["device"] = speaker
        sd.play(audio, **kwargs)
        print("TTS playback complete.")
    finally:
        try:
            if os.path.isfile(path):
                os.remove(path)
        except OSError:
            pass


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Donna audio hardware diagnostics.")
    p.add_argument("--mic", type=int, default=None, help="Input device index")
    p.add_argument("--speaker", type=int, default=None, help="Output device index")
    p.add_argument("--seconds", type=float, default=7.0, help="Record duration (default: 7)")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    print("=== Donna Audio Diagnostics ===")
    list_devices()
    try:
        record_and_playback(args.mic, args.speaker, seconds=args.seconds)
        tts_test(args.speaker)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print("\nAll diagnostics finished.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
