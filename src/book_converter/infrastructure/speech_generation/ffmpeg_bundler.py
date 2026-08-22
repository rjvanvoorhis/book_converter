import dataclasses
import pathlib
import shutil
import typing

from book_converter.core import entities as core_entities
from book_converter.infrastructure.speech_generation import ffmpeg_support


@dataclasses.dataclass(frozen=True)
class FfmpegBundleInitializer:
    def create(
        self, target: str, metadata: core_entities.BookMetadata | None
    ) -> "FfmpegBundler":
        target_path = pathlib.Path(target)
        # Own work dir next to the real output rather than the OS temp dir: it's on
        # the same drive as the target, survives long enough to inspect after a
        # crash, and isn't subject to third-party temp-cleanup tools deleting it
        # mid-run. Any leftovers from a previous crashed attempt for this exact
        # target are stale (the target was never confirmed written) and safe to
        # discard before starting over.
        work_dir = target_path.parent / f".{target_path.stem}.bundle-tmp"
        if work_dir.exists():
            shutil.rmtree(work_dir)
        work_dir.mkdir(parents=True, exist_ok=True)
        return FfmpegBundler(target=target_path, metadata=metadata, work_dir=work_dir)


@dataclasses.dataclass
class FfmpegBundler:
    target: pathlib.Path
    metadata: core_entities.BookMetadata | None
    work_dir: pathlib.Path
    _parts: list[tuple[str, pathlib.Path, float]] = dataclasses.field(default_factory=list)

    def add_part(self, title: str, part: typing.IO) -> None:
        part_path = self.work_dir / f"part_{len(self._parts):04d}"
        part_path.write_bytes(part.read())
        duration = ffmpeg_support.probe_duration_seconds(part_path)
        self._parts.append((title, part_path, duration))

    def finalize(self) -> str:
        if not self._parts:
            raise ValueError("Cannot finalize an audiobook with no chapters")

        concat_list = self.work_dir / "concat_list.txt"
        concat_list.write_text(
            "\n".join(f"file '{path.as_posix()}'" for _, path, _ in self._parts) + "\n",
            encoding="utf-8",
        )

        intermediate = self.work_dir / "intermediate.m4a"
        ffmpeg_support.run_ffmpeg(
            [
                "-f", "concat", "-safe", "0", "-i", str(concat_list),
                "-c:a", "aac", "-b:a", "64k", "-vn", str(intermediate),
            ]
        )

        chapters_file = self.work_dir / "chapters.txt"
        chapters_file.write_text(_ffmetadata(self.metadata, self._parts), encoding="utf-8")

        self.target.parent.mkdir(parents=True, exist_ok=True)
        ffmpeg_support.run_ffmpeg(
            [
                "-i", str(intermediate), "-i", str(chapters_file),
                "-map_metadata", "1", "-codec", "copy", "-f", "mp4", str(self.target),
            ]
        )

        if not self.target.exists() or self.target.stat().st_size == 0:
            raise RuntimeError(
                f"ffmpeg reported success but produced no output at '{self.target}'"
            )

        # Only clean up the work dir once the real output is confirmed on disk, so
        # a failure never leaves us with neither the target nor the intermediates.
        shutil.rmtree(self.work_dir, ignore_errors=True)
        return str(self.target)


def _ffmetadata(
    metadata: core_entities.BookMetadata | None,
    parts: list[tuple[str, pathlib.Path, float]],
) -> str:
    lines = [";FFMETADATA1"]
    if metadata is not None:
        lines.append(f"title={_escape(metadata.title)}")
        if metadata.author:
            lines.append(f"artist={_escape(metadata.author)}")

    cursor_ms = 0
    for title, _path, duration in parts:
        start_ms = cursor_ms
        cursor_ms += round(duration * 1000)
        lines.append("")
        lines.append("[CHAPTER]")
        lines.append("TIMEBASE=1/1000")
        lines.append(f"START={start_ms}")
        lines.append(f"END={cursor_ms}")
        lines.append(f"title={_escape(title)}")

    return "\n".join(lines) + "\n"


def _escape(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace("=", "\\=")
        .replace(";", "\\;")
        .replace("#", "\\#")
        .replace("\n", "\\\n")
    )
