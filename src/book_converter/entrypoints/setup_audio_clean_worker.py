import pathlib
import shutil
import subprocess
import sys

# audio-clean-worker is a standalone uv project (its own pyproject.toml/
# uv.lock), not a workspace member of this one - it needs a Python version
# and a torch pin that conflict with the main project's own, so it has to be
# resolved and installed separately. See
# infrastructure/speech_generation/resemble_enhance_audio_cleaner.py for why.
_WORKER_DIR = pathlib.Path(__file__).resolve().parents[3] / "audio-clean-worker"


def main() -> None:
    uv = shutil.which("uv")
    if uv is None:
        raise RuntimeError("uv is required to set up audio-clean-worker but was not found on PATH")

    result = subprocess.run([uv, "sync"], cwd=_WORKER_DIR, check=False)
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
