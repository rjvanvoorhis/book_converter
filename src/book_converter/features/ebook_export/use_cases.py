import dataclasses
import pathlib
import re

from book_converter.features.ebook_export import dto, interfaces


@dataclasses.dataclass
class ExportEbookUseCase:
    """Produces ebook files from any source - one ebook per work. A series
    is never merged into an omnibus: each of its works becomes its own file,
    numbered by position inside a folder named after the series.

    Where the source site has its own download for the requested format
    (AO3), that file is used as is - it carries the site's metadata, tags and
    styling. Otherwise the file is built from the parsed book by the writer
    registered for the format."""

    book_repository: interfaces.BookRepository
    writers: dict[str, interfaces.EbookWriter]
    file_store: interfaces.EbookFileStore
    native_source: interfaces.NativeEbookSource | None = None
    work_lister: interfaces.WorkLister | None = None

    def execute(self, input_dto: dto.ExportEbookInput) -> dto.ExportEbookOutput:
        file_format = input_dto.format.lower().lstrip(".")
        if file_format not in self.writers and self.native_source is None:
            self._unknown_format(file_format)

        collection = (
            self.work_lister.list_works(input_dto.identifier)
            if self.work_lister is not None
            else None
        )
        if collection is None:
            identifiers = [input_dto.identifier]
            folder = pathlib.Path(input_dto.target)
            prefixes: list[str | None] = [None]
        else:
            identifiers = collection.identifiers
            folder = pathlib.Path(input_dto.target) / _safe_filename(
                collection.title or "series"
            )
            width = max(2, len(str(len(identifiers))))
            prefixes = [str(i).zfill(width) for i in range(1, len(identifiers) + 1)]

        ebooks = [
            self._export_one(
                identifier, folder, file_format, prefix, single=collection is None
            )
            for identifier, prefix in zip(identifiers, prefixes)
        ]
        return dto.ExportEbookOutput(
            format=file_format,
            collection=collection.title if collection else None,
            ebooks=ebooks,
        )

    def _export_one(
        self,
        identifier: str,
        folder: pathlib.Path,
        file_format: str,
        prefix: str | None,
        single: bool,
    ) -> dto.ExportedEbook:
        native = (
            self.native_source.fetch(identifier, file_format)
            if self.native_source is not None
            else None
        )
        if native is not None:
            data, name = native.data, native.name
        else:
            writer = self.writers.get(file_format)
            if writer is None:
                self._unknown_format(file_format)
            book = self.book_repository.get_book(identifier)
            data = writer.write(book)
            name = " - ".join(
                part for part in (book.metadata.author, book.metadata.title) if part
            )

        if single and folder.suffix.lower() == f".{file_format}":
            destination = folder
        else:
            stem = _safe_filename(name)
            destination = (
                folder / f"{prefix} - {stem}.{file_format}"
                if prefix
                else (folder / f"{stem}.{file_format}")
            )
        return dto.ExportedEbook(
            path=self.file_store.save(str(destination), data),
            native=native is not None,
        )

    def _unknown_format(self, file_format: str) -> None:
        available = ", ".join(sorted(self.writers))
        raise ValueError(
            f"Unknown ebook format '{file_format}'. Available: {available}"
        )


def _safe_filename(name: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|]+', "", name).strip(" .")
    return cleaned or "book"
