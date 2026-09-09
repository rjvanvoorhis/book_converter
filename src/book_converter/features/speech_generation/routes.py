import dataclasses
import json
import threading
import typing

from book_converter.features.speech_generation import dto, interfaces, use_cases
from book_converter.infrastructure.speech_generation import (
    artifact_store,
    audiobook_library,
    audit_service,
    in_memory_task_store,
    pending_edit_store,
    pronunciation_dict_store,
    review_store,
    transcript_resegmenter,
    voice_sample_service,
)
from book_converter.presentation import api

_UseCaseT = typing.TypeVar("_UseCaseT")

_DEFAULT_AUDIOBOOK_FOLDER = "data/audiobooks"
_DEFAULT_PRONUNCIATIONS_FOLDER = "pronunciation-dicts"
_DEFAULT_VOICE_SAMPLES_FOLDER = "data/voice_samples"


def build_routes(
    build_text_annotator: interfaces.TextAnnotatorFactory,
    tts_providers: dict[str, interfaces.TTSProvider],
    book_repositories_by_source: dict[str, interfaces.BookRepository],
    bundle_initializer: interfaces.BundleInitializer,
    dialogue_segmenter: interfaces.DialogueSegmenter,
    task_store: in_memory_task_store.InMemoryTaskStore,
    audio_cleaners: dict[str, interfaces.AudioCleaner],
) -> list[api.Route]:
    return [
        api.Route(
            rule="/audiobooks",
            method="POST",
            handler=_create_audiobook_handler(
                book_repositories_by_source,
                build_text_annotator,
                tts_providers,
                bundle_initializer,
                dialogue_segmenter,
                task_store,
            ),
        ),
        api.Route(
            rule="/audiobooks/tasks/{task_id}",
            handler=_get_task_handler(task_store),
        ),
        api.Route(
            rule="/audiobooks/tasks/{task_id}/status",
            method="PUT",
            handler=_set_task_status_handler(task_store),
        ),
        api.Route(
            rule="/audiobooks/sample",
            method="POST",
            handler=_create_sample_handler(
                book_repositories_by_source,
                build_text_annotator,
                tts_providers,
                task_store,
            ),
        ),
        api.Route(
            rule="/audiobooks/sample/{task_id}/audio",
            handler=_get_sample_audio_handler(task_store),
        ),
        api.Route(
            rule="/engines/{engine}/voices",
            handler=_list_voices_handler(tts_providers),
        ),
        api.Route(
            rule="/audiobooks/library",
            handler=_list_audiobooks_handler(),
        ),
        api.Route(
            rule="/audiobooks/transcript",
            handler=_get_transcript_handler(),
        ),
        api.Route(
            rule="/audiobooks/transcript",
            method="PUT",
            handler=_resegment_transcript_handler(),
        ),
        api.Route(
            rule="/audiobooks/audio",
            handler=_get_audio_handler(),
        ),
        api.Route(
            rule="/audiobooks/clip",
            handler=_get_clip_handler(),
        ),
        api.Route(
            rule="/audiobooks/review",
            handler=_get_review_handler(),
        ),
        api.Route(
            rule="/audiobooks/review",
            method="POST",
            handler=_set_review_handler(),
        ),
        api.Route(
            rule="/audiobooks/artifacts",
            handler=_get_artifacts_handler(),
        ),
        api.Route(
            rule="/audiobooks/artifact-scans",
            method="POST",
            handler=_detect_artifacts_handler(task_store),
        ),
        api.Route(
            rule="/audiobooks/edits",
            handler=_get_edits_handler(),
        ),
        api.Route(
            rule="/audiobooks/edits",
            method="DELETE",
            handler=_discard_edit_handler(),
        ),
        api.Route(
            rule="/audiobooks/edits/audio",
            handler=_get_edit_audio_handler(),
        ),
        api.Route(
            rule="/audiobooks/edits/regenerations",
            method="POST",
            handler=_stage_regeneration_handler(
                tts_providers, build_text_annotator, task_store
            ),
        ),
        api.Route(
            rule="/audiobooks/edits/cuts",
            method="POST",
            handler=_stage_cut_handler(),
        ),
        api.Route(
            rule="/audiobooks/edits/apply",
            method="POST",
            handler=_apply_edits_handler(task_store),
        ),
        api.Route(
            rule="/pronunciations",
            handler=_list_pronunciation_dicts_handler(),
        ),
        api.Route(
            rule="/pronunciations/dict",
            handler=_get_pronunciation_dict_handler(),
        ),
        api.Route(
            rule="/pronunciations/dict",
            method="POST",
            handler=_save_pronunciation_dict_handler(),
        ),
        api.Route(
            rule="/voice-samples/source",
            handler=_probe_voice_sample_source_handler(),
        ),
        api.Route(
            rule="/voice-samples/source/audio",
            handler=_get_voice_sample_source_audio_handler(),
        ),
        api.Route(
            rule="/voice-samples/source/clip",
            handler=_get_voice_sample_source_clip_handler(),
        ),
        api.Route(
            rule="/voice-samples/cleaners",
            handler=_list_audio_cleaners_handler(audio_cleaners),
        ),
        api.Route(
            rule="/voice-samples/library",
            handler=_list_voice_samples_handler(),
        ),
        api.Route(
            rule="/voice-samples/audio",
            handler=_get_voice_sample_audio_handler(),
        ),
        api.Route(
            rule="/voice-samples",
            method="POST",
            handler=_create_voice_sample_handler(audio_cleaners, task_store),
        ),
        api.Route(
            rule="/voice-samples",
            method="DELETE",
            handler=_delete_voice_sample_handler(),
        ),
    ]


