import dataclasses
import urllib.parse

import bs4
import requests

from book_converter.features.text_extraction import entities


@dataclasses.dataclass(frozen=True)
class AO3EbookRepository:
    base_url: str = "https://archiveofourown.org"
    preferred_format: entities.BookFormat = "epub"
    timeout: float = 60.0

    def get_book(self, identifier: str) -> entities.RawBook:
        requested_format = self.preferred_format.lower()
        soup = self._get_work_soup(identifier)

        download_button = soup.find("li", {"class": "download"})
        if download_button is None:
            raise ValueError(f"Could not find a download menu for work '{identifier}'")

        for download_type in download_button.find_all("li"):
            link = download_type.a
            if link is None:
                continue
            if link.get_text().lower() == requested_format:
                url = urllib.parse.urljoin(self.base_url, link.attrs["href"])
                response = requests.get(url, timeout=self.timeout)
                response.raise_for_status()
                return entities.RawBook(format=requested_format, data=response.content)

        raise ValueError(f"Format '{requested_format}' is not supported")

    def _get_work_soup(self, work_id: str) -> bs4.BeautifulSoup:
        response = requests.get(
            f"{self.base_url}/works/{work_id}",
            params={"view_adult": "true", "view_full_work": "true"},
            timeout=self.timeout,
        )
        if response.status_code == 404:
            raise ValueError(f"Could not find work '{work_id}'")
        response.raise_for_status()
        return bs4.BeautifulSoup(response.content, "lxml")
