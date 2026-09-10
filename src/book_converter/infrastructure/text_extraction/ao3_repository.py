import dataclasses
import json
import logging
import pathlib
import re
import time

import requests

from book_converter.features.text_extraction import entities
from book_converter.infrastructure.text_extraction import html_text

logger = logging.getLogger(__name__)

_SERIES_ID = re.compile(r"/series/(\d+)")
_WORK_ID = re.compile(r"/works/(\d+)")

# Transient upstream failures worth retrying: standard 5xx plus Cloudflare's
# extended error range (521-530), which AO3 surfaces when its origin is briefly
# unreachable even though the site is otherwise up.
_RETRYABLE_STATUS_CODES = {500, 502, 503, 504, *range(520, 531)}

# Every CLI invocation (book-converter load/extract-chapter) starts a fresh
# process, so without caching, a session that logs in would re-run the full
# login handshake on every single call - slow, and it hammers AO3's login
# endpoint enough to make it flaky. Cache the logged-in session's cookies
# here instead and only re-login when they've actually expired.
_DEFAULT_SESSION_CACHE_PATH = pathlib.Path("ao3_session_cache.json")


@dataclasses.dataclass
class AO3EbookRepository:
    base_url: str = "https://archiveofourown.org"
    timeout: float = 60.0
    max_retries: int = 5
    retry_backoff_seconds: float = 2.0
    # Optional AO3 account credentials - unlocks works restricted to
    # registered users. Anonymous (both None) works exactly as before.
    username: str | None = None
    password: str | None = None
    session_cache_path: pathlib.Path = _DEFAULT_SESSION_CACHE_PATH

    _session: requests.Session | None = dataclasses.field(
        default=None, init=False, repr=False, compare=False
    )

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
        response = self._get(f"{self.base_url}/series/{series_id}")
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
        response = self._get(
            f"{self.base_url}/works/{work_id}",
            params={"view_adult": "true", "view_full_work": "true"},
        )
        if response.status_code == 404:
            raise ValueError(f"Could not find work '{work_id}'")
        response.raise_for_status()
        response.encoding = "utf-8"
        return response.text

    def _get(self, url: str, params: dict | None = None) -> requests.Response:
        session = self._get_session()
        attempts = max(1, self.max_retries)
        for attempt in range(1, attempts + 1):
            try:
                response = session.get(url, params=params, timeout=self.timeout)
            except requests.RequestException:
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

    def _get_session(self) -> requests.Session:
        if self._session is not None:
            return self._session
        if not (self.username and self.password):
            self._session = requests.Session()
            return self._session

        session = requests.Session()
        if self._load_cached_cookies(session) and self._is_logged_in(session):
            self._session = session
            return self._session

        session = self._log_in()
        if self._is_logged_in(session):
            self._save_cookies(session)
        self._session = session
        return self._session

    def _log_in(self) -> requests.Session:
        """Log in with the configured AO3 account so works restricted to
        registered users become fetchable. Falls back to an anonymous
        session (same behavior as before credentials existed) if the login
        form can't be found or AO3 rejects the credentials - login is a
        nice-to-have, not something that should break extraction. Retries
        the whole GET-then-POST handshake like `_get` does, since AO3's
        Cloudflare-fronted origin returns transient 5xx/52x errors often
        enough that a single blip shouldn't be treated as a hard failure.
        """
        attempts = max(1, self.max_retries)
        for attempt in range(1, attempts + 1):
            session = requests.Session()
            try:
                login_page = session.get(
                    f"{self.base_url}/users/login", timeout=self.timeout
                )
                if login_page.status_code in _RETRYABLE_STATUS_CODES:
                    raise requests.HTTPError(
                        f"{login_page.status_code} fetching login page",
                        response=login_page,
                    )
                login_page.raise_for_status()

                tree = html_text.parse_html(login_page.text)
                form = next(iter(tree.xpath('//form[@id="new_user"]')), None)
                token_input = (
                    form.xpath('.//input[@name="authenticity_token"]')
                    if form is not None
                    else []
                )
                if not token_input:
                    logger.warning("Could not find AO3 login form; continuing without login")
                    return session

                response = session.post(
                    f"{self.base_url}/users/login",
                    data={
                        "user[login]": self.username,
                        "user[password]": self.password,
                        "authenticity_token": token_input[0].get("value"),
                    },
                    timeout=self.timeout,
                )
                if response.status_code in _RETRYABLE_STATUS_CODES:
                    raise requests.HTTPError(
                        f"{response.status_code} posting login", response=response
                    )
                response.raise_for_status()

                if "/users/logout" not in response.text:
                    logger.warning(
                        "AO3 login did not appear to succeed (check credentials); "
                        "continuing without login"
                    )
                return session
            except requests.RequestException:
                if attempt == attempts:
                    logger.warning(
                        "AO3 login failed after %d attempt(s); continuing without login",
                        attempts,
                    )
                    return session
                logger.warning(
                    "AO3 login request failed (attempt %d/%d), retrying...",
                    attempt,
                    attempts,
                )
                time.sleep(self.retry_backoff_seconds * attempt)

        raise AssertionError("unreachable")

    def _is_logged_in(self, session: requests.Session) -> bool:
        try:
            response = session.get(self.base_url, timeout=self.timeout)
        except requests.RequestException:
            return False
        return "/users/logout" in response.text

    def _load_cached_cookies(self, session: requests.Session) -> bool:
        if not self.session_cache_path.is_file():
            return False
        try:
            cookies = json.loads(self.session_cache_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        session.cookies.update(cookies)
        return True

    def _save_cookies(self, session: requests.Session) -> None:
        try:
            self.session_cache_path.write_text(
                json.dumps(session.cookies.get_dict()), encoding="utf-8"
            )
        except OSError:
            logger.warning("Could not cache AO3 session cookies at '%s'", self.session_cache_path)


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

    raise ValueError(
        f"Could not determine an AO3 work or series id from '{identifier}'"
    )


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