@dataclasses.dataclass(frozen=True)
class _TaskProgressReporter:
    task_store: in_memory_task_store.InMemoryTaskStore
    task_id: str

    def report(self, message: str) -> None:
        self.task_store.report_progress(self.task_id, message)

    def is_cancelled(self) -> bool:
        return self.task_store.is_cancellation_requested(self.task_id)


def _create_audiobook_handler(
    book_repositories_by_source: dict[str, interfaces.BookRepository],
    build_text_annotator: interfaces.TextAnnotatorFactory,
    tts_providers: dict[str, interfaces.TTSProvider],
    bundle_initializer: interfaces.BundleInitializer,
    dialogue_segmenter: interfaces.DialogueSegmenter,
    task_store: in_memory_task_store.InMemoryTaskStore,
) -> api.Handler:
    def handle(request: api.Request) -> api.Response:
        payload = json.loads(request.content)

        resolved = _resolve_provider_and_source(
            payload, tts_providers, book_repositories_by_source
        )
        if isinstance(resolved, api.Response):
            return resolved
        tts_provider, book_repo = resolved

        # Build text annotator
        pronunciations_path = payload.get("pronunciations")
        add_pauses = payload.get("add_pauses", False)
        text_annotator = build_text_annotator(
            pronunciations_path=pronunciations_path, add_pauses=add_pauses
        )

        # Create use case
        use_case = use_cases.CreateAudiobookUseCase(
            book_repository=book_repo,
            tts_provider=tts_provider,
            bundle_initializer=bundle_initializer,
            text_annotator=text_annotator,
            dialogue_segmenter=dialogue_segmenter,
        )

        input_dto = dto.CreateAudiobookInput(
            identifier=payload["identifier"],
            name=payload["name"],
            audiobook_folder=payload.get("audiobook_folder", _DEFAULT_AUDIOBOOK_FOLDER),
            engine=payload.get("engine", "kokoro"),
            voice=payload.get("voice", "af_heart"),
            batch_size=payload.get("batch_size", 1),
            chapters_per_chunk=payload.get("chapters_per_chunk"),
            dialogue_voice=payload.get("dialogue_voice"),
        )

        # Generation can run for a very long time (many sequential TTS calls),
        # so it runs on a background thread and this handler returns
        # immediately with a task id the client polls for progress/results.
        task_id = task_store.create()
        progress = _TaskProgressReporter(task_store=task_store, task_id=task_id)

        def run() -> None:
            try:
                output = use_case.execute(input_dto, progress=progress)
                task_store.complete(task_id, dataclasses.asdict(output))
            except interfaces.TaskCancelled:
                task_store.mark_cancelled(task_id)
            except Exception as exc:  # noqa: BLE001 - reported via the task, not raised
                task_store.fail(task_id, str(exc))

        threading.Thread(target=run, daemon=True).start()
        return _json_response({"task_id": task_id}, status_code=202)

    return handle


