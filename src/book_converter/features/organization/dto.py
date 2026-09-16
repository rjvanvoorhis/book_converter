import dataclasses

from book_converter.features.organization import entities


@dataclasses.dataclass(frozen=True)
class ListGroupsOutput:
    groups: list[entities.Group]


@dataclasses.dataclass(frozen=True)
class ListUnassignedOutput:
    paths: list[str]
