import dataclasses
import typing

from book_converter.core import entities as core_entities


class BookRepository(typing.Protocol):
    def get_book(self, identifier: str) -> core_entities.Book: ...


class EbookWriter(typing.Protocol):
    @property
    def format(self) -> str: ...

    def write(self, book: core_entities.Book) -> bytes: ...


@dataclasses.dataclass(frozen=True)
class NativeEbook:
    data: bytes
    # The site's own suggested file name (without extension).
    name: str


class NativeEbookSource(typing.Protocol):
    def fetch(self, identifier: str, file_format: str) -> NativeEbook | None:
        """The work as the source site's own ebook file in `file_format`, or
        None when the site doesn't offer one - callers then build the file
        from the parsed Book instead."""
        ...


@dataclasses.dataclass(frozen=True)
class WorkCollection:
    """A series: each identifier is exported as its own ebook, in order."""

    title: str | None
    identifiers: list[str]


class WorkLister(typing.Protocol):
    def list_works(self, identifier: str) -> WorkCollection | None:
        """The works behind a series identifier, or None when `identifier`
        is a single work."""
        ...


class EbookFileStore(typing.Protocol):
    def save(self, destination: str, data: bytes) -> str:
        """Writes `data` and returns the path actually written."""
        ...
