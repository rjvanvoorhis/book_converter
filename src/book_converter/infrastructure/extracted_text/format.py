import json
import pathlib
import re

from book_converter.core import entities as core_entities

_MANIFEST_FILENAME = "book.json"


def write_book(folder: str, book: core_entities.Book) -> None:
    target = pathlib.Path(folder)
    target.mkdir(parents=True, exist_ok=True)

    chapters_manifest = []
    for chapter in book.chapters:
        filename = f"{chapter.order:04d}_{_slugify(chapter.title)}.txt"
        (target / filename).write_text(chapter.content, encoding="utf-8")
        chapters_manifest.append(
            {
                "id": chapter.id,
                "title": chapter.title,
                "order": chapter.order,
                "filename": filename,
            }
        )

    manifest = {
        "title": book.metadata.title,
        "author": book.metadata.author,
        "language": book.metadata.language,
        "identifier": book.metadata.identifier,
        "chapters": chapters_manifest,
    }
    (target / _MANIFEST_FILENAME).write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def read_book(folder: str) -> core_entities.Book:
    source = pathlib.Path(folder)
    manifest_path = source / _MANIFEST_FILENAME
    if not manifest_path.is_file():
        raise FileNotFoundError(f"No extracted-text manifest found at '{manifest_path}'")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    metadata = core_entities.BookMetadata(
        title=manifest["title"],
        author=manifest.get("author"),
        language=manifest.get("language"),
        identifier=manifest.get("identifier"),
    )
    book = core_entities.Book(metadata=metadata)

    for entry in sorted(manifest["chapters"], key=lambda entry: entry["order"]):
        content = (source / entry["filename"]).read_text(encoding="utf-8")
        book.add_chapter(
            core_entities.Chapter(
                id=core_entities.ChapterId(entry["id"]),
                title=entry["title"],
                content=content,
                order=entry["order"],
            )
        )

    return book


def _slugify(title: str) -> str:
    slug = re.sub(r"[^\w]+", "-", title.strip().lower()).strip("-")
    return slug or "chapter"
