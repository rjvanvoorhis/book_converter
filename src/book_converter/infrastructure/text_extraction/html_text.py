import html as html_lib
import re
import unicodedata

from lxml import html as lxml_html


_BLOCK_TAGS = (
    "p",
    "div",
    "li",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "blockquote",
    "tr",
    "table",
    "section",
    "article",
    "header",
    "footer",
    "figure",
    "figcaption",
)

_HEADING_TAGS = ("h1", "h2", "h3", "h4", "h5", "h6")

_CHARACTER_HARMONIZATION = str.maketrans(
    {
        "‘": "'",  # ‘ left single quote
        "’": "'",  # ’ right single quote
        "‚": "'",  # ‚ single low-9 quote
        "“": '"',  # “ left double quote
        "”": '"',  # ” right double quote
        "„": '"',  # „ double low-9 quote
        "–": "-",  # – en dash
        "—": "-",  # — em dash
        "…": "...",  # … ellipsis
        " ": " ",  # non-breaking space
        "​": "",  # zero-width space
        "‌": "",  # zero-width non-joiner
        "‍": "",  # zero-width joiner
        "﻿": "",  # byte order mark / zero-width no-break space
    }
)

_SPACE_BEFORE_PUNCTUATION = re.compile(r"[ \t]+([,.;:!?])")


def parse_html(markup: str | bytes) -> lxml_html.HtmlElement:
    return lxml_html.fromstring(markup)


def element_classes(element: lxml_html.HtmlElement) -> set[str]:
    return set((element.get("class") or "").split())


def find_by_classes(
    tree: lxml_html.HtmlElement, tag: str, *classes: str
) -> list[lxml_html.HtmlElement]:
    required = set(classes)
    return [
        element
        for element in tree.iter(tag)
        if required.issubset(element_classes(element))
    ]


def extract_heading(tree: lxml_html.HtmlElement) -> str | None:
    heading = next(tree.iter(*_HEADING_TAGS), None)
    if heading is None:
        return None
    return normalize_text(heading.text_content()) or None


def strip_elements_by_class(tree: lxml_html.HtmlElement, *classes: str) -> None:
    """Remove elements (and their subtrees) carrying all of the given classes.

    Used to drop screen-reader-only landmarks (e.g. AO3's "Chapter Text"
    heading) that would otherwise be read out as part of the body text.
    """
    for element in list(tree.iter()):
        if set(classes).issubset(element_classes(element)):
            element.drop_tree()


_AO3_NOTE_LABELS = frozenset(
    {
        "summary",
        "chapter summary",
        "notes",
        "chapter notes",
        "end notes",
        "chapter end notes",
        "work notes",
        "series notes",
    }
)


def strip_ao3_paratext(tree: lxml_html.HtmlElement) -> None:
    """Drop the author-supplied paratext AO3 puts around a chapter: the
    "Summary"/"Notes" blocks above it, the "See the end of the chapter for
    more notes" pointer, and the "End Notes" block below it. In an AO3 export
    these are `<p>Chapter Notes</p>` labels, each followed by a
    `<blockquote class="userstuff">` (the note) or, when the note is at the
    end, only by a `div.endnote-link` pointer. The story itself lives
    elsewhere, so removing them leaves it untouched. A blockquote is only
    dropped when the label paragraph immediately precedes it, so a quotation
    inside the story is never mistaken for a note."""
    for label in list(tree.iter("p")):
        if label.getparent() is None:
            continue
        if normalize_text(label.text_content()).rstrip(":").lower() not in _AO3_NOTE_LABELS:
            continue
        following = label.getnext()
        if (
            following is not None
            and following.tag == "blockquote"
            and "userstuff" in element_classes(following)
        ):
            following.drop_tree()
            label.drop_tree()
        elif following is not None and following.tag == "div" and "endnote-link" in element_classes(following):
            label.drop_tree()  # note lives at the end; the pointer goes below

    for pointer in list(tree.iter("div")):
        if "endnote-link" in element_classes(pointer):
            pointer.drop_tree()


