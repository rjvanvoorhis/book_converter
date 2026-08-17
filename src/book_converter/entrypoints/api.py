from book_converter.entrypoints import composition_root
from book_converter.infrastructure.web.fastapi_application import FastApiApplication


def main(port: int = 8000) -> None:
    container = composition_root.build_container()
    app = FastApiApplication().add_routes(container.routes)
    app.listen(port)


if __name__ == "__main__":
    main()
