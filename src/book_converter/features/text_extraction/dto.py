import dataclasses


@dataclasses.dataclass
class LoadEbookInput:
    identifier: str


@dataclasses.dataclass
class ChapterDto:
    id: int
    title: str
    order: int
    word_count: int


@dataclasses.dataclass
class LoadEbookOutput:
    title: str
    author: str | None
    language: str | None
    identifier: str | None
    total_chapters: int
    total_word_count: int
    chapters: list[ChapterDto]


@dataclasses.dataclass
class ExtractChapterInput:
    identifier: str
    chapter_id: int


@dataclasses.dataclass
class ExtractChapterOutput:
    chapter_id: int
    title: str
    content: str
    word_count: int
