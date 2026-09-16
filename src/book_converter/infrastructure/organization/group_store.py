import dataclasses
import json
import pathlib
import re
import threading

from book_converter.features.organization import entities, interfaces

_lock = threading.Lock()

_SLUG_UNSAFE_CHARS = re.compile(r"[^a-z0-9]+")


@dataclasses.dataclass
class JsonGroupStore:
    """Groups works into series, persisted as one JSON file - same
    read-modify-write-under-lock shape as review_store/
    pronunciation_dict_store, just keyed by group id instead of by audiobook
    path."""

    path: pathlib.Path = pathlib.Path("data/organization/groups.json")

    def list_groups(self) -> list[entities.Group]:
        return list(self._read().values())

    def get_group(self, group_id: str) -> entities.Group | None:
        return self._read().get(group_id)

    def find_group_for_member(self, path: str) -> entities.Group | None:
        for group in self._read().values():
            if any(member.path == path for member in group.members):
                return group
        return None

    def create_group(
        self,
        name: str,
        library_id: str,
        folder_id: str,
        is_standalone: bool = False,
        source: entities.GroupSource | None = None,
    ) -> entities.Group:
        with _lock:
            groups = self._read_locked()
            group_id = self._unique_id(groups, name)
            group = entities.Group(
                id=group_id,
                name=name,
                library_id=library_id,
                folder_id=folder_id,
                is_standalone=is_standalone,
                source=source,
                members=[],
            )
            groups[group_id] = group
            self._write_locked(groups)
            return group

    def rename_group(self, group_id: str, name: str) -> entities.Group:
        with _lock:
            groups = self._read_locked()
            group = self._require(groups, group_id)
            group.name = name
            self._write_locked(groups)
            return group

    def delete_group(self, group_id: str) -> None:
        with _lock:
            groups = self._read_locked()
            self._require(groups, group_id)
            del groups[group_id]
            self._write_locked(groups)

    def add_member(
        self, group_id: str, path: str, sequence: int | None
    ) -> entities.Group:
        with _lock:
            groups = self._read_locked()
            group = self._require(groups, group_id)
            group.members = [member for member in group.members if member.path != path]
            group.members.append(entities.GroupMember(path=path, sequence=sequence))
            group.members.sort(key=_sort_key)
            self._write_locked(groups)
            return group

    def remove_member(self, group_id: str, path: str) -> entities.Group:
        with _lock:
            groups = self._read_locked()
            group = self._require(groups, group_id)
            group.members = [member for member in group.members if member.path != path]
            self._write_locked(groups)
            return group

    def reorder_members(
        self, group_id: str, ordered_paths: list[str]
    ) -> entities.Group:
        with _lock:
            groups = self._read_locked()
            group = self._require(groups, group_id)
            members_by_path = {member.path: member for member in group.members}
            missing = [path for path in ordered_paths if path not in members_by_path]
            if missing:
                raise ValueError(
                    f"'{missing[0]}' is not a member of group '{group_id}'"
                )
            sequence_by_path = {
                path: index + 1 for index, path in enumerate(ordered_paths)
            }
            group.members = [
                dataclasses.replace(
                    member, sequence=sequence_by_path.get(member.path, member.sequence)
                )
                for member in group.members
            ]
            group.members.sort(key=_sort_key)
            self._write_locked(groups)
            return group

    def _require(
        self, groups: dict[str, entities.Group], group_id: str
    ) -> entities.Group:
        group = groups.get(group_id)
        if group is None:
            raise interfaces.GroupNotFound(group_id)
        return group

    def _unique_id(self, groups: dict[str, entities.Group], name: str) -> str:
        base = _SLUG_UNSAFE_CHARS.sub("-", name.strip().lower()).strip("-") or "group"
        candidate = base
        suffix = 2
        while candidate in groups:
            candidate = f"{base}-{suffix}"
            suffix += 1
        return candidate

    def _read(self) -> dict[str, entities.Group]:
        with _lock:
            return self._read_locked()

    def _read_locked(self) -> dict[str, entities.Group]:
        if not self.path.is_file():
            return {}
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        return {
            group_id: _group_from_dict(group_id, data)
            for group_id, data in raw.get("groups", {}).items()
        }

    def _write_locked(self, groups: dict[str, entities.Group]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "groups": {
                group_id: _group_to_dict(group) for group_id, group in groups.items()
            }
        }
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _sort_key(member: entities.GroupMember) -> tuple[int, int]:
    # Unsequenced members (None) sort after every numbered one.
    return (1, 0) if member.sequence is None else (0, member.sequence)


def _group_to_dict(group: entities.Group) -> dict:
    return {
        "name": group.name,
        "library_id": group.library_id,
        "folder_id": group.folder_id,
        "is_standalone": group.is_standalone,
        "source": (
            {"type": group.source.type, "identifier": group.source.identifier}
            if group.source is not None
            else None
        ),
        "members": [
            {"path": member.path, "sequence": member.sequence}
            for member in group.members
        ],
    }


def _group_from_dict(group_id: str, data: dict) -> entities.Group:
    source_data = data.get("source")
    return entities.Group(
        id=group_id,
        name=data["name"],
        library_id=data["library_id"],
        folder_id=data["folder_id"],
        is_standalone=data.get("is_standalone", False),
        source=(
            entities.GroupSource(
                type=source_data["type"], identifier=source_data["identifier"]
            )
            if source_data
            else None
        ),
        members=[
            entities.GroupMember(path=entry["path"], sequence=entry.get("sequence"))
            for entry in data.get("members", [])
        ],
    )
