import dataclasses
import logging
import os
import pathlib
import subprocess
import time
import typing

from book_converter.features.media_library import entities
from book_converter.infrastructure.media_library import local_filesystem_store

logger = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True)
class MountSpec:
    """What it takes to mount one NAS share at a given local mount point -
    keyed by that local mount point (the value side of path_prefix_map) in
    NasShareStore.mounts, since that's the thing register() actually brings
    online."""

    remote: str  # e.g. "//nas.local/audiobooks" (cifs) or "nas.local:/export/audiobooks" (nfs)
    fs_type: str  # "cifs", "nfs", "nfs4", ...
    options: list[str] = dataclasses.field(default_factory=list)


def _run_mount_command(command: list[str]) -> None:
    # mount(8) needs root. Rather than requiring book_converter itself to
    # run as root, escalate through sudo - see entrypoints.
    # setup_audiobookshelf_mount_user, which grants a dedicated,
    # unprivileged user exactly this (and only this) via a sudoers.d rule.
    # `-n` fails fast instead of hanging on a password prompt if that grant
    # isn't in place.
    if hasattr(os, "geteuid") and os.geteuid() != 0:
        command = ["sudo", "-n", *command]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(
            f"mount command failed ({' '.join(command)}): {result.stderr.strip()}"
        )


@dataclasses.dataclass
class NasShareStore:
    """A NAS share reached at a different local path than the one the media
    server itself reports for that same share - e.g. Audiobookshelf sees
    '/audiobooks' inside its own container while book_converter sees the
    same share mounted at '/mnt/nas/audiobooks'. `path_prefix_map`
    (server-reported prefix -> this process's local mount prefix) translates
    one to the other; writes retry a few times, since network mounts hiccup
    in ways a local disk doesn't.

    Unlike `LocalFilesystemStore`, this store can bootstrap itself: if
    `mounts` describes how to mount a given local prefix (remote share
    address, filesystem type, mount options) and it isn't reachable yet,
    `register()` actually performs the mount rather than requiring it to
    already exist - see interfaces.LibraryFileStore.register."""

    path_prefix_map: dict[str, str]
    mounts: dict[str, MountSpec] = dataclasses.field(default_factory=dict)
    max_retries: int = 3
    retry_backoff_seconds: float = 1.0
    mount_runner: typing.Callable[[list[str]], None] = _run_mount_command
    _delegate: local_filesystem_store.LocalFilesystemStore = dataclasses.field(
        default_factory=local_filesystem_store.LocalFilesystemStore, repr=False
    )

    def join(self, base_path: str, *parts: str) -> str:
        return self._delegate.join(self._translate(base_path), *parts)

    def ensure_directory(self, path: str) -> None:
        self._retry(lambda: self._delegate.ensure_directory(self._translate(path)))

    def write_file(self, source_local_path: str, destination_path: str) -> None:
        self._retry(
            lambda: self._delegate.write_file(
                source_local_path, self._translate(destination_path)
            )
        )

    def write_text(self, destination_path: str, content: str) -> None:
        self._retry(
            lambda: self._delegate.write_text(
                self._translate(destination_path), content
            )
        )

    def health_check(self, path: str) -> entities.HealthCheckResult:
        # A pure check - never mounts anything on its own. See register()
        # for the bootstrapping counterpart.
        return self._delegate.health_check(self._translate(path))

    def register(self, path: str) -> entities.HealthCheckResult:
        local_path = self._translate(path)
        check = self._delegate.health_check(local_path)
        if check.healthy:
            return check

        mount_point, spec = self._mount_spec_for(local_path)
        if spec is None:
            # Nothing configured to bootstrap this path with - surface the
            # original failure rather than a confusing "no mount spec" one,
            # since from the caller's point of view this is still just "not
            # healthy".
            return check

        pathlib.Path(mount_point).mkdir(parents=True, exist_ok=True)
        command = ["mount", "-t", spec.fs_type, spec.remote, mount_point]
        if spec.options:
            command += ["-o", ",".join(spec.options)]
        self.mount_runner(command)

        return self._delegate.health_check(local_path)

    def _mount_spec_for(
        self, local_path: str
    ) -> tuple[str, MountSpec] | tuple[None, None]:
        matches = [
            (mount_point, spec)
            for mount_point, spec in self.mounts.items()
            if local_path == mount_point
            or local_path.startswith(mount_point.rstrip("/") + "/")
        ]
        if not matches:
            return None, None
        return max(matches, key=lambda pair: len(pair[0]))

    def _translate(self, path: str) -> str:
        # Longest prefix wins, so a more specific mapping (e.g. a
        # sub-folder mapped separately from its parent) takes precedence.
        matches = [
            (remote_prefix, local_prefix)
            for remote_prefix, local_prefix in self.path_prefix_map.items()
            if path == remote_prefix or path.startswith(remote_prefix.rstrip("/") + "/")
        ]
        if not matches:
            # Already translated (e.g. a path this store itself returned
            # earlier in the same import) or simply not covered by any
            # mapping - passed through unchanged either way.
            return path
        remote_prefix, local_prefix = max(matches, key=lambda pair: len(pair[0]))
        remainder = path[len(remote_prefix.rstrip("/")) :]
        return local_prefix.rstrip("/") + remainder

    def _retry(self, action: typing.Callable[[], None]) -> None:
        attempts = max(1, self.max_retries)
        for attempt in range(1, attempts + 1):
            try:
                action()
                return
            except OSError:
                if attempt == attempts:
                    raise
                logger.warning(
                    "NAS write failed (attempt %d/%d), retrying...", attempt, attempts
                )
                time.sleep(self.retry_backoff_seconds * attempt)
