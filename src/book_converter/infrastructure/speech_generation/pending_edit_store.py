import json
import pathlib
import shutil
import threading

from book_converter.infrastructure.speech_generation import ffmpeg_support

_lock = threading.Lock()


def list_edits(m4b_path: str) -> dict:
    """Every staged edit, keyed by segment index (as a string, matching how
    review_store keys its own entries) - empty until the user stages
    anything. Persisted to disk (not just held in memory) so a staged
    regeneration - the real, already-synthesized take, not a disposable
    preview - survives a server restart or the user coming back later,
    right up until it's applied or discarded."""
    manifest_path = _manifest_path(pathlib.Path(m4b_path))
    if not manifest_path.is_file():
        return {}
    with _lock:
        return json.loads(manifest_path.read_text(encoding="utf-8"))


def stage_cut(
    m4b_path: str, segment_index: int, cut_start_seconds: float, cut_end_seconds: float
) -> dict:
    return _update_manifest(
        m4b_path,
        segment_index,
        {
            "kind": "cut",
            "cut_start_seconds": cut_start_seconds,
            "cut_end_seconds": cut_end_seconds,
        },
    )


def stage_regeneration(m4b_path: str, segment_index: int, text: str, audio_bytes: bytes) -> dict:
    """Persist the actual generated take to disk, not a throwaway preview -
    this is the exact audio that gets spliced into the book if the edit is
    applied. Duration is probed once here (rather than trusted from the TTS
    provider, whose own reported duration isn't reliable) so applying the
    edit later doesn't need to re-decode the audio just to know how long it
    is."""
    m4b = pathlib.Path(m4b_path)
    audio_path = _audio_path(m4b, segment_index)
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    audio_path.write_bytes(audio_bytes)
    duration = ffmpeg_support.probe_duration_seconds(audio_path)
    return _update_manifest(
        m4b_path, segment_index, {"kind": "regenerate", "text": text, "duration": duration}
    )


def edit_audio_path(m4b_path: str, segment_index: int) -> pathlib.Path:
    """Path to a staged regeneration's saved audio, for both serving it to
    the client to listen to and for applying it directly with ffmpeg -
    neither needs the bytes read into Python."""
    return _audio_path(pathlib.Path(m4b_path), segment_index)


def discard_edit(m4b_path: str, segment_index: int) -> dict:
    m4b = pathlib.Path(m4b_path)
    _audio_path(m4b, segment_index).unlink(missing_ok=True)
    with _lock:
        manifest = _read_manifest(m4b)
        manifest.pop(str(segment_index), None)
        _write_manifest(m4b, manifest)
        return manifest


def clear_edits(m4b_path: str) -> None:
    """Drop every staged edit, e.g. once they've all been baked into the
    audiobook - the audio and text they described no longer describes a
    pending change, and their segment indices would no longer line up with
    the just-edited transcript's positions anyway."""
    edits_dir = _edits_dir(pathlib.Path(m4b_path))
    with _lock:
        shutil.rmtree(edits_dir, ignore_errors=True)


def _update_manifest(m4b_path: str, segment_index: int, entry: dict) -> dict:
    m4b = pathlib.Path(m4b_path)
    with _lock:
        manifest = _read_manifest(m4b)
        manifest[str(segment_index)] = entry
        _write_manifest(m4b, manifest)
        return manifest


def _read_manifest(m4b_path: pathlib.Path) -> dict:
    manifest_path = _manifest_path(m4b_path)
    if not manifest_path.is_file():
        return {}
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def _write_manifest(m4b_path: pathlib.Path, manifest: dict) -> None:
    manifest_path = _manifest_path(m4b_path)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def _edits_dir(m4b_path: pathlib.Path) -> pathlib.Path:
    return m4b_path.with_name(f"{m4b_path.name}.edits")


def _manifest_path(m4b_path: pathlib.Path) -> pathlib.Path:
    return _edits_dir(m4b_path) / "manifest.json"


def _audio_path(m4b_path: pathlib.Path, segment_index: int) -> pathlib.Path:
    return _edits_dir(m4b_path) / f"segment-{segment_index}.audio"
