import dataclasses
import json
import re

import requests

from book_converter.features.text_extraction import entities
from book_converter.infrastructure.text_extraction import html_text

_SERIES_ID = re.compile(r"/series/(\d+)")
_WORK_ID = re.compile(r"/works/(\d+)")


@dataclasses.dataclass(frozen=True)
class AO3EbookRepository:
    base_url: str = "https://archiveofourown.org"
    timeout: float = 60.0

    def get_book(self, identifier: str) -> entities.RawBook:
        kind, value = _parse_identifier(identifier)
        if kind == "series":
            return self._get_series(value)
        return self._get_work(value)

    def _get_work(self, work_id: str) -> entities.RawBook:
        html = self._fetch_work_html(work_id)
        payload = {
            "series_title": None,
            "works": [{"identifier": work_id, "html": html}],
        }
        return entities.RawBook(format="ao3", data=_encode(payload))

    def _get_series(self, series_id: str) -> entities.RawBook:
        response = requests.get(
            f"{self.base_url}/series/{series_id}", timeout=self.timeout
        )
        if response.status_code == 404:
            raise ValueError(f"Could not find series '{series_id}'")
        response.raise_for_status()
        response.encoding = "utf-8"

        series_title, work_ids = _parse_series_page(response.text)
        if not work_ids:
            raise ValueError(f"Series '{series_id}' does not contain any works")

        payload = {
            "series_title": series_title,
            "works": [
                {"identifier": work_id, "html": self._fetch_work_html(work_id)}
                for work_id in work_ids
            ],
        }
        return entities.RawBook(format="ao3", data=_encode(payload))

    def _fetch_work_html(self, work_id: str) -> str:
        response = requests.get(
            f"{self.base_url}/works/{work_id}",
            params={"view_adult": "true", "view_full_work": "true"},
            timeout=self.timeout,
        )
        if response.status_code == 404:
            raise ValueError(f"Could not find work '{work_id}'")
        response.raise_for_status()
        response.encoding = "utf-8"
        return response.text


def _encode(payload: dict) -> bytes:
    return json.dumps(payload).encode("utf-8")


def _parse_identifier(identifier: str) -> tuple[str, str]:
    identifier = identifier.strip()

    if identifier.startswith("series:"):
        return "series", identifier.removeprefix("series:")

    series_match = _SERIES_ID.search(identifier)
    if series_match:
        return "series", series_match.group(1)

    work_match = _WORK_ID.search(identifier)
    if work_match:
        return "work", work_match.group(1)

    if identifier.isdigit():
        return "work", identifier

    raise ValueError(f"Could not determine an AO3 work or series id from '{identifier}'")


def _parse_series_page(markup: str) -> tuple[str | None, list[str]]:
    tree = html_text.parse_html(markup)

    title = None
    headings = html_text.find_by_classes(tree, "div", "series-show", "region")
    if headings:
        heading = headings[0].find(".//h2")
        if heading is not None:
            title = html_text.normalize_text(heading.text_content()) or None

    work_ids = []
    listings = html_text.find_by_classes(tree, "ul", "series", "work", "index", "group")
    if listings:
        for entry in listings[0].xpath('.//li[@role="article"]'):
            heading = entry.find(".//h4")
            if heading is None:
                continue
            link = next(
                (
                    a
                    for a in heading.iter("a")
                    if a.get("href") and _WORK_ID.search(a.get("href"))
                ),
                None,
            )
            if link is None:
                continue
            work_ids.append(_WORK_ID.search(link.get("href")).group(1))

    return title, work_ids
