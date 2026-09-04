import json
import pathlib


def list_dicts(folder: str) -> list[dict]:
    root = pathlib.Path(folder)
    if not root.is_dir():
        return []
    return [
        {"path": str(path), "name": path.stem}
        for path in sorted(root.glob("*.json"))
    ]


def read_dict(path: str) -> dict[str, dict]:
    dict_path = pathlib.Path(path)
    if not dict_path.is_file():
        raise FileNotFoundError(f"No pronunciation dictionary found at '{path}'")
    raw = json.loads(dict_path.read_text(encoding="utf-8"))
    return {word: _normalize_entry(entry) for word, entry in raw.items()}


def write_dict(path: str, entries: dict[str, dict]) -> None:
    dict_path = pathlib.Path(path)
    dict_path.parent.mkdir(parents=True, exist_ok=True)
    dict_path.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")


def _normalize_entry(entry: object) -> dict:
    # Legacy format: a bare string, which pronunciation_text_annotator.py
    # treats as an IPA-method entry.
    if isinstance(entry, str):
        return {"value": entry, "method": "ipa"}
    return {"value": entry.get("value", ""), "method": entry.get("method", "ipa")}
