import dataclasses

from book_converter.features.organization import dto, entities, interfaces


@dataclasses.dataclass(frozen=True)
class ListGroupsUseCase:
    store: interfaces.GroupStore

    def execute(self) -> dto.ListGroupsOutput:
        return dto.ListGroupsOutput(groups=self.store.list_groups())


@dataclasses.dataclass(frozen=True)
class CreateGroupUseCase:
    """A series MUST belong to a library (and, within it, a folder) from the
    moment it exists - there's no "create now, assign later" path, since
    that's exactly what let a series get split across libraries before."""

    store: interfaces.GroupStore

    def execute(
        self, name: str, library_id: str, folder_id: str, is_standalone: bool = False
    ) -> entities.Group:
        return self.store.create_group(
            name=name,
            library_id=library_id,
            folder_id=folder_id,
            is_standalone=is_standalone,
        )


@dataclasses.dataclass(frozen=True)
class RenameGroupUseCase:
    store: interfaces.GroupStore

    def execute(self, group_id: str, name: str) -> entities.Group:
        return self.store.rename_group(group_id, name)


@dataclasses.dataclass(frozen=True)
class DeleteGroupUseCase:
    store: interfaces.GroupStore

    def execute(self, group_id: str) -> None:
        self.store.delete_group(group_id)


@dataclasses.dataclass(frozen=True)
class AddMemberUseCase:
    store: interfaces.GroupStore

    def execute(self, group_id: str, path: str, sequence: int | None) -> entities.Group:
        return self.store.add_member(group_id, path, sequence)


@dataclasses.dataclass(frozen=True)
class RemoveMemberUseCase:
    store: interfaces.GroupStore

    def execute(self, group_id: str, path: str) -> entities.Group:
        return self.store.remove_member(group_id, path)


@dataclasses.dataclass(frozen=True)
class ReorderMembersUseCase:
    store: interfaces.GroupStore

    def execute(self, group_id: str, ordered_paths: list[str]) -> entities.Group:
        return self.store.reorder_members(group_id, ordered_paths)


@dataclasses.dataclass(frozen=True)
class ListUnassignedUseCase:
    store: interfaces.GroupStore

    def execute(self, all_paths: list[str]) -> dto.ListUnassignedOutput:
        grouped = {
            member.path
            for group in self.store.list_groups()
            for member in group.members
        }
        return dto.ListUnassignedOutput(
            paths=[path for path in all_paths if path not in grouped]
        )
