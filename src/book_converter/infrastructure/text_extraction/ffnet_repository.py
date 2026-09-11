import dataclasses
import json
import logging
import pathlib
import random
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

# Cloudflare's per-story-fetch TLS fingerprint check passes instantly, but
# it also rate-limits by IP: a burst of chapter requests a couple seconds
# apart degrades to 200-with-no-content around chapter ~10 and then to a
# 429 "Just a moment..." challenge that blocks the *entire* site (not just
# this story) for the IP, for every client - a real browser included.
# Backing off hard and persisting each chapter to disk (see
# `_cache_path`/`_read_cached`/`_write_cache`) means a run that trips the
# limiter doesn't have to re-fetch chapters it already has once it's
# retried later.
_CF_CHALLENGE_MARKER = "Just a moment"

_CHAPTER_OPTION = re.compile(r"<option\s+value=(\d+)[^>]*>(\d+)\.\s*([^<]*)")


@dataclasses.dataclass(frozen=True)
class FfNetEbookRepository:
    base_url: str = "https://www.fanfiction.net"
    timeout: float = 60.0
    max_retries: int = 4
    retry_backoff_seconds: float = 20.0
    request_delay_seconds: float = 8.0
    request_delay_jitter_seconds: float = 4.0
    cache_dir: pathlib.Path | None = pathlib.Path("data/cache/ffnet")

    def get_book(self, identifier: str) -> entities.RawBook:
        local_export = _load_local_export(identifier)
        if local_export is not None:
            return local_export

        story_id = _parse_identifier(identifier)

        first_chapter_html = self._fetch_chapter_html(story_id, 1)
        chapter_titles = _parse_chapter_titles(first_chapter_html)

        chapters = [{"number": 1, "html": first_chapter_html}]
        for number, _title in chapter_titles[1:]:
            if self._read_cached(story_id, number) is None:
                self._sleep_between_requests()
            chapters.append(
                {"number": number, "html": self._fetch_chapter_html(story_id, number)}
            )

        payload = {"story_id": story_id, "chapters": chapters}
        return entities.RawBook(format="ffnet", data=_encode(payload))

    def _sleep_between_requests(self) -> None:
        jitter = random.uniform(0, self.request_delay_jitter_seconds)
        time.sleep(self.request_delay_seconds + jitter)

    def _fetch_chapter_html(self, story_id: str, chapter_number: int) -> str:
        cached = self._read_cached(story_id, chapter_number)
        if cached is not None:
            return cached

        html = self._fetch_chapter_html_uncached(story_id, chapter_number)
        self._write_cache(story_id, chapter_number, html)
        return html

    def _fetch_chapter_html_uncached(
        self, story_id: str, chapter_number: int
    ) -> str:
        response = self._get(f"{self.base_url}/s/{story_id}/{chapter_number}/")
        if response.status_code == 404:
            raise ValueError(
                f"Could not find chapter {chapter_number} of story '{story_id}'"
            )
        response.raise_for_status()
        if not _has_story_content(response.text):
            raise ValueError(
                f"Could not find story content for '{story_id}' - fanfiction.net "
                "may be rate-limiting this IP (a Cloudflare challenge page looks "
                "like a normal response); wait before retrying"
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
                is_soft_challenge = (
                    response.status_code == 200 and not _has_story_content(response.text)
                )
                if (
                    response.status_code not in _RETRYABLE_STATUS_CODES
                    and not is_soft_challenge
                ) or attempt == attempts:
                    return response
                logger.warning(
                    "Request to '%s' returned %d%s (attempt %d/%d), backing off...",
                    url,
                    response.status_code,
                    " (soft challenge page)" if is_soft_challenge else "",
                    attempt,
                    attempts,
                )
            # Cloudflare's rate-limit window is measured in minutes, not
            # seconds - a short backoff just spends the retry budget
            # hammering a wall. Back off hard and grow it per attempt.
            time.sleep(self.retry_backoff_seconds * (2 ** (attempt - 1)))

        raise AssertionError("unreachable")

    def _cache_path(self, story_id: str, chapter_number: int) -> pathlib.Path | None:
        if self.cache_dir is None:
            return None
        return self.cache_dir / story_id / f"{chapter_number}.html"

    def _read_cached(self, story_id: str, chapter_number: int) -> str | None:
        path = self._cache_path(story_id, chapter_number)
        if path is None or not path.is_file():
            return None
        return path.read_text(encoding="utf-8")

    def _write_cache(self, story_id: str, chapter_number: int, html: str) -> None:
        path = self._cache_path(story_id, chapter_number)
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(html, encoding="utf-8")


def _load_local_export(identifier: str) -> entities.RawBook | None:
    # The ffnet-story-exporter.user.js Violentmonkey script (scripts/ffnet_export/)
    # captures each chapter's HTML as the user browses a story normally in
    # their own logged-in browser - sidesteps Cloudflare's rate limiter
    # entirely, since it's never a bulk automated fetch - and exports a
    # `<slug>-<story_id>.ffnet.json` file in exactly this repository's own
    # RawBook payload shape (see `_encode`). Treat that export as a valid
    # `identifier` so it drops straight into the existing ffnet pipeline.
    path = pathlib.Path(identifier)
    if path.suffix != ".json" or not path.is_file():
        return None
    data = path.read_bytes()
    payload = json.loads(data.decode("utf-8"))
    if "story_id" not in payload or "chapters" not in payload:
        raise ValueError(
            f"'{identifier}' doesn't look like an ffnet story export "
            "(expected 'story_id' and 'chapters' keys)"
        )
    return entities.RawBook(format="ffnet", data=data)


def _has_story_content(markup: str) -> bool:
    if _CF_CHALLENGE_MARKER in markup:
        return False
    return "id='storytext'" in markup or 'id="storytext"' in markup


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
