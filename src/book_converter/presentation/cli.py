import typing


class Command(typing.Protocol):
    @property
    def name(self) -> str: ...

    @property
    def description(self) -> str: ...

    def execute(self, *args: typing.Any, **kwargs: typing.Any) -> str: ...
