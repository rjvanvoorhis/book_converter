import json
import pathlib
import threading

_lock = threading.Lock()


def read_cuts(m4b_path: str) -> list[dict]:
    path = _artifacts_path(pathlib.Path(m4b_path))
    if not path.is_file():
        return []
    with _lock:
        data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("cuts", [])


def write_cuts(m4b_path: str, cuts: list[dict]) -> None:
    path = _artifacts_path(pathlib.Path(m4b_path))
    with _lock:
        path.write_text(json.dumps({"cuts": cuts}, indent=2), encoding="utf-8")


def clear_cuts(m4b_path: str) -> None:
    """Drop a stale scan result, e.g. after regenerating segments shifts
    every later timestamp - the old cut positions no longer line up with
    the rebuilt file."""
    path = _artifacts_path(pathlib.Path(m4b_path))
    with _lock:
        path.unlink(missing_ok=True)


def _artifacts_path(m4b_path: pathlib.Path) -> pathlib.Path:
    return m4b_path.with_name(f"{m4b_path.name}.artifacts.json")
