import dataclasses

from book_converter.features.speech_generation import commands as speech_generation_commands
from book_converter.features.speech_generation import routes as speech_generation_routes
from book_converter.features.speech_generation import use_cases as speech_generation_use_cases
from book_converter.features.text_extraction import commands as text_extraction_commands
from book_converter.features.text_extraction import routes as text_extraction_routes
from book_converter.features.text_extraction import use_cases as text_extraction_use_cases
from book_converter.infrastructure.speech_generation import book_repository
from book_converter.infrastructure.speech_generation import ffmpeg_bundler
from book_converter.infrastructure.speech_generation import kokoro_tts_provider
from book_converter.infrastructure.speech_generation import pause_text_annotator
from book_converter.infrastructure.speech_generation import pronunciation_text_annotator
from book_converter.infrastructure.speech_generation import text_annotator
from book_converter.infrastructure.text_extraction import epub_converter
from book_converter.infrastructure.text_extraction import filesystem_repository
from book_converter.presentation import api
from book_converter.presentation import cli


@dataclasses.dataclass(frozen=True)
class Container:
    commands: list[cli.Command]
    routes: list[api.Route]


def build_container() -> Container:
    ebook_repository = filesystem_repository.FilesystemEbookRepository()
    ebook_converter = epub_converter.EpubConverter()

    load_ebook = text_extraction_use_cases.LoadEbookUseCase(
        repository=ebook_repository, converter=ebook_converter
    )
    extract_chapter = text_extraction_use_cases.ExtractChapterUseCase(
        repository=ebook_repository, converter=ebook_converter
    )

    tts_provider = kokoro_tts_provider.KokoroTtsProvider()

    create_audiobook = speech_generation_use_cases.CreateAudiobookUseCase(
        book_repository=book_repository.EbookBookRepository(
            repository=ebook_repository, converter=ebook_converter
        ),
        tts_provider=tts_provider,
        bundle_initializer=ffmpeg_bundler.FfmpegBundleInitializer(),
        text_annotator=text_annotator.CompositeTextAnnotator(
            annotators=[
                pronunciation_text_annotator.PronunciationTextAnnotator(pronunciations={}),
                pause_text_annotator.PauseTextAnnotator(),
            ]
        ),
    )
    list_voices = speech_generation_use_cases.ListVoiceProfilesUseCase(
        tts_provider=tts_provider
    )

    return Container(
        commands=[
            *text_extraction_commands.build_commands(load_ebook, extract_chapter),
            *speech_generation_commands.build_commands(create_audiobook, list_voices),
        ],
        routes=[
            *text_extraction_routes.build_routes(load_ebook, extract_chapter),
            *speech_generation_routes.build_routes(create_audiobook, list_voices),
        ],
    )
