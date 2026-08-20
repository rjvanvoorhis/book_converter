import logging

from book_converter.entrypoints import composition_root
from book_converter.infrastructure.cli.typer_cli import TyperCli


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    container = composition_root.build_container()
    app = TyperCli().add_commands(container.commands)
    app.run(argv)


if __name__ == "__main__":
    main()