_INLINE_AUTHOR_NOTE = re.compile(r"^\W*author[\u2018\u2019']?s? notes?", re.I)  # no trailing \b: <strong>Note</strong><br/>Text has no space between


def strip_trailing_author_note(
    tree: lxml_html.HtmlElement,
    max_fraction: float = 0.10,
    max_words: int = 1000,
) -> None:
    """Non-AO3 sources (e.g. an FFN-style export) put the author's note in
    the story's own paragraphs: a paragraph that opens "Author's Note" and
    runs to the end of the chapter. Drop that paragraph and everything after
    it, but only when what would go is a small tail of the chapter - a note
    that claims to start a third of the text is far more likely to be a
    character reading an "author's note" in-story than paratext."""
    paragraphs = [p for p in tree.iter("p") if p.text_content().strip()]
    if not paragraphs:
        return
    total = sum(len(p.text_content().split()) for p in paragraphs)
    for index, paragraph in enumerate(paragraphs):
        if not _INLINE_AUTHOR_NOTE.match(paragraph.text_content().strip()):
            continue
        tail = paragraphs[index:]
        tail_words = sum(len(p.text_content().split()) for p in tail)
        if tail_words <= max_words and tail_words <= max_fraction * total:
            for doomed in tail:
                if doomed.getparent() is not None:
                    doomed.drop_tree()
        return


_SOURCE_WHITESPACE = re.compile(r"\s+")


def _collapse_source_whitespace(tree: lxml_html.HtmlElement) -> None:
    """Whitespace in markup is formatting, not content: pretty-printed
    epubs wrap every text run in a span with newlines and indentation
    between it and a neighbouring <em>. Left as is, those newlines survive
    into `normalize_text`, where a whitespace-only line reads as a paragraph
    break and splits "When the <em>Momiji</em> was tied in" into three
    paragraphs. Collapse it to single spaces up front so only block tags and
    <br> (added afterwards) produce line breaks. <pre> content is verbatim."""
    for element in tree.iter():
        in_pre = any(a.tag == "pre" for a in element.iterancestors())
        if element.tail and not in_pre:
            element.tail = _SOURCE_WHITESPACE.sub(" ", element.tail)
        if (
            isinstance(element.tag, str)
            and element.text
            and not in_pre
            and element.tag != "pre"
        ):
            element.text = _SOURCE_WHITESPACE.sub(" ", element.text)


def extract_body_text(tree: lxml_html.HtmlElement) -> str:
    _collapse_source_whitespace(tree)

    for br in tree.iter("br"):
        br.tail = "\n" + (br.tail or "")

    for block in tree.iter(*_BLOCK_TAGS):
        block.tail = "\n\n" + (block.tail or "")

    return normalize_text(tree.text_content())


def normalize_text(raw_text: str) -> str:
    normalized = unicodedata.normalize("NFKC", raw_text).translate(
        _CHARACTER_HARMONIZATION
    )
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in normalized.splitlines()]

    paragraphs: list[str] = []
    current: list[str] = []
    for line in lines:
        if line:
            current.append(line)
        elif current:
            paragraphs.append(" ".join(current))
            current = []
    if current:
        paragraphs.append(" ".join(current))

    return _SPACE_BEFORE_PUNCTUATION.sub(r"\1", "\n\n".join(paragraphs))


_RICH_BLOCK_TAGS = frozenset(
    {"p", "blockquote", "h1", "h2", "h3", "h4", "h5", "h6", "li", "pre"}
)
_RICH_LIST_TAGS = frozenset({"ul", "ol"})
_RICH_INLINE_TAGS = {
    "em": "em",
    "i": "em",
    "strong": "strong",
    "b": "strong",
    "u": "u",
    "s": "s",
    "strike": "s",
    "del": "s",
    "sub": "sub",
    "sup": "sup",
    "code": "code",
}
_DROPPED_TAGS = frozenset({"script", "style", "head", "title", "noscript"})
_INVISIBLE_CHARS = dict.fromkeys(map(ord, "\u200b\u200c\u200d\ufeff"))


