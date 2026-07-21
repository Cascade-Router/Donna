"""
Train a custom OpenWakeWord model for "Donna" and copy it to ./donna.onnx.

Windows-friendly adaptations vs the original Colab-oriented script:
- Skips TFLite-only packages
- Avoids broken AudioSet tar URLs (uses ESC-50 backgrounds)
- Avoids the 17 GB ACAV feature dump (uses validation features for negatives)
- Clones piper-sample-generator for synthetic clip generation
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

import yaml


def run_cmd(cmd: str) -> None:
    """Helper to run shell commands cross-platform."""
    print(f"Running: {cmd}", flush=True)
    subprocess.check_call(cmd, shell=True)


def download_file(url: str, output_path: str) -> None:
    """Download a file with a simple progress callback."""
    if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
        print(f"File {output_path} already exists. Skipping download.", flush=True)
        return

    print(f"Downloading {url} to {output_path}...", flush=True)
    last_pct = [-1]

    def _reporthook(block_num: int, block_size: int, total_size: int) -> None:
        if total_size <= 0:
            return
        downloaded = block_num * block_size
        pct = min(100, int(downloaded * 100 / total_size))
        if pct != last_pct[0] and pct % 5 == 0:
            last_pct[0] = pct
            print(f"  {pct}% ({downloaded / (1024 * 1024):.1f} / {total_size / (1024 * 1024):.1f} MB)", flush=True)

    tmp = output_path + ".partial"
    try:
        urllib.request.urlretrieve(url, tmp, reporthook=_reporthook)
        os.replace(tmp, output_path)
    except Exception:
        if os.path.isfile(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
        raise


def patch_openwakeword_soundfile_load() -> None:
    """torchaudio>=2.9 load() requires torchcodec; use soundfile on Windows instead."""
    data_py = Path("openwakeword/openwakeword/data.py")
    if not data_py.is_file():
        return
    text = data_py.read_text(encoding="utf-8")
    if "_load_audio_soundfile" in text:
        return
    needle = "import torchaudio\n"
    if needle not in text:
        print("[Warning] Could not patch data.py for soundfile load.", flush=True)
        return
    patch = (
        "import torchaudio\n"
        "import soundfile as sf\n"
        "\n"
        "def _load_audio_soundfile(uri, *args, **kwargs):\n"
        "    data, sample_rate = sf.read(uri, dtype=\"float32\")\n"
        "    if getattr(data, \"ndim\", 1) > 1:\n"
        "        data = data.mean(axis=1)\n"
        "    return torch.from_numpy(np.ascontiguousarray(data)).unsqueeze(0), int(sample_rate)\n"
        "\n"
        "torchaudio.load = _load_audio_soundfile\n"
    )
    data_py.write_text(text.replace(needle, patch, 1), encoding="utf-8")
    print(f"[Patch] Routed torchaudio.load via soundfile in {data_py}", flush=True)


def patch_openwakeword_train_piper_model() -> None:
    """Newer generate_samples() requires model=; openWakeWord train.py omits it."""
    train_py = Path("openwakeword/openwakeword/train.py")
    if not train_py.is_file():
        return
    text = train_py.read_text(encoding="utf-8")
    marker = "from generate_samples import generate_samples as _generate_samples"
    if marker in text:
        return
    old = "from generate_samples import generate_samples"
    if old not in text:
        print("[Warning] Could not patch train.py for Piper model path.", flush=True)
        return
    new = (
        "from generate_samples import generate_samples as _generate_samples\n"
        "    _piper_model = os.path.abspath(os.path.join(\n"
        "        config[\"piper_sample_generator_path\"],\n"
        "        \"models\",\n"
        "        \"en_US-libritts_r-medium.pt\",\n"
        "    ))\n"
        "    def generate_samples(*args, **kwargs):\n"
        "        kwargs.setdefault(\"model\", _piper_model)\n"
        "        return _generate_samples(*args, **kwargs)"
    )
    train_py.write_text(text.replace(old, new, 1), encoding="utf-8")
    print(f"[Patch] Injected Piper model default into {train_py}", flush=True)


def patch_torchaudio_compat() -> None:
    """torch_audiomentations 0.11 breaks on torchaudio>=2.9 (no set_audio_backend)."""
    try:
        import torch_audiomentations.utils.io as io_mod
    except Exception:
        path = (
            Path(sys.executable).resolve().parent.parent
            / "Lib"
            / "site-packages"
            / "torch_audiomentations"
            / "utils"
            / "io.py"
        )
        if not path.is_file():
            return
        text = path.read_text(encoding="utf-8")
        if "hasattr(torchaudio, \"set_audio_backend\")" in text:
            return
        text = text.replace(
            "torchaudio.USE_SOUNDFILE_LEGACY_INTERFACE = False\n"
            "torchaudio.set_audio_backend(\"soundfile\")\n",
            "if hasattr(torchaudio, \"USE_SOUNDFILE_LEGACY_INTERFACE\"):\n"
            "    torchaudio.USE_SOUNDFILE_LEGACY_INTERFACE = False\n"
            "if hasattr(torchaudio, \"set_audio_backend\"):\n"
            "    torchaudio.set_audio_backend(\"soundfile\")\n",
        )
        path.write_text(text, encoding="utf-8")
        print(f"[Patch] Updated {path} for torchaudio compatibility.", flush=True)
        return

    # Import succeeded — already compatible or patched.
    _ = io_mod


def setup_environment() -> None:
    """Installs necessary packages and clones repositories."""
    print("--- Step 1: Setting up environment ---", flush=True)
    patch_torchaudio_compat()


    if not os.path.exists("openwakeword"):
        run_cmd("git clone https://github.com/dscripka/openwakeword")
    run_cmd(f"{sys.executable} -m pip install -e ./openwakeword --no-deps")

    if not os.path.exists("piper-sample-generator"):
        run_cmd("git clone https://github.com/rhasspy/piper-sample-generator")
    # openWakeWord imports root-level generate_samples.py; pin pre-package-layout commit.
    try:
        run_cmd("git -C piper-sample-generator checkout c9d824c")
    except subprocess.CalledProcessError:
        run_cmd("git -C piper-sample-generator fetch --depth 50 origin master")
        run_cmd("git -C piper-sample-generator checkout c9d824c")

    models_piper = Path("piper-sample-generator/models")
    models_piper.mkdir(parents=True, exist_ok=True)
    download_file(
        "https://github.com/rhasspy/piper-sample-generator/releases/download/v2.0.0/en_US-libritts_r-medium.pt",
        str(models_piper / "en_US-libritts_r-medium.pt"),
    )
    patch_openwakeword_train_piper_model()
    patch_openwakeword_soundfile_load()

    deps = [
        "pyyaml",
        "scipy",
        "tqdm",
        "mutagen==1.47.0",
        "torchinfo==1.8.0",
        "torchmetrics==1.2.0",
        "speechbrain==0.5.14",
        "audiomentations==0.33.0",
        "torch-audiomentations==0.11.0",
        "acoustics==0.2.6",
        "onnxruntime",
        "onnx",
        "pronouncing==0.2.0",
        "deep-phonemizer==0.0.19",
        "piper-tts",
        "soundfile",
        "numpy",
    ]
    run_cmd(f"{sys.executable} -m pip install {' '.join(deps)}")

    models_dir = "./openwakeword/openwakeword/resources/models"
    os.makedirs(models_dir, exist_ok=True)
    base_url = "https://github.com/dscripka/openWakeWord/releases/download/v0.5.1/"
    for model_file in [
        "embedding_model.onnx",
        "embedding_model.tflite",
        "melspectrogram.onnx",
        "melspectrogram.tflite",
    ]:
        download_file(base_url + model_file, os.path.join(models_dir, model_file))


def download_data() -> None:
    """Downloads RIR / background / validation feature datasets."""
    import numpy as np
    import scipy.io.wavfile
    import soundfile as sf
    from tqdm import tqdm

    print("--- Step 2: Downloading Data (This may take a while) ---", flush=True)

    mit_rirs_dir = "./mit_rirs"
    rir_src = Path("./MIT_environmental_impulse_responses/16khz")
    if not os.path.exists(mit_rirs_dir) or not any(Path(mit_rirs_dir).glob("*.wav")):
        os.makedirs(mit_rirs_dir, exist_ok=True)
        if not rir_src.is_dir():
            run_cmd(
                "git clone https://huggingface.co/datasets/davidscripka/MIT_environmental_impulse_responses"
            )
        wavs = list(rir_src.glob("*.wav"))
        if not wavs:
            raise RuntimeError(f"No RIR wavs found under {rir_src}")
        for src in tqdm(wavs, desc="Copying RIR data"):
            dest = Path(mit_rirs_dir) / src.name
            if dest.exists():
                continue
            rate, data = scipy.io.wavfile.read(str(src))
            scipy.io.wavfile.write(str(dest), rate, data)

    output_dir = Path("./audioset_16k")
    if not output_dir.exists() or not any(output_dir.glob("*.wav")):
        output_dir.mkdir(parents=True, exist_ok=True)
        esc_zip = "esc50.zip"
        esc_url = "https://github.com/karolpiczak/ESC-50/archive/master.zip"
        try:
            download_file(esc_url, esc_zip)
            with zipfile.ZipFile(esc_zip, "r") as zf:
                zf.extractall("esc50_src")
            wavs = list(Path("esc50_src").glob("**/audio/*.wav"))
            if not wavs:
                wavs = list(Path("esc50_src").glob("**/*.wav"))
            for src in tqdm(wavs, desc="Preparing ESC-50 background WAVs"):
                dest = output_dir / src.name
                if dest.exists():
                    continue
                audio, rate = sf.read(str(src), dtype="float32")
                if audio.ndim > 1:
                    audio = audio.mean(axis=1)
                if rate != 16000:
                    duration = len(audio) / float(rate)
                    new_len = max(1, int(round(duration * 16000)))
                    x_old = np.linspace(0.0, 1.0, num=len(audio), endpoint=False)
                    x_new = np.linspace(0.0, 1.0, num=new_len, endpoint=False)
                    audio = np.interp(x_new, x_old, audio.astype(np.float64)).astype(np.float32)
                pcm = np.clip(audio * 32767.0, -32768, 32767).astype(np.int16)
                scipy.io.wavfile.write(str(dest), 16000, pcm)
        except Exception as esc_exc:  # noqa: BLE001
            print(
                f"[Warning] ESC-50 download failed ({esc_exc}); using MIT RIRs as background.",
                flush=True,
            )
            for src in list(Path(mit_rirs_dir).glob("*.wav"))[:80]:
                dest = output_dir / src.name
                if not dest.exists():
                    dest.write_bytes(src.read_bytes())

    if not any(output_dir.glob("*.wav")):
        raise RuntimeError("No background WAVs available under audioset_16k/")

    # Use the ~185 MB validation feature set instead of the 17 GB ACAV dump.
    print(
        "[Info] Using validation_set_features.npy for negative training features "
        "(skips 17 GB ACAV download). Quality is lower than full Colab training, "
        "but enough to produce a working donna.onnx.",
        flush=True,
    )
    download_file(
        "https://huggingface.co/datasets/davidscripka/openwakeword_features/resolve/main/validation_set_features.npy",
        "./validation_set_features.npy",
    )


def resample_training_clips_to_16k(model_dir: str = "./my_custom_model/donna") -> None:
    """Piper libritts clips are 22050 Hz; openWakeWord augmentation requires 16 kHz."""
    import numpy as np
    import soundfile as sf
    from tqdm import tqdm

    root = Path(model_dir)
    wavs = []
    for sub in ("positive_train", "positive_test", "negative_train", "negative_test"):
        wavs.extend((root / sub).glob("*.wav"))
    if not wavs:
        return

    converted = 0
    for path in tqdm(wavs, desc="Resampling clips to 16 kHz"):
        audio, rate = sf.read(str(path), dtype="float32")
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        if int(rate) == 16000:
            continue
        duration = len(audio) / float(rate)
        new_len = max(1, int(round(duration * 16000)))
        x_old = np.linspace(0.0, 1.0, num=len(audio), endpoint=False)
        x_new = np.linspace(0.0, 1.0, num=new_len, endpoint=False)
        audio = np.interp(x_new, x_old, audio.astype(np.float64)).astype(np.float32)
        sf.write(str(path), audio, 16000)
        converted += 1
    print(f"[Info] Resampled {converted} clips to 16 kHz under {root}", flush=True)


def train_wakeword(target_word: str = "hey donna") -> None:
    """Configures and runs the openWakeWord training script."""
    print(f"--- Step 3: Training model for '{target_word}' ---", flush=True)

    config_path = "my_model.yaml"
    config = yaml.safe_load(open("openwakeword/examples/custom_model.yml", "r", encoding="utf-8"))

    model_name = "donna"
    config["target_phrase"] = [target_word, "donna"]
    config["model_name"] = model_name
    config["n_samples"] = 1500
    config["n_samples_val"] = 400
    config["steps"] = 12000
    config["tts_batch_size"] = 8
    config["augmentation_batch_size"] = 8
    config["augmentation_rounds"] = 1
    config["output_dir"] = "./my_custom_model"
    config["max_negative_weight"] = 400
    config["piper_sample_generator_path"] = "./piper-sample-generator"
    config["rir_paths"] = ["./mit_rirs"]
    config["background_paths"] = ["./audioset_16k"]
    config["background_paths_duplication_rate"] = [1]
    config["false_positive_validation_data_path"] = "./validation_set_features.npy"
    # Reuse validation features as the negative feature pool (smaller / practical).
    config["feature_data_files"] = {"validation_negatives": "./validation_set_features.npy"}
    config["batch_n_per_class"] = {
        # Flat validation features are windowed by 16; ~1100 rows => ~68 negative windows.
        "validation_negatives": 1100,
        "adversarial_negative": 32,
        "positive": 64,
    }

    with open(config_path, "w", encoding="utf-8") as file:
        yaml.dump(config, file)

    train_script = "openwakeword/openwakeword/train.py"

    print("Generating clips...", flush=True)
    run_cmd(f"{sys.executable} {train_script} --training_config {config_path} --generate_clips")
    resample_training_clips_to_16k(os.path.join(config["output_dir"], model_name))

    print("Augmenting clips...", flush=True)
    run_cmd(f"{sys.executable} {train_script} --training_config {config_path} --augment_clips")

    print("Training model...", flush=True)
    run_cmd(f"{sys.executable} {train_script} --training_config {config_path} --train_model")

    dest = os.path.join(os.path.dirname(os.path.abspath(__file__)), "donna.onnx")
    candidates = [
        Path(f"my_custom_model/{model_name}.onnx"),
        *Path("./my_custom_model").rglob("*.onnx"),
    ]
    for candidate in candidates:
        if candidate.is_file() and candidate.stat().st_size > 0:
            shutil.copy2(str(candidate), dest)
            print(f"\nSUCCESS! Model ready at: {candidate}", flush=True)
            print(f"Copied to agent path: {dest}", flush=True)
            return

    print("\nSomething went wrong, model file not found.", flush=True)
    raise SystemExit(1)


if __name__ == "__main__":
    setup_environment()
    download_data()
    train_wakeword(target_word="hey donna")
