import dataclasses


@dataclasses.dataclass(frozen=True)
class CreateAudiobookInput:
    identifier: str
    name: str
    audiobook_folder: str
    engine: str
    voice: str
    batch_size: int = 1
    chapters_per_chunk: int | None = None
    dialogue_voice: str | None = None


@dataclasses.dataclass(frozen=True)
class CreateAudiobookOutput:
    destinations: list[str]
    transcripts: list[str]
    total_duration: int


@dataclasses.dataclass(frozen=True)
class CreateSampleInput:
    identifier: str
    source: str
    engine: str
    voice: str
    sentence_count: int = 3


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
