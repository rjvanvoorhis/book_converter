import typing

from book_converter.features.media_library import entities


class MediaLibrary(typing.Protocol):
    def list_libraries(self) -> list[entities.Library]: ...

    def list_items(self, library_id: str) -> list[entities.LibraryItem]: ...

    def import_item(
        self,
        source_path: str,
        library_id: str,
        folder_id: str,
        metadata: entities.ImportMetadata,
    ) -> entities.ImportResult:
        """Copies `source_path` into the given library folder (following the
        media server's own directory-naming convention) and triggers a scan
        so it picks the new item up."""
        ...

    def list_series(self, library_id: str) -> list[entities.RemoteSeries]:
        """Series as Audiobookshelf itself understands them (metadata-driven,
        with a per-book sequence) - the counterpart to organization.
        GroupStore's own groups, pulled in the opposite direction (from the
        media server, into book_converter) so series set up directly in
        Audiobookshelf show up here too."""
        ...

    def predict_relative_path(self, metadata: entities.ImportMetadata) -> str:
        """The relative path `import_item` would place this metadata at,
        without writing anything - the same folder-naming convention that
        method uses internally, exposed so a caller can check whether a work
        is already imported (by comparing against list_items) without
        needing to know that convention itself. Audiobookshelf is the only
        source of truth for import status - nothing is cached on our side."""
        ...

    def health_check_folder(
        self, library_id: str, folder_id: str
    ) -> entities.HealthCheckResult:
        """Whether the given library folder is reachable/writable right now,
        without changing anything - see LibraryFileStore.health_check."""
        ...

    def register_folder(
        self, library_id: str, folder_id: str
    ) -> entities.HealthCheckResult:
        """Sets up whatever this folder needs to become usable (see
        LibraryFileStore.register) and returns the resulting health check -
        the project should be able to bootstrap access to a configured
        library on its own, not require it to have been set up by hand
        first."""
        ...


class LibraryFileStore(typing.Protocol):
    """Writes a staged file into wherever a media library's folder actually
    lives. Paths in and out are opaque strings the implementation alone
    interprets - nothing here assumes a local/mounted filesystem, so this
    same port could later be satisfied by e.g. an S3-backed adapter without
    any change to callers. `source_local_path` is always a real local path
    (book_converter's own staging folder is always local); everything else
    - `base_path`/`destination_path` - is library-side and store-specific."""

    def join(self, base_path: str, *parts: str) -> str: ...

    def ensure_directory(self, path: str) -> None: ...

    def write_file(self, source_local_path: str, destination_path: str) -> None: ...

    def write_text(self, destination_path: str, content: str) -> None: ...

    def health_check(self, path: str) -> entities.HealthCheckResult:
        """Checks whether `path` is reachable and writable right now,
        without changing any state - e.g. does not mount anything on its
        own. See `register` for the bootstrapping counterpart."""
        ...

    def register(self, path: str) -> entities.HealthCheckResult:
        """Sets up whatever `path` needs to become usable - for local
        storage that's just making sure the directory exists; for a NAS
        share that's actually performing the mount, if it isn't mounted
        already. Idempotent: calling it again once healthy is a cheap no-op.
        Returns the resulting health check."""
        ...


class LibraryNotFound(Exception):
    pass
