import dataclasses
import json
import typing

from book_converter.features.ebook_export import dto, use_cases
from book_converter.presentation import api

_DEFAULT_EBOOKS_FOLDER = "data/ebooks"


def build_routes(
    export_by_source: dict[str, use_cases.ExportEbookUseCase],
    formats: list[str],
    default_ebooks_folder: str = _DEFAULT_EBOOKS_FOLDER,
) -> list[api.Route]:
    return [
        api.Route(
            rule="/ebooks/formats",
            handler=_formats_handler(formats, default_ebooks_folder),
        ),
        api.Route(
            rule="/ebooks/export",
            method="POST",
            handler=_export_handler(export_by_source),
        ),
    ]


def _formats_handler(formats: list[str], default_folder: str) -> api.Handler:
    def handle(request: api.Request) -> api.Response:
        return _json({"formats": formats, "default_folder": default_folder})

    return handle


def _export_handler(
    export_by_source: dict[str, use_cases.ExportEbookUseCase],
) -> api.Handler:
    def handle(request: api.Request) -> api.Response:
        payload = json.loads(request.content)
        source = payload.get("source", "file")
        use_case = export_by_source.get(source)
        if use_case is None:
            available = ", ".join(sorted(export_by_source))
            return _json({"error": f"Unknown source '{source}'. Available: {available}"}, 400)
        if not payload.get("identifier") or not payload.get("target"):
            return _json({"error": "Required fields: identifier, target"}, 400)
        try:
            output = use_case.execute(
                dto.ExportEbookInput(
                    identifier=payload["identifier"],
                    target=payload["target"],
                    format=payload.get("format", "epub"),
                )
            )
        except (ValueError, FileNotFoundError) as exc:
            return _json({"error": str(exc)}, 400)
        return _json(output)

    return handle


def _json(output: typing.Any, status_code: int = 200) -> api.Response:
    payload = dataclasses.asdict(output) if dataclasses.is_dataclass(output) else output
    return api.Response(
        status_code=status_code,
        headers={"Content-Type": "application/json"},
        body=json.dumps(payload).encode("utf-8"),
    )
