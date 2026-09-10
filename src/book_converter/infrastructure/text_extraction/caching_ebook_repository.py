import dataclasses
import time

from book_converter.features.text_extraction import entities, interfaces


@dataclasses.dataclass
class CachingEbookRepository:
    """Wraps a network-backed EbookRepository so that loading a book (to
    preview it), then extracting a chapter, then saving it for later don't
    each independently re-fetch and re-parse the same source - the UI's
    Load -> Review -> Save for later flow would otherwise make up to three
    round trips to the same AO3/FanFiction.net work for one user action.
    RawBook is just fetched bytes, safe to hand out to multiple callers -
    each conversion produces a fresh Book/Chapter graph downstream."""

    repository: interfaces.EbookRepository
    ttl_seconds: float = 600.0

    _cache: dict[str, tuple[float, entities.RawBook]] = dataclasses.field(
        default_factory=dict, init=False, repr=False, compare=False
    )

    def get_book(self, identifier: str) -> entities.RawBook:
        now = time.monotonic()
        cached = self._cache.get(identifier)
        if cached is not None and now - cached[0] < self.ttl_seconds:
            return cached[1]

        book = self.repository.get_book(identifier)
        self._cache[identifier] = (now, book)
        return book
