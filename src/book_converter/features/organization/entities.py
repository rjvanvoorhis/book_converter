import dataclasses


@dataclasses.dataclass(frozen=True)
class GroupSource:
    """Where a group came from, if it wasn't created by hand - e.g. a sync
    from Audiobookshelf's own Series. Purely informational; nothing keys off
    of it except for display and de-duplicating a repeated sync."""

    type: str
    identifier: str


@dataclasses.dataclass(frozen=True)
class GroupMember:
    # Path to a staged audiobook, e.g. under data/audiobooks - same identifier
    # audiobook_library.list_audiobooks and review_store key off of.
    path: str
    # Position within the series - None means "belongs here but isn't
    # numbered" (e.g. a side story), not "not yet ordered". Never meaningful
    # for a standalone group's members (see Group.is_standalone).
    sequence: int | None


@dataclasses.dataclass
class Group:
    """A series - or, if `is_standalone`, the "no series" bucket for works
    that genuinely don't belong to one. Every group is bound to exactly one
    media library folder, fixed at creation, so importing any of its members
    never needs a library/folder picked again - see GroupStore.create_group.
    """

    id: str
    name: str
    library_id: str
    folder_id: str
    # True for a "no series" bucket: its members still need somewhere to
    # import to (hence still library_id/folder_id), but no series name/
    # sequence is ever attached to them on import.
    is_standalone: bool
    source: GroupSource | None
    members: list[GroupMember]
