import contextlib
import logging
import pathlib
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


def run_ffmpeg(args: list[str], *, total_duration: float | None = None, label: str | None = None) -> None:
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
                label or "ffmpeg", percent, processed_seconds, total_duration,
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
