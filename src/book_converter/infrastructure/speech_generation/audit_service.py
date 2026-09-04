import logging
import pathlib
import shutil
import tempfile

from book_converter.features.speech_generation import entities, interfaces
from book_converter.infrastructure.speech_generation import (
    audiobook_library,
    ffmpeg_support,
    noise_artifact_filter,
    pending_edit_store,
)

logger = logging.getLogger(__name__)

# Decoding and scanning a full audiobook in one shot loads the entire raw PCM
# plus the detector's own per-frame working arrays (amplitude ratio,
# spectral centroid track, rolling stats) into memory at once - for an
# 8-hour book that's enough to OOM the process. Scanning in bounded chunks
# instead keeps peak memory proportional to one chunk, not the whole book.
# The overlap is wide enough to fully contain the longest artifact we've
# confirmed (~13s) plus margin, so nothing spanning a chunk boundary is
# missed - it just gets picked up again, more centered, by the next chunk.
_SCAN_CHUNK_SECONDS = 300.0
_SCAN_CHUNK_OVERLAP_SECONDS = 20.0
_MERGE_GAP_SECONDS = 0.5

# Below this, a stream-copy extract is treated as "nothing there" rather
# than a real clip worth concatenating - avoids feeding ffmpeg a
# sub-frame sliver at a splice boundary (e.g. an edit that starts exactly
# at t=0, where there's no "before" clip at all).
_MIN_PART_SECONDS = 0.05


def detect_artifacts(
    m4b_path: str, progress: interfaces.ProgressReporter | None = None
) -> list[dict]:
    source = pathlib.Path(m4b_path)
    total_seconds = ffmpeg_support.probe_duration_seconds(source)

    cuts: list[tuple[float, float]] = []
    chunk_start = 0.0
    while chunk_start < total_seconds:
        chunk_duration = min(
            _SCAN_CHUNK_SECONDS + _SCAN_CHUNK_OVERLAP_SECONDS, total_seconds - chunk_start
        )
        _notify(
            progress,
            f"Scanning {_format_hhmmss(chunk_start)} / {_format_hhmmss(total_seconds)}",
        )
        wav_bytes = ffmpeg_support.decode_to_mono_pcm_wav(
            source, start_seconds=chunk_start, duration_seconds=chunk_duration
        )
        for cut in noise_artifact_filter.find_artifacts(wav_bytes):
            start = chunk_start + cut.start_seconds
            if start >= chunk_start + _SCAN_CHUNK_SECONDS:
                # Falls in the trailing overlap - the next chunk will find
                # this same artifact more centered in its own window.
                continue
            cuts.append((start, chunk_start + cut.end_seconds))
        chunk_start += _SCAN_CHUNK_SECONDS

    return [
        {"start_seconds": start, "end_seconds": end}
        for start, end in _merge_overlapping(cuts)
    ]


def _merge_overlapping(cuts: list[tuple[float, float]]) -> list[tuple[float, float]]:
    merged: list[list[float]] = []
    for start, end in sorted(cuts):
        if merged and start <= merged[-1][1] + _MERGE_GAP_SECONDS:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [(start, end) for start, end in merged]


