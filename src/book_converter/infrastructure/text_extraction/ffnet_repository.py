import dataclasses
import json
import logging
import re
import time

from curl_cffi import requests
from curl_cffi.requests.exceptions import RequestException

from book_converter.features.text_extraction import entities

logger = logging.getLogger(__name__)

_STORY_ID = re.compile(r"/s/(\d+)")

# FanFiction.net sits behind a Cloudflare challenge that blocks plain
# `requests` (and even curl with a spoofed User-Agent) regardless of
# headers - it's keyed off the TLS/JA3 fingerprint. `curl_cffi` with
# `impersonate="chrome"` reproduces a real Chrome handshake and gets a
# normal 200 response instead of the "Just a moment..." interstitial.
_IMPERSONATE = "chrome"

_RETRYABLE_STATUS_CODES = {403, 429, 500, 502, 503, 504}

_CHAPTER_OPTION = re.compile(r"<option\s+value=(\d+)[^>]*>(\d+)\.\s*([^<]*)")


@dataclasses.dataclass(frozen=True)
class FfNetEbookRepository:
    base_url: str = "https://www.fanfiction.net"
    timeout: float = 60.0
    max_retries: int = 4
    retry_backoff_seconds: float = 3.0
    request_delay_seconds: float = 2.0

    def get_book(self, identifier: str) -> entities.RawBook:
        story_id = _parse_identifier(identifier)

        first_chapter_html = self._fetch_chapter_html(story_id, 1)
        chapter_titles = _parse_chapter_titles(first_chapter_html)

        chapters = [{"number": 1, "html": first_chapter_html}]
        for number, _title in chapter_titles[1:]:
            time.sleep(self.request_delay_seconds)
            chapters.append(
                {"number": number, "html": self._fetch_chapter_html(story_id, number)}
            )

        payload = {"story_id": story_id, "chapters": chapters}
        return entities.RawBook(format="ffnet", data=_encode(payload))

    def _fetch_chapter_html(self, story_id: str, chapter_number: int) -> str:
        response = self._get(f"{self.base_url}/s/{story_id}/{chapter_number}/")
        if response.status_code == 404:
            raise ValueError(
                f"Could not find chapter {chapter_number} of story '{story_id}'"
            )
        response.raise_for_status()
        if (
            "id='storytext'" not in response.text
            and 'id="storytext"' not in response.text
        ):
            raise ValueError(
                f"Could not find story content for '{story_id}' - the page may not "
                "have rendered correctly"
            )
        return response.text

    def _get(self, url: str) -> requests.Response:
        attempts = max(1, self.max_retries)
        for attempt in range(1, attempts + 1):
            try:
                response = requests.get(
                    url, impersonate=_IMPERSONATE, timeout=self.timeout
                )
            except RequestException:
                if attempt == attempts:
                    raise
                logger.warning(
                    "Request to '%s' failed (attempt %d/%d), retrying...",
                    url,
                    attempt,
                    attempts,
                )
            else:
                if (
                    response.status_code not in _RETRYABLE_STATUS_CODES
                    or attempt == attempts
                ):
                    return response
                logger.warning(
                    "Request to '%s' returned %d (attempt %d/%d), retrying...",
                    url,
                    response.status_code,
                    attempt,
                    attempts,
                )
            time.sleep(self.retry_backoff_seconds * attempt)

        raise AssertionError("unreachable")


def _encode(payload: dict) -> bytes:
    return json.dumps(payload).encode("utf-8")


def _parse_identifier(identifier: str) -> str:
    identifier = identifier.strip()

    story_match = _STORY_ID.search(identifier)
    if story_match:
        return story_match.group(1)

    if identifier.isdigit():
        return identifier

    raise ValueError(
        f"Could not determine a FanFiction.net story id from '{identifier}'"
    )


def _parse_chapter_titles(markup: str) -> list[tuple[int, str]]:
    # FFN renders the chapter-select dropdown twice per page (top and
    # bottom nav), so dedupe by chapter number while preserving order.
    seen: dict[int, str] = {}
    for _value, number, title in _CHAPTER_OPTION.findall(markup):
        seen.setdefault(int(number), title.strip())
    if not seen:
        return [(1, "")]
    return sorted(seen.items())
