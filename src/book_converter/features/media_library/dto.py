import dataclasses

from book_converter.features.media_library import entities


@dataclasses.dataclass(frozen=True)
class ListLibrariesOutput:
    libraries: list[entities.Library]


@dataclasses.dataclass(frozen=True)
class ListItemsOutput:
    items: list[entities.LibraryItem]


@dataclasses.dataclass(frozen=True)
class ImportWorkInput:
    group_id: str
    source_path: str
    title: str
    author: str | None = None


@dataclasses.dataclass(frozen=True)
class ImportWorkOutput:
    destination_path: str


@dataclasses.dataclass(frozen=True)
class SyncSeriesOutput:
    # Audiobookshelf series with no matching local group (by name) - nothing
    # is auto-created for these (see CreateGroupUseCase's "library MUST be
    # chosen up front" rule); the caller creates one by hand if it wants to
    # track that series locally too.
    unlinked_series_names: list[str]


@dataclasses.dataclass(frozen=True)
class HealthCheckLibraryOutput:
    folders: list[entities.FolderHealth]


@dataclasses.dataclass(frozen=True)
class MemberStatus:
    path: str
    # The Audiobookshelf item id this member currently resolves to, or None
    # if it isn't there right now - Audiobookshelf itself is the only source
    # of truth for this, checked live every time, never cached locally.
    imported_item_id: str | None


@dataclasses.dataclass(frozen=True)
class GroupStatusOutput:
    members: list[MemberStatus]
