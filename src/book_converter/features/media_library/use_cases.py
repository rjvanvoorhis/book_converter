import dataclasses

from book_converter.features.media_library import dto, entities, interfaces
from book_converter.features.organization import interfaces as organization_interfaces


@dataclasses.dataclass(frozen=True)
class ListLibrariesUseCase:
    media_library: interfaces.MediaLibrary

    def execute(self) -> dto.ListLibrariesOutput:
        return dto.ListLibrariesOutput(libraries=self.media_library.list_libraries())


@dataclasses.dataclass(frozen=True)
class HealthCheckLibraryUseCase:
    """Checks every folder in a library at once, so a caller (the
    Organization tab's library picker) can show accessibility for the whole
    library up front instead of one folder at a time."""

    media_library: interfaces.MediaLibrary

    def execute(self, library_id: str) -> dto.HealthCheckLibraryOutput:
        library = next(
            (
                library
                for library in self.media_library.list_libraries()
                if library.id == library_id
            ),
            None,
        )
        if library is None:
            raise interfaces.LibraryNotFound(f"Unknown library '{library_id}'")
        folders = [
            entities.FolderHealth(
                folder_id=folder.id,
                path=folder.path,
                health=self.media_library.health_check_folder(library_id, folder.id),
            )
            for folder in library.folders
        ]
        return dto.HealthCheckLibraryOutput(folders=folders)


@dataclasses.dataclass(frozen=True)
class ListItemsUseCase:
    media_library: interfaces.MediaLibrary

    def execute(self, library_id: str) -> dto.ListItemsOutput:
        return dto.ListItemsOutput(items=self.media_library.list_items(library_id))


@dataclasses.dataclass(frozen=True)
class ImportWorkUseCase:
    """Imports one staged work into the media library its series is bound
    to. A work can only be imported once it's a member of some group (see
    organization.CreateGroupUseCase) - that's what fixes the destination
    library/folder and, for a real series, the series name/sequence
    metadata. Always performs the copy + metadata.json write + scan, even if
    the work already appears to be there - Audiobookshelf is the only source
    of truth for import status (see GroupStatusUseCase), so there's no local
    idempotency flag to short-circuit on."""

    media_library: interfaces.MediaLibrary
    group_store: organization_interfaces.GroupStore

    def execute(self, input_dto: dto.ImportWorkInput) -> dto.ImportWorkOutput:
        group = self.group_store.get_group(input_dto.group_id)
        if group is None:
            raise organization_interfaces.GroupNotFound(input_dto.group_id)
        member = next(
            (m for m in group.members if m.path == input_dto.source_path), None
        )
        if member is None:
            raise ValueError(
                f"'{input_dto.source_path}' is not assigned to group '{group.id}' - "
                "assign it to a series (or the standalone bucket) before importing"
            )

        series = (
            None
            if group.is_standalone
            else entities.SeriesInfo(name=group.name, sequence=member.sequence)
        )
        metadata = entities.ImportMetadata(
            title=input_dto.title, author=input_dto.author, series=series
        )
        result = self.media_library.import_item(
            input_dto.source_path, group.library_id, group.folder_id, metadata
        )
        return dto.ImportWorkOutput(destination_path=result.destination_path)


@dataclasses.dataclass(frozen=True)
class GroupStatusUseCase:
    """Whether each of a group's members is actually present in its bound
    media library right now - Audiobookshelf is the only source of truth for
    this, so it's re-derived live every call (one list_items round trip for
    the whole group, then a pure local path-prediction check per member)
    rather than cached locally. If a member was deleted on the
    Audiobookshelf side, this reflects that immediately."""

    media_library: interfaces.MediaLibrary
    group_store: organization_interfaces.GroupStore

    def execute(
        self, group_id: str, title_by_path: dict[str, str]
    ) -> dto.GroupStatusOutput:
        group = self.group_store.get_group(group_id)
        if group is None:
            raise organization_interfaces.GroupNotFound(group_id)

        items_by_relative_path = {
            item.relative_path: item
            for item in self.media_library.list_items(group.library_id)
        }

        statuses = []
        for member in group.members:
            title = title_by_path.get(member.path, member.path)
            series = (
                None
                if group.is_standalone
                else entities.SeriesInfo(name=group.name, sequence=member.sequence)
            )
            metadata = entities.ImportMetadata(title=title, author=None, series=series)
            expected_path = self.media_library.predict_relative_path(metadata)
            item = items_by_relative_path.get(expected_path)
            statuses.append(
                dto.MemberStatus(
                    path=member.path, imported_item_id=item.id if item else None
                )
            )
        return dto.GroupStatusOutput(members=statuses)


@dataclasses.dataclass(frozen=True)
class HealthCheckFolderUseCase:
    media_library: interfaces.MediaLibrary

    def execute(self, library_id: str, folder_id: str) -> entities.HealthCheckResult:
        return self.media_library.health_check_folder(library_id, folder_id)


@dataclasses.dataclass(frozen=True)
class RegisterFolderUseCase:
    """Bootstraps a library folder so it's usable without a human having to
    set it up by hand first (e.g. mounting a NAS share) - see
    interfaces.MediaLibrary.register_folder."""

    media_library: interfaces.MediaLibrary

    def execute(self, library_id: str, folder_id: str) -> entities.HealthCheckResult:
        return self.media_library.register_folder(library_id, folder_id)


@dataclasses.dataclass(frozen=True)
class DiscoverUnlinkedSeriesUseCase:
    """Reports which of Audiobookshelf's own Series for a library have no
    matching local group (by name) - a discovery aid, not an importer.
    Groups are assembled locally *before* anything is imported now (see
    organization.CreateGroupUseCase), so there's no "pull members from
    Audiobookshelf into a group" step anymore - see GroupStatusUseCase for
    checking whether an already-assigned member actually made it there."""

    media_library: interfaces.MediaLibrary
    group_store: organization_interfaces.GroupStore

    def execute(self, library_id: str) -> dto.SyncSeriesOutput:
        local_series_names = {
            group.name
            for group in self.group_store.list_groups()
            if group.library_id == library_id and not group.is_standalone
        }
        unlinked = [
            series.name
            for series in self.media_library.list_series(library_id)
            if series.name not in local_series_names
        ]
        return dto.SyncSeriesOutput(unlinked_series_names=unlinked)
