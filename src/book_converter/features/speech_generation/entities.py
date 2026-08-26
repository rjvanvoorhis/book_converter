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


UNKNOWN_SPEAKER = "unknown"


@dataclasses.dataclass(frozen=True)
class DialogueSegment:
    """A run of chapter text to synthesize as one TTS call.

    `speaker` is None for narration, or a speaker tag for dialogue. Today the
    only tag produced is UNKNOWN_SPEAKER (quote-detection doesn't attempt to
    identify who's speaking); a future attribution pass can assign real
    character names here without changing how segments are consumed.
    """

    text: str
    speaker: str | None
