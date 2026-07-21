"""Temporary wake-score probe — same mic path as Donna (16 kHz + openWakeWord).

Usage:
  python debug_wake.py           # settings.json mic_id
  python debug_wake.py 1         # force device index
  Ctrl+C to stop.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import sounddevice as sd

ROOT = Path(__file__).resolve().parent
SETTINGS = ROOT / "settings.json"
SAMPLE_RATE = 16000
WAKE_CHUNK = 1280  # 80 ms @ 16 kHz
THRESHOLD = 0.80


def load_mic() -> int:
    try:
        return int(json.loads(SETTINGS.read_text(encoding="utf-8")).get("mic_id", 1))
    except Exception:
        return 1


def resample(audio: np.ndarray, src: int, dst: int) -> np.ndarray:
    audio = np.asarray(audio, dtype=np.float32).reshape(-1)
    if src == dst or audio.size == 0:
        return audio
    n = max(1, int(round(audio.size * dst / float(src))))
    x0 = np.linspace(0.0, 1.0, num=audio.size, endpoint=False)
    x1 = np.linspace(0.0, 1.0, num=n, endpoint=False)
    return np.interp(x1, x0, audio).astype(np.float32)


def main() -> int:
    device_id = load_mic()
    for a in sys.argv[1:]:
        if a.isdigit():
            device_id = int(a)
            break

    info = sd.query_devices(device_id)
    name = info.get("name")
    rate = int(float(info.get("default_samplerate") or 44100))
    max_ch = int(info.get("max_input_channels") or 1)
    channels = 1 if max_ch >= 1 else max_ch
    # Prefer mono; fall back to stereo mean (matches MicIngest try 1 then 2).
    print(f"Device [{device_id}] {name}  native={rate}Hz max_ch={max_ch}")
    print(f"Loading openWakeWord from {ROOT / 'donna.onnx'} ...")

    from openwakeword.model import Model as OpenWakeWordModel

    onnx = ROOT / "donna.onnx"
    if not onnx.is_file():
        print(f"ERROR: missing {onnx}")
        return 1
    oww = OpenWakeWordModel(
        wakeword_models=[str(onnx)],
        inference_framework="onnx",
    )
    print(f"Models: {list(getattr(oww, 'models', {}).keys())}")
    print(f"Say 'Donna' now. Threshold={THRESHOLD}. Ctrl+C to stop.\n")

    native_chunk = max(1, int(round(WAKE_CHUNK * rate / float(SAMPLE_RATE))))
    peak_rms = 0.0
    peak_score = 0.0
    consec = 0

    try:
        with sd.InputStream(
            device=device_id,
            channels=channels,
            samplerate=rate,
            dtype="float32",
            blocksize=native_chunk,
            latency="high",
        ) as stream:
            while True:
                data, overflowed = stream.read(native_chunk)
                arr = np.asarray(data, dtype=np.float32)
                if arr.ndim > 1:
                    mono = arr.mean(axis=1)
                else:
                    mono = arr.reshape(-1)
                audio = resample(mono, rate, SAMPLE_RATE)
                if audio.size < WAKE_CHUNK:
                    pad = np.zeros(WAKE_CHUNK, dtype=np.float32)
                    pad[: audio.size] = audio
                    audio = pad
                else:
                    audio = audio[:WAKE_CHUNK]

                rms = float(np.sqrt(np.mean(np.square(audio))) + 1e-12)
                peak_rms = max(peak_rms, rms)
                pcm = np.clip(audio * 32767.0, -32768, 32767).astype(np.int16)
                try:
                    pred = oww.predict(pcm)
                except Exception:
                    pred = oww.predict(audio)
                pred = pred if isinstance(pred, dict) else {}
                best = 0.0
                best_key = ""
                for k, v in pred.items():
                    try:
                        fv = float(v)
                    except (TypeError, ValueError):
                        continue
                    if "donna" in str(k).lower() and fv >= best:
                        best = fv
                        best_key = str(k)
                peak_score = max(peak_score, best)
                hit = best >= THRESHOLD
                if hit:
                    consec += 1
                else:
                    consec = 0
                flag = "HIT" if consec >= 3 else ("HOT" if hit else ("LIVE" if rms > 0.001 else "flat"))
                ov = " OVFL" if overflowed else ""
                print(
                    f"RMS={rms:.6f} peak_rms={peak_rms:.6f}  "
                    f"score={best:.3f} peak_score={peak_score:.3f}  "
                    f"consec={consec} [{flag}] {best_key}{ov}",
                    flush=True,
                )
                time.sleep(0.01)
    except KeyboardInterrupt:
        print("\nStopped.", flush=True)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", flush=True)
        if channels == 1 and max_ch >= 2:
            print("Retry tip: device may need stereo — re-run after editing script.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
