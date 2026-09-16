import dataclasses
import json
import pathlib
import re

import requests

from book_converter.features.media_library import entities, interfaces

_UNSAFE_PATH_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

# Audiobookshelf's series-listing endpoint requires a positive `limit`
# (unlike items/collections, where 0 means "no limit") - large enough to
# cover any single library's series in one page.
_SERIES_PAGE_LIMIT = 1000


@dataclasses.dataclass
class AudiobookshelfClient:
    """Real Audiobookshelf adapter. Audiobookshelf has no documented direct-
    upload endpoint for adding a new item with metadata in one call - its own
    docs describe adding media by placing files under a library folder and
    scanning, so `import_item` does exactly that: copy the file into an
    Author/Series/Title folder under the target library folder, write an
    explicit metadata.json (rather than relying on folder-name parsing) so
    series/sequence survive the trip, then trigger a scan.

    Actually placing that file is delegated to `file_store` - this class
    only decides the directory layout and metadata.json contents, not how or
    where they're physically written, so the same client works whether the
    library folder Audiobookshelf reports is a local path, a NAS share
    mounted somewhere else, or (eventually) something else entirely."""

    base_url: str
    api_key: str
    file_store: interfaces.LibraryFileStore
    timeout: float = 30.0

    def list_libraries(self) -> list[entities.Library]:
        response = self._get("/api/libraries")
        return [
            _library_from_dict(entry) for entry in response.json().get("libraries", [])
        ]

    def list_items(self, library_id: str) -> list[entities.LibraryItem]:
        response = self._get(
            f"/api/libraries/{library_id}/items",
            params={"minified": 1},
            not_found_id=library_id,
        )
        return [_item_from_dict(entry) for entry in response.json().get("results", [])]

    def import_item(
        self,
        source_path: str,
        library_id: str,
        folder_id: str,
        metadata: entities.ImportMetadata,
    ) -> entities.ImportResult:
        folder = self._get_folder(library_id, folder_id)

        # The staging file is always local to this process, regardless of
        # what kind of storage the library folder itself lives on.
        source = pathlib.Path(source_path)
        if not source.is_file():
            raise FileNotFoundError(f"No staged file at '{source_path}'")

        dir_parts = _item_dir_parts(metadata)
        item_dir = self.file_store.join(folder.path, *dir_parts)
        self.file_store.ensure_directory(item_dir)

        destination = self.file_store.join(item_dir, source.name)
        self.file_store.write_file(str(source), destination)
        self.file_store.write_text(
            self.file_store.join(item_dir, "metadata.json"),
            json.dumps(_metadata_json(metadata), indent=2),
        )

        self._post(f"/api/libraries/{library_id}/scan")
        # Forward-slash, folder-relative, and - importantly - the *folder*,
        # not the file within it: for an item that lives in its own
        # subfolder (which every import here creates - Author/Series/Title),
        # Audiobookshelf's own relPath for that item is the folder path, not
        # the audio file's path. Matching this exactly is what lets a later
        # series sync (list_series) tie its books back to this import.
        relative_path = "/".join(dir_parts)
        return entities.ImportResult(
            destination_path=destination, relative_path=relative_path
        )

    def predict_relative_path(self, metadata: entities.ImportMetadata) -> str:
        return "/".join(_item_dir_parts(metadata))

    def list_series(self, library_id: str) -> list[entities.RemoteSeries]:
        response = self._get(
            f"/api/libraries/{library_id}/series",
            params={"limit": _SERIES_PAGE_LIMIT},
            not_found_id=library_id,
        )
        return [
            _series_from_dict(entry) for entry in response.json().get("results", [])
        ]

    def health_check_folder(
        self, library_id: str, folder_id: str
    ) -> entities.HealthCheckResult:
        folder = self._get_folder(library_id, folder_id)
        return self.file_store.health_check(folder.path)

    def register_folder(
        self, library_id: str, folder_id: str
    ) -> entities.HealthCheckResult:
        folder = self._get_folder(library_id, folder_id)
        return self.file_store.register(folder.path)

    def _get_folder(self, library_id: str, folder_id: str) -> entities.LibraryFolder:
        for library in self.list_libraries():
            if library.id != library_id:
                continue
            for folder in library.folders:
                if folder.id == folder_id:
                    return folder
            raise interfaces.LibraryNotFound(
                f"No folder '{folder_id}' in library '{library_id}'"
            )
        raise interfaces.LibraryNotFound(f"Unknown library '{library_id}'")

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"}

    def _get(
        self, path: str, params: dict | None = None, not_found_id: str | None = None
    ) -> requests.Response:
        response = requests.get(
            f"{self.base_url}{path}",
            headers=self._headers(),
            params=params,
            timeout=self.timeout,
        )
        if response.status_code == 404 and not_found_id is not None:
            raise interfaces.LibraryNotFound(f"Unknown library '{not_found_id}'")
        response.raise_for_status()
        return response

    def _post(self, path: str) -> requests.Response:
        response = requests.post(
            f"{self.base_url}{path}", headers=self._headers(), timeout=self.timeout
        )
        response.raise_for_status()
        return response


