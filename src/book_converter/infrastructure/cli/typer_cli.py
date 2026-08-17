import functools
import typing

import typer

from book_converter.presentation import cli


class TyperCli:
    def __init__(self) -> None:
        self._app = typer.Typer()

    def add_command(self, command: cli.Command) -> typing.Self:
        self._app.command(name=command.name, help=command.description)(
            _wrap(command)
        )
        return self

    def add_commands(self, commands: list[cli.Command]) -> typing.Self:
        for command in commands:
            self.add_command(command)
        return self

    def run(self, argv: list[str] | None = None) -> None:
        self._app(args=argv)


def _wrap(command: cli.Command) -> typing.Callable[..., None]:
    @functools.wraps(command.execute)
    def handler(*args: typing.Any, **kwargs: typing.Any) -> None:
        typer.echo(command.execute(*args, **kwargs))

    return handler