def _resolve_provider_and_source(
    payload: dict,
    tts_providers: dict[str, interfaces.TTSProvider],
    book_repositories_by_source: dict[str, interfaces.BookRepository],
) -> tuple[interfaces.TTSProvider, interfaces.BookRepository] | api.Response:
    source = payload.get("source", "file")
    tts_provider_name = payload.get("tts_provider", "pocket-tts")

    if tts_provider_name not in tts_providers:
        available = ", ".join(sorted(tts_providers.keys()))
        error_msg = f"Unknown TTS provider '{tts_provider_name}'. Available: {available}"
        return _json_error_response(error_msg, 400)

    if source not in book_repositories_by_source:
        available = ", ".join(sorted(book_repositories_by_source.keys()))
        error_msg = f"Unknown source '{source}'. Available: {available}"
        return _json_error_response(error_msg, 400)

    return tts_providers[tts_provider_name], book_repositories_by_source[source]


def _create_sample_handler(
    book_repositories_by_source: dict[str, interfaces.BookRepository],
    build_text_annotator: interfaces.TextAnnotatorFactory,
    tts_providers: dict[str, interfaces.TTSProvider],
    task_store: in_memory_task_store.InMemoryTaskStore,
) -> api.Handler:
    def handle(request: api.Request) -> api.Response:
        payload = json.loads(request.content)

        resolved = _resolve_provider_and_source(
            payload, tts_providers, book_repositories_by_source
        )
        if isinstance(resolved, api.Response):
            return resolved
        tts_provider, book_repo = resolved

        pronunciations_path = payload.get("pronunciations")
        add_pauses = payload.get("add_pauses", False)
        text_annotator = build_text_annotator(
            pronunciations_path=pronunciations_path, add_pauses=add_pauses
        )

        use_case = use_cases.CreateSampleUseCase(
            book_repository=book_repo,
            tts_provider=tts_provider,
            text_annotator=text_annotator,
        )

        input_dto = dto.CreateSampleInput(
            identifier=payload["identifier"],
            source=payload.get("source", "file"),
            engine=payload.get("engine", "kokoro"),
            voice=payload.get("voice", "af_heart"),
            sentence_count=payload.get("sentence_count", 3),
        )

        # Fetching the book and running TTS both take real time, so this
        # follows the same task/poll pattern as full audiobook generation
        # rather than holding the request open.
        task_id = task_store.create()
        progress = _TaskProgressReporter(task_store=task_store, task_id=task_id)

        def run() -> None:
            try:
                speech = use_case.execute(input_dto, progress=progress)
                audio_bytes = speech.data.read()
                content_type = _sniff_audio_content_type(audio_bytes)
                task_store.store_blob(task_id, audio_bytes, content_type)
                task_store.complete(
                    task_id, {"content_type": content_type, "duration": speech.duration}
                )
            except interfaces.TaskCancelled:
                task_store.mark_cancelled(task_id)
            except Exception as exc:  # noqa: BLE001 - reported via the task, not raised
                task_store.fail(task_id, str(exc))

        threading.Thread(target=run, daemon=True).start()
        return _json_response({"task_id": task_id}, status_code=202)

    return handle


def _get_sample_audio_handler(
    task_store: in_memory_task_store.InMemoryTaskStore,
) -> api.Handler:
    def handle(request: api.Request) -> api.Response:
        (task_id,) = request.params
        blob = task_store.get_blob(task_id)
        if blob is None:
            return _json_error_response(f"No sample audio for task '{task_id}'", 404)
        data, content_type = blob
        return api.Response(
            status_code=200, headers={"Content-Type": content_type}, body=data
        )

    return handle


def _sniff_audio_content_type(data: bytes) -> str:
    if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return "audio/wav"
    if data[:3] == b"ID3" or (len(data) > 1 and data[0] == 0xFF and (data[1] & 0xE0) == 0xE0):
        return "audio/mpeg"
    if len(data) >= 8 and data[4:8] == b"ftyp":
        return "audio/mp4"
    return "application/octet-stream"


