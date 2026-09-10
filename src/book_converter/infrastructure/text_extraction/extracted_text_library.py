import json
import pathlib
import shutil

_MANIFEST_FILENAME = "book.json"
_REVIEW_FILENAME = "review.json"
REVIEW_FLAGS = ("good", "bad")


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
        review = _read_review(book_folder)
        results.append(
            {
                "path": str(book_folder),
                "title": manifest.get("title") or book_folder.name,
                "author": manifest.get("author"),
                "chapter_count": len(manifest.get("chapters", [])),
                "review_flag": review.get("flag"),
                "review_note": review.get("note"),
            }
        )
    return results


def delete_extracted_text(path: str) -> None:
    target = pathlib.Path(path)
    if target.is_dir() and (target / _MANIFEST_FILENAME).is_file():
        shutil.rmtree(target)


def save_review(path: str, flag: str | None, note: str | None) -> dict:
    """Flag an extracted-text folder good/bad, with an optional free-text
    note on what worked (or didn't) - used to build a taste profile for
    finding similar stories later. Passing flag=None with no note clears
    the review entirely."""
    book_folder = pathlib.Path(path)
    if not (book_folder / _MANIFEST_FILENAME).is_file():
        raise FileNotFoundError(f"No extracted text found at '{path}'")

    review_path = book_folder / _REVIEW_FILENAME
    note = note.strip() if note else None
    if flag is None and not note:
        review_path.unlink(missing_ok=True)
        return {"flag": None, "note": None}

    review = {"flag": flag, "note": note}
    review_path.write_text(json.dumps(review), encoding="utf-8")
    return review


def _read_review(book_folder: pathlib.Path) -> dict:
    review_path = book_folder / _REVIEW_FILENAME
    if not review_path.is_file():
        return {}
    try:
        return json.loads(review_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
