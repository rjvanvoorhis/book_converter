import pathlib
import re
import subprocess
import tempfile

from book_converter.features.speech_generation import interfaces
from book_converter.infrastructure.speech_generation import ffmpeg_support

# Pocket TTS resamples whatever it's given internally, but standardizing on
# one rate/channel layout here keeps saved samples consistent with the rest
# of this codebase's audio (see ffmpeg_support.decode_to_mono_pcm_wav) -
# regardless of which cleaner (if any) ran, since a model-based cleaner can
# hand back a different sample rate/encoding than it was given.
_SAMPLE_RATE = 24000

# Trims leading/trailing dead air, applied both forwards and reversed (via
# areverse) since silenceremove only strips from the start of whatever it's
# given.
_SILENCE_TRIM_FILTERS = [
    "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.05:detection=peak",
    "areverse",
    "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.05:detection=peak",
    "areverse",
]

_LOUDNESS_NORMALIZE_FILTER = "loudnorm=I=-16:TP=-1.5:LRA=11"

_UNSAFE_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def probe_source_duration(path: str) -> float:
    source = pathlib.Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"No audio file found at '{path}'")
    return ffmpeg_support.probe_duration_seconds(source)


def read_source_bytes(path: str) -> bytes:
    """The whole source recording, for scrubbing through it in a normal
    player to find a good clip start point - unlike read_source_clip_bytes,
    no ffmpeg decode pass, so it works for any format the browser itself can
    play (the common case for a short interview/voice recording)."""
    source = pathlib.Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"No audio file found at '{path}'")
    return source.read_bytes()


def read_source_clip_bytes(path: str, start_seconds: float, end_seconds: float) -> bytes:
    """Unprocessed preview of [start, end) from an arbitrary source recording -
    for auditioning a candidate clip before cleaning and saving it, the same
    way audiobook_library.read_clip_bytes previews an audiobook segment."""
    source = pathlib.Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"No audio file found at '{path}'")
    with tempfile.TemporaryDirectory() as tmp_dir:
        clip_path = pathlib.Path(tmp_dir) / "clip.wav"
        ffmpeg_support.extract_clip(source, start_seconds, end_seconds, clip_path)
        return clip_path.read_bytes()


def list_samples(folder: str) -> list[dict]:
    root = pathlib.Path(folder)
    if not root.is_dir():
        return []
    samples = []
    for wav_path in sorted(root.glob("*.wav")):
        try:
            duration = ffmpeg_support.probe_duration_seconds(wav_path)
        except (subprocess.CalledProcessError, ValueError):
            duration = 0.0
        samples.append(
            {"path": str(wav_path), "name": wav_path.stem, "duration_seconds": duration}
        )
    return samples


def read_sample_bytes(path: str) -> bytes:
    sample_path = pathlib.Path(path)
    if not sample_path.is_file():
        raise FileNotFoundError(f"No voice sample found at '{path}'")
    return sample_path.read_bytes()


def delete_sample(path: str) -> None:
    sample_path = pathlib.Path(path)
    sample_path.unlink(missing_ok=True)


def create_sample(
    source_path: str,
    start_seconds: float,
    end_seconds: float,
    output_folder: str,
    name: str,
    *,
    cleaner: interfaces.AudioCleaner | None,
    trim_silence: bool = True,
    normalize_loudness: bool = True,
) -> dict:
    """Extract [start, end) from `source_path` and, unless `cleaner` is
    None, run it through `cleaner` before saving it as a standalone WAV
    under `output_folder` - ready to hand to a cloning-capable TTS engine's
    `--voice` argument. Cloning reproduces whatever's in the sample,
    including its noise, so cleaning it first (matching Pocket TTS's own
    recommendation) measurably improves clone fidelity.

    Order matters: `cleaner` runs before silence-trimming, since a noisy
    "silence" can sit above the trim threshold until the noise floor's been
    pulled down; loudness normalization runs last so it's working off the
    already-cleaned signal rather than amplifying noise along with speech.
    """
    source = pathlib.Path(source_path)
    if not source.is_file():
        raise FileNotFoundError(f"No audio file found at '{source_path}'")
    if end_seconds <= start_seconds:
        raise ValueError("end_seconds must be greater than start_seconds")

    out_dir = pathlib.Path(output_folder)
    out_dir.mkdir(parents=True, exist_ok=True)
    output_path = _unique_path(out_dir, _safe_filename(name))

    with tempfile.TemporaryDirectory() as tmp_dir:
        raw_clip = pathlib.Path(tmp_dir) / "raw.wav"
        ffmpeg_support.extract_clip(source, start_seconds, end_seconds, raw_clip)
        wav_bytes = raw_clip.read_bytes()

    if cleaner is not None:
        wav_bytes = cleaner.clean(wav_bytes)
    if trim_silence:
        wav_bytes = ffmpeg_support.apply_audio_filters(wav_bytes, _SILENCE_TRIM_FILTERS)
    if normalize_loudness:
        wav_bytes = ffmpeg_support.apply_audio_filters(wav_bytes, [_LOUDNESS_NORMALIZE_FILTER])
    wav_bytes = ffmpeg_support.standardize_wav(wav_bytes, _SAMPLE_RATE)

    output_path.write_bytes(wav_bytes)

    duration = ffmpeg_support.probe_duration_seconds(output_path)
    return {"path": str(output_path), "name": output_path.stem, "duration_seconds": duration}


def _safe_filename(name: str) -> str:
    cleaned = _UNSAFE_FILENAME_CHARS.sub(" ", name).strip().rstrip(".")
    return " ".join(cleaned.split()) or "voice-sample"


def _unique_path(out_dir: pathlib.Path, stem: str) -> pathlib.Path:
    candidate = out_dir / f"{stem}.wav"
    counter = 2
    while candidate.exists():
        candidate = out_dir / f"{stem} ({counter}).wav"
        counter += 1
    return candidate
