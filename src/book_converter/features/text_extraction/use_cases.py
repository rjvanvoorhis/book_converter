import dataclasses

from book_converter.features.text_extraction import dto
from book_converter.features.text_extraction import interfaces


@dataclasses.dataclass
class LoadEbookUseCase:
    repository: interfaces.EbookRepository
    converter: interfaces.EbookConverter

    def execute(self, input_dto: dto.LoadEbookInput) -> dto.LoadEbookOutput:

        book = self.repository.get_book(input_dto.identifier)
        converted = self.converter.convert(book)

        return dto.LoadEbookOutput(
            title=converted.metadata.title,
            author=converted.metadata.author,
            language=converted.metadata.language,
            identifier=converted.metadata.identifier,
            total_chapters=len(converted.chapters),
            total_word_count=converted.get_total_word_count(),
            chapters=[
                dto.ChapterDto(
                    id=chapter.id,
                    title=chapter.title,
                    order=chapter.order,
                    word_count=chapter.get_word_count(),
                )
                for chapter in converted.chapters
            ],
        )


@dataclasses.dataclass
class ExtractChapterUseCase:
    repository: interfaces.EbookRepository
    converter: interfaces.EbookConverter

    def execute(self, input_dto: dto.ExtractChapterInput) -> dto.ExtractChapterOutput:
        book = self.repository.get_book(input_dto.identifier)
        converted = self.converter.convert(book)
        chapter = converted.get_chapter_by_id(input_dto.chapter_id)
        return dto.ExtractChapterOutput(
            chapter_id=chapter.id,
            title=chapter.title,
            content=chapter.content,
            word_count=chapter.get_word_count(),
        )
