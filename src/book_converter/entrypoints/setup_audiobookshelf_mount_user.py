import os
import pathlib
import pwd
import shutil
import subprocess
import sys

# Mounting a NAS share (see infrastructure.media_library.nas_share_store)
# needs root - but running the whole application as root just to get that
# one privilege is overkill and risky. Instead this creates a dedicated,
# unprivileged system user with a narrowly scoped, passwordless sudo grant
# for exactly the mount(8) invocations NasShareStore.register can issue
# (cifs/nfs/nfs4 only - nothing else), so the app can bootstrap its own NAS
# mounts without being root itself. Run book_converter as this user
# (systemd User=, `sudo -u`, etc.) once it's been created.
_DEFAULT_USERNAME = "book-converter"
_SUDOERS_DIR = pathlib.Path("/etc/sudoers.d")
_SUDOERS_FILENAME = "book-converter-mounts"


def _user_exists(username: str) -> bool:
    try:
        pwd.getpwnam(username)
        return True
    except KeyError:
        return False


def _run(command: list[str]) -> None:
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(
            f"command failed ({' '.join(command)}): {result.stderr.strip()}"
        )


def _sudoers_rule(username: str) -> str:
    # Scoped to the mount(8) filesystem types NasShareStore actually uses,
    # not a blanket NOPASSWD:ALL - an operator wanting it tighter still
    # (e.g. pinned to one remote host) can hand-edit the generated file.
    return (
        f"{username} ALL=(root) NOPASSWD: "
        "/usr/bin/mount -t cifs *, "
        "/usr/bin/mount -t nfs *, "
        "/usr/bin/mount -t nfs4 *\n"
    )


def main(username: str | None = None) -> None:
    # console_scripts entry points call main() with no arguments (argv isn't
    # forwarded automatically), so an override passed on the command line -
    # `book-converter-setup-mount-user myuser` - has to be read here rather
    # than only under `if __name__ == "__main__"`.
    if username is None and len(sys.argv) > 1:
        username = sys.argv[1]
    username = username or _DEFAULT_USERNAME

    if hasattr(os, "geteuid") and os.geteuid() != 0:
        raise RuntimeError(
            "This script creates a system user and writes to /etc/sudoers.d - "
            "run it with sudo/as root."
        )

    if shutil.which("useradd") is None:
        raise RuntimeError(
            "useradd was not found on PATH - this script supports Linux systems "
            "using shadow-utils only"
        )

    if _user_exists(username):
        print(f"User '{username}' already exists, skipping creation.")
    else:
        print(f"Creating system user '{username}'...")
        _run(
            [
                "useradd",
                "--system",
                "--create-home",
                "--shell",
                "/usr/sbin/nologin",
                username,
            ]
        )

    print(f"Granting '{username}' scoped, passwordless NAS-mount access...")
    _SUDOERS_DIR.mkdir(parents=True, exist_ok=True)
    sudoers_path = _SUDOERS_DIR / _SUDOERS_FILENAME
    sudoers_path.write_text(_sudoers_rule(username), encoding="utf-8")
    sudoers_path.chmod(0o440)

    # A malformed sudoers file can break sudo entirely - validate before
    # leaving it in place.
    visudo = shutil.which("visudo")
    if visudo is not None:
        _run([visudo, "-c", "-f", str(sudoers_path)])

    print(
        f"Done. Run book_converter as '{username}' (systemd User=, `sudo -u "
        f"{username}`, ...) to let it mount NAS shares configured via "
        "AUDIOBOOKSHELF_NAS_MOUNTS - see .env.example."
    )


if __name__ == "__main__":
    main()
