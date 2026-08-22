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


def extract_body_text(tree: lxml_html.HtmlElement) -> str:
    for br in tree.iter("br"):
        br.tail = "\n" + (br.tail or "")

    for block in tree.iter(*_BLOCK_TAGS):
        block.tail = "\n\n" + (block.tail or "")

    return normalize_text(tree.text_content())


def normalize_text(raw_text: str) -> str:
    normalized = unicodedata.normalize("NFKC", raw_text).translate(_CHARACTER_HARMONIZATION)
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
