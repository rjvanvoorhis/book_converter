import dataclasses
import json
import typing

from book_converter.features.organization import interfaces, use_cases
from book_converter.infrastructure.speech_generation import audiobook_library
from book_converter.presentation import api

_DEFAULT_AUDIOBOOK_FOLDER = "data/audiobooks"


def build_routes(store: interfaces.GroupStore) -> list[api.Route]:
    return [
        api.Route(rule="/organization/groups", handler=_list_groups_handler(store)),
        api.Route(
            rule="/organization/groups",
            method="POST",
            handler=_create_group_handler(store),
        ),
        api.Route(
            rule="/organization/groups/{group_id}",
            method="PUT",
            handler=_rename_group_handler(store),
        ),
        api.Route(
            rule="/organization/groups/{group_id}",
            method="DELETE",
            handler=_delete_group_handler(store),
        ),
        api.Route(
            rule="/organization/groups/{group_id}/members",
            method="POST",
            handler=_add_member_handler(store),
        ),
        api.Route(
            rule="/organization/groups/{group_id}/members",
            method="DELETE",
            handler=_remove_member_handler(store),
        ),
        api.Route(
            rule="/organization/groups/{group_id}/reorder",
            method="POST",
            handler=_reorder_members_handler(store),
        ),
        api.Route(
            rule="/organization/unassigned",
            handler=_list_unassigned_handler(store),
        ),
    ]


def _list_groups_handler(store: interfaces.GroupStore) -> api.Handler:
    def handle(request: api.Request) -> api.Response:
        output = use_cases.ListGroupsUseCase(store=store).execute()
        return _json_response(output)

    return handle


def _create_group_handler(store: interfaces.GroupStore) -> api.Handler:
    def handle(request: api.Request) -> api.Response:
        payload = json.loads(request.content)
        name = payload.get("name")
        library_id = payload.get("library_id")
        folder_id = payload.get("folder_id")
        if not name or not library_id or not folder_id:
            return _json_error_response(
                "Required fields: name, library_id, folder_id", 400
            )
        group = use_cases.CreateGroupUseCase(store=store).execute(
            name=name,
            library_id=library_id,
            folder_id=folder_id,
            is_standalone=bool(payload.get("is_standalone", False)),
        )
        return _json_response(group, status_code=201)

    return handle


def _rename_group_handler(store: interfaces.GroupStore) -> api.Handler:
    def handle(request: api.Request) -> api.Response:
        (group_id,) = request.params
        payload = json.loads(request.content)
        name = payload.get("name")
        if not name:
            return _json_error_response("Missing 'name'", 400)
        try:
            group = use_cases.RenameGroupUseCase(store=store).execute(group_id, name)
        except interfaces.GroupNotFound:
            return _json_error_response(f"Unknown group '{group_id}'", 404)
        return _json_response(group)

    return handle


def _delete_group_handler(store: interfaces.GroupStore) -> api.Handler:
    def handle(request: api.Request) -> api.Response:
        (group_id,) = request.params
        try:
            use_cases.DeleteGroupUseCase(store=store).execute(group_id)
        except interfaces.GroupNotFound:
            return _json_error_response(f"Unknown group '{group_id}'", 404)
        return _json_response({"id": group_id})

    return handle


def _add_member_handler(store: interfaces.GroupStore) -> api.Handler:
    def handle(request: api.Request) -> api.Response:
        (group_id,) = request.params
        payload = json.loads(request.content)
        path = payload.get("path")
        if not path:
            return _json_error_response("Required field: path", 400)
        sequence = payload.get("sequence")
        try:
            group = use_cases.AddMemberUseCase(store=store).execute(
                group_id, path, int(sequence) if sequence is not None else None
            )
        except interfaces.GroupNotFound:
            return _json_error_response(f"Unknown group '{group_id}'", 404)
        return _json_response(group)

    return handle


def _remove_member_handler(store: interfaces.GroupStore) -> api.Handler:
    def handle(request: api.Request) -> api.Response:
        (group_id,) = request.params
        path = _query_value(request, "path", None)
        if not path:
            return _json_error_response("Missing 'path' query parameter", 400)
        try:
            group = use_cases.RemoveMemberUseCase(store=store).execute(group_id, path)
        except interfaces.GroupNotFound:
            return _json_error_response(f"Unknown group '{group_id}'", 404)
        return _json_response(group)

    return handle


def _reorder_members_handler(store: interfaces.GroupStore) -> api.Handler:
    def handle(request: api.Request) -> api.Response:
        (group_id,) = request.params
        payload = json.loads(request.content)
        paths = payload.get("paths")
        if not isinstance(paths, list) or not paths:
            return _json_error_response("Required field: paths (non-empty list)", 400)
        try:
            group = use_cases.ReorderMembersUseCase(store=store).execute(
                group_id, paths
            )
        except interfaces.GroupNotFound:
            return _json_error_response(f"Unknown group '{group_id}'", 404)
        except ValueError as exc:
            return _json_error_response(str(exc), 400)
        return _json_response(group)

    return handle


def _list_unassigned_handler(store: interfaces.GroupStore) -> api.Handler:
    def handle(request: api.Request) -> api.Response:
        folder = _query_value(request, "audiobook_folder", _DEFAULT_AUDIOBOOK_FOLDER)
        all_paths = [item["path"] for item in audiobook_library.list_audiobooks(folder)]
        output = use_cases.ListUnassignedUseCase(store=store).execute(all_paths)
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
