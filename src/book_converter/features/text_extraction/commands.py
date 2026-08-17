import dataclasses
import typing

from book_converter.features.text_extraction import dto
from book_converter.features.text_extraction import use_cases
from book_converter.presentation import cli

_UseCaseT = typing.TypeVar("_UseCaseT")


@dataclasses.dataclass(frozen=True)
class LoadEbookCommand:
    use_cases_by_source: dict[str, use_cases.LoadEbookUseCase]

    @property
    def name(self) -> str:
        return "load"

    @property
    def description(self) -> str:
        return "Load an ebook and display its metadata and chapter list."

    def execute(self, identifier: str, source: str = "file") -> str:
        use_case = _resolve(self.use_cases_by_source, source)
        output = use_case.execute(dto.LoadEbookInput(identifier=identifier))
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
    use_cases_by_source: dict[str, use_cases.ExtractChapterUseCase]

    @property
    def name(self) -> str:
        return "extract-chapter"

    @property
    def description(self) -> str:
        return "Print the text content of a single chapter."

    def execute(self, identifier: str, chapter_id: int, source: str = "file") -> str:
        use_case = _resolve(self.use_cases_by_source, source)
        output = use_case.execute(
            dto.ExtractChapterInput(identifier=identifier, chapter_id=chapter_id)
        )
        return output.content


@dataclasses.dataclass(frozen=True)
class ExtractTextCommand:
    use_cases_by_source: dict[str, use_cases.ExtractTextUseCase]

    @property
    def name(self) -> str:
        return "extract-text"

    @property
    def description(self) -> str:
        return (
            "Extract an ebook's chapters to a folder of plain-text files "
            "for review and editing before speech generation."
        )

    def execute(self, identifier: str, target: str, source: str = "file") -> str:
        use_case = _resolve(self.use_cases_by_source, source)
        output = use_case.execute(
            dto.ExtractTextInput(identifier=identifier, target=target)
        )
        return f"Extracted {output.total_chapters} chapters to {output.destination}"


@dataclasses.dataclass(frozen=True)
class CopyEditTextCommand:
    use_cases_by_editor: dict[str, use_cases.CopyEditTextUseCase]

    @property
    def name(self) -> str:
        return "copyedit"

    @property
    def description(self) -> str:
        return "Run a copyedit pass over an extracted-text folder in place."

    def execute(self, identifier: str, editor: str = "languagetool") -> str:
        use_case = _resolve(self.use_cases_by_editor, editor, label="editor")
        output = use_case.execute(dto.CopyEditInput(identifier=identifier))
        changed = [chapter for chapter in output.chapters if chapter.diff]
        if not changed:
            return f"No changes suggested for {output.destination}."

        lines = [
            f"Updated {len(changed)}/{len(output.chapters)} chapters in "
            f"{output.destination}:",
            "",
        ]
        for chapter in changed:
            lines.append(chapter.diff)
            lines.append("")
        return "\n".join(lines)


def build_commands(
    load_ebook_by_source: dict[str, use_cases.LoadEbookUseCase],
    extract_chapter_by_source: dict[str, use_cases.ExtractChapterUseCase],
    extract_text_by_source: dict[str, use_cases.ExtractTextUseCase],
    copyedit_by_editor: dict[str, use_cases.CopyEditTextUseCase],
) -> list[cli.Command]:
    return [
        LoadEbookCommand(use_cases_by_source=load_ebook_by_source),
        ExtractChapterCommand(use_cases_by_source=extract_chapter_by_source),
        ExtractTextCommand(use_cases_by_source=extract_text_by_source),
        CopyEditTextCommand(use_cases_by_editor=copyedit_by_editor),
    ]


def _resolve(
    use_cases_by_key: dict[str, _UseCaseT], key: str, label: str = "source"
) -> _UseCaseT:
    try:
        return use_cases_by_key[key]
    except KeyError:
        available = ", ".join(sorted(use_cases_by_key))
        raise ValueError(f"Unknown {label} '{key}'. Available: {available}") from None
