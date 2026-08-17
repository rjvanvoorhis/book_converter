import io
import unicodedata

import ebooklib
from ebooklib import epub

from book_converter.core import entities as core_entities
from book_converter.features.text_extraction import entities
from book_converter.infrastructure.text_extraction import html_text


class EpubConverter:
    def supports(self) -> list[entities.BookFormat]:
        return ["epub"]

    def convert(self, raw_book: entities.RawBook) -> core_entities.Book:
        if raw_book.format != "epub":
            raise ValueError(f"EpubConverter does not support format '{raw_book.format}'")

        source = epub.read_epub(io.BytesIO(raw_book.data))
        book = core_entities.Book(metadata=_extract_metadata(source))

        titles_by_href = _toc_titles_by_href(source.toc)

        order = 0
        for idref, _linear in source.spine:
            item = source.get_item_with_id(idref)
            if item is None or item.get_type() != ebooklib.ITEM_DOCUMENT:
                continue
            if not item.is_chapter():
                continue

            tree = html_text.parse_html(item.get_content())

            title = titles_by_href.get(_strip_fragment(item.get_name()))
            if not title:
                title = html_text.extract_heading(tree) or f"Chapter {order + 1}"

            content = html_text.extract_body_text(tree)
            if not content:
                continue

            book.add_chapter(
                core_entities.Chapter(
                    id=core_entities.ChapterId(order),
                    title=title,
                    content=content,
                    order=order,
                )
            )
            order += 1

        return book


def _extract_metadata(source: epub.EpubBook) -> core_entities.BookMetadata:
    title = _first_metadata_value(source, "title") or "Untitled"
    author = _first_metadata_value(source, "creator")
    return core_entities.BookMetadata(
        title=unicodedata.normalize("NFKC", title),
        author=unicodedata.normalize("NFKC", author) if author else None,
        language=_first_metadata_value(source, "language"),
        identifier=_first_metadata_value(source, "identifier"),
    )


def _first_metadata_value(source: epub.EpubBook, name: str) -> str | None:
    values = source.get_metadata("DC", name)
    return values[0][0] if values else None


def _toc_titles_by_href(toc) -> dict[str, str]:
    titles: dict[str, str] = {}
    _walk_toc(toc, titles)
    return titles


def _walk_toc(entries, titles: dict[str, str]) -> None:
    for entry in entries:
        if isinstance(entry, epub.Link):
            titles.setdefault(_strip_fragment(entry.href), entry.title)
        elif isinstance(entry, (tuple, list)):
            _walk_toc(entry, titles)


def _strip_fragment(href: str) -> str:
    return href.split("#", 1)[0]
