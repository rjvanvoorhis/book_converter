import pathlib
import subprocess
import tempfile
import typing

# resemble-enhance pins torch==2.1.1, which has no prebuilt wheels for this
# project's Python version - so unlike every other adapter in this package,
# it doesn't run in-process. It gets its own isolated virtualenv (a
# supported-elsewhere Python version, e.g. 3.11) with resemble-enhance
# installed into it, and this adapter shells out to that interpreter running
# resemble_enhance_worker.py - the same "invoke an external tool as a
# subprocess" shape ffmpeg_support already uses for ffmpeg itself.
_WORKER_SCRIPT = pathlib.Path(__file__).with_name("resemble_enhance_worker.py")

_Mode = typing.Literal["denoise", "enhance"]


class ResembleEnhanceAudioCleaner:
    """ML-based denoising and restoration via resemble-enhance - slower than
    FfmpegAudioCleaner (a model forward pass vs. a DSP filter) but
    meaningfully closer to studio quality, which matters more for a
    20-30-second voice-cloning sample than raw speed does."""

    def __init__(self, python_executable: str, mode: _Mode = "enhance") -> None:
        self._python_executable = python_executable
        self._mode = mode
        if mode == "enhance":
            self.id = "resemble-enhance"
            self.description = "ML denoise + restoration (resemble-enhance); slower, highest fidelity"
        else:
            self.id = "resemble-enhance-denoise-only"
            self.description = "ML denoise only, no restoration (resemble-enhance); slower than ffmpeg"

    @staticmethod
    def is_available(python_executable: str) -> bool:
        """Whether the isolated venv this adapter needs has actually been
        set up - lets the composition root skip registering this cleaner
        (rather than fail at request time) when it hasn't been."""
        return pathlib.Path(python_executable).is_file()

    def clean(self, wav_bytes: bytes) -> bytes:
        with tempfile.TemporaryDirectory() as tmp_dir:
            source = pathlib.Path(tmp_dir) / "in.wav"
            output = pathlib.Path(tmp_dir) / "out.wav"
            source.write_bytes(wav_bytes)

            result = subprocess.run(
                [
                    self._python_executable,
                    str(_WORKER_SCRIPT),
                    str(source),
                    str(output),
                    self._mode,
                ],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                raise RuntimeError(
                    f"resemble-enhance worker failed (exit {result.returncode}): "
                    f"{result.stderr.strip()}"
                )
            return output.read_bytes()
