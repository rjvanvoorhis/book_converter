import typing
import dataclasses


type BookFormat = typing.Literal["epub", "mobi"]


@dataclasses.dataclass
class RawBook:
    format: BookFormat
    data: bytes
