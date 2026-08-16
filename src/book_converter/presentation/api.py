import dataclasses
import typing

type MultiDict[T] = dict[str, list[T]]
type Method = typing.Literal["HEAD", "OPTIONS", "GET", "POST", "PATCH", "PUT", "DELETE"]


@dataclasses.dataclass(frozen=True)
class Request:
    path: str
    method: Method
    content: bytes
    params: list[str] = dataclasses.field(default_factory=list[str])
    query: MultiDict[str] = dataclasses.field(default_factory=dict[str, list[str]])
    headers: dict[str, str] = dataclasses.field(default_factory=dict[str, str])
    files: MultiDict[typing.IO] = dataclasses.field(
        default_factory=dict[str, typing.IO]
    )
    form: MultiDict[str] = dataclasses.field(dict[str, list[str]])


@dataclasses.dataclass(frozen=True)
class Response:
    status_code: int
    headers: dict[str, str]
    body: bytes


type Handler = typing.Callable[[Request], Response]


@dataclasses.dataclass(frozen=True)
class Route:
    rule: str
    handler: Handler


class Application(typing.Protocol):
    def add_route(self, route: Route) -> typing.Self: ...

    def add_routes(self, routes: list[Route]) -> typing.Self: ...

    def listen(self, port: int) -> None: ...