def _list_audiobooks_handler() -> api.Handler:
    def handle(request: api.Request) -> api.Response:
        folder = _query_value(request, "audiobook_folder", _DEFAULT_AUDIOBOOK_FOLDER)
        return _json_response({"audiobooks": audiobook_library.list_audiobooks(folder)})

    return handle


def _get_transcript_handler() -> api.Handler:
    def handle(request: api.Request) -> api.Response:
        path = _query_value(request, "path", None)
        if not path:
            return _json_error_response("Missing 'path' query parameter", 400)
        try:
            return _json_response(audiobook_library.read_transcript(path))
        except FileNotFoundError as exc:
            return _json_error_response(str(exc), 404)

    return handle


def _resegment_transcript_handler() -> api.Handler:
    def handle(request: api.Request) -> api.Response:
        payload = json.loads(request.content)
        path = payload.get("path")
        if not path:
            return _json_error_response("Missing 'path'", 400)

        # Pure in-memory text processing plus one JSON write - fast even for
        # a multi-thousand-segment book, so unlike detect/regenerate this
        # doesn't need the async task/poll pattern.
        try:
            stats = transcript_resegmenter.resegment_long_segments(path)
        except FileNotFoundError as exc:
            return _json_error_response(str(exc), 404)
        return _json_response(stats)

    return handle


def _get_audio_handler() -> api.Handler:
    def handle(request: api.Request) -> api.Response:
        path = _query_value(request, "path", None)
        if not path:
            return _json_error_response("Missing 'path' query parameter", 400)
        try:
            data = audiobook_library.read_audio_bytes(path)
        except FileNotFoundError as exc:
            return _json_error_response(str(exc), 404)
        return api.Response(
            status_code=200, headers={"Content-Type": "audio/mp4"}, body=data
        )

    return handle


def _get_clip_handler() -> api.Handler:
    def handle(request: api.Request) -> api.Response:
        path = _query_value(request, "path", None)
        start = _query_value(request, "start", None)
        end = _query_value(request, "end", None)
        if not path or start is None or end is None:
            return _json_error_response("Required query params: path, start, end", 400)
        try:
            data = audiobook_library.read_clip_bytes(path, float(start), float(end))
        except FileNotFoundError as exc:
            return _json_error_response(str(exc), 404)
        return api.Response(
            status_code=200, headers={"Content-Type": "audio/wav"}, body=data
        )

    return handle


def _get_review_handler() -> api.Handler:
    def handle(request: api.Request) -> api.Response:
        path = _query_value(request, "path", None)
        if not path:
            return _json_error_response("Missing 'path' query parameter", 400)
        return _json_response(review_store.read_review(path))

    return handle


def _set_review_handler() -> api.Handler:
    def handle(request: api.Request) -> api.Response:
        payload = json.loads(request.content)
        path = payload.get("path")
        segment_index = payload.get("segment_index")
        status = payload.get("status")
        if not path or segment_index is None or not status:
            return _json_error_response(
                "Required fields: path, segment_index, status", 400
            )
        review = review_store.set_segment_status(
            path, int(segment_index), status, payload.get("note")
        )
        return _json_response(review)

    return handle


def _get_artifacts_handler() -> api.Handler:
    def handle(request: api.Request) -> api.Response:
        path = _query_value(request, "path", None)
        if not path:
            return _json_error_response("Missing 'path' query parameter", 400)
        return _json_response({"cuts": artifact_store.read_cuts(path)})

    return handle


def _detect_artifacts_handler(
    task_store: in_memory_task_store.InMemoryTaskStore,
) -> api.Handler:
    def handle(request: api.Request) -> api.Response:
        payload = json.loads(request.content)
        path = payload.get("path")
        if not path:
            return _json_error_response("Missing 'path'", 400)

        # Decoding and scanning a full audiobook can take a while, so this
        # follows the same task/poll pattern as generation.
        task_id = task_store.create()
        progress = _TaskProgressReporter(task_store=task_store, task_id=task_id)

        def run() -> None:
            try:
                cuts = audit_service.detect_artifacts(path, progress=progress)
                artifact_store.write_cuts(path, cuts)
                task_store.complete(task_id, {"cuts": cuts})
            except interfaces.TaskCancelled:
                task_store.mark_cancelled(task_id)
            except Exception as exc:  # noqa: BLE001 - reported via the task, not raised
                task_store.fail(task_id, str(exc))

        threading.Thread(target=run, daemon=True).start()
        return _json_response({"task_id": task_id}, status_code=202)

    return handle


