import typing
from book_converter.core import entities as core_entities
from book_converter.features.text_extraction import entities


class EbookRepository(typing.Protocol):
    def get_book(self, identifier: str) -> entities.RawBook: ...


class EbookConverter(typing.Protocol):
    def supports(self) -> list[entities.BookFormat]: ...

    def convert(self, raw_book: entities.RawBook) -> core_entities.Book: ...


class EbookSaver(typing.Protocol):
    def save(identifier: str, book: core_entities.Book) -> None: ...
