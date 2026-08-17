import dataclasses
import json
import typing

from book_converter.features.speech_generation import dto
from book_converter.features.speech_generation import use_cases
from book_converter.presentation import api


def build_routes(
    create_audiobook: use_cases.CreateAudiobookUseCase,
    list_voices: use_cases.ListVoiceProfilesUseCase,
) -> list[api.Route]:
    return [
        api.Route(
            rule="/audiobooks",
            method="POST",
            handler=_create_audiobook_handler(create_audiobook),
        ),
        api.Route(
            rule="/engines/{engine}/voices",
            handler=_list_voices_handler(list_voices),
        ),
    ]


def _create_audiobook_handler(use_case: use_cases.CreateAudiobookUseCase) -> api.Handler:
    def handle(request: api.Request) -> api.Response:
        payload = json.loads(request.content)
        output = use_case.execute(
            dto.CreateAudiobookInput(
                identifier=payload["identifier"],
                target=payload["target"],
                engine=payload.get("engine", "kokoro"),
                voice=payload.get("voice", "af_heart"),
            )
        )
        return _json_response(output)

    return handle


def _list_voices_handler(use_case: use_cases.ListVoiceProfilesUseCase) -> api.Handler:
    def handle(request: api.Request) -> api.Response:
        (engine,) = request.params
        output = use_case.execute(dto.ListVoiceProfilesInput(engine=engine))
        return _json_response(output)

    return handle


def _json_response(output: typing.Any) -> api.Response:
    body = json.dumps(dataclasses.asdict(output)).encode("utf-8")
    return api.Response(
        status_code=200,
        headers={"Content-Type": "application/json"},
        body=body,
    )
