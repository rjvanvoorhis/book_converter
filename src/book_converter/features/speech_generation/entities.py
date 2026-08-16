import typing
import dataclasses

VoiceId = typing.NewType("VoiceId", str)
type EngineId = typing.Literal["kokoro"]


@dataclasses.dataclass
class EngineProfile:
    id: EngineId
    description: str | None


@dataclasses.dataclass
class VoiceProfile:
    id: VoiceId
    description: str | None


@dataclasses.dataclass
class SpeechResult:
    data: typing.IO
    duration: int
