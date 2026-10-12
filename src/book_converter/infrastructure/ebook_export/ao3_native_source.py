import dataclasses
import pathlib
import urllib.parse

from book_converter.features.ebook_export import interfaces
from book_converter.infrastructure.text_extraction import ao3_repository


@dataclasses.dataclass(frozen=True)
class Ao3EbookSource:
    """AO3's own "Download" files (EPUB, MOBI, AZW3, PDF, HTML), and the
    expansion of a series into its works."""

    repository: ao3_repository.AO3EbookRepository

    def fetch(self, identifier: str, file_format: str) -> interfaces.NativeEbook | None:
        download = self.repository.download_work(identifier, file_format)
        if download is None:
            return None
        data, href = download
        stem = pathlib.PurePosixPath(urllib.parse.urlparse(href).path).stem
        return interfaces.NativeEbook(data=data, name=stem.replace("_", " "))

    def list_works(self, identifier: str) -> interfaces.WorkCollection | None:
        series = self.repository.list_series_works(identifier)
        if series is None:
            return None
        title, work_ids = series
        return interfaces.WorkCollection(title=title, identifiers=work_ids)
