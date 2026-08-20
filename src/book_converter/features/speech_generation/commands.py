import dataclasses
import typing

from book_converter.features.speech_generation import dto
from book_converter.features.speech_generation import interfaces
from book_converter.features.speech_generation import use_cases
from book_converter.presentation import cli

_UseCaseT = typing.TypeVar("_UseCaseT")


@dataclasses.dataclass(frozen=True)
class CreateAudiobookCommand:
    use_cases_by_source: dict[str, use_cases.CreateAudiobookUseCase]
    build_text_annotator: interfaces.TextAnnotatorFactory
    tts_providers: dict[str, interfaces.TTSProvider]
    book_repositories_by_source: dict[str, interfaces.BookRepository]
    bundle_initializer: interfaces.BundleInitializer

    @property
    def name(self) -> str:
        return "create-audiobook"

    @property
    def description(self) -> str:
        return "Convert an ebook into an audiobook."

    def execute(
        self,
        identifier: str,
        target: str,
        source: str = "file",
        engine: str = "kokoro",
        voice: str = "af_heart",
        tts_provider: str = "pocket-tts",
        pronunciations: str | None = None,
        add_pauses: bool = False,
    ) -> str:
        # Get the TTS provider
        if tts_provider not in self.tts_providers:
            available = ", ".join(sorted(self.tts_providers.keys()))
            raise ValueError(
                f"Unknown TTS provider '{tts_provider}'. Available: {available}"
            )
        selected_tts_provider = self.tts_providers[tts_provider]

        # Build text annotator
        text_annotator = self.build_text_annotator(
            pronunciations_path=pronunciations, add_pauses=add_pauses
        )

        # Create use case with the selected TTS provider and text annotator
        book_repo = _resolve(self.book_repositories_by_source, source)
        use_case = use_cases.CreateAudiobookUseCase(
            book_repository=book_repo,
            tts_provider=selected_tts_provider,
            bundle_initializer=self.bundle_initializer,
            text_annotator=text_annotator,
        )

        output = use_case.execute(
            dto.CreateAudiobookInput(
                identifier=identifier, target=target, engine=engine, voice=voice
            )
        )
        minutes, seconds = divmod(output.total_duration, 60)
        return f"Created {output.destination} ({minutes}m{seconds:02d}s)"


@dataclasses.dataclass(frozen=True)
class ListVoicesCommand:
    use_case: use_cases.ListVoiceProfilesUseCase
    tts_providers: dict[str, interfaces.TTSProvider]

    @property
    def name(self) -> str:
        return "list-voices"

    @property
    def description(self) -> str:
        return "List available voice ids for a TTS engine."

    def execute(self, engine: str = "kokoro", tts_provider: str = "pocket-tts") -> str:
        if tts_provider not in self.tts_providers:
            available = ", ".join(sorted(self.tts_providers.keys()))
            raise ValueError(
                f"Unknown TTS provider '{tts_provider}'. Available: {available}"
            )
        selected_tts_provider = self.tts_providers[tts_provider]

        output = use_cases.ListVoiceProfilesUseCase(
            tts_provider=selected_tts_provider
        ).execute(dto.ListVoiceProfilesInput(engine=engine))
        lines = [
            (
                voice.id
                if not voice.description or voice.description == voice.id
                else f"{voice.id} - {voice.description}"
            )
            for voice in output.voices
        ]
        return "\n".join(lines)


def build_commands(
    create_audiobook_by_source: dict[str, use_cases.CreateAudiobookUseCase],
    list_voices: use_cases.ListVoiceProfilesUseCase,
    build_text_annotator: interfaces.TextAnnotatorFactory,
    tts_providers: dict[str, interfaces.TTSProvider],
    book_repositories_by_source: dict[str, interfaces.BookRepository],
    bundle_initializer: interfaces.BundleInitializer,
) -> list[cli.Command]:
    return [
        CreateAudiobookCommand(
            use_cases_by_source=create_audiobook_by_source,
            build_text_annotator=build_text_annotator,
            tts_providers=tts_providers,
            book_repositories_by_source=book_repositories_by_source,
            bundle_initializer=bundle_initializer,
        ),
        ListVoicesCommand(use_case=list_voices, tts_providers=tts_providers),
    ]


def _resolve(use_cases_by_source: dict[str, _UseCaseT], source: str) -> _UseCaseT:
    try:
        return use_cases_by_source[source]
    except KeyError:
        available = ", ".join(sorted(use_cases_by_source))
        raise ValueError(f"Unknown source '{source}'. Available: {available}") from None
