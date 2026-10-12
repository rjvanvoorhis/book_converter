import pathlib


class FilesystemEbookFileStore:
    def save(self, destination: str, data: bytes) -> str:
        path = pathlib.Path(destination)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return str(path)
