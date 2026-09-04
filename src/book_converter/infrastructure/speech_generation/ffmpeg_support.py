import contextlib
import logging
import pathlib
import shutil
import subprocess
import tempfile
import threading
import typing

logger = logging.getLogger(__name__)


def probe_duration_seconds(path: pathlib.Path) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(result.stdout.strip())


def probe_duration_seconds_from_bytes(data: bytes) -> float:
    with _temp_file(data) as path:
        return probe_duration_seconds(path)


def generate_silence(seconds: float, output_path: pathlib.Path) -> None:
    # Explicit output format since output_path has no extension for ffmpeg to
    # infer a container from (matching the extension-less part_NNNN files
    # elsewhere in the bundle work dir).
    run_ffmpeg(
        [
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=24000:cl=mono",
            "-t",
            str(seconds),
            "-f",
            "wav",
            str(output_path),
        ]
    )


def extract_clip(
    source: pathlib.Path,
    start_seconds: float,
    end_seconds: float,
    output_path: pathlib.Path,
) -> None:
    """Extract [start_seconds, end_seconds) from `source` as a standalone WAV
    clip. Re-encodes rather than stream-copying: `-c copy` can only cut on
    keyframe boundaries in an AAC/mp4 container, which drifts from the exact
    times a transcript records.

    `-ss`/`-t` are given *before* `-i` (input seeking) rather than after
    (output seeking): output seeking decodes and discards everything from
    the start of the file up to the cut point on every call, which is fine
    for one clip but is O(elapsed time) per call - called once per segment
    on an hours-long book, that's the difference between this taking
    seconds and taking effectively forever."""
    run_ffmpeg(
        [
            "-ss",
            str(start_seconds),
            "-t",
            str(end_seconds - start_seconds),
            "-i",
            str(source),
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            "-f",
            "wav",
            str(output_path),
        ]
    )


def decode_to_mono_pcm_wav(
    source: pathlib.Path,
    sample_rate: int = 24000,
    start_seconds: float | None = None,
    duration_seconds: float | None = None,
) -> bytes:
    """Decode `source` (e.g. a finalized .m4b) to mono 16-bit PCM WAV bytes,
    the format the noise-artifact detector expects. With `start_seconds`/
    `duration_seconds`, decodes just that range instead of the whole file -
    decoding a multi-hour audiobook in full loads the entire raw PCM (plus
    the detector's own working arrays) into memory at once, which is enough
    to OOM on a long book; callers doing a full-file scan should decode and
    process it in bounded chunks instead."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as handle:
        output_path = pathlib.Path(handle.name)
    try:
        range_args = []
        if start_seconds is not None:
            range_args += ["-ss", str(start_seconds)]
        if duration_seconds is not None:
            range_args += ["-t", str(duration_seconds)]
        run_ffmpeg(
            [
                *range_args,
                "-i",
                str(source),
                "-ac",
                "1",
                "-ar",
                str(sample_rate),
                "-c:a",
                "pcm_s16le",
                "-f",
                "wav",
                str(output_path),
            ]
        )
        return output_path.read_bytes()
    finally:
        output_path.unlink(missing_ok=True)


def trim_copy(
    source: pathlib.Path,
    output_path: pathlib.Path,
    start_seconds: float | None = None,
    end_seconds: float | None = None,
) -> None:
    """Extract [start_seconds, end_seconds) from `source` as a stream copy -
    no decoding or re-encoding, just repackaging the existing compressed
    audio packets. Unlike `extract_clip`, this doesn't land on the exact
    sample: `-c copy` can only cut on an AAC frame boundary (tens of
    milliseconds), the same trade-off every other approximate-timing
    operation in this codebase already makes. What it buys back is speed
    independent of book length - no full decode/re-encode pass - which is
    the whole point when splicing edits into an existing audiobook instead
    of rebuilding it from scratch.

    `-ss` before `-i` for a start bound (input seeking, cheap - doesn't
    decode the skipped portion) matches `extract_clip`'s reasoning; an end
    bound alone (no start) uses `-t` after `-i` since there's nothing to
    seek past.
    """
    args = []
    if start_seconds is not None:
        args += ["-ss", str(start_seconds)]
    args += ["-i", str(source)]
    if end_seconds is not None:
        args += ["-t", str(end_seconds - (start_seconds or 0.0))]
    args += ["-map", "0:a", "-c", "copy", "-f", "mp4", str(output_path)]
    run_ffmpeg(args)


def encode_wav_to_aac(source_wav: pathlib.Path, output_path: pathlib.Path) -> None:
    """Encode raw TTS output to the same codec/params the rest of the book's
    audio already uses (see FfmpegBundler.finalize), so it can be stream-
    copy-concatenated with the untouched audio on either side of an edit
    with no mismatch."""
    run_ffmpeg(
        [
            "-i",
            str(source_wav),
            "-c:a",
            "aac",
            "-b:a",
            "48k",
            "-ac",
            "1",
            "-vn",
            "-f",
            "mp4",
            str(output_path),
        ]
    )


def concat_copy(parts: list[pathlib.Path], output_path: pathlib.Path) -> None:
    """Concatenate already-compatible (same codec/params) audio files with
    no re-encoding - just remuxing packets - so cost is independent of how
    much audio is being stitched back together."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        concat_list = pathlib.Path(tmp_dir) / "concat_list.txt"
        concat_list.write_text(
            "\n".join(
                f"file {_quote_concat_path(part.resolve().as_posix())}" for part in parts
            )
            + "\n",
            encoding="utf-8",
        )
        run_ffmpeg(
            [
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_list),
                "-c",
                "copy",
                "-f",
                "mp4",
                str(output_path),
            ]
        )


