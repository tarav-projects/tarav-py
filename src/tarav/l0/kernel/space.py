"""Common Record-source listing and loading contracts."""

import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .records import DIRECTORY_ENTRY_PATH, TaravObject
from .types import TypeRegistry


@dataclass(frozen=True)
class Entry:
    name: str
    kind: str


class RecordProvider:
    """A workflow-owned provider of one navigable Record collection."""

    def list(self, address: str = "") -> tuple[Entry, ...]:
        raise NotImplementedError

    def load(self, address: str) -> TaravObject:
        raise NotImplementedError


class FilesystemProvider(RecordProvider):
    """Browse an explicitly registered local collection, including JSONL Records."""
    # tarav.breadcrumb 562d460901f4

    def __init__(self, root: Path, records: TypeRegistry[TaravObject]) -> None:
        self.root = root.expanduser().resolve()
        self.records = records

    def path(self, address: str) -> Path:
        relative = PurePosixPath(address)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Provider address must remain relative to its root")
        target = (self.root / address).resolve()
        if not target.is_relative_to(self.root):
            raise ValueError("Provider address escapes its root")
        return target

    def list(self, address: str = "") -> tuple[Entry, ...]:
        selected = self.path(address)
        if selected.suffix == ".jsonl":
            return tuple(
                Entry(str(position), "record")
                for position, _ in enumerate(_jsonl_records(selected))
            )
        entries = []
        for path in sorted(selected.iterdir()):
            if path.name.startswith("."):
                continue
            if path.is_symlink():
                kind = "artifact"
            elif path.is_dir():
                kind = (
                    "directory-record"
                    if any((path / name).exists() for name in DIRECTORY_ENTRY_PATH)
                    else "collection"
                )
            else:
                kind = (
                    "record" if path.suffix == ".json" else
                    "collection" if path.suffix == ".jsonl" else "artifact"
                )
            entries.append(Entry(path.name, kind))
        return tuple(entries)

    def load(self, address: str) -> TaravObject:
        parent, separator, item = address.rpartition("/")
        if separator and parent.endswith(".jsonl"):
            if not item.isdecimal() or (len(item) > 1 and item.startswith("0")):
                raise ValueError("JSONL Record position must be a canonical integer")
            path = self.path(parent)
            payloads = _jsonl_records(path)
            try:
                payload = payloads[int(item)]
            except IndexError as exc:
                raise FileNotFoundError(address) from exc
            result = self.records.from_record(payload)
            result.source = path
            return result
        return self.records.load(self.path(address))


def _jsonl_records(path: Path) -> tuple[dict[str, object], ...]:
    records = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSONL Record at {path}:{line_number}") from exc
        if not isinstance(value, dict):
            raise ValueError(f"JSONL Record must be an object at {path}:{line_number}")
        records.append(value)
    return tuple(records)


__all__ = ["Entry", "FilesystemProvider", "RecordProvider"]
