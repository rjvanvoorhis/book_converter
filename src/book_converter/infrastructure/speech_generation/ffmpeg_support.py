import contextlib
import pathlib
import subprocess
import tempfile
import typing


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


def run_ffmpeg(args: list[str]) -> None:
    subprocess.run(["ffmpeg", "-y", "-v", "error", *args], capture_output=True, text=True, check=True)


@contextlib.contextmanager
def _temp_file(data: bytes) -> typing.Generator[pathlib.Path]:
    handle = tempfile.NamedTemporaryFile(delete=False)
    try:
        handle.write(data)
        handle.close()
        yield pathlib.Path(handle.name)
    finally:
        pathlib.Path(handle.name).unlink(missing_ok=True)
