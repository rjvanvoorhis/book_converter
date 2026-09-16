import dataclasses
import os
import pathlib

import dotenv

from book_converter.features.media_library import routes as media_library_routes
from book_converter.features.organization import routes as organization_routes
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
from book_converter.infrastructure.media_library import (
    audiobookshelf_client,
    local_filesystem_store,
    nas_share_store,
    smb_file_store,
)
from book_converter.infrastructure.organization import group_store
from book_converter.infrastructure.speech_generation import (
    book_repository,
    extracted_text_book_repository,
    ffmpeg_audio_cleaner,
    ffmpeg_bundler,
    in_memory_task_store,
    kokoro_tts_provider,
    pocket_tts_provider,
    quote_dialogue_segmenter,
    resemble_enhance_audio_cleaner,
    text_annotator,
)
from book_converter.infrastructure.text_extraction import (
    ao3_converter,
    ao3_repository,
    azw3_converter,
    caching_ebook_repository,
    dispatching_converter,
    epub_converter,
    extracted_text_saver,
    ffnet_converter,
    ffnet_repository,
    filesystem_repository,
    language_tool_copy_editor,
    lm_studio_copy_editor,
)
from book_converter.presentation import api, cli


@dataclasses.dataclass(frozen=True)
class Container:
    commands: list[cli.Command]
    routes: list[api.Route]


def _build_media_library_file_store() -> (
    local_filesystem_store.LocalFilesystemStore
    | nas_share_store.NasShareStore
    | smb_file_store.SmbFileStore
):
    storage = (os.environ.get("AUDIOBOOKSHELF_STORAGE") or "local").strip().lower()
    if storage == "local":
        return local_filesystem_store.LocalFilesystemStore()
    if storage == "nas":
        # Linux-only: assumes the share is (or can be, via entrypoints.
        # setup_audiobookshelf_mount_user) mounted at the OS level. Use
        # 'smb' instead on macOS/Windows, or on Linux without root access
        # to set up a mount.
        return nas_share_store.NasShareStore(
            path_prefix_map=_parse_path_map(
                os.environ.get("AUDIOBOOKSHELF_PATH_MAP", "")
            ),
            mounts=_parse_nas_mounts(os.environ.get("AUDIOBOOKSHELF_NAS_MOUNTS", "")),
        )
    if storage == "smb":
        # Cross-platform (macOS/Windows/Linux): speaks SMB2/3 directly, no
        # OS mount or elevated privileges required. `server` is just the SMB
        # host - which share a path belongs to is derived from the path
        # itself (see SmbFileStore's docstring), not configured here.
        server = os.environ.get("AUDIOBOOKSHELF_SMB_SERVER")
        username = os.environ.get("AUDIOBOOKSHELF_SMB_USERNAME")
        password = os.environ.get("AUDIOBOOKSHELF_SMB_PASSWORD")
        if not server or not username or not password:
            raise ValueError(
                "AUDIOBOOKSHELF_STORAGE=smb requires AUDIOBOOKSHELF_SMB_SERVER, "
                "AUDIOBOOKSHELF_SMB_USERNAME and AUDIOBOOKSHELF_SMB_PASSWORD"
            )
        return smb_file_store.SmbFileStore(
            server=server,
            username=username,
            password=password,
            port=int(os.environ.get("AUDIOBOOKSHELF_SMB_PORT") or 445),
            path_prefix_map=_parse_path_map(
                os.environ.get("AUDIOBOOKSHELF_PATH_MAP", "")
            ),
        )
    raise ValueError(
        f"Unknown AUDIOBOOKSHELF_STORAGE '{storage}' - expected 'local', 'nas' or 'smb'"
    )


def _parse_path_map(raw: str) -> dict[str, str]:
    """Parses AUDIOBOOKSHELF_PATH_MAP, e.g.
    '/audiobooks=/mnt/nas/audiobooks,/podcasts=/mnt/nas/podcasts' - one
    server-reported-prefix=local-mount-prefix pair per comma-separated
    entry."""
    path_map = {}
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        remote_prefix, _, local_prefix = entry.partition("=")
        if not remote_prefix or not local_prefix:
            raise ValueError(
                f"Invalid AUDIOBOOKSHELF_PATH_MAP entry '{entry}' - "
                "expected 'remote-prefix=local-prefix'"
            )
        path_map[remote_prefix] = local_prefix
    return path_map


def _parse_nas_mounts(raw: str) -> dict[str, nas_share_store.MountSpec]:
    """Parses AUDIOBOOKSHELF_NAS_MOUNTS, e.g.
    '/mnt/nas/audiobooks|cifs|//nas.local/audiobooks|username=svc,password=secret,vers=3.0'
    - one 'local-mount-point|fs_type|remote' or
    'local-mount-point|fs_type|remote|opt1,opt2' entry per ';'-separated
    section. A local mount point with no entry here simply can't be
    auto-mounted by RegisterFolderUseCase - it still works fine if it's
    already mounted some other way (e.g. /etc/fstab)."""
    mounts: dict[str, nas_share_store.MountSpec] = {}
    for entry in raw.split(";"):
        entry = entry.strip()
        if not entry:
            continue
        fields = entry.split("|")
        if len(fields) not in (3, 4):
            raise ValueError(
                f"Invalid AUDIOBOOKSHELF_NAS_MOUNTS entry '{entry}' - expected "
                "'local-mount-point|fs_type|remote' or "
                "'local-mount-point|fs_type|remote|opt1,opt2'"
            )
        mount_point, fs_type, remote = fields[:3]
        options = fields[3].split(",") if len(fields) == 4 and fields[3] else []
        mounts[mount_point] = nas_share_store.MountSpec(
            remote=remote, fs_type=fs_type, options=options
        )
    return mounts


