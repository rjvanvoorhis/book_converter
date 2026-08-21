import dataclasses

from book_converter.core import entities as core_entities
from book_converter.features.text_extraction import entities
from book_converter.features.text_extraction import interfaces


@dataclasses.dataclass(frozen=True)
class DispatchingEbookConverter:
    converters: list[interfaces.EbookConverter]

    def supports(self) -> list[entities.BookFormat]:
        return [
            book_format
            for converter in self.converters
            for book_format in converter.supports()
        ]

    def convert(self, raw_book: entities.RawBook) -> core_entities.Book:
        for converter in self.converters:
            if raw_book.format in converter.supports():
                return converter.convert(raw_book)

        raise ValueError(f"No converter is registered for format '{raw_book.format}'")
