import dataclasses
import hashlib
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
        # Resolved to absolute: ffmpeg's concat demuxer resolves relative paths in
        # the list file relative to the list file's own directory (not the process
        # cwd), so a relative work_dir here would make it double up the path and
        # fail to find the chapter files.
        target_path = pathlib.Path(target).resolve()
        # Own work dir next to the real output rather than the OS temp dir: it's on
        # the same drive as the target, survives long enough to inspect after a
        # crash, and isn't subject to third-party temp-cleanup tools deleting it
        # mid-run. Named from a hash of the target path rather than the human title:
        # titles can contain characters (quotes, unicode, ...) that are valid on
        # the filesystem but trip up other tools' own path syntax (as ffmpeg's
        # concat list quoting did), so intermediate plumbing paths stay boring and
        # ASCII-only. Hashing (not e.g. a running counter) keeps it deterministic
        # per target, which is what lets a crashed attempt's leftovers be found
        # and cleared before starting over.
        digest = hashlib.sha1(str(target_path).encode()).hexdigest()[:12]
        work_dir = target_path.parent / f".bundle-tmp-{digest}"
        if work_dir.exists():
            shutil.rmtree(work_dir)
        work_dir.mkdir(parents=True, exist_ok=True)
        return FfmpegBundler(target=target_path, metadata=metadata, work_dir=work_dir)


@dataclasses.dataclass(frozen=True)
class _Part:
    title: str
    path: pathlib.Path
    duration: float
    new_chapter: bool


@dataclasses.dataclass
class FfmpegBundler:
    target: pathlib.Path
    metadata: core_entities.BookMetadata | None
    work_dir: pathlib.Path
    _parts: list[_Part] = dataclasses.field(default_factory=list)

    def add_part(self, title: str, part: typing.IO, new_chapter: bool = True) -> None:
        part_path = self.work_dir / f"part_{len(self._parts):04d}"
        part_path.write_bytes(part.read())
        duration = ffmpeg_support.probe_duration_seconds(part_path)
        self._parts.append(
            _Part(
                title=title, path=part_path, duration=duration, new_chapter=new_chapter
            )
        )

    def add_silence(self, seconds: float) -> None:
        """Insert a short silent gap, e.g. between a chapter's narration/dialogue
        segments — ffmpeg's concat demuxer otherwise abuts clips with no gap,
        which sounds glued together when segments came from separate TTS calls.
        """
        part_path = self.work_dir / f"part_{len(self._parts):04d}"
        ffmpeg_support.generate_silence(seconds, part_path)
        self._parts.append(
            _Part(title="", path=part_path, duration=seconds, new_chapter=False)
        )

    def finalize(self) -> str:
        if not self._parts:
            raise ValueError("Cannot finalize an audiobook with no chapters")

        concat_list = self.work_dir / "concat_list.txt"
        concat_list.write_text(
            "\n".join(
                f"file {_quote_concat_path(part.path.as_posix())}"
                for part in self._parts
            )
            + "\n",
            encoding="utf-8",
        )

        total_duration = sum(part.duration for part in self._parts)

        intermediate = self.work_dir / "intermediate.m4a"
        ffmpeg_support.run_ffmpeg(
            [
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_list),
                # Spoken-word narration doesn't need music-grade quality: mono at
                # 48k is indistinguishable from the prior 64k stereo for speech
                # and meaningfully smaller.
                "-c:a",
                "aac",
                "-b:a",
                "48k",
                "-ac",
                "1",
                "-vn",
                str(intermediate),
            ],
            total_duration=total_duration,
            label=f"Encoding '{self.target.name}'",
        )

        chapters_file = self.work_dir / "chapters.txt"
        chapters_file.write_text(
            _ffmetadata(self.metadata, self._parts), encoding="utf-8"
        )

        self.target.parent.mkdir(parents=True, exist_ok=True)
        ffmpeg_support.run_ffmpeg(
            [
                "-i",
                str(intermediate),
                "-i",
                str(chapters_file),
                "-map_metadata",
                "1",
                "-codec",
                "copy",
                "-f",
                "mp4",
                str(self.target),
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


def _quote_concat_path(path: str) -> str:
    """Quote a path for ffmpeg's concat demuxer list, escaping literal single quotes.

    The concat format takes the whole `'...'` span literally with no escape
    character recognized inside it, so a literal quote (e.g. a title like
    "Can't") has to close the quoted span, insert an escaped quote outside of
    it, then reopen quoting — the same trick POSIX shells use.
    """
    return "'" + path.replace("'", "'\\''") + "'"


def _ffmetadata(metadata: core_entities.BookMetadata | None, parts: list[_Part]) -> str:
    lines = [";FFMETADATA1"]
    if metadata is not None:
        lines.append(f"title={_escape(metadata.title)}")
        if metadata.author:
            lines.append(f"artist={_escape(metadata.author)}")

    # Group parts into chapters: a run of parts starting at each new_chapter=True
    # entry (or the very first part, regardless of its flag) and extending
    # through any new_chapter=False continuation entries that follow it. This
    # keeps one [CHAPTER] marker per real book chapter even when a chapter was
    # synthesized as several segments (e.g. narration/dialogue turns).
    chapters: list[tuple[str, int, int]] = []
    cursor_ms = 0
    chapter_title: str | None = None
    chapter_start_ms = 0
    for part in parts:
        if part.new_chapter and chapter_title is not None:
            chapters.append((chapter_title, chapter_start_ms, cursor_ms))
            chapter_title = None
        if chapter_title is None:
            chapter_title = part.title
            chapter_start_ms = cursor_ms
        cursor_ms += round(part.duration * 1000)
    if chapter_title is not None:
        chapters.append((chapter_title, chapter_start_ms, cursor_ms))

    for title, start_ms, end_ms in chapters:
        lines.append("")
        lines.append("[CHAPTER]")
        lines.append("TIMEBASE=1/1000")
        lines.append(f"START={start_ms}")
        lines.append(f"END={end_ms}")
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
