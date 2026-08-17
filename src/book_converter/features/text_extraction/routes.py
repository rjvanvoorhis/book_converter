import dataclasses
import json
import typing

from book_converter.features.text_extraction import dto
from book_converter.features.text_extraction import use_cases
from book_converter.presentation import api

_UseCaseT = typing.TypeVar("_UseCaseT")


def build_routes(
    load_ebook_by_source: dict[str, use_cases.LoadEbookUseCase],
    extract_chapter_by_source: dict[str, use_cases.ExtractChapterUseCase],
    extract_text_by_source: dict[str, use_cases.ExtractTextUseCase],
    copyedit_by_editor: dict[str, use_cases.CopyEditTextUseCase],
) -> list[api.Route]:
    return [
        api.Route(
            rule="/books/{identifier}", handler=_load_ebook_handler(load_ebook_by_source)
        ),
        api.Route(
            rule="/books/{identifier}/chapters/{chapter_id}",
            handler=_extract_chapter_handler(extract_chapter_by_source),
        ),
        api.Route(
            rule="/extracted-texts",
            method="POST",
            handler=_extract_text_handler(extract_text_by_source),
        ),
        api.Route(
            rule="/extracted-texts/copyedit",
            method="POST",
            handler=_copyedit_handler(copyedit_by_editor),
        ),
    ]


def _load_ebook_handler(
    use_cases_by_source: dict[str, use_cases.LoadEbookUseCase]
) -> api.Handler:
    def handle(request: api.Request) -> api.Response:
        (identifier,) = request.params
        use_case = _resolve(use_cases_by_source, _query_value(request, "source", "file"))
        output = use_case.execute(dto.LoadEbookInput(identifier=identifier))
        return _json_response(output)

    return handle


def _extract_chapter_handler(
    use_cases_by_source: dict[str, use_cases.ExtractChapterUseCase]
) -> api.Handler:
    def handle(request: api.Request) -> api.Response:
        identifier, chapter_id = request.params
        use_case = _resolve(use_cases_by_source, _query_value(request, "source", "file"))
        output = use_case.execute(
            dto.ExtractChapterInput(identifier=identifier, chapter_id=int(chapter_id))
        )
        return _json_response(output)

    return handle


def _extract_text_handler(
    use_cases_by_source: dict[str, use_cases.ExtractTextUseCase]
) -> api.Handler:
    def handle(request: api.Request) -> api.Response:
        payload = json.loads(request.content)
        use_case = _resolve(use_cases_by_source, payload.get("source", "file"))
        output = use_case.execute(
            dto.ExtractTextInput(
                identifier=payload["identifier"], target=payload["target"]
            )
        )
        return _json_response(output)

    return handle


def _copyedit_handler(
    use_cases_by_editor: dict[str, use_cases.CopyEditTextUseCase]
) -> api.Handler:
    def handle(request: api.Request) -> api.Response:
        payload = json.loads(request.content)
        use_case = _resolve(
            use_cases_by_editor, payload.get("editor", "languagetool"), label="editor"
        )
        output = use_case.execute(dto.CopyEditInput(identifier=payload["identifier"]))
        return _json_response(output)

    return handle


def _query_value(request: api.Request, key: str, default: str) -> str:
    values = request.query.get(key)
    return values[0] if values else default


def _resolve(
    use_cases_by_key: dict[str, _UseCaseT], key: str, label: str = "source"
) -> _UseCaseT:
    try:
        return use_cases_by_key[key]
    except KeyError:
        available = ", ".join(sorted(use_cases_by_key))
        raise ValueError(f"Unknown {label} '{key}'. Available: {available}") from None


def _json_response(output: typing.Any) -> api.Response:
    body = json.dumps(dataclasses.asdict(output)).encode("utf-8")
    return api.Response(
        status_code=200,
        headers={"Content-Type": "application/json"},
        body=body,
    )
