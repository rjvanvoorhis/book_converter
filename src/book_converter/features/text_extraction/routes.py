import dataclasses
import json
import typing

from book_converter.features.text_extraction import dto
from book_converter.features.text_extraction import use_cases
from book_converter.presentation import api


def build_routes(
    load_ebook: use_cases.LoadEbookUseCase,
    extract_chapter: use_cases.ExtractChapterUseCase,
) -> list[api.Route]:
    return [
        api.Route(rule="/books/{identifier}", handler=_load_ebook_handler(load_ebook)),
        api.Route(
            rule="/books/{identifier}/chapters/{chapter_id}",
            handler=_extract_chapter_handler(extract_chapter),
        ),
    ]


def _load_ebook_handler(use_case: use_cases.LoadEbookUseCase) -> api.Handler:
    def handle(request: api.Request) -> api.Response:
        (identifier,) = request.params
        output = use_case.execute(dto.LoadEbookInput(identifier=identifier))
        return _json_response(output)

    return handle


def _extract_chapter_handler(use_case: use_cases.ExtractChapterUseCase) -> api.Handler:
    def handle(request: api.Request) -> api.Response:
        identifier, chapter_id = request.params
        output = use_case.execute(
            dto.ExtractChapterInput(identifier=identifier, chapter_id=int(chapter_id))
        )
        return _json_response(output)

    return handle


def _json_response(output: typing.Any) -> api.Response:
    body = json.dumps(dataclasses.asdict(output)).encode("utf-8")
    return api.Response(
        status_code=200,
        headers={"Content-Type": "application/json"},
        body=body,
    )
