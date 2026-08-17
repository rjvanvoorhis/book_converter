import dataclasses
import typing

from book_converter.features.speech_generation import dto
from book_converter.features.speech_generation import use_cases
from book_converter.presentation import cli

_UseCaseT = typing.TypeVar("_UseCaseT")


@dataclasses.dataclass(frozen=True)
class CreateAudiobookCommand:
    use_cases_by_source: dict[str, use_cases.CreateAudiobookUseCase]

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
    ) -> str:
        use_case = _resolve(self.use_cases_by_source, source)
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

    @property
    def name(self) -> str:
        return "list-voices"

    @property
    def description(self) -> str:
        return "List available voice ids for a TTS engine."

    def execute(self, engine: str = "kokoro") -> str:
        output = self.use_case.execute(dto.ListVoiceProfilesInput(engine=engine))
        lines = [
            voice.id if not voice.description or voice.description == voice.id
            else f"{voice.id} - {voice.description}"
            for voice in output.voices
        ]
        return "\n".join(lines)


def build_commands(
    create_audiobook_by_source: dict[str, use_cases.CreateAudiobookUseCase],
    list_voices: use_cases.ListVoiceProfilesUseCase,
) -> list[cli.Command]:
    return [
        CreateAudiobookCommand(use_cases_by_source=create_audiobook_by_source),
        ListVoicesCommand(use_case=list_voices),
    ]


def _resolve(use_cases_by_source: dict[str, _UseCaseT], source: str) -> _UseCaseT:
    try:
        return use_cases_by_source[source]
    except KeyError:
        available = ", ".join(sorted(use_cases_by_source))
        raise ValueError(f"Unknown source '{source}'. Available: {available}") from None