def _format_hhmmss(seconds: float) -> str:
    hours, remainder = divmod(int(seconds), 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def generate_segment_audio(
    text: str,
    speaker: str | None,
    tts_provider: interfaces.TTSProvider,
    engine: str,
    voice: str,
    dialogue_voice: str | None,
    text_annotator: interfaces.TextAnnotator | None,
) -> entities.SpeechResult:
    """Synthesize one segment's real audio, in isolation from the rest of
    the book. There's no separate throwaway "preview" step: this *is* the
    take that gets baked in if the caller stages it (see
    pending_edit_store.stage_regeneration) - generating one segment is
    already fast, so there's nothing a disposable preview would save."""
    final_text = _prepare_text(text, text_annotator)
    voice_to_use = _select_voice(speaker, voice, dialogue_voice)
    return tts_provider.generate(final_text, engine, voice_to_use)


def validate_cut_range(
    m4b_path: str, segment_index: int, cut_start_seconds: float, cut_end_seconds: float
) -> None:
    transcript = audiobook_library.read_transcript(m4b_path)
    segments = transcript["segments"]
    if not 0 <= segment_index < len(segments):
        raise ValueError(f"No segment at index {segment_index}")
    segment = segments[segment_index]
    seg_start = segment["start_seconds"]
    seg_end = segment["end_seconds"]
    if not seg_start <= cut_start_seconds < cut_end_seconds <= seg_end:
        raise ValueError(
            f"Cut range [{cut_start_seconds}, {cut_end_seconds}) must fall "
            f"within segment {segment_index}'s span [{seg_start}, {seg_end})"
        )


def apply_pending_edits(
    m4b_path: str, progress: interfaces.ProgressReporter | None = None
) -> str:
    """Bake every staged edit into the real audiobook file directly - no
    full decode/re-encode of the book at all.

    Each edit only touches its own [start, end) span: the untouched audio
    before and after is stream-copied (see ffmpeg_support.trim_copy), not
    decoded, and only a regenerated segment's own new audio ever gets
    encoded. Edits are applied from the last segment to the first - that
    ordering is what lets every edit use its own original timestamps
    unmodified: at the moment edit N is applied, nothing *before* segment
    N's position has been touched yet, because every edit already applied
    in this loop was for a later segment and only ever changed content
    after its own point.

    The only timing we maintain ourselves afterward is the transcript's
    segment boundaries and the book's chapter markers - both are just the
    old timing plus each edit's own duration delta (new length minus what
    it replaced), applied as a running offset to everything after it. No
    re-probing of the rebuilt audio is needed to know that.
    """
    transcript = audiobook_library.read_transcript(m4b_path)
    segments = transcript["segments"]
    edits = pending_edit_store.list_edits(m4b_path)
    if not edits:
        raise ValueError("No pending edits to apply")

    source_path = pathlib.Path(m4b_path)
    work_path = source_path.with_name(f"{source_path.name}.applying")
    shutil.copyfile(source_path, work_path)

    try:
        edited_indices = sorted((int(key) for key in edits), reverse=True)
        for count, index in enumerate(edited_indices):
            edit = edits[str(index)]
            _notify(
                progress,
                f"Applying edit {count + 1}/{len(edited_indices)} "
                f"(segment {index + 1}/{len(segments)})",
            )
            _splice_edit(work_path, segments[index], edit, m4b_path, index)

        new_segments = _apply_deltas_to_segments(segments, edits)
        chapters = _chapters_from_segments(new_segments)
        _notify(progress, "Updating chapter markers")
        ffmpeg_support.write_chapters(work_path, chapters, transcript.get("title"))

        transcript["segments"] = new_segments
        audiobook_library.write_transcript(m4b_path, transcript)
        # Only replace the real file once every step above has succeeded,
        # so a failure partway through never leaves the user's library in
        # a half-edited state.
        work_path.replace(source_path)
    finally:
        work_path.unlink(missing_ok=True)

    return str(source_path)


def _splice_edit(
    work_path: pathlib.Path, segment: dict, edit: dict, m4b_path: str, index: int
) -> None:
    if edit["kind"] == "cut":
        remove_start = edit["cut_start_seconds"]
        remove_end = edit["cut_end_seconds"]
        replacement_wav_path = None
    else:
        remove_start = segment["start_seconds"]
        remove_end = segment["end_seconds"]
        replacement_wav_path = pending_edit_store.edit_audio_path(m4b_path, index)

    total_duration = ffmpeg_support.probe_duration_seconds(work_path)

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = pathlib.Path(tmp_dir)
        parts: list[pathlib.Path] = []

        if remove_start > _MIN_PART_SECONDS:
            before_path = tmp / "before.m4a"
            ffmpeg_support.trim_copy(work_path, before_path, end_seconds=remove_start)
            parts.append(before_path)

        if replacement_wav_path is not None:
            middle_path = tmp / "middle.m4a"
            ffmpeg_support.encode_wav_to_aac(replacement_wav_path, middle_path)
            parts.append(middle_path)

        if total_duration - remove_end > _MIN_PART_SECONDS:
            after_path = tmp / "after.m4a"
            ffmpeg_support.trim_copy(work_path, after_path, start_seconds=remove_end)
            parts.append(after_path)

        if not parts:
            raise ValueError("Cut range would remove the entire audiobook")

        spliced_path = tmp / "spliced.m4b"
        ffmpeg_support.concat_copy(parts, spliced_path)
        shutil.move(str(spliced_path), str(work_path))


def _apply_deltas_to_segments(segments: list[dict], edits: dict) -> list[dict]:
    new_segments: list[dict] = []
    offset = 0.0
    for index, segment in enumerate(segments):
        edit = edits.get(str(index))
        start = segment["start_seconds"] + offset
        if edit is None:
            end = segment["end_seconds"] + offset
            text = segment["text"]
        elif edit["kind"] == "cut":
            removed = edit["cut_end_seconds"] - edit["cut_start_seconds"]
            end = segment["end_seconds"] + offset - removed
            offset -= removed
            text = segment["text"]
        else:  # "regenerate"
            end = start + edit["duration"]
            offset += edit["duration"] - (segment["end_seconds"] - segment["start_seconds"])
            text = edit["text"]
        new_segments.append(
            {
                "chapter_title": segment["chapter_title"],
                "speaker": segment["speaker"],
                "text": text,
                "start_seconds": start,
                "end_seconds": end,
            }
        )
    return new_segments


def _chapters_from_segments(segments: list[dict]) -> list[dict]:
    chapters: list[dict] = []
    for segment in segments:
        if chapters and chapters[-1]["title"] == segment["chapter_title"]:
            chapters[-1]["end_seconds"] = segment["end_seconds"]
        else:
            chapters.append(
                {
                    "title": segment["chapter_title"],
                    "start_seconds": segment["start_seconds"],
                    "end_seconds": segment["end_seconds"],
                }
            )
    return chapters


def _prepare_text(text: str, text_annotator: interfaces.TextAnnotator | None) -> str:
    return text_annotator.annotate(text) if text_annotator is not None else text


def _select_voice(speaker: str | None, voice: str, dialogue_voice: str | None) -> str:
    return voice if speaker is None else (dialogue_voice or voice)


def _notify(progress: interfaces.ProgressReporter | None, message: str) -> None:
    logger.info(message)
    if progress is not None:
        if progress.is_cancelled():
            raise interfaces.TaskCancelled(message)
        progress.report(message)
