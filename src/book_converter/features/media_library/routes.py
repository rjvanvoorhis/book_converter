import dataclasses
import json
import typing

from book_converter.features.media_library import dto, interfaces, use_cases
from book_converter.features.organization import interfaces as organization_interfaces
from book_converter.infrastructure.speech_generation import audiobook_library
from book_converter.presentation import api

_DEFAULT_AUDIOBOOK_FOLDER = "data/audiobooks"


def build_routes(
    media_library: interfaces.MediaLibrary,
    group_store: organization_interfaces.GroupStore,
) -> list[api.Route]:
    return [
        api.Route(
            rule="/media-library/libraries",
            handler=_list_libraries_handler(media_library),
        ),
        api.Route(
            rule="/media-library/libraries/{library_id}/health",
            handler=_health_check_library_handler(media_library),
        ),
        api.Route(
            rule="/media-library/libraries/{library_id}/items",
            handler=_list_items_handler(media_library),
        ),
        api.Route(
            rule="/media-library/import",
            method="POST",
            handler=_import_handler(media_library, group_store),
        ),
        api.Route(
            rule="/media-library/libraries/{library_id}/folders/{folder_id}/health",
            handler=_health_check_handler(media_library),
        ),
        api.Route(
            rule="/media-library/libraries/{library_id}/folders/{folder_id}/register",
            method="POST",
            handler=_register_folder_handler(media_library),
        ),
        api.Route(
            rule="/media-library/libraries/{library_id}/unlinked-series",
            handler=_unlinked_series_handler(media_library, group_store),
        ),
        api.Route(
            rule="/media-library/groups/{group_id}/status",
            handler=_group_status_handler(media_library, group_store),
        ),
    ]


def _list_libraries_handler(media_library: interfaces.MediaLibrary) -> api.Handler:
    def handle(request: api.Request) -> api.Response:
        output = use_cases.ListLibrariesUseCase(media_library=media_library).execute()
        return _json_response(output)

    return handle


def _list_items_handler(media_library: interfaces.MediaLibrary) -> api.Handler:
    def handle(request: api.Request) -> api.Response:
        (library_id,) = request.params
        output = use_cases.ListItemsUseCase(media_library=media_library).execute(
            library_id
        )
        return _json_response(output)

    return handle


def _import_handler(
    media_library: interfaces.MediaLibrary,
    group_store: organization_interfaces.GroupStore,
) -> api.Handler:
    def handle(request: api.Request) -> api.Response:
        payload = json.loads(request.content)
        group_id = payload.get("group_id")
        source_path = payload.get("source_path")
        title = payload.get("title")
        if not group_id or not source_path or not title:
            return _json_error_response(
                "Required fields: group_id, source_path, title", 400
            )

        input_dto = dto.ImportWorkInput(
            group_id=group_id,
            source_path=source_path,
            title=title,
            author=payload.get("author"),
        )
        use_case = use_cases.ImportWorkUseCase(
            media_library=media_library, group_store=group_store
        )
        try:
            output = use_case.execute(input_dto)
        except interfaces.LibraryNotFound as exc:
            return _json_error_response(str(exc), 404)
        except organization_interfaces.GroupNotFound as exc:
            return _json_error_response(f"Unknown group '{exc}'", 404)
        except FileNotFoundError as exc:
            return _json_error_response(str(exc), 404)
        except ValueError as exc:
            return _json_error_response(str(exc), 400)
        return _json_response(output)

    return handle


def _health_check_library_handler(
    media_library: interfaces.MediaLibrary,
) -> api.Handler:
    def handle(request: api.Request) -> api.Response:
        (library_id,) = request.params
        try:
            output = use_cases.HealthCheckLibraryUseCase(
                media_library=media_library
            ).execute(library_id)
        except interfaces.LibraryNotFound as exc:
            return _json_error_response(str(exc), 404)
        return _json_response(output)

    return handle


def _health_check_handler(media_library: interfaces.MediaLibrary) -> api.Handler:
    def handle(request: api.Request) -> api.Response:
        library_id, folder_id = request.params
        try:
            output = use_cases.HealthCheckFolderUseCase(
                media_library=media_library
            ).execute(library_id, folder_id)
        except interfaces.LibraryNotFound as exc:
            return _json_error_response(str(exc), 404)
        return _json_response(output)

    return handle


def _register_folder_handler(media_library: interfaces.MediaLibrary) -> api.Handler:
    def handle(request: api.Request) -> api.Response:
        library_id, folder_id = request.params
        try:
            output = use_cases.RegisterFolderUseCase(
                media_library=media_library
            ).execute(library_id, folder_id)
        except interfaces.LibraryNotFound as exc:
            return _json_error_response(str(exc), 404)
        return _json_response(output)

    return handle


def _unlinked_series_handler(
    media_library: interfaces.MediaLibrary,
    group_store: organization_interfaces.GroupStore,
) -> api.Handler:
    def handle(request: api.Request) -> api.Response:
        (library_id,) = request.params
        try:
            output = use_cases.DiscoverUnlinkedSeriesUseCase(
                media_library=media_library, group_store=group_store
            ).execute(library_id)
        except interfaces.LibraryNotFound as exc:
            return _json_error_response(str(exc), 404)
        return _json_response(output)

    return handle


def _group_status_handler(
    media_library: interfaces.MediaLibrary,
    group_store: organization_interfaces.GroupStore,
) -> api.Handler:
    def handle(request: api.Request) -> api.Response:
        (group_id,) = request.params
        folder = _query_value(request, "audiobook_folder", _DEFAULT_AUDIOBOOK_FOLDER)
        title_by_path = {
            item["path"]: item["title"]
            for item in audiobook_library.list_audiobooks(folder)
        }
        try:
            output = use_cases.GroupStatusUseCase(
                media_library=media_library, group_store=group_store
            ).execute(group_id, title_by_path)
        except organization_interfaces.GroupNotFound as exc:
            return _json_error_response(f"Unknown group '{exc}'", 404)
        except interfaces.LibraryNotFound as exc:
            return _json_error_response(str(exc), 404)
        return _json_response(output)

    return handle


def _query_value(request: api.Request, key: str, default: str | None) -> str | None:
    values = request.query.get(key)
    return values[0] if values else default


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
