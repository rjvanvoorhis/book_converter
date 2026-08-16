import dataclasses

from book_converter.features.speech_generation import interfaces
from book_converter.features.speech_generation import dto


@dataclasses.dataclass(frozen=True)
class CreateAudiobookUseCase:
    book_repository: interfaces.BookRepository
    tts_provider: interfaces.TTSProvider
    bundle_initializer: interfaces.BundleInitializer
    text_annotator: interfaces.TextAnnotator | None

    def execute(self, input_dto: dto.CreateAudiobookInput):
        book = self.book_repository.get_book(input_dto.identifier)
        bundler = self.bundle_initializer.create(
            input_dto.target, metadata=book.metadata
        )
        duration = 0
        for chapter in book.chapters:
            text = self.text_annotator.annotate(chapter.content)
            part = self.tts_provider.generate(text, input_dto.engine, input_dto.voice)
            bundler.add_part(chapter.title, part.data)
            duration += part.duration
        return dto.CreateAudiobookOutput(
            destination=bundler.finalize(), total_duration=duration
        )
