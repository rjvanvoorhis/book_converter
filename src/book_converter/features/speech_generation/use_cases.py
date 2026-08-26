import dataclasses
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

from book_converter.features.speech_generation import entities
from book_converter.features.speech_generation import interfaces
from book_converter.features.speech_generation import dto

logger = logging.getLogger(__name__)

_UNSAFE_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

# Gap inserted between a chapter's narration/dialogue segments. ffmpeg's concat
# demuxer otherwise abuts separately-synthesized clips with no gap at all.
_SEGMENT_GAP_SECONDS = 0.4


@dataclasses.dataclass(frozen=True)
class CreateAudiobookUseCase:
    book_repository: interfaces.BookRepository
    tts_provider: interfaces.TTSProvider
    bundle_initializer: interfaces.BundleInitializer
    text_annotator: interfaces.TextAnnotator | None
    dialogue_segmenter: interfaces.DialogueSegmenter

    def execute(self, input_dto: dto.CreateAudiobookInput) -> dto.CreateAudiobookOutput:
        book = self.book_repository.get_book(input_dto.identifier)
        batch_size = max(1, input_dto.batch_size)

        # A book made of multiple works (e.g. an AO3 series) gets one file per part.
        # Each part is generated and written to disk before moving to the next, so a
        # crash partway through a long series only costs the part in flight, and a
        # re-run can skip parts that already finished.
        parts = book.get_parts()
        if len(parts) > 1:
            return self._create_audiobooks_per_part(parts, input_dto, batch_size)

        # Split into chunks if requested
        if input_dto.chapters_per_chunk is not None:
            return self._create_chunked_audiobooks(book, input_dto, batch_size)
        else:
            return self._create_single_audiobook(book, input_dto, batch_size)

    def _generate_chapter_audio(
        self,
        chapters: list,
        input_dto: dto.CreateAudiobookInput,
        batch_size: int,
    ) -> dict[int, list[entities.SpeechResult]]:
        """Generate audio for all chapters, split into paragraph-level segments,
        and return results indexed by chapter index.

        Segmenting always runs, not just when `dialogue_voice` is set: chunking
        text at paragraph boundaries (particularly around dialogue) measurably
        improves output quality with some TTS models, independent of whether a
        second voice is in play. Without `dialogue_voice`, dialogue segments
        just fall back to the regular narrator `voice`, so a chapter with no
        dialogue at all still collapses to one segment via the segmenter's own
        narration-merging (identical to one TTS call per chapter, as before).
        """
        chapter_segments: dict[int, list[entities.DialogueSegment]] = {}
        for index, chapter in enumerate(chapters):
            text = chapter.content
            if self.text_annotator is not None:
                text = self.text_annotator.annotate(text)
            chapter_segments[index] = self.dialogue_segmenter.segment(text)

        with ThreadPoolExecutor(max_workers=batch_size) as executor:
            futures = {}
            for chapter_index, segments in chapter_segments.items():
                for segment_index, segment in enumerate(segments):
                    voice = (
                        input_dto.voice
                        if segment.speaker is None
                        else (input_dto.dialogue_voice or input_dto.voice)
                    )
                    future = executor.submit(
                        self.tts_provider.generate, segment.text, input_dto.engine, voice
                    )
                    futures[future] = (chapter_index, segment_index)

            results: dict[int, dict[int, entities.SpeechResult]] = {}
            for future in as_completed(futures):
                chapter_index, segment_index = futures[future]
                results.setdefault(chapter_index, {})[segment_index] = future.result()
                _log_segment_generated(
                    chapters, chapter_index, segment_index, len(chapter_segments[chapter_index])
                )

        return {
            chapter_index: [segment_results[i] for i in range(len(segment_results))]
            for chapter_index, segment_results in results.items()
        }

    def _create_audiobooks_per_part(
        self,
        parts: list,
        input_dto: dto.CreateAudiobookInput,
        batch_size: int,
    ) -> dto.CreateAudiobookOutput:
        """Create one audiobook file per part (e.g. one per work in a series).

        Each part's audio is generated and bundled to its final destination before
        the next part starts, so completed parts survive a crash/OOM later in the
        run and a re-run can skip parts whose output already exists.
        """
        target_dir = input_dto.target
        destinations = []
        total_duration = 0

        for part_number, part in enumerate(parts, start=1):
            file_name = f"{_safe_filename(part.metadata.title)}.m4b"
            part_target = os.path.join(target_dir, file_name)

            if os.path.exists(part_target):
                logger.info(
                    "Skipping part %d/%d '%s': '%s' already exists",
                    part_number, len(parts), part.metadata.title, part_target,
                )
                destinations.append(part_target)
                continue

            logger.info(
                "Generating part %d/%d '%s' (%d chapter(s), batch_size=%d)",
                part_number, len(parts), part.metadata.title, len(part.chapters), batch_size,
            )
            chapter_parts = self._generate_chapter_audio(part.chapters, input_dto, batch_size)

            bundler = self.bundle_initializer.create(part_target, metadata=part.metadata)
            part_duration = 0
            for chapter_index, chapter in enumerate(part.chapters):
                part_duration += _bundle_chapter_segments(
                    bundler, chapter.title, chapter_parts[chapter_index]
                )

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
        input_dto: dto.CreateAudiobookInput,
        batch_size: int,
    ) -> dto.CreateAudiobookOutput:
        """Create a single audiobook from all chapters."""
        chapters = book.chapters
        chapter_parts = self._generate_chapter_audio(chapters, input_dto, batch_size)

        bundler = self.bundle_initializer.create(
            input_dto.target, metadata=book.metadata
        )
        duration = 0

        for index, chapter in enumerate(chapters):
            duration += _bundle_chapter_segments(bundler, chapter.title, chapter_parts[index])

        destination = bundler.finalize()
        logger.info("Finished audiobook '%s' (%ds total)", destination, duration)
        return dto.CreateAudiobookOutput(destinations=[destination], total_duration=duration)

    def _create_chunked_audiobooks(
        self,
        book,
        input_dto: dto.CreateAudiobookInput,
        batch_size: int,
    ) -> dto.CreateAudiobookOutput:
        """Create multiple audiobook files, chunked by chapter count.

        Each chunk is generated and bundled to its final destination before the
        next chunk starts, mirroring the per-part flow so a long run stays
        crash-safe and resumable.
        """
        chapters = book.chapters
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

            if os.path.exists(chunk_target):
                logger.info(
                    "Skipping chunk %d/%d: '%s' already exists",
                    chunk_idx + 1, num_chunks, chunk_target,
                )
                destinations.append(chunk_target)
                continue

            chapter_parts = self._generate_chapter_audio(chunk_chapters, input_dto, batch_size)

            bundler = self.bundle_initializer.create(
                chunk_target, metadata=book.metadata
            )
            chunk_duration = 0

            for local_idx, chapter in enumerate(chunk_chapters):
                chunk_duration += _bundle_chapter_segments(
                    bundler, chapter.title, chapter_parts[local_idx]
                )

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


def _bundle_chapter_segments(
    bundler: interfaces.Bundler, title: str, segments: list[entities.SpeechResult]
) -> float:
    """Add one chapter's segments to the bundler, gapped and grouped under a
    single chapter marker, and return the chapter's total duration."""
    duration = 0.0
    for segment_index, speech in enumerate(segments):
        if segment_index > 0:
            bundler.add_silence(_SEGMENT_GAP_SECONDS)
        bundler.add_part(title, speech.data, new_chapter=(segment_index == 0))
        duration += speech.duration
    return duration


def _log_segment_generated(
    chapters: list, chapter_index: int, segment_index: int, segment_count: int
) -> None:
    if segment_count == 1:
        logger.info(
            "Generated audio for chapter %d/%d: '%s'",
            chapter_index + 1, len(chapters), chapters[chapter_index].title,
        )
    else:
        logger.info(
            "Generated audio for chapter %d/%d segment %d/%d: '%s'",
            chapter_index + 1, len(chapters), segment_index + 1, segment_count,
            chapters[chapter_index].title,
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
