import dataclasses
import pathlib
import shutil
import tempfile
import typing

from book_converter.core import entities as core_entities
from book_converter.infrastructure.speech_generation import ffmpeg_support


@dataclasses.dataclass(frozen=True)
class FfmpegBundleInitializer:
    def create(
        self, target: str, metadata: core_entities.BookMetadata | None
    ) -> "FfmpegBundler":
        work_dir = pathlib.Path(tempfile.mkdtemp(prefix="book_converter_bundle_"))
        return FfmpegBundler(target=pathlib.Path(target), metadata=metadata, work_dir=work_dir)


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
