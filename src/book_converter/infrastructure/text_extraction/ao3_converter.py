import dataclasses
import json

from book_converter.core import entities as core_entities
from book_converter.features.text_extraction import entities
from book_converter.infrastructure.text_extraction import html_text


@dataclasses.dataclass
class _ParsedWork:
    title: str
    author: str | None
    language: str | None
    chapters: list[tuple[str | None, str]]


class Ao3HtmlConverter:
    def supports(self) -> list[entities.BookFormat]:
        return ["ao3"]

    def convert(self, raw_book: entities.RawBook) -> core_entities.Book:
        if raw_book.format != "ao3":
            raise ValueError(f"Ao3HtmlConverter does not support format '{raw_book.format}'")

        payload = json.loads(raw_book.data.decode("utf-8"))
        works = [_parse_work(entry["html"]) for entry in payload["works"]]
        series_title = payload.get("series_title")
        multi_work = len(works) > 1
        position_width = max(2, len(str(len(works))))

        book = core_entities.Book(metadata=_build_metadata(works, series_title))

        order = 0
        parts = []
        for index, work in enumerate(works):
            position = index + 1 if multi_work else None
            work_metadata = _work_metadata(work, position, position_width)
            part_chapters = []
            for chapter_title, content in work.chapters:
                if not content:
                    continue
                chapter = core_entities.Chapter(
                    id=core_entities.ChapterId(order),
                    title=chapter_title or work.title,
                    content=content,
                    order=order,
                )
                book.add_chapter(chapter)
                part_chapters.append(chapter)
                order += 1
            parts.append(core_entities.BookPart(metadata=work_metadata, chapters=part_chapters))

        if not book.chapters:
            raise ValueError("Could not find any chapter content in the AO3 work")

        if multi_work:
            book.parts = [part for part in parts if part.chapters]

        return book


def _work_metadata(
    work: _ParsedWork, position: int | None, position_width: int
) -> core_entities.BookMetadata:
    title = work.title
    if position is not None:
        title = f"Book {str(position).zfill(position_width)} - {title}"
    return core_entities.BookMetadata(
        title=title, author=work.author, language=work.language, identifier=None
    )


def _build_metadata(
    works: list[_ParsedWork], series_title: str | None
) -> core_entities.BookMetadata:
    first = works[0]
    return core_entities.BookMetadata(
        title=series_title or first.title,
        author=first.author,
        language=first.language,
        identifier=None,
    )


def _parse_work(markup: str) -> _ParsedWork:
    tree = html_text.parse_html(markup)
    title = _work_title(tree)
    return _ParsedWork(
        title=title,
        author=_work_author(tree),
        language=_work_language(tree),
        chapters=_work_chapters(tree),
    )


def _work_title(tree) -> str:
    preface = next(
        (
            element
            for element in html_text.find_by_classes(tree, "div", "preface", "group")
            if "chapter" not in html_text.element_classes(element)
        ),
        None,
    )
    heading = preface.find(".//h2") if preface is not None else None
    if heading is None:
        return "Untitled"
    return html_text.normalize_text(heading.text_content()) or "Untitled"


def _work_author(tree) -> str | None:
    bylines = html_text.find_by_classes(tree, "h3", "byline", "heading")
    if not bylines:
        return None
    names = [
        html_text.normalize_text(link.text_content()) for link in bylines[0].iter("a")
    ]
    names = [name for name in names if name]
    return ", ".join(names) or None


def _work_language(tree) -> str | None:
    nodes = html_text.find_by_classes(tree, "dd", "language")
    if not nodes:
        return None
    return html_text.normalize_text(nodes[0].text_content()) or None


def _work_chapters(tree) -> list[tuple[str | None, str]]:
    chapters_div = next(iter(tree.xpath('//div[@id="chapters"]')), None)
    if chapters_div is None:
        return []

    chapter_divs = chapters_div.xpath('./div[starts-with(@id, "chapter-")]')
    if not chapter_divs:
        chapter_divs = [chapters_div]

    return [
        (_chapter_title(chapter_div), _chapter_content(chapter_div))
        for chapter_div in chapter_divs
    ]


def _chapter_title(chapter_div) -> str | None:
    prefaces = [
        element
        for element in chapter_div.iter("div")
        if {"chapter", "preface", "group"}.issubset(
            html_text.element_classes(element)
        )
    ]
    if not prefaces:
        return None
    headings = [
        element
        for element in prefaces[0].iter("h3")
        if "title" in html_text.element_classes(element)
    ]
    if not headings:
        return None
    return html_text.normalize_text(headings[0].text_content()) or None


def _chapter_content(chapter_div) -> str:
    articles = [
        element for element in chapter_div.iter("div") if element.get("role") == "article"
    ]
    if not articles:
        return ""
    return html_text.extract_body_text(articles[0])
