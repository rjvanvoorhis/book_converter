import dataclasses

import requests
import bs4

from book_converter.features.text_extraction import entities

@dataclasses.dataclass
class AO3EbookRepository:
    
    base_url: str = "https://archiveofourown.org"
    format: entities.BookFormat = "epub"

    def _get_work_soup(self, work_id: str):
        soup = bs4.BeautifulSoup(requests.get(f"{self.base_url}/works/{work_id}?view_adult=true&view_full_work=true").content, "lxml")
        if "Error 404" in self._soup.find("h2", {"class", "heading"}).text:
            raise ValueError(f"Could not find work '{work_id}'")
        return soup

    def get_book(self, identifier: str) -> entities.RawBook:
        format = self.format.lower()
        soup = self._get_work_soup(identifier)
        download_button = soup.find("li", {"class": "download"})
        for download_type in download_button.find_all("li"):
            if download_type.a.get_text().lower() == format:
                url = f"{self.base_url}/{download_type.a.attrs['href']}"
                response = requests.get(url)
                response.raise_for_status()
                return entities.RawBook(
                    format=format,
                    data=response.content
                )
        raise ValueError(f"Format '{format}' is not supported")
    