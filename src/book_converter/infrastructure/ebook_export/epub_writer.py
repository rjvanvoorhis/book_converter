import html as html_lib
import io
import re
import uuid

from ebooklib import epub

from book_converter.core import entities as core_entities

_LANGUAGE_CODES = {
    "english": "en",
    "french": "fr",
    "german": "de",
    "spanish": "es",
    "italian": "it",
    "portuguese": "pt",
    "russian": "ru",
    "japanese": "ja",
    "chinese": "zh",
}
_SCENE_BREAK = re.compile(r"^(?:[*#~=_-]\s*){3,}$")
_STYLESHEET = """\
p { margin: 0; text-indent: 1.2em; }
h2 + p, hr + p { text-indent: 0; }
hr { margin: 1.5em 25%; }
"""


class EpubWriter:
    format = "epub"

    def write(self, book: core_entities.Book) -> bytes:
        metadata = book.metadata
        language = _language_code(metadata.language)

        output = epub.EpubBook()
        output.set_identifier(_identifier(metadata))
        output.set_title(metadata.title)
        output.set_language(language)
        if metadata.author:
            output.add_author(metadata.author)

        style = epub.EpubItem(
            uid="style",
            file_name="style.css",
            media_type="text/css",
            content=_STYLESHEET,
        )
        output.add_item(style)

        by_chapter_id: dict[int, epub.EpubHtml] = {}
        for index, chapter in enumerate(book.chapters, start=1):
            item = epub.EpubHtml(
                title=chapter.title,
                file_name=f"chapter_{index:04d}.xhtml",
                lang=language,
            )
            item.set_content(_chapter_html(chapter))
            item.add_item(style)
            output.add_item(item)
            by_chapter_id[chapter.id] = item

        output.toc = list(by_chapter_id.values())
        output.add_item(epub.EpubNcx())
        output.add_item(epub.EpubNav())
        output.spine = ["nav", *by_chapter_id.values()]

        buffer = io.BytesIO()
        epub.write_epub(buffer, output)
        return buffer.getvalue()


def _chapter_html(chapter: core_entities.Chapter) -> str:
    if chapter.html:
        return chapter.html
    return _html_from_text(chapter.title, chapter.content)


def _html_from_text(title: str, content: str) -> str:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", content) if p.strip()]
    # Sources that read the title aloud prepend it to the text; the heading
    # added here replaces it.
    if paragraphs and paragraphs[0] == title.strip():
        paragraphs = paragraphs[1:]

    body = [f"<h2>{html_lib.escape(title, quote=False)}</h2>"]
    for paragraph in paragraphs:
        if _SCENE_BREAK.match(paragraph):
            body.append("<hr/>")
            continue
        lines = (html_lib.escape(line, quote=False) for line in paragraph.splitlines())
        body.append("<p>" + "<br/>".join(lines) + "</p>")
    return "\n".join(body)


def _language_code(language: str | None) -> str:
    if not language:
        return "en"
    value = language.strip().lower()
    if re.fullmatch(r"[a-z]{2,3}(-[a-z0-9]+)*", value):
        return value
    return _LANGUAGE_CODES.get(value, "en")


def _identifier(metadata: core_entities.BookMetadata) -> str:
    if metadata.identifier:
        return metadata.identifier
    # Stable per work, so re-exporting updates the same item in a library
    # rather than appearing as a new book.
    seed = f"{metadata.author or ''}\n{metadata.title}"
    return f"urn:uuid:{uuid.uuid5(uuid.NAMESPACE_URL, seed)}"
