"""Temporary mic RMS probe — find which PortAudio input actually hears you.

Usage:
  python debug_mic.py              # use settings.json mic_id (or default 1)
  python debug_mic.py 3            # force device index 3
  python debug_mic.py --scan       # auto-cycle input devices every ~8s if flat
  python debug_mic.py --list       # list input devices and exit

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
CHUNK_SEC = 0.5
FLAT_RMS = 0.001  # below this = likely deaf / wrong endpoint


def list_inputs() -> list[tuple[int, str, int, float]]:
    rows: list[tuple[int, str, int, float]] = []
    devices = sd.query_devices()
    for idx, dev in enumerate(devices):
        ch = int(dev.get("max_input_channels") or 0)
        if ch < 1:
            continue
        name = str(dev.get("name") or f"device-{idx}")
        rate = float(dev.get("default_samplerate") or 16000)
        rows.append((idx, name, ch, rate))
    return rows


def load_default_mic() -> int:
    try:
        cfg = json.loads(SETTINGS.read_text(encoding="utf-8"))
        return int(cfg.get("mic_id", 1))
    except Exception:
        return 1


def probe_device(device_id: int, duration_sec: float = 20.0) -> float:
    """Stream from device_id; print RMS every CHUNK_SEC. Return peak RMS seen."""
    devices = sd.query_devices()
    if device_id < 0 or device_id >= len(devices):
        print(f"[ERR] device {device_id} out of range (0..{len(devices) - 1})")
        return 0.0
    info = devices[device_id]
    if int(info.get("max_input_channels") or 0) < 1:
        print(f"[ERR] device {device_id} has no input channels: {info.get('name')}")
        return 0.0

    name = info.get("name")
    rate = int(float(info.get("default_samplerate") or 16000))
    channels = 1
    frames = max(1, int(rate * CHUNK_SEC))
    print("=" * 60)
    print(f"Probing INPUT [{device_id}] {name}")
    print(f"  rate={rate} Hz  channels={channels}  chunk={CHUNK_SEC}s")
    print("  Speak into the mic now. Ctrl+C to stop.")
    print("=" * 60)

    peak = 0.0
    t0 = time.perf_counter()
    try:
        with sd.InputStream(
            device=device_id,
            channels=channels,
            samplerate=rate,
            dtype="float32",
            blocksize=frames,
        ) as stream:
            while True:
                data, overflowed = stream.read(frames)
                mono = np.asarray(data, dtype=np.float32).reshape(-1)
                rms = float(np.sqrt(np.mean(np.square(mono))) + 1e-12)
                peak = max(peak, rms)
                flag = "FLAT" if rms < FLAT_RMS else "LIVE"
                ov = " OVERFLOW" if overflowed else ""
                elapsed = time.perf_counter() - t0
                print(
                    f"[{elapsed:6.1f}s] device={device_id}  "
                    f"RMS={rms:.6f}  peak={peak:.6f}  [{flag}]{ov}",
                    flush=True,
                )
                if duration_sec > 0 and elapsed >= duration_sec:
                    break
    except KeyboardInterrupt:
        print("\nStopped by user.", flush=True)
    except Exception as exc:  # noqa: BLE001
        print(f"[ERR] open/read failed on device {device_id}: {exc}", flush=True)
        return peak

    print(f"Done. peak_RMS={peak:.6f} on device {device_id}", flush=True)
    return peak


def scan_all(hold_sec: float = 8.0) -> None:
    """Cycle each input device; hold longer on LIVE hits."""
    rows = list_inputs()
    print(f"Found {len(rows)} input device(s). Cycling {hold_sec:.0f}s each.\n")
    results: list[tuple[int, str, float]] = []
    for idx, name, _ch, _rate in rows:
        print(f"\n>>> Next: [{idx}] {name}")
        peak = probe_device(idx, duration_sec=hold_sec)
        results.append((idx, name, peak))
        if peak >= FLAT_RMS:
            print(f"*** CANDIDATE [{idx}] peak={peak:.6f} — speak again if unsure")
    print("\n" + "=" * 60)
    print("SCAN SUMMARY (speak while each device was active):")
    for idx, name, peak in results:
        tag = "LIVE" if peak >= FLAT_RMS else "flat"
        print(f"  [{idx}] peak={peak:.6f}  [{tag}]  {name}")
    live = [r for r in results if r[2] >= FLAT_RMS]
    if live:
        best = max(live, key=lambda r: r[2])
        print(f"\nBest LIVE device: [{best[0]}] peak={best[2]:.6f}  {best[1]}")
    else:
        print("\nNo LIVE device found — check Windows privacy / Sonar routing.")


def main() -> int:
    args = sys.argv[1:]
    if "--list" in args or "-l" in args:
        print("Input devices:")
        for idx, name, ch, rate in list_inputs():
            print(f"  [{idx}] ch={ch} rate={rate:.0f}  {name}")
        try:
            default = sd.default.device[0]
            print(f"sounddevice default input: {default}")
        except Exception:
            pass
        return 0

    if "--scan" in args:
        scan_all(hold_sec=8.0)
        return 0

    device_id = load_default_mic()
    for a in args:
        if a.lstrip("-").isdigit() or (a.isdigit()):
            device_id = int(a)
            break

    print("Input devices:")
    for idx, name, ch, rate in list_inputs():
        mark = " <<<" if idx == device_id else ""
        print(f"  [{idx}] ch={ch} rate={rate:.0f}  {name}{mark}")
    print()
    # duration_sec=0 → run until Ctrl+C
    probe_device(device_id, duration_sec=0.0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
