import json
import pathlib
import tempfile

from book_converter.infrastructure.speech_generation import ffmpeg_support


def list_audiobooks(folder: str) -> list[dict]:
    """Find every .m4b under `folder` (including series subfolders) that has
    a transcript sidecar, since the audit page has nothing to show without
    one."""
    root = pathlib.Path(folder)
    if not root.is_dir():
        return []

    audiobooks = []
    for m4b_path in sorted(root.rglob("*.m4b")):
        transcript_path = _transcript_path(m4b_path)
        if not transcript_path.is_file():
            continue
        title = m4b_path.stem
        try:
            transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
            title = transcript.get("title") or title
            segment_count = len(transcript.get("segments", []))
        except (json.JSONDecodeError, OSError):
            segment_count = 0
        audiobooks.append(
            {
                "path": str(m4b_path),
                "title": title,
                "segment_count": segment_count,
            }
        )
    return audiobooks


def read_transcript(m4b_path: str) -> dict:
    transcript_path = _transcript_path(pathlib.Path(m4b_path))
    if not transcript_path.is_file():
        raise FileNotFoundError(f"No transcript found for '{m4b_path}'")
    return json.loads(transcript_path.read_text(encoding="utf-8"))


def write_transcript(m4b_path: str, transcript: dict) -> None:
    transcript_path = _transcript_path(pathlib.Path(m4b_path))
    transcript_path.write_text(json.dumps(transcript, indent=2), encoding="utf-8")


def read_audio_bytes(m4b_path: str) -> bytes:
    path = pathlib.Path(m4b_path)
    if not path.is_file():
        raise FileNotFoundError(f"No audiobook found at '{m4b_path}'")
    return path.read_bytes()


def read_clip_bytes(m4b_path: str, start_seconds: float, end_seconds: float) -> bytes:
    """Extract just [start_seconds, end_seconds) as a standalone WAV clip,
    for a player that only ever needs one segment at a time - loading a
    multi-hour audiobook whole (as `read_audio_bytes` does) just to play a
    few seconds of it wastes memory and bandwidth for no reason."""
    path = pathlib.Path(m4b_path)
    if not path.is_file():
        raise FileNotFoundError(f"No audiobook found at '{m4b_path}'")
    with tempfile.TemporaryDirectory() as tmp_dir:
        clip_path = pathlib.Path(tmp_dir) / "clip.wav"
        ffmpeg_support.extract_clip(path, start_seconds, end_seconds, clip_path)
        return clip_path.read_bytes()


def _transcript_path(m4b_path: pathlib.Path) -> pathlib.Path:
    return m4b_path.with_name(f"{m4b_path.name}.transcript.json")
