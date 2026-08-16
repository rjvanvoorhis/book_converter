import dataclasses


@dataclasses.dataclass(frozen=True)
class CreateAudiobookInput:
    identifier: str
    target: str
    engine: str
    voice: str


@dataclasses.dataclass(frozen=True)
class CreateAudiobookOutput:
    destination: str
    total_duration: int