def _get_edits_handler() -> api.Handler:
    def handle(request: api.Request) -> api.Response:
        path = _query_value(request, "path", None)
        if not path:
            return _json_error_response("Missing 'path' query parameter", 400)
        return _json_response({"edits": pending_edit_store.list_edits(path)})

    return handle


def _discard_edit_handler() -> api.Handler:
    def handle(request: api.Request) -> api.Response:
        path = _query_value(request, "path", None)
        index = _query_value(request, "segment_index", None)
        if not path or index is None:
            return _json_error_response("Required query params: path, segment_index", 400)
        return _json_response({"edits": pending_edit_store.discard_edit(path, int(index))})

    return handle


def _get_edit_audio_handler() -> api.Handler:
    def handle(request: api.Request) -> api.Response:
        path = _query_value(request, "path", None)
        index = _query_value(request, "segment_index", None)
        if not path or index is None:
            return _json_error_response("Required query params: path, segment_index", 400)
        audio_path = pending_edit_store.edit_audio_path(path, int(index))
        if not audio_path.is_file():
            return _json_error_response(f"No staged audio for segment {index}", 404)
        data = audio_path.read_bytes()
        return api.Response(
            status_code=200,
            headers={"Content-Type": _sniff_audio_content_type(data)},
            body=data,
        )

    return handle


def _stage_regeneration_handler(
    tts_providers: dict[str, interfaces.TTSProvider],
    build_text_annotator: interfaces.TextAnnotatorFactory,
    task_store: in_memory_task_store.InMemoryTaskStore,
) -> api.Handler:
    def handle(request: api.Request) -> api.Response:
        payload = json.loads(request.content)

        tts_provider_name = payload.get("tts_provider", "pocket-tts")
        if tts_provider_name not in tts_providers:
            available = ", ".join(sorted(tts_providers.keys()))
            error_msg = (
                f"Unknown TTS provider '{tts_provider_name}'. Available: {available}"
            )
            return _json_error_response(error_msg, 400)
        tts_provider = tts_providers[tts_provider_name]

        path = payload.get("path")
        index = payload.get("segment_index")
        text = payload.get("text")
        if not path or index is None or not text:
            return _json_error_response("Required fields: path, segment_index, text", 400)

        try:
            transcript = audiobook_library.read_transcript(path)
        except FileNotFoundError as exc:
            return _json_error_response(str(exc), 404)
        segments = transcript["segments"]
        if not 0 <= int(index) < len(segments):
            return _json_error_response(f"No segment at index {index}", 400)
        speaker = segments[int(index)]["speaker"]

        text_annotator = build_text_annotator(
            pronunciations_path=payload.get("pronunciations"),
            add_pauses=payload.get("add_pauses", False),
        )

        # This *is* the real take, not a disposable preview, so it runs
        # through the task/poll pattern like every other TTS call - but the
        # result is persisted to disk (pending_edit_store), not a transient
        # blob, so the user can listen to it, walk away, and come back
        # later without regenerating again.
        task_id = task_store.create()

        def run() -> None:
            try:
                speech = audit_service.generate_segment_audio(
                    text,
                    speaker,
                    tts_provider,
                    payload.get("engine", "kokoro"),
                    payload.get("voice", "af_heart"),
                    payload.get("dialogue_voice"),
                    text_annotator,
                )
                audio_bytes = speech.data.read()
                edits = pending_edit_store.stage_regeneration(
                    path, int(index), text, audio_bytes
                )
                task_store.complete(task_id, {"segment_index": int(index), "edits": edits})
            except Exception as exc:  # noqa: BLE001 - reported via the task, not raised
                task_store.fail(task_id, str(exc))

        threading.Thread(target=run, daemon=True).start()
        return _json_response({"task_id": task_id}, status_code=202)

    return handle


