import dataclasses
import difflib

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


@dataclasses.dataclass
class ExtractTextUseCase:
    repository: interfaces.EbookRepository
    converter: interfaces.EbookConverter
    saver: interfaces.EbookSaver

    def execute(self, input_dto: dto.ExtractTextInput) -> dto.ExtractTextOutput:
        raw_book = self.repository.get_book(input_dto.identifier)
        book = self.converter.convert(raw_book)
        self.saver.save(input_dto.target, book)
        return dto.ExtractTextOutput(
            destination=input_dto.target, total_chapters=len(book.chapters)
        )


@dataclasses.dataclass
class CopyEditTextUseCase:
    repository: interfaces.ExtractedTextRepository
    editor: interfaces.CopyEditor
    saver: interfaces.EbookSaver

    def execute(self, input_dto: dto.CopyEditInput) -> dto.CopyEditOutput:
        book = self.repository.get_book(input_dto.identifier)

        chapter_results = []
        for chapter in book.chapters:
            original = chapter.content
            edited = self.editor.edit(original)
            diff = _diff(chapter.title, original, edited) if edited != original else ""
            chapter_results.append(
                dto.ChapterEditDto(id=chapter.id, title=chapter.title, diff=diff)
            )
            chapter.content = edited

        self.saver.save(input_dto.identifier, book)
        return dto.CopyEditOutput(
            destination=input_dto.identifier, chapters=chapter_results
        )


def _diff(title: str, original: str, edited: str) -> str:
    return "\n".join(
        difflib.unified_diff(
            original.splitlines(),
            edited.splitlines(),
            fromfile=f"{title} (original)",
            tofile=f"{title} (edited)",
            lineterm="",
        )
    )
