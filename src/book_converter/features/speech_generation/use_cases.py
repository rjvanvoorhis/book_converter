import dataclasses
from concurrent.futures import ThreadPoolExecutor, as_completed

from book_converter.features.speech_generation import interfaces
from book_converter.features.speech_generation import dto


@dataclasses.dataclass(frozen=True)
class CreateAudiobookUseCase:
    book_repository: interfaces.BookRepository
    tts_provider: interfaces.TTSProvider
    bundle_initializer: interfaces.BundleInitializer
    text_annotator: interfaces.TextAnnotator | None

    def execute(self, input_dto: dto.CreateAudiobookInput) -> dto.CreateAudiobookOutput:
        book = self.book_repository.get_book(input_dto.identifier)
        bundler = self.bundle_initializer.create(
            input_dto.target, metadata=book.metadata
        )
        duration = 0

        # Process chapters in batches
        batch_size = max(1, input_dto.batch_size)  # Ensure batch_size is at least 1
        chapters = book.chapters

        with ThreadPoolExecutor(max_workers=batch_size) as executor:
            # Submit all chapters for processing
            futures = {}
            for chapter in chapters:
                text = chapter.content
                if self.text_annotator is not None:
                    text = self.text_annotator.annotate(text)
                future = executor.submit(
                    self.tts_provider.generate,
                    text,
                    input_dto.engine,
                    input_dto.voice,
                )
                futures[future] = chapter

            # Collect results in chapter order
            chapter_parts = {}
            for future in as_completed(futures):
                chapter = futures[future]
                part = future.result()
                chapter_parts[chapter] = part

        # Add parts to bundler in original chapter order
        for chapter in chapters:
            part = chapter_parts[chapter]
            bundler.add_part(chapter.title, part.data)
            duration += part.duration

        return dto.CreateAudiobookOutput(
            destination=bundler.finalize(), total_duration=duration
        )


@dataclasses.dataclass(frozen=True)
class ListVoiceProfilesUseCase:
    tts_provider: interfaces.TTSProvider

    def execute(
        self, input_dto: dto.ListVoiceProfilesInput
    ) -> dto.ListVoiceProfilesOutput:
        profiles = self.tts_provider.get_voice_profiles(input_dto.engine)
        return dto.ListVoiceProfilesOutput(
            voices=[
                dto.VoiceProfileDto(id=profile.id, description=profile.description)
                for profile in profiles
            ]
        )
