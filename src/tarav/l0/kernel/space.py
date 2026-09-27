"""Common Record-space listing and loading contracts."""

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
    """Browse an explicitly registered local collection; no content guessing."""

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
        entries = []
        for path in sorted(self.path(address).iterdir()):
            if path.name.startswith("."):
                continue
            if path.is_dir():
                kind = (
                    "directory-record"
                    if any((path / name).exists() for name in DIRECTORY_ENTRY_PATH)
                    else "collection"
                )
            else:
                kind = "record" if path.suffix == ".json" else "artifact"
            entries.append(Entry(path.name, kind))
        return tuple(entries)

    def load(self, address: str) -> TaravObject:
        return self.records.load(self.path(address))


__all__ = ["Entry", "FilesystemProvider", "RecordProvider"]
