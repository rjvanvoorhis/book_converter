import json
import pathlib
import threading

# A segment's review status. Absent from the file entirely means
# "unreviewed" - only explicit decisions get persisted.
Status = str  # "ok" | "flagged" | "fixed"

_lock = threading.Lock()


def read_review(m4b_path: str) -> dict:
    review_path = _review_path(pathlib.Path(m4b_path))
    if not review_path.is_file():
        return {"segments": {}}
    with _lock:
        return json.loads(review_path.read_text(encoding="utf-8"))


def set_segment_status(
    m4b_path: str, segment_index: int, status: Status, note: str | None = None
) -> dict:
    review_path = _review_path(pathlib.Path(m4b_path))
    with _lock:
        review = (
            json.loads(review_path.read_text(encoding="utf-8"))
            if review_path.is_file()
            else {"segments": {}}
        )
        entry: dict = {"status": status}
        if note:
            entry["note"] = note
        review["segments"][str(segment_index)] = entry
        review_path.write_text(json.dumps(review, indent=2), encoding="utf-8")
        return review


def clear_review(m4b_path: str) -> None:
    """Drop stale review state, e.g. after re-segmenting shifts every later
    segment's index - old entries would otherwise attach to the wrong
    segment."""
    path = _review_path(pathlib.Path(m4b_path))
    with _lock:
        path.unlink(missing_ok=True)


def _review_path(m4b_path: pathlib.Path) -> pathlib.Path:
    return m4b_path.with_name(f"{m4b_path.name}.review.json")
