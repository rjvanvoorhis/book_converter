import dataclasses

from book_converter.features.speech_generation import dto
from book_converter.features.speech_generation import use_cases
from book_converter.presentation import cli


@dataclasses.dataclass(frozen=True)
class CreateAudiobookCommand:
    use_case: use_cases.CreateAudiobookUseCase

    @property
    def name(self) -> str:
        return "create-audiobook"

    @property
    def description(self) -> str:
        return "Convert an ebook into an audiobook."

    def execute(
        self, identifier: str, target: str, engine: str = "kokoro", voice: str = "af_heart"
    ) -> str:
        output = self.use_case.execute(
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
    create_audiobook: use_cases.CreateAudiobookUseCase,
    list_voices: use_cases.ListVoiceProfilesUseCase,
) -> list[cli.Command]:
    return [
        CreateAudiobookCommand(use_case=create_audiobook),
        ListVoicesCommand(use_case=list_voices),
    ]
