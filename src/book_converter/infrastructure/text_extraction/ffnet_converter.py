import json
import re

from book_converter.core import entities as core_entities
from book_converter.features.text_extraction import entities
from book_converter.infrastructure.text_extraction import html_text

# FanFiction.net doesn't close <option> tags, so a regex is simpler than
# coaxing lxml into treating them as leaf nodes.
_CHAPTER_OPTION = re.compile(r"<option\s+value=(\d+)[^>]*>(\d+)\.\s*([^<]*)")


class FfNetHtmlConverter:
    def supports(self) -> list[entities.BookFormat]:
        return ["ffnet"]

    def convert(self, raw_book: entities.RawBook) -> core_entities.Book:
        if raw_book.format != "ffnet":
            raise ValueError(
                f"FfNetHtmlConverter does not support format '{raw_book.format}'"
            )

        payload = json.loads(raw_book.data.decode("utf-8"))
        chapters_payload = payload["chapters"]

        first_tree = html_text.parse_html(chapters_payload[0]["html"])
        book = core_entities.Book(metadata=_extract_metadata(first_tree))
        single_chapter = len(chapters_payload) == 1

        for entry in chapters_payload:
            tree = (
                first_tree
                if entry is chapters_payload[0]
                else html_text.parse_html(entry["html"])
            )
            number = entry["number"]
            content = _chapter_content(tree)
            if not content:
                continue
            fallback_title = (
                book.metadata.title if single_chapter else f"Chapter {number}"
            )
            title = _chapter_title(entry["html"], number) or fallback_title
            order = number - 1
            book.add_chapter(
                core_entities.Chapter(
                    id=core_entities.ChapterId(order),
                    title=title,
                    content=f"{title}\n\n{content}",
                    order=order,
                )
            )

        if not book.chapters:
            raise ValueError(
                "Could not find any chapter content in the FanFiction.net story"
            )

        return book


def _extract_metadata(tree) -> core_entities.BookMetadata:
    return core_entities.BookMetadata(
        title=_story_title(tree),
        author=_story_author(tree),
        language=_story_language(tree),
        identifier=None,
    )


def _story_title(tree) -> str:
    heading = next(
        iter(tree.xpath('//div[@id="profile_top"]//b[@class="xcontrast_txt"]')), None
    )
    if heading is None:
        return "Untitled"
    return html_text.normalize_text(heading.text_content()) or "Untitled"


def _story_author(tree) -> str | None:
    link = next(
        (
            a
            for a in tree.xpath('//div[@id="profile_top"]//a')
            if (a.get("href") or "").startswith("/u/")
        ),
        None,
    )
    if link is None:
        return None
    return html_text.normalize_text(link.text_content()) or None


def _story_language(tree) -> str | None:
    spans = tree.xpath('//span[@class="xgray xcontrast_txt"]')
    if not spans:
        return None
    fields = spans[0].text_content().split(" - ")
    if len(fields) < 2:
        return None
    return html_text.normalize_text(fields[1]) or None


def _chapter_title(markup: str, chapter_number: int) -> str | None:
    for value, _number, title in _CHAPTER_OPTION.findall(markup):
        if int(value) == chapter_number:
            return html_text.normalize_text(title)
    return None


def _chapter_content(tree) -> str:
    story_div = tree.get_element_by_id("storytext", None)
    if story_div is None:
        return ""
    return html_text.extract_body_text(story_div)