def build_container() -> Container:
    # Optional gitignored .env (see .env.example) - a no-op if it doesn't
    # exist, so this is safe to call unconditionally. Real environment
    # variables already set take precedence over the file either way.
    dotenv.load_dotenv()

    ebook_converter = dispatching_converter.DispatchingEbookConverter(
        converters=[
            epub_converter.EpubConverter(),
            azw3_converter.Azw3Converter(),
            ao3_converter.Ao3HtmlConverter(),
            ffnet_converter.FfNetHtmlConverter(),
        ]
    )
    ao3_username = os.environ.get("AO3_USERNAME") or None
    ao3_password = os.environ.get("AO3_PASSWORD") or None
    # Wrapped so the UI's Load -> Review -> Save for later flow (and the
    # per-chapter viewer) hit the source once instead of once per step -
    # see caching_ebook_repository for why.
    ebook_repositories = {
        source: caching_ebook_repository.CachingEbookRepository(repository=repository)
        for source, repository in {
            "file": filesystem_repository.FilesystemEbookRepository(),
            "ao3": ao3_repository.AO3EbookRepository(
                username=ao3_username, password=ao3_password
            ),
            "ffnet": ffnet_repository.FfNetEbookRepository(),
        }.items()
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

    # Voice-sample cleaners: ffmpeg is always available (a hard dependency
    # of this project already); resemble-enhance needs its own isolated
    # Python 3.11 environment (see resemble_enhance_audio_cleaner.py for
    # why) - a standalone uv project under audio-clean-worker/ with its own
    # pyproject.toml/uv.lock, set up by running `uv sync` there. A fresh
    # checkout won't have that .venv until someone does, so this cleaner is
    # only registered - and only shows up as an option in the UI - once it
    # actually exists.
    project_root = pathlib.Path(__file__).resolve().parents[3]
    resemble_enhance_python = str(
        project_root / "audio-clean-worker" / ".venv" / "bin" / "python"
    )
    audio_cleaners = {"ffmpeg": ffmpeg_audio_cleaner.FfmpegAudioCleaner()}
    if resemble_enhance_audio_cleaner.ResembleEnhanceAudioCleaner.is_available(
        resemble_enhance_python
    ):
        for mode in ("enhance", "denoise"):
            cleaner = resemble_enhance_audio_cleaner.ResembleEnhanceAudioCleaner(
                resemble_enhance_python, mode=mode
            )
            audio_cleaners[cleaner.id] = cleaner

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

    # Tracks in-flight audiobook generation runs so the API can hand back a
    # task id and let the client poll instead of blocking on the request.
    audiobook_task_store = in_memory_task_store.InMemoryTaskStore()

    # Quote-detection dialogue segmenter (phase 1 of speaker attribution): tags
    # detected dialogue with entities.UNKNOWN_SPEAKER rather than a real name.
    dialogue_segmenter = quote_dialogue_segmenter.QuoteDialogueSegmenter()

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
            dialogue_segmenter=dialogue_segmenter,
        )

    create_audiobook_by_source = {
        source: create_audiobook_use_case(book_repo)
        for source, book_repo in book_repositories_by_source.items()
    }

    list_voices = speech_generation_use_cases.ListVoiceProfilesUseCase(
        tts_provider=default_tts_provider
    )

    # Groups staged works into series (data/organization/groups.json) - a
    # series is bound to its media library/folder at creation and never
    # auto-created (see organization.CreateGroupUseCase); always available,
    # independent of whether a media library adapter is configured below.
    organization_group_store = group_store.JsonGroupStore()

    # Audiobookshelf adapter: only registered - and only shows up as a route
    # - once a target server is actually configured, same "absent unless
    # configured" pattern as the resemble-enhance audio cleaner above.
    audiobookshelf_url = os.environ.get("AUDIOBOOKSHELF_URL") or None
    audiobookshelf_api_key = os.environ.get("AUDIOBOOKSHELF_API_KEY") or None
    media_library_route_list: list[api.Route] = []
    if audiobookshelf_url and audiobookshelf_api_key:
        media_library_route_list = media_library_routes.build_routes(
            media_library=audiobookshelf_client.AudiobookshelfClient(
                base_url=audiobookshelf_url.rstrip("/"),
                api_key=audiobookshelf_api_key,
                file_store=_build_media_library_file_store(),
            ),
            group_store=organization_group_store,
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
                dialogue_segmenter,
            ),
        ],
        routes=[
            *text_extraction_routes.build_routes(
                load_ebook_by_source,
                extract_chapter_by_source,
                extract_text_by_source,
                copyedit_by_editor,
                default_extracted_texts_folder=os.environ.get(
                    "EXTRACTED_TEXTS_FOLDER", "data/texts"
                ),
            ),
            *speech_generation_routes.build_routes(
                text_annotator.build_text_annotator,
                tts_providers,
                book_repositories_by_source,
                bundle_initializer,
                dialogue_segmenter,
                audiobook_task_store,
                audio_cleaners,
            ),
            *organization_routes.build_routes(organization_group_store),
            *media_library_route_list,
        ],
    )
