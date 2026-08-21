import dataclasses
import json
import typing

from book_converter.features.speech_generation import dto
from book_converter.features.speech_generation import interfaces
from book_converter.features.speech_generation import use_cases
from book_converter.presentation import api

_UseCaseT = typing.TypeVar("_UseCaseT")


def build_routes(
    build_text_annotator: interfaces.TextAnnotatorFactory,
    tts_providers: dict[str, interfaces.TTSProvider],
    book_repositories_by_source: dict[str, interfaces.BookRepository],
    bundle_initializer: interfaces.BundleInitializer,
) -> list[api.Route]:
    return [
        api.Route(
            rule="/audiobooks",
            method="POST",
            handler=_create_audiobook_handler(
                book_repositories_by_source,
                build_text_annotator,
                tts_providers,
                bundle_initializer,
            ),
        ),
        api.Route(
            rule="/engines/{engine}/voices",
            handler=_list_voices_handler(tts_providers),
        ),
    ]


def _create_audiobook_handler(
    book_repositories_by_source: dict[str, interfaces.BookRepository],
    build_text_annotator: interfaces.TextAnnotatorFactory,
    tts_providers: dict[str, interfaces.TTSProvider],
    bundle_initializer: interfaces.BundleInitializer,
) -> api.Handler:
    def handle(request: api.Request) -> api.Response:
        payload = json.loads(request.content)

        # Get source and TTS provider
        source = payload.get("source", "file")
        tts_provider_name = payload.get("tts_provider", "pocket-tts")

        if tts_provider_name not in tts_providers:
            available = ", ".join(sorted(tts_providers.keys()))
            error_msg = (
                f"Unknown TTS provider '{tts_provider_name}'. Available: {available}"
            )
            return _json_error_response(error_msg, 400)

        if source not in book_repositories_by_source:
            available = ", ".join(sorted(book_repositories_by_source.keys()))
            error_msg = f"Unknown source '{source}'. Available: {available}"
            return _json_error_response(error_msg, 400)

        tts_provider = tts_providers[tts_provider_name]
        book_repo = book_repositories_by_source[source]

        # Build text annotator
        pronunciations_path = payload.get("pronunciations")
        add_pauses = payload.get("add_pauses", False)
        text_annotator = build_text_annotator(
            pronunciations_path=pronunciations_path, add_pauses=add_pauses
        )

        # Create use case
        use_case = use_cases.CreateAudiobookUseCase(
            book_repository=book_repo,
            tts_provider=tts_provider,
            bundle_initializer=bundle_initializer,
            text_annotator=text_annotator,
        )

        output = use_case.execute(
            dto.CreateAudiobookInput(
                identifier=payload["identifier"],
                target=payload["target"],
                engine=payload.get("engine", "kokoro"),
                voice=payload.get("voice", "af_heart"),
                batch_size=payload.get("batch_size", 1),
                chapters_per_chunk=payload.get("chapters_per_chunk"),
            )
        )
        return _json_response(output)

    return handle


def _list_voices_handler(
    tts_providers: dict[str, interfaces.TTSProvider],
) -> api.Handler:
    def handle(request: api.Request) -> api.Response:
        (engine,) = request.params

        # Extract tts_provider from query parameters (query is MultiDict[str] = dict[str, list[str]])
        tts_provider_name = "pocket-tts"  # default
        if "tts_provider" in request.query and request.query["tts_provider"]:
            tts_provider_name = request.query["tts_provider"][0]

        if tts_provider_name not in tts_providers:
            available = ", ".join(sorted(tts_providers.keys()))
            error_msg = (
                f"Unknown TTS provider '{tts_provider_name}'. Available: {available}"
            )
            return _json_error_response(error_msg, 400)

        tts_provider = tts_providers[tts_provider_name]
        output = use_cases.ListVoiceProfilesUseCase(tts_provider=tts_provider).execute(
            dto.ListVoiceProfilesInput(engine=engine)
        )
        return _json_response(output)

    return handle


def _resolve(use_cases_by_source: dict[str, _UseCaseT], source: str) -> _UseCaseT:
    try:
        return use_cases_by_source[source]
    except KeyError:
        available = ", ".join(sorted(use_cases_by_source))
        raise ValueError(f"Unknown source '{source}'. Available: {available}") from None


def _json_response(output: typing.Any) -> api.Response:
    body = json.dumps(dataclasses.asdict(output)).encode("utf-8")
    return api.Response(
        status_code=200,
        headers={"Content-Type": "application/json"},
        body=body,
    )


def _json_error_response(message: str, status_code: int = 400) -> api.Response:
    body = json.dumps({"error": message}).encode("utf-8")
    return api.Response(
        status_code=status_code,
        headers={"Content-Type": "application/json"},
        body=body,
    )
