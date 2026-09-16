import dataclasses
import logging
import shutil
import typing
import uuid

from book_converter.features.media_library import entities

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class SmbFileStore:
    """Speaks SMB2/3 directly to a network share (via the `smbclient`
    interface bundled in the `smbprotocol` package) - the cross-platform
    alternative to NasShareStore's OS-mount approach, since mounting a share
    and a privileged helper user (see entrypoints.
    setup_audiobookshelf_mount_user) are both Linux-specific and don't work
    on macOS/Windows. No OS mount, no elevated privileges: just a server and
    credentials - `server` points at the SMB *host* (e.g. a NAS's IP), not a
    specific share, since a NAS commonly exposes each library folder as its
    own top-level share (Audiobookshelf reporting a folder path of
    '/audiobooks' typically means a share literally named 'audiobooks', not
    a subpath of some other fixed share).

    Which share a given path belongs to is therefore derived from the path
    itself, not configured up front: the first path segment is the share
    name and everything after it is the subpath within that share (so
    '/audiobooks/Author/Title' -> share 'audiobooks', subpath
    'Author/Title'). `path_prefix_map` remaps a path (or prefix of one) to a
    different 'share/subpath' first, for the rarer case where
    Audiobookshelf's own reported path doesn't already look like that (e.g.
    it reports '/mnt/audiobooks' for a share actually named 'audiobooks')."""

    server: str
    username: str
    password: str
    port: int = 445
    path_prefix_map: dict[str, str] = dataclasses.field(default_factory=dict)
    # Defaults to the real `smbclient` module; overridden in tests with a
    # fake that doesn't need a real SMB server.
    client: typing.Any = None
    _session_ready: bool = dataclasses.field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.client is None:
            import smbclient

            self.client = smbclient

    def join(self, base_path: str, *parts: str) -> str:
        self._ensure_session()
        base = self._translate(base_path)
        return "\\".join([base, *parts]) if parts else base

    def ensure_directory(self, path: str) -> None:
        self._ensure_session()
        self.client.makedirs(self._translate(path), exist_ok=True)

    def write_file(self, source_local_path: str, destination_path: str) -> None:
        self._ensure_session()
        with (
            open(source_local_path, "rb") as source,
            self.client.open_file(self._translate(destination_path), mode="wb") as dest,
        ):
            shutil.copyfileobj(source, dest)

    def write_text(self, destination_path: str, content: str) -> None:
        self._ensure_session()
        with self.client.open_file(
            self._translate(destination_path), mode="w", encoding="utf-8"
        ) as f:
            f.write(content)

    def health_check(self, path: str) -> entities.HealthCheckResult:
        try:
            target = self._translate(path)
            self._ensure_session()
            if not self.client.path.isdir(target):
                return entities.HealthCheckResult(
                    False, f"'{target}' is not a directory"
                )
            probe = f"{target}\\.book-converter-healthcheck-{uuid.uuid4().hex}"
            with self.client.open_file(probe, mode="w") as f:
                f.write("ok")
            self.client.remove(probe)
        except Exception as exc:  # noqa: BLE001 - reported, not raised
            return entities.HealthCheckResult(
                False, f"'{path}' is not reachable/writable: {exc}"
            )
        return entities.HealthCheckResult(
            True, f"'{target}' is accessible and writable"
        )

    def register(self, path: str) -> entities.HealthCheckResult:
        # There's nothing to "bring online" the way a NAS mount needs to be
        # - just make sure the share-relative subpath exists, then report
        # whatever the real state is (health_check re-translates `path`
        # itself, so any failure here still surfaces a clear reason there).
        try:
            self._ensure_session()
            self.client.makedirs(self._translate(path), exist_ok=True)
        except Exception as exc:  # noqa: BLE001 - health_check below reports the real reason
            logger.warning("Could not create '%s' on the share: %s", path, exc)
        return self.health_check(path)

    def _ensure_session(self) -> None:
        if self._session_ready:
            return
        self.client.register_session(
            self.server, username=self.username, password=self.password, port=self.port
        )
        self._session_ready = True

    def _translate(self, path: str) -> str:
        if path.startswith("\\\\"):
            # Already a full UNC path this store produced earlier in the
            # same operation (e.g. join()'s result passed back into
            # ensure_directory) - nothing left to translate.
            return path
        mapped = self._map_prefix(path).strip("/")
        share, _, subpath = mapped.partition("/")
        if not share:
            raise ValueError(
                f"Could not determine an SMB share from path '{path}' - the first "
                "path segment is used as the share name (see SmbFileStore's "
                "docstring), or add an AUDIOBOOKSHELF_PATH_MAP entry for it"
            )
        unc = f"\\\\{self.server}\\{share}"
        subpath = subpath.replace("/", "\\")
        return f"{unc}\\{subpath}" if subpath else unc

    def _map_prefix(self, path: str) -> str:
        matches = [
            (remote_prefix, mapped_prefix)
            for remote_prefix, mapped_prefix in self.path_prefix_map.items()
            if path == remote_prefix or path.startswith(remote_prefix.rstrip("/") + "/")
        ]
        if not matches:
            return path
        remote_prefix, mapped_prefix = max(matches, key=lambda pair: len(pair[0]))
        remainder = path[len(remote_prefix.rstrip("/")) :]
        return f"{mapped_prefix.rstrip('/')}{remainder}" if mapped_prefix else remainder
