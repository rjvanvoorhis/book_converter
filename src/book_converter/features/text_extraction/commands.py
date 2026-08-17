import dataclasses

from book_converter.features.text_extraction import dto
from book_converter.features.text_extraction import use_cases
from book_converter.presentation import cli


@dataclasses.dataclass(frozen=True)
class LoadEbookCommand:
    use_case: use_cases.LoadEbookUseCase

    @property
    def name(self) -> str:
        return "load"

    @property
    def description(self) -> str:
        return "Load an ebook and display its metadata and chapter list."

    def execute(self, identifier: str) -> str:
        output = self.use_case.execute(dto.LoadEbookInput(identifier=identifier))
        lines = [
            f"{output.title} by {output.author or 'Unknown'}",
            f"Language: {output.language or 'Unknown'}",
            f"Chapters: {output.total_chapters} ({output.total_word_count} words)",
        ]
        lines.extend(
            f"  [{chapter.id}] {chapter.title} ({chapter.word_count} words)"
            for chapter in output.chapters
        )
        return "\n".join(lines)


@dataclasses.dataclass(frozen=True)
class ExtractChapterCommand:
    use_case: use_cases.ExtractChapterUseCase

    @property
    def name(self) -> str:
        return "extract-chapter"

    @property
    def description(self) -> str:
        return "Print the text content of a single chapter."

    def execute(self, identifier: str, chapter_id: int) -> str:
        output = self.use_case.execute(
            dto.ExtractChapterInput(identifier=identifier, chapter_id=chapter_id)
        )
        return output.content


def build_commands(
    load_ebook: use_cases.LoadEbookUseCase,
    extract_chapter: use_cases.ExtractChapterUseCase,
) -> list[cli.Command]:
    return [
        LoadEbookCommand(use_case=load_ebook),
        ExtractChapterCommand(use_case=extract_chapter),
    ]
