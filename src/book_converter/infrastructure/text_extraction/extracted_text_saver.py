from book_converter.core import entities as core_entities
from book_converter.infrastructure.extracted_text import format


class ExtractedTextSaver:
    def save(self, identifier: str, book: core_entities.Book) -> None:
        format.write_book(identifier, book)