def extract_body_html(tree: lxml_html.HtmlElement) -> str:
    """Sanitized XHTML for the element's body: only paragraphs, headings,
    quotes, lists, rules and basic inline emphasis survive, with all
    attributes dropped. Unlike `extract_body_text` this keeps the author's
    typography (curly quotes, dashes, italics) - it's what ebooks are built
    from, where the plain text is what gets spoken."""
    return "\n".join(_render_blocks(tree))


def _render_blocks(element: lxml_html.HtmlElement) -> list[str]:
    blocks: list[str] = []
    inline: list[str] = []

    def flush() -> None:
        paragraph = _tidy("".join(inline))
        inline.clear()
        if _has_content(paragraph):
            blocks.append(f"<p>{paragraph}</p>")

    inline.append(_escape(element.text))
    for child in element:
        tag = child.tag if isinstance(child.tag, str) else ""
        if tag in _DROPPED_TAGS:
            pass
        elif tag == "hr":
            flush()
            blocks.append("<hr/>")
        elif tag in _RICH_BLOCK_TAGS:
            flush()
            inner = _tidy(_render_inline(child))
            if tag == "blockquote" and _has_block_children(child):
                nested = _render_blocks(child)
                if nested:
                    blocks.append("<blockquote>\n" + "\n".join(nested) + "\n</blockquote>")
            elif _has_content(inner):
                blocks.append(f"<{tag}>{inner}</{tag}>")
        elif tag in _RICH_LIST_TAGS:
            flush()
            items = [
                f"<li>{_tidy(_render_inline(item))}</li>"
                for item in child.iter("li")
                if _has_content(_tidy(_render_inline(item)))
            ]
            if items:
                blocks.append(f"<{tag}>\n" + "\n".join(items) + f"\n</{tag}>")
        elif _has_block_children(child) or tag in _BLOCK_TAGS:
            flush()
            blocks.extend(_render_blocks(child))
        else:
            inline.append(_render_inline_node(child))
        inline.append(_escape(child.tail))
    flush()
    return blocks


def _has_block_children(element: lxml_html.HtmlElement) -> bool:
    known = _RICH_BLOCK_TAGS | _RICH_LIST_TAGS | set(_BLOCK_TAGS) | {"hr"}
    return any(isinstance(c.tag, str) and c.tag in known for c in element.iter()
               if c is not element)


def _render_inline(element: lxml_html.HtmlElement) -> str:
    parts = [_escape(element.text)]
    for child in element:
        parts.append(_render_inline_node(child))
        parts.append(_escape(child.tail))
    return "".join(parts)


def _render_inline_node(node: lxml_html.HtmlElement) -> str:
    tag = node.tag if isinstance(node.tag, str) else ""
    if tag in _DROPPED_TAGS:
        return ""
    if tag == "br":
        return "<br/>"
    inner = _render_inline(node)
    wrapper = _RICH_INLINE_TAGS.get(tag)
    if wrapper is None or not inner.strip():
        return inner
    return f"<{wrapper}>{inner}</{wrapper}>"


def _escape(text: str | None) -> str:
    if not text:
        return ""
    text = text.translate(_INVISIBLE_CHARS).replace("\xa0", " ")
    return html_lib.escape(re.sub(r"\s+", " ", text), quote=False)


def _tidy(markup: str) -> str:
    markup = re.sub(r"\s*<br/>\s*", "<br/>", markup)
    markup = re.sub(r"^(?:<br/>)+|(?:<br/>)+$", "", markup.strip())
    return re.sub(r" {2,}", " ", markup).strip()


def _has_content(markup: str) -> bool:
    return bool(re.sub(r"<[^>]+>", "", markup).strip())
