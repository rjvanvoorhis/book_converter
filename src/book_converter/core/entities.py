import typing
import dataclasses


ChapterId = typing.NewType("ChapterId", int)


@dataclasses.dataclass(frozen=True)
class BookMetadata:
    title: str
    author: str | None
    language: str | None
    identifier: str | None


@dataclasses.dataclass
class Chapter:
    id: ChapterId
    title: str
    content: str
    order: int

    def get_word_count(self):
        return len(self.content.split())


@dataclasses.dataclass
class Book:
    metadata: BookMetadata
    chapters: list[Chapter] = dataclasses.field(default_factory=list)

    def add_chapter(self, chapter: Chapter) -> None:
        if any(existing.id == chapter.id for existing in self.chapters):
            raise ValueError(
                f"Book '{self.metadata.title}' already contains chapter '{chapter.id}'"
            )
        self.chapters.append(chapter)

    def get_total_word_count(self) -> int:
        return sum(chapter.get_word_count() for chapter in self.chapters)

    def get_chapter_by_id(self, id: ChapterId) -> Chapter | None:
        for chapter in self.chapters:
            if chapter.id == id:
                return chapter
        return None