def _stage_cut_handler() -> api.Handler:
    def handle(request: api.Request) -> api.Response:
        payload = json.loads(request.content)
        path = payload.get("path")
        index = payload.get("segment_index")
        cut_start = payload.get("cut_start_seconds")
        cut_end = payload.get("cut_end_seconds")
        if not path or index is None or cut_start is None or cut_end is None:
            return _json_error_response(
                "Required fields: path, segment_index, cut_start_seconds, cut_end_seconds",
                400,
            )

        # Staging a cut is just a manifest write - no ffmpeg work happens
        # until the edit is actually applied - so unlike every TTS-backed
        # action in this API, this is a plain synchronous request.
        try:
            audit_service.validate_cut_range(
                path, int(index), float(cut_start), float(cut_end)
            )
        except FileNotFoundError as exc:
            return _json_error_response(str(exc), 404)
        except ValueError as exc:
            return _json_error_response(str(exc), 400)

        edits = pending_edit_store.stage_cut(
            path, int(index), float(cut_start), float(cut_end)
        )
        return _json_response({"edits": edits})

    return handle


def _apply_edits_handler(
    task_store: in_memory_task_store.InMemoryTaskStore,
) -> api.Handler:
    def handle(request: api.Request) -> api.Response:
        payload = json.loads(request.content)
        path = payload.get("path")
        if not path:
            return _json_error_response("Missing 'path'", 400)

        edited_indices = [int(key) for key in pending_edit_store.list_edits(path)]
        if not edited_indices:
            return _json_error_response("No pending edits to apply", 400)

        task_id = task_store.create()
        progress = _TaskProgressReporter(task_store=task_store, task_id=task_id)

        def run() -> None:
            try:
                destination = audit_service.apply_pending_edits(path, progress=progress)
                for index in edited_indices:
                    review_store.set_segment_status(path, index, "fixed")
                pending_edit_store.clear_edits(path)
                artifact_store.clear_cuts(path)
                task_store.complete(
                    task_id,
                    {"destination": destination, "segments_applied": len(edited_indices)},
                )
            except interfaces.TaskCancelled:
                task_store.mark_cancelled(task_id)
            except Exception as exc:  # noqa: BLE001 - reported via the task, not raised
                task_store.fail(task_id, str(exc))

        threading.Thread(target=run, daemon=True).start()
        return _json_response({"task_id": task_id}, status_code=202)

    return handle


def _list_pronunciation_dicts_handler() -> api.Handler:
    def handle(request: api.Request) -> api.Response:
        folder = _query_value(request, "folder", _DEFAULT_PRONUNCIATIONS_FOLDER)
        return _json_response(
            {"dictionaries": pronunciation_dict_store.list_dicts(folder)}
        )

    return handle


def _get_pronunciation_dict_handler() -> api.Handler:
    def handle(request: api.Request) -> api.Response:
        path = _query_value(request, "path", None)
        if not path:
            return _json_error_response("Missing 'path' query parameter", 400)
        try:
            return _json_response({"entries": pronunciation_dict_store.read_dict(path)})
        except FileNotFoundError as exc:
            return _json_error_response(str(exc), 404)

    return handle


def _save_pronunciation_dict_handler() -> api.Handler:
    def handle(request: api.Request) -> api.Response:
        payload = json.loads(request.content)
        path = payload.get("path")
        entries = payload.get("entries")
        if not path or entries is None:
            return _json_error_response("Required fields: path, entries", 400)
        pronunciation_dict_store.write_dict(path, entries)
        return _json_response({"path": path, "entries": entries})

    return handle


def _probe_voice_sample_source_handler() -> api.Handler:
    def handle(request: api.Request) -> api.Response:
        path = _query_value(request, "path", None)
        if not path:
            return _json_error_response("Missing 'path' query parameter", 400)
        try:
            duration = voice_sample_service.probe_source_duration(path)
        except FileNotFoundError as exc:
            return _json_error_response(str(exc), 404)
        return _json_response({"path": path, "duration_seconds": duration})

    return handle


