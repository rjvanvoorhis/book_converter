import typing
import dataclasses


type BookFormat = typing.Literal["epub", "mobi", "azw3", "ao3", "ffnet"]


@dataclasses.dataclass
class RawBook:
    format: BookFormat
    data: bytes
