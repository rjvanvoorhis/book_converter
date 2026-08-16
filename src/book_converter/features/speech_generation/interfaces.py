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


class BookRepository(typing.Protocol):
    def get_book(self, identifier: str) -> core_entities.Book: ...


class Bundler(typing.Protocol):
    def add_part(self, title: str, part: typing.IO) -> None: ...

    def finalize(self) -> str: ...


class BundleInitializer(typing.Protocol):
    def create(
        self, target: str, metadata: core_entities.BookMetadata | None
    ) -> Bundler: ...
