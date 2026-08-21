import dataclasses
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

from book_converter.features.speech_generation import interfaces
from book_converter.features.speech_generation import dto

logger = logging.getLogger(__name__)

_UNSAFE_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


@dataclasses.dataclass(frozen=True)
class CreateAudiobookUseCase:
    book_repository: interfaces.BookRepository
    tts_provider: interfaces.TTSProvider
    bundle_initializer: interfaces.BundleInitializer
    text_annotator: interfaces.TextAnnotator | None

    def execute(self, input_dto: dto.CreateAudiobookInput) -> dto.CreateAudiobookOutput:
        book = self.book_repository.get_book(input_dto.identifier)
        chapters = book.chapters
        total = len(chapters)
        batch_size = max(1, input_dto.batch_size)

        logger.info(
            "Generating audio for %d chapter(s) of '%s' (batch_size=%d)",
            total,
            input_dto.identifier,
            batch_size,
        )

        # Generate audio for all chapters
        chapter_parts = self._generate_chapter_audio(
            chapters, input_dto, batch_size
        )

        # A book made of multiple works (e.g. an AO3 series) gets one file per part
        parts = book.get_parts()
        if len(parts) > 1:
            return self._create_audiobooks_per_part(
                parts, chapters, chapter_parts, input_dto
            )

        # Split into chunks if requested
        if input_dto.chapters_per_chunk is not None:
            return self._create_chunked_audiobooks(
                book, chapters, chapter_parts, input_dto
            )
        else:
            return self._create_single_audiobook(book, chapters, chapter_parts, input_dto)

    def _generate_chapter_audio(
        self,
        chapters: list,
        input_dto: dto.CreateAudiobookInput,
        batch_size: int,
    ) -> dict[int, "SpeechResult"]:
        """Generate audio for all chapters and return them indexed by chapter index."""
        with ThreadPoolExecutor(max_workers=batch_size) as executor:
            futures = {}
            for index, chapter in enumerate(chapters):
                text = chapter.content
                if self.text_annotator is not None:
                    text = self.text_annotator.annotate(text)
                future = executor.submit(
                    self.tts_provider.generate,
                    text,
                    input_dto.engine,
                    input_dto.voice,
                )
                futures[future] = index

            chapter_parts = {}
            completed = 0
            for future in as_completed(futures):
                index = futures[future]
                part = future.result()
                chapter_parts[index] = part
                completed += 1
                logger.info(
                    "Generated audio for chapter %d/%d: '%s'",
                    completed,
                    len(chapters),
                    chapters[index].title,
                )

        return chapter_parts

    def _create_audiobooks_per_part(
        self,
        parts: list,
        chapters: list,
        chapter_parts: dict[int, "SpeechResult"],
        input_dto: dto.CreateAudiobookInput,
    ) -> dto.CreateAudiobookOutput:
        """Create one audiobook file per part (e.g. one per work in a series)."""
        index_by_chapter_id = {chapter.id: index for index, chapter in enumerate(chapters)}
        target_dir = input_dto.target
        destinations = []
        total_duration = 0

        for part in parts:
            file_name = f"{_safe_filename(part.metadata.title)}.m4b"
            part_target = os.path.join(target_dir, file_name)
            bundler = self.bundle_initializer.create(part_target, metadata=part.metadata)
            part_duration = 0

            for chapter in part.chapters:
                speech = chapter_parts[index_by_chapter_id[chapter.id]]
                bundler.add_part(chapter.title, speech.data)
                part_duration += speech.duration

            destination = bundler.finalize()
            destinations.append(destination)
            total_duration += part_duration
            logger.info(
                "Finished audiobook '%s' (%ds)", destination, part_duration
            )

        logger.info(
            "Finished all %d part audiobook(s) (%ds total)", len(parts), total_duration
        )
        return dto.CreateAudiobookOutput(
            destinations=destinations, total_duration=total_duration
        )

    def _create_single_audiobook(
        self,
        book,
        chapters: list,
        chapter_parts: dict[int, "SpeechResult"],
        input_dto: dto.CreateAudiobookInput,
    ) -> dto.CreateAudiobookOutput:
        """Create a single audiobook from all chapters."""
        bundler = self.bundle_initializer.create(
            input_dto.target, metadata=book.metadata
        )
        duration = 0

        for index, chapter in enumerate(chapters):
            part = chapter_parts[index]
            bundler.add_part(chapter.title, part.data)
            duration += part.duration

        destination = bundler.finalize()
        logger.info("Finished audiobook '%s' (%ds total)", destination, duration)
        return dto.CreateAudiobookOutput(destinations=[destination], total_duration=duration)

    def _create_chunked_audiobooks(
        self,
        book,
        chapters: list,
        chapter_parts: dict[int, "SpeechResult"],
        input_dto: dto.CreateAudiobookInput,
    ) -> dto.CreateAudiobookOutput:
        """Create multiple audiobook files, chunked by chapter count."""
        chapters_per_chunk = input_dto.chapters_per_chunk
        destinations = []
        total_duration = 0

        # Split target path to create numbered outputs
        target_path = input_dto.target
        base, ext = os.path.splitext(target_path)

        num_chunks = (len(chapters) + chapters_per_chunk - 1) // chapters_per_chunk
        logger.info(
            "Creating %d audiobook chunk(s), %d chapters per chunk",
            num_chunks,
            chapters_per_chunk,
        )

        for chunk_idx in range(num_chunks):
            start_idx = chunk_idx * chapters_per_chunk
            end_idx = min(start_idx + chapters_per_chunk, len(chapters))
            chunk_chapters = chapters[start_idx:end_idx]

            # Create target path for this chunk
            if num_chunks > 1:
                chunk_target = f"{base}-part-{chunk_idx + 1}{ext}"
            else:
                chunk_target = target_path

            bundler = self.bundle_initializer.create(
                chunk_target, metadata=book.metadata
            )
            chunk_duration = 0

            for local_idx, chapter in enumerate(chunk_chapters):
                global_idx = start_idx + local_idx
                part = chapter_parts[global_idx]
                bundler.add_part(chapter.title, part.data)
                chunk_duration += part.duration

            destination = bundler.finalize()
            destinations.append(destination)
            total_duration += chunk_duration
            logger.info(
                "Finished audiobook chunk %d/%d: '%s' (%ds)",
                chunk_idx + 1,
                num_chunks,
                destination,
                chunk_duration,
            )

        logger.info("Finished all audiobook chunks (%ds total)", total_duration)
        return dto.CreateAudiobookOutput(
            destinations=destinations, total_duration=total_duration
        )


def _safe_filename(title: str) -> str:
    cleaned = _UNSAFE_FILENAME_CHARS.sub(" ", title).strip().rstrip(".")
    return " ".join(cleaned.split()) or "untitled"


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
