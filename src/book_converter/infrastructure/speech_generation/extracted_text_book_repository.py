from book_converter.core import entities as core_entities
from book_converter.infrastructure.extracted_text import format


class ExtractedTextBookRepository:
    def get_book(self, identifier: str) -> core_entities.Book:
        return format.read_book(identifier)