def _get_voice_sample_source_audio_handler() -> api.Handler:
    def handle(request: api.Request) -> api.Response:
        path = _query_value(request, "path", None)
        if not path:
            return _json_error_response("Missing 'path' query parameter", 400)
        try:
            data = voice_sample_service.read_source_bytes(path)
        except FileNotFoundError as exc:
            return _json_error_response(str(exc), 404)
        return api.Response(
            status_code=200,
            headers={"Content-Type": _sniff_audio_content_type(data)},
            body=data,
        )

    return handle


def _get_voice_sample_source_clip_handler() -> api.Handler:
    def handle(request: api.Request) -> api.Response:
        path = _query_value(request, "path", None)
        start = _query_value(request, "start", None)
        end = _query_value(request, "end", None)
        if not path or start is None or end is None:
            return _json_error_response("Required query params: path, start, end", 400)
        try:
            data = voice_sample_service.read_source_clip_bytes(
                path, float(start), float(end)
            )
        except FileNotFoundError as exc:
            return _json_error_response(str(exc), 404)
        return api.Response(
            status_code=200, headers={"Content-Type": "audio/wav"}, body=data
        )

    return handle


def _list_audio_cleaners_handler(
    audio_cleaners: dict[str, interfaces.AudioCleaner],
) -> api.Handler:
    def handle(request: api.Request) -> api.Response:
        cleaners = [
            {"id": cleaner.id, "description": cleaner.description}
            for cleaner in audio_cleaners.values()
        ]
        return _json_response({"cleaners": cleaners})

    return handle


def _list_voice_samples_handler() -> api.Handler:
    def handle(request: api.Request) -> api.Response:
        folder = _query_value(request, "folder", _DEFAULT_VOICE_SAMPLES_FOLDER)
        return _json_response({"samples": voice_sample_service.list_samples(folder)})

    return handle


def _get_voice_sample_audio_handler() -> api.Handler:
    def handle(request: api.Request) -> api.Response:
        path = _query_value(request, "path", None)
        if not path:
            return _json_error_response("Missing 'path' query parameter", 400)
        try:
            data = voice_sample_service.read_sample_bytes(path)
        except FileNotFoundError as exc:
            return _json_error_response(str(exc), 404)
        return api.Response(
            status_code=200, headers={"Content-Type": "audio/wav"}, body=data
        )

    return handle


def _create_voice_sample_handler(
    audio_cleaners: dict[str, interfaces.AudioCleaner],
    task_store: in_memory_task_store.InMemoryTaskStore,
) -> api.Handler:
    def handle(request: api.Request) -> api.Response:
        payload = json.loads(request.content)
        source_path = payload.get("source_path")
        start_seconds = payload.get("start_seconds")
        end_seconds = payload.get("end_seconds")
        name = payload.get("name")
        if not source_path or start_seconds is None or end_seconds is None or not name:
            return _json_error_response(
                "Required fields: source_path, start_seconds, end_seconds, name", 400
            )

        cleaner = None
        if payload.get("clean", True):
            cleaner_id = payload.get("cleaner", "ffmpeg")
            if cleaner_id not in audio_cleaners:
                available = ", ".join(sorted(audio_cleaners)) or "(none registered)"
                return _json_error_response(
                    f"Unknown cleaner '{cleaner_id}'. Available: {available}", 400
                )
            cleaner = audio_cleaners[cleaner_id]

        # A model-based cleaner can take real time (loading a neural net and
        # running a forward pass, not just an ffmpeg filter - tens of
        # seconds is normal on CPU), so unlike the ffmpeg-only path this
        # used to be, it follows the task/poll pattern like every other
        # TTS-adjacent action here rather than holding the request open.
        task_id = task_store.create()
        # create_sample doesn't report incremental progress (there's nothing
        # to break into steps a user would care about), but a model-based
        # cleaner can take the better part of a minute - report once up
        # front so the client shows something other than "Queued" for that
        # whole stretch.
        cleaner_label = f" with {cleaner.id}" if cleaner is not None else ""
        task_store.report_progress(task_id, f"Cleaning{cleaner_label}...")

        def run() -> None:
            try:
                sample = voice_sample_service.create_sample(
                    source_path,
                    float(start_seconds),
                    float(end_seconds),
                    payload.get("output_folder", _DEFAULT_VOICE_SAMPLES_FOLDER),
                    name,
                    cleaner=cleaner,
                    trim_silence=payload.get("trim_silence", True),
                    normalize_loudness=payload.get("normalize_loudness", True),
                )
                task_store.complete(task_id, sample)
            except (FileNotFoundError, ValueError, RuntimeError) as exc:
                task_store.fail(task_id, str(exc))

        threading.Thread(target=run, daemon=True).start()
        return _json_response({"task_id": task_id}, status_code=202)

    return handle


