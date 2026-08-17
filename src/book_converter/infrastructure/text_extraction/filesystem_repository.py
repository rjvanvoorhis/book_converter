import pathlib

from book_converter.features.text_extraction import entities

_SUPPORTED_FORMATS = ("epub", "mobi")


class FilesystemEbookRepository:
    def get_book(self, identifier: str) -> entities.RawBook:
        path = pathlib.Path(identifier)
        if not path.is_file():
            raise FileNotFoundError(f"No ebook file found at '{identifier}'")

        suffix = path.suffix.lower().lstrip(".")
        if suffix not in _SUPPORTED_FORMATS:
            raise ValueError(f"Unsupported ebook format '{suffix}' for '{identifier}'")

        return entities.RawBook(format=suffix, data=path.read_bytes())