_UNKNOWN_AUTHOR_PLACEHOLDER = "Unknown Author"


def _item_dir_parts(metadata: entities.ImportMetadata) -> list[str]:
    # Audiobookshelf infers author/series/title purely from folder *depth*
    # (see its own scandir.js getBookDataFromDir), not from any label on the
    # segments: with exactly two segments the first is always read as the
    # author, and series is only recognized with three or more. So a series
    # import always needs a real three-level Author/Series/Title path - even
    # when the author isn't known yet - or Audiobookshelf reads the series
    # name itself as the author. metadata.json's explicit "series" (written
    # below) still overrides whatever series name/sequence the folder
    # structure implies, so getting the *author* slot right here is what
    # actually matters.
    parts = []
    if metadata.series:
        parts.append(
            _safe_path_component(metadata.author or _UNKNOWN_AUTHOR_PLACEHOLDER)
        )
        parts.append(_safe_path_component(metadata.series.name))
    elif metadata.author:
        parts.append(_safe_path_component(metadata.author))
    parts.append(_safe_path_component(metadata.title))
    return parts


def _metadata_json(metadata: entities.ImportMetadata) -> dict:
    payload: dict = {"title": metadata.title}
    if metadata.author:
        payload["authors"] = [metadata.author]
    if metadata.series:
        # Audiobookshelf's metadata.json "series" field is a plain array of
        # "Name #sequence" strings (parsed server-side by
        # parseSeriesString.parse) - NOT a list of {name, sequence} objects.
        # A wrongly-shaped entry is silently dropped by its validator rather
        # than rejected, so this is easy to get wrong without erroring. No
        # "#sequence" suffix at all when there isn't one (a side story that
        # belongs to the series but isn't numbered).
        name = metadata.series.name
        sequence = metadata.series.sequence
        payload["series"] = [name if sequence is None else f"{name} #{sequence}"]
    return payload


def _safe_path_component(value: str) -> str:
    cleaned = _UNSAFE_PATH_CHARS.sub(" ", value).strip().rstrip(".")
    return " ".join(cleaned.split()) or "untitled"


def _library_from_dict(data: dict) -> entities.Library:
    return entities.Library(
        id=data["id"],
        name=data.get("name", data["id"]),
        folders=[
            entities.LibraryFolder(id=folder["id"], path=folder.get("fullPath", ""))
            for folder in data.get("folders", [])
        ],
    )


def _item_from_dict(data: dict) -> entities.LibraryItem:
    media = data.get("media", {})
    item_metadata = media.get("metadata", {})
    return entities.LibraryItem(
        id=data["id"],
        title=item_metadata.get("title", data.get("path", data["id"])),
        author=item_metadata.get("authorName"),
        series=_series_field_value(item_metadata.get("series"), "name"),
        relative_path=data.get("relPath", data.get("path", "")),
    )


def _series_field_value(series_field: object, key: str) -> object:
    # An item's own `media.metadata.series` field takes two different shapes
    # depending on context: a list of {id, name, sequence} in most item
    # responses (an item can belong to more than one series), but a single
    # {id, sequence} object when the item is nested inside a specific
    # series' own listing (list_series) - tolerate both rather than assume
    # one.
    if isinstance(series_field, dict):
        return series_field.get(key)
    if isinstance(series_field, list) and series_field:
        return series_field[0].get(key)
    return None


def _series_from_dict(data: dict) -> entities.RemoteSeries:
    return entities.RemoteSeries(
        id=data["id"],
        name=data.get("name", data["id"]),
        books=[
            _series_book_from_dict(entry, position)
            for position, entry in enumerate(data.get("books", []), start=1)
        ],
    )


def _series_book_from_dict(data: dict, position: int) -> entities.RemoteSeriesBook:
    item = _item_from_dict(data)
    media = data.get("media", {})
    raw_sequence = _series_field_value(
        media.get("metadata", {}).get("series"), "sequence"
    )
    # Fall back to the book's position in Audiobookshelf's own list when the
    # sequence isn't a parseable number (e.g. missing, or blank).
    parsed_sequence = _parse_sequence(raw_sequence)
    sequence = position if parsed_sequence is None else parsed_sequence
    return entities.RemoteSeriesBook(
        id=item.id,
        title=item.title,
        relative_path=item.relative_path,
        sequence=sequence,
    )


def _parse_sequence(raw: object) -> int | None:
    if raw is None:
        return None
    try:
        return int(float(raw))
    except (TypeError, ValueError):
        return None
