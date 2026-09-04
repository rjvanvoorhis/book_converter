import pathlib

# Browsing is meant for picking a "file" source identifier, so it only
# surfaces the ebook formats that source actually knows how to read - see
# filesystem_repository.py's own _SUPPORTED_FORMATS.
_DEFAULT_EXTENSIONS = ("epub", "mobi", "azw3")


def browse(path: str | None, extensions: tuple[str, ...] = _DEFAULT_EXTENSIONS) -> dict:
    directory = pathlib.Path(path) if path else pathlib.Path.cwd()
    if not directory.is_dir():
        raise NotADirectoryError(f"'{directory}' is not a directory")
    directory = directory.resolve()

    dirs = []
    files = []
    for entry in directory.iterdir():
        if entry.name.startswith("."):
            continue
        if entry.is_dir():
            dirs.append({"name": entry.name, "path": str(entry), "is_dir": True})
        elif entry.suffix.lower().lstrip(".") in extensions:
            files.append({"name": entry.name, "path": str(entry), "is_dir": False})

    dirs.sort(key=lambda item: item["name"].lower())
    files.sort(key=lambda item: item["name"].lower())

    parent = directory.parent
    return {
        "path": str(directory),
        "parent": str(parent) if parent != directory else None,
        "entries": dirs + files,
    }
