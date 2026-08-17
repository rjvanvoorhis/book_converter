import dataclasses

from book_converter.core import entities as core_entities
from book_converter.features.text_extraction import interfaces as text_extraction_interfaces


@dataclasses.dataclass(frozen=True)
class EbookBookRepository:
    repository: text_extraction_interfaces.EbookRepository
    converter: text_extraction_interfaces.EbookConverter

    def get_book(self, identifier: str) -> core_entities.Book:
        raw_book = self.repository.get_book(identifier)
        return self.converter.convert(raw_book)