def _delete_voice_sample_handler() -> api.Handler:
    def handle(request: api.Request) -> api.Response:
        path = _query_value(request, "path", None)
        if not path:
            return _json_error_response("Missing 'path' query parameter", 400)
        voice_sample_service.delete_sample(path)
        return _json_response({"path": path})

    return handle


def _query_value(request: api.Request, key: str, default: str | None) -> str | None:
    values = request.query.get(key)
    return values[0] if values else default


def _get_task_handler(
    task_store: in_memory_task_store.InMemoryTaskStore,
) -> api.Handler:
    def handle(request: api.Request) -> api.Response:
        (task_id,) = request.params
        task = task_store.get(task_id)
        if task is None:
            return _json_error_response(f"Unknown task '{task_id}'", 404)
        return _json_response(task)

    return handle


def _set_task_status_handler(
    task_store: in_memory_task_store.InMemoryTaskStore,
) -> api.Handler:
    def handle(request: api.Request) -> api.Response:
        (task_id,) = request.params
        task = task_store.get(task_id)
        if task is None:
            return _json_error_response(f"Unknown task '{task_id}'", 404)

        payload = json.loads(request.content) if request.content else {}
        status = payload.get("status")
        # "cancelled" is the only status a client can put a task into -
        # every other status is a side effect of the task's own execution,
        # not something set from outside.
        if status != "cancelled":
            return _json_error_response(
                "Required field 'status' must be 'cancelled'", 400
            )
        if not task_store.request_cancellation(task_id):
            return _json_error_response(
                f"Task '{task_id}' already finished ({task.status})", 409
            )
        return _json_response(task_store.get(task_id))

    return handle


def _list_voices_handler(
    tts_providers: dict[str, interfaces.TTSProvider],
) -> api.Handler:
    def handle(request: api.Request) -> api.Response:
        (engine,) = request.params

        # Extract tts_provider from query parameters (query is MultiDict[str] = dict[str, list[str]])
        tts_provider_name = "pocket-tts"  # default
        if request.query.get("tts_provider"):
            tts_provider_name = request.query["tts_provider"][0]

        if tts_provider_name not in tts_providers:
            available = ", ".join(sorted(tts_providers.keys()))
            error_msg = (
                f"Unknown TTS provider '{tts_provider_name}'. Available: {available}"
            )
            return _json_error_response(error_msg, 400)

        tts_provider = tts_providers[tts_provider_name]
        output = use_cases.ListVoiceProfilesUseCase(tts_provider=tts_provider).execute(
            dto.ListVoiceProfilesInput(engine=engine)
        )
        return _json_response(output)

    return handle


def _resolve(use_cases_by_source: dict[str, _UseCaseT], source: str) -> _UseCaseT:
    try:
        return use_cases_by_source[source]
    except KeyError:
        available = ", ".join(sorted(use_cases_by_source))
        raise ValueError(f"Unknown source '{source}'. Available: {available}") from None


def _json_response(output: typing.Any, status_code: int = 200) -> api.Response:
    payload = dataclasses.asdict(output) if dataclasses.is_dataclass(output) else output
    body = json.dumps(payload).encode("utf-8")
    return api.Response(
        status_code=status_code,
        headers={"Content-Type": "application/json"},
        body=body,
    )


def _json_error_response(message: str, status_code: int = 400) -> api.Response:
    body = json.dumps({"error": message}).encode("utf-8")
    return api.Response(
        status_code=status_code,
        headers={"Content-Type": "application/json"},
        body=body,
    )
