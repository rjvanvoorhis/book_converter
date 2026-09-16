import dataclasses


@dataclasses.dataclass(frozen=True)
class LibraryFolder:
    id: str
    path: str


@dataclasses.dataclass(frozen=True)
class Library:
    id: str
    name: str
    folders: list[LibraryFolder]


@dataclasses.dataclass(frozen=True)
class LibraryItem:
    id: str
    title: str
    author: str | None
    series: str | None
    relative_path: str


@dataclasses.dataclass(frozen=True)
class SeriesInfo:
    name: str
    # None means "in this series, but not numbered" (e.g. a side story) -
    # written to Audiobookshelf as just the series name, no "#sequence".
    sequence: int | None


@dataclasses.dataclass(frozen=True)
class ImportMetadata:
    title: str
    author: str | None
    series: SeriesInfo | None


@dataclasses.dataclass(frozen=True)
class ImportResult:
    destination_path: str
    relative_path: str


@dataclasses.dataclass(frozen=True)
class HealthCheckResult:
    healthy: bool
    detail: str


@dataclasses.dataclass(frozen=True)
class FolderHealth:
    """One folder's accessibility within a library-wide health check - see
    HealthCheckLibraryUseCase. Carries the folder's own id/path alongside the
    result so a caller (e.g. the Organization tab) can render per-folder
    badges without a second round trip to resolve which folder is which."""

    folder_id: str
    path: str
    health: HealthCheckResult


@dataclasses.dataclass(frozen=True)
class RemoteSeriesBook:
    id: str
    title: str
    relative_path: str
    # Audiobookshelf's own sequence for this book within the series - None
    # when it didn't report one parseable as a number, in which case the
    # book's position in Audiobookshelf's own list is used instead.
    sequence: int | None


@dataclasses.dataclass(frozen=True)
class RemoteSeries:
    """A series as Audiobookshelf itself understands it (media metadata,
    distinct from book_converter's own organization.Group) - the source side
    of a series sync."""

    id: str
    name: str
    books: list[RemoteSeriesBook]
