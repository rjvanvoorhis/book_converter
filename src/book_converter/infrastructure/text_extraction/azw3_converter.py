import shutil
import tempfile
from pathlib import Path

import mobi
from ebooklib import epub

from book_converter.core import entities as core_entities
from book_converter.features.text_extraction import entities
from book_converter.infrastructure.text_extraction import epub_converter


class Azw3Converter:
    def supports(self) -> list[entities.BookFormat]:
        return ["azw3"]

    def convert(self, raw_book: entities.RawBook) -> core_entities.Book:
        if raw_book.format != "azw3":
            raise ValueError(
                f"Azw3Converter does not support format '{raw_book.format}'"
            )

        with tempfile.TemporaryDirectory(prefix="azw3-in-") as input_dir:
            source_path = Path(input_dir) / "book.azw3"
            source_path.write_bytes(raw_book.data)
            extract_dir, output_path = mobi.extract(str(source_path))
            try:
                if not output_path.endswith(".epub"):
                    raise ValueError(
                        "Could not extract text from azw3 file: "
                        "the book does not contain a KF8 (epub-convertible) part"
                    )
                source = epub.read_epub(output_path)
                return epub_converter.convert_epub_book(source)
            finally:
                shutil.rmtree(extract_dir, ignore_errors=True)