def write_chapters(path: pathlib.Path, chapters: list[dict], title: str | None) -> None:
    """Rewrite just an existing mp4/m4b's chapter markers in place, leaving
    the audio itself untouched (`-c copy`) - used after a splice shifts
    every later chapter's timing by the edit's duration delta."""
    lines = [";FFMETADATA1"]
    if title:
        lines.append(f"title={_escape_ffmetadata(title)}")
    for chapter in chapters:
        lines += [
            "",
            "[CHAPTER]",
            "TIMEBASE=1/1000",
            f"START={round(chapter['start_seconds'] * 1000)}",
            f"END={round(chapter['end_seconds'] * 1000)}",
            f"title={_escape_ffmetadata(chapter['title'])}",
        ]

    with tempfile.TemporaryDirectory() as tmp_dir:
        chapters_file = pathlib.Path(tmp_dir) / "chapters.txt"
        chapters_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
        remuxed_path = pathlib.Path(tmp_dir) / "remuxed.m4b"
        run_ffmpeg(
            [
                "-i",
                str(path),
                "-i",
                str(chapters_file),
                "-map_metadata",
                "1",
                "-codec",
                "copy",
                "-f",
                "mp4",
                str(remuxed_path),
            ]
        )
        shutil.move(str(remuxed_path), str(path))


def _quote_concat_path(path: str) -> str:
    """Quote a path for ffmpeg's concat demuxer list, escaping literal single quotes.

    The concat format takes the whole `'...'` span literally with no escape
    character recognized inside it, so a literal quote (e.g. a title like
    "Can't") has to close the quoted span, insert an escaped quote outside of
    it, then reopen quoting - the same trick POSIX shells use.
    """
    return "'" + path.replace("'", "'\\''") + "'"


def _escape_ffmetadata(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace("=", "\\=")
        .replace(";", "\\;")
        .replace("#", "\\#")
        .replace("\n", "\\\n")
    )


def run_ffmpeg(
    args: list[str], *, total_duration: float | None = None, label: str | None = None
) -> None:
    """Run ffmpeg, logging periodic progress if `total_duration` (seconds) is known."""
    process = subprocess.Popen(
        ["ffmpeg", "-y", "-v", "error", "-nostats", "-progress", "pipe:1", *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )

    stderr_lines: list[str] = []
    stderr_thread = threading.Thread(
        target=lambda: stderr_lines.extend(process.stderr), daemon=True
    )
    stderr_thread.start()

    last_logged_percent = -1
    assert process.stdout is not None
    for line in process.stdout:
        key, _, value = line.strip().partition("=")
        if key != "out_time" or not total_duration:
            continue
        processed_seconds = _parse_ffmpeg_timestamp(value)
        if processed_seconds is None:
            continue
        percent = max(0, min(100, int(processed_seconds / total_duration * 100)))
        if percent >= last_logged_percent + 10:
            last_logged_percent = percent
            logger.info(
                "%s: %d%% (%.0fs/%.0fs)",
                label or "ffmpeg",
                percent,
                processed_seconds,
                total_duration,
            )

    process.wait()
    stderr_thread.join()

    if process.returncode != 0:
        raise RuntimeError(
            f"ffmpeg failed (exit {process.returncode}) for args {args}: {''.join(stderr_lines).strip()}"
        )


def _parse_ffmpeg_timestamp(value: str) -> float | None:
    """Parse ffmpeg's `-progress` out_time field, e.g. '00:12:34.560000'."""
    try:
        hours, minutes, seconds = value.split(":")
        return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    except ValueError:
        return None


@contextlib.contextmanager
def _temp_file(data: bytes) -> typing.Generator[pathlib.Path]:
    handle = tempfile.NamedTemporaryFile(delete=False)
    try:
        handle.write(data)
        handle.close()
        yield pathlib.Path(handle.name)
    finally:
        pathlib.Path(handle.name).unlink(missing_ok=True)
