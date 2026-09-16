import pathlib
import shutil
import uuid

from book_converter.features.media_library import entities


class LocalFilesystemStore:
    """Plain local/mounted-filesystem implementation of LibraryFileStore.
    Assumes whatever path the media server reports for a library folder is
    directly usable from this process as-is - true when book_converter and
    the media server share a filesystem (same host, or an already-identical
    bind mount). For a share that's mounted at a different local path than
    the server reports, see NasShareStore instead."""

    def join(self, base_path: str, *parts: str) -> str:
        return str(pathlib.PurePath(base_path, *parts))

    def ensure_directory(self, path: str) -> None:
        pathlib.Path(path).mkdir(parents=True, exist_ok=True)

    def write_file(self, source_local_path: str, destination_path: str) -> None:
        shutil.copy2(source_local_path, destination_path)

    def write_text(self, destination_path: str, content: str) -> None:
        pathlib.Path(destination_path).write_text(content, encoding="utf-8")

    def health_check(self, path: str) -> entities.HealthCheckResult:
        target = pathlib.Path(path)
        if not target.is_dir():
            return entities.HealthCheckResult(False, f"'{path}' is not a directory")

        probe = target / f".book-converter-healthcheck-{uuid.uuid4().hex}"
        try:
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
        except OSError as exc:
            return entities.HealthCheckResult(False, f"'{path}' is not writable: {exc}")
        return entities.HealthCheckResult(True, f"'{path}' is accessible and writable")

    def register(self, path: str) -> entities.HealthCheckResult:
        # Nothing to bootstrap beyond the directory itself existing - a
        # local path either already works or it never will (there's no
        # remote resource to bring online, unlike NasShareStore).
        self.ensure_directory(path)
        return self.health_check(path)
