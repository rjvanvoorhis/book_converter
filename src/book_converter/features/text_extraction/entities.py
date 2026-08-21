import typing
import dataclasses


type BookFormat = typing.Literal["epub", "mobi", "ao3"]


@dataclasses.dataclass
class RawBook:
    format: BookFormat
    data: bytes
