import dataclasses


@dataclasses.dataclass(frozen=True)
class CreateAudiobookInput:
    identifier: str
    target: str
    engine: str
    voice: str
    batch_size: int = 1


@dataclasses.dataclass(frozen=True)
class CreateAudiobookOutput:
    destination: str
    total_duration: int


@dataclasses.dataclass(frozen=True)
class ListVoiceProfilesInput:
    engine: str


@dataclasses.dataclass(frozen=True)
class VoiceProfileDto:
    id: str
    description: str | None


@dataclasses.dataclass(frozen=True)
class ListVoiceProfilesOutput:
    voices: list[VoiceProfileDto]
