import json
import pathlib
import shutil

_MANIFEST_FILENAME = "book.json"


def list_extracted_texts(folder: str) -> list[dict]:
    """Every extracted-text folder (one level under `folder`, each with its
    own book.json manifest - see extracted_text.format.write_book) - the
    "saved for later" library the UI lists and the Create Audiobook page's
    `extracted` source later reads from."""
    root = pathlib.Path(folder)
    if not root.is_dir():
        return []

    results = []
    for manifest_path in sorted(root.glob("*/" + _MANIFEST_FILENAME)):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        book_folder = manifest_path.parent
        results.append(
            {
                "path": str(book_folder),
                "title": manifest.get("title") or book_folder.name,
                "author": manifest.get("author"),
                "chapter_count": len(manifest.get("chapters", [])),
            }
        )
    return results


def delete_extracted_text(path: str) -> None:
    target = pathlib.Path(path)
    if target.is_dir() and (target / _MANIFEST_FILENAME).is_file():
        shutil.rmtree(target)
