"""Standalone worker for `resemble_enhance_audio_cleaner.ResembleEnhanceAudioCleaner`.

Runs under its own isolated Python 3.11 virtualenv (see that module for why:
resemble-enhance pins torch==2.1.1, which has no wheels for the main
project's Python version), invoked as a subprocess rather than imported -
this file's imports are only ever satisfied there, never in the main app's
venv.

Usage: python resemble_enhance_worker.py <input.wav> <output.wav> <denoise|enhance>
"""

import pathlib
import sys
import urllib.request

import soundfile as sf
import torch
from resemble_enhance.enhancer.inference import denoise, enhance

_RUN_BY_MODE = {"denoise": denoise, "enhance": enhance}

# The pinned resemble-enhance==0.0.1's own downloader shells out to
# `git lfs pull`, which isn't available here (and would need a sudo install
# to fix) - so this fetches the same three files straight over HTTPS
# instead, into a cache directory we pass in as `run_dir` rather than
# letting the library manage its own model_repo/ under site-packages.
_MODEL_BASE_URL = "https://huggingface.co/ResembleAI/resemble-enhance/resolve/main/enhancer_stage2"
_MODEL_FILES = ["hparams.yaml", "ds/G/latest", "ds/G/default/mp_rank_00_model_states.pt"]
_MODEL_CACHE_DIR = pathlib.Path.home() / ".cache" / "resemble-enhance" / "enhancer_stage2"


def _ensure_model_downloaded(run_dir: pathlib.Path) -> None:
    for relpath in _MODEL_FILES:
        path = run_dir / relpath
        if path.exists():
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        print(f"Downloading {relpath}...", file=sys.stderr)
        urllib.request.urlretrieve(f"{_MODEL_BASE_URL}/{relpath}?download=true", path)


def main() -> None:
    input_path, output_path, mode = sys.argv[1], sys.argv[2], sys.argv[3]
    run = _RUN_BY_MODE[mode]
    _ensure_model_downloaded(_MODEL_CACHE_DIR)

    # always_2d + mean(axis=1) downmixes any channel count to mono - the
    # model expects a single 1D waveform (see inference.inference_chunk's
    # own `dwav.dim() == 1` assertion upstream).
    data, sample_rate = sf.read(input_path, dtype="float32", always_2d=True)
    dwav = torch.from_numpy(data.mean(axis=1))

    device = "cuda" if torch.cuda.is_available() else "cpu"
    enhanced_wav, output_sample_rate = run(dwav, sample_rate, device, run_dir=_MODEL_CACHE_DIR)

    sf.write(output_path, enhanced_wav.cpu().numpy(), output_sample_rate)


if __name__ == "__main__":
    main()
