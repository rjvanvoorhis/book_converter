import dataclasses

from book_converter.features.speech_generation import (
    commands as speech_generation_commands,
)
from book_converter.features.speech_generation import (
    interfaces as speech_generation_interfaces,
)
from book_converter.features.speech_generation import routes as speech_generation_routes
from book_converter.features.speech_generation import (
    use_cases as speech_generation_use_cases,
)
from book_converter.features.text_extraction import commands as text_extraction_commands
from book_converter.features.text_extraction import routes as text_extraction_routes
from book_converter.features.text_extraction import (
    use_cases as text_extraction_use_cases,
)
from book_converter.infrastructure.speech_generation import book_repository
from book_converter.infrastructure.speech_generation import (
    extracted_text_book_repository,
)
from book_converter.infrastructure.speech_generation import ffmpeg_bundler
from book_converter.infrastructure.speech_generation import kokoro_tts_provider
from book_converter.infrastructure.speech_generation import pocket_tts_provider
from book_converter.infrastructure.speech_generation import text_annotator
from book_converter.infrastructure.text_extraction import ao3_repository
from book_converter.infrastructure.text_extraction import epub_converter
from book_converter.infrastructure.text_extraction import extracted_text_saver
from book_converter.infrastructure.text_extraction import filesystem_repository
from book_converter.infrastructure.text_extraction import language_tool_copy_editor
from book_converter.infrastructure.text_extraction import lm_studio_copy_editor
from book_converter.presentation import api
from book_converter.presentation import cli


@dataclasses.dataclass(frozen=True)
class Container:
    commands: list[cli.Command]
    routes: list[api.Route]


def build_container() -> Container:
    ebook_converter = epub_converter.EpubConverter()
    ebook_repositories = {
        "file": filesystem_repository.FilesystemEbookRepository(),
        "ao3": ao3_repository.AO3EbookRepository(),
    }
    text_saver = extracted_text_saver.ExtractedTextSaver()

    load_ebook_by_source = {
        source: text_extraction_use_cases.LoadEbookUseCase(
            repository=repository, converter=ebook_converter
        )
        for source, repository in ebook_repositories.items()
    }
    extract_chapter_by_source = {
        source: text_extraction_use_cases.ExtractChapterUseCase(
            repository=repository, converter=ebook_converter
        )
        for source, repository in ebook_repositories.items()
    }
    extract_text_by_source = {
        source: text_extraction_use_cases.ExtractTextUseCase(
            repository=repository, converter=ebook_converter, saver=text_saver
        )
        for source, repository in ebook_repositories.items()
    }

    extracted_text_repository = (
        extracted_text_book_repository.ExtractedTextBookRepository()
    )
    copy_editors = {
        "languagetool": language_tool_copy_editor.LanguageToolCopyEditor(),
        "lmstudio": lm_studio_copy_editor.LmStudioCopyEditor(),
    }
    copyedit_by_editor = {
        name: text_extraction_use_cases.CopyEditTextUseCase(
            repository=extracted_text_repository, editor=editor, saver=text_saver
        )
        for name, editor in copy_editors.items()
    }

    # Create TTS providers
    tts_providers = {
        "kokoro": kokoro_tts_provider.KokoroTtsProvider(),
        "pocket-tts": pocket_tts_provider.PocketTtsProvider(),
    }

    # Create book repositories for both ebook and extracted text sources
    book_repositories_by_source = {
        source: book_repository.EbookBookRepository(
            repository=repository, converter=ebook_converter
        )
        for source, repository in ebook_repositories.items()
    }
    book_repositories_by_source["extracted"] = extracted_text_repository

    # Initialize FFmpeg bundler
    bundle_initializer = ffmpeg_bundler.FfmpegBundleInitializer()

    # Create default use cases (these won't be used directly but kept for compatibility)
    default_tts_provider = tts_providers["pocket-tts"]
    default_text_annotator = text_annotator.build_text_annotator()

    def create_audiobook_use_case(
        book_repo: speech_generation_interfaces.BookRepository,
    ) -> speech_generation_use_cases.CreateAudiobookUseCase:
        return speech_generation_use_cases.CreateAudiobookUseCase(
            book_repository=book_repo,
            tts_provider=default_tts_provider,
            bundle_initializer=bundle_initializer,
            text_annotator=default_text_annotator,
        )

    create_audiobook_by_source = {
        source: create_audiobook_use_case(book_repo)
        for source, book_repo in book_repositories_by_source.items()
    }

    list_voices = speech_generation_use_cases.ListVoiceProfilesUseCase(
        tts_provider=default_tts_provider
    )

    return Container(
        commands=[
            *text_extraction_commands.build_commands(
                load_ebook_by_source,
                extract_chapter_by_source,
                extract_text_by_source,
                copyedit_by_editor,
            ),
            *speech_generation_commands.build_commands(
                create_audiobook_by_source,
                list_voices,
                text_annotator.build_text_annotator,
                tts_providers,
                book_repositories_by_source,
                bundle_initializer,
            ),
        ],
        routes=[
            *text_extraction_routes.build_routes(
                load_ebook_by_source,
                extract_chapter_by_source,
                extract_text_by_source,
                copyedit_by_editor,
            ),
            *speech_generation_routes.build_routes(
                text_annotator.build_text_annotator,
                tts_providers,
                book_repositories_by_source,
                bundle_initializer,
            ),
        ],
    )
