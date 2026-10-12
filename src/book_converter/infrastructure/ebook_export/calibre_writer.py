import dataclasses
import pathlib
import shutil
import subprocess
import tempfile

from book_converter.core import entities as core_entities
from book_converter.infrastructure.ebook_export import epub_writer

_CALIBRE_FORMATS = ("azw3", "mobi", "pdf", "fb2", "txt")


@dataclasses.dataclass(frozen=True)
class CalibreEbookWriter:
    """Builds an epub, then has Calibre's `ebook-convert` turn it into
    `format`. Only registered when Calibre is installed - see
    `build_writers`."""

    format: str
    executable: str
    epub: epub_writer.EpubWriter = dataclasses.field(
        default_factory=epub_writer.EpubWriter
    )

    def write(self, book: core_entities.Book) -> bytes:
        with tempfile.TemporaryDirectory(prefix="ebook-export-") as work_dir:
            source = pathlib.Path(work_dir) / "book.epub"
            target = pathlib.Path(work_dir) / f"book.{self.format}"
            source.write_bytes(self.epub.write(book))
            result = subprocess.run(
                [self.executable, str(source), str(target)],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0 or not target.is_file():
                raise RuntimeError(
                    f"ebook-convert failed for '{self.format}': "
                    f"{(result.stderr or result.stdout).strip()[-500:]}"
                )
            return target.read_bytes()


def build_writers() -> dict:
    writers = {"epub": epub_writer.EpubWriter()}
    executable = shutil.which("ebook-convert")
    if executable:
        for file_format in _CALIBRE_FORMATS:
            writers[file_format] = CalibreEbookWriter(
                format=file_format, executable=executable
            )
    return writers
