import typing

from book_converter.features.organization import entities


class GroupStore(typing.Protocol):
    def list_groups(self) -> list[entities.Group]: ...

    def get_group(self, group_id: str) -> entities.Group | None: ...

    def find_group_for_member(self, path: str) -> entities.Group | None: ...

    def create_group(
        self,
        name: str,
        library_id: str,
        folder_id: str,
        is_standalone: bool = False,
        source: entities.GroupSource | None = None,
    ) -> entities.Group: ...

    def rename_group(self, group_id: str, name: str) -> entities.Group: ...

    def delete_group(self, group_id: str) -> None: ...

    def add_member(
        self, group_id: str, path: str, sequence: int | None
    ) -> entities.Group: ...

    def remove_member(self, group_id: str, path: str) -> entities.Group: ...

    def reorder_members(
        self, group_id: str, ordered_paths: list[str]
    ) -> entities.Group:
        """Resequences exactly the given paths to 1..N in the given order -
        any other member not included keeps its current sequence untouched.
        Raises ValueError if a path isn't actually a member of this group."""
        ...


class GroupNotFound(Exception):
    pass
