import typing

from book_converter.core import entities as core_entities
from book_converter.features.speech_generation import entities


class TTSProvider(typing.Protocol):
    def get_engine_profiles(self) -> list[entities.EngineProfile]: ...

    def get_voice_profiles(
        self, engine: entities.EngineId
    ) -> list[entities.VoiceProfile]: ...

    def generate(
        self, text: str, engine: entities.EngineId, voice: entities.VoiceId
    ) -> entities.SpeechResult: ...


class TextAnnotator(typing.Protocol):
    def annotate(self, text: str) -> str: ...


class AudioCleaner(typing.Protocol):
    """Reduces noise/artifacts in a short audio clip (e.g. a voice-cloning
    sample) that would otherwise get reproduced by a cloning-capable TTS
    engine along with the voice itself. Implementations trade quality
    against speed/dependencies - see infrastructure/speech_generation for
    the concrete adapters (a zero-dependency ffmpeg filter chain vs. a
    higher-quality ML model)."""

    def clean(self, wav_bytes: bytes) -> bytes: ...


class ProgressReporter(typing.Protocol):
    """Receives human-readable status updates as a long-running audiobook
    generation run progresses, so a caller (e.g. an HTTP polling endpoint)
    can surface them without needing to tail server logs. Also doubles as
    the cancellation check: a use case calls `is_cancelled()` at its own
    natural checkpoints (between segments, between chapters/parts) and
    raises TaskCancelled to unwind cleanly - nothing can forcibly interrupt
    a running thread, so cancellation is cooperative."""

    def report(self, message: str) -> None: ...

    def is_cancelled(self) -> bool: ...


class TaskCancelled(Exception):
    """Raised at a ProgressReporter checkpoint once cancellation has been
    requested, so a long-running use case unwinds instead of running to
    completion. Callers (e.g. the HTTP task runner) catch this separately
    from other failures and record it as "cancelled", not "failed"."""


class DialogueSegmenter(typing.Protocol):
    def segment(self, text: str) -> list[entities.DialogueSegment]: ...


class TextAnnotatorFactory(typing.Protocol):
    def __call__(
        self, pronunciations_path: str | None = None, add_pauses: bool = False
    ) -> TextAnnotator: ...


class BookRepository(typing.Protocol):
    def get_book(self, identifier: str) -> core_entities.Book: ...


class Bundler(typing.Protocol):
    def add_part(
        self,
        title: str,
        part: typing.IO,
        text: str,
        speaker: str | None = None,
        new_chapter: bool = True,
    ) -> None: ...

    def add_silence(self, seconds: float) -> None: ...

    def finalize(self) -> str: ...


class BundleInitializer(typing.Protocol):
    def create(
        self, target: str, metadata: core_entities.BookMetadata | None
    ) -> Bundler: ...
