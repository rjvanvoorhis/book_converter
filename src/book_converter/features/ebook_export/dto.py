import dataclasses


@dataclasses.dataclass
class ExportEbookInput:
    identifier: str
    target: str
    format: str = "epub"


@dataclasses.dataclass
class ExportedEbook:
    path: str
    # True when the file is the source site's own download rather than one
    # this project built from the parsed text.
    native: bool


@dataclasses.dataclass
class ExportEbookOutput:
    format: str
    # The series title when the identifier was a series, else None.
    collection: str | None
    # One ebook per work, in series order.
    ebooks: list[ExportedEbook]
