"""File and directory serialization of registered Records.

Directory discovery and type-field discovery are separate ordered searches.
Neither skips a present but invalid preferred entry.
"""

from pathlib import Path
from typing import TypeVar

from .ships import TypeShip
from .types import (
    RecordTypeMismatch,
    TaravRecord,
    TypeRegistry,
    _json_load_record,
)

DIRECTORY_ENTRY_PATH = (
    "__tarav.json",
    "main.json",
    "type.json",
    "archive.json",
    "registration.json",
)


class FileRecord(TaravRecord):
    type_ship = TypeShip("fca80371-e492-497b-bf43-044ab2c10220")
    type_name = "Tarav.FileRecord"


class DirectoryRecord(TaravRecord):
    type_ship = TypeShip("1e07c649-a55f-4805-915e-464a8e9b2de1")
    type_name = "Tarav.DirectoryRecord"

    @property
    def directory(self) -> Path:
        if self.source is None:
            raise ValueError("DirectoryRecord has no retained source")
        return self.source.parent


def entry_file(path: str | Path) -> Path:
    """Select one entry without opening payload files or searching recursively."""
    source = Path(path).expanduser().absolute()
    if source.is_dir():
        for name in DIRECTORY_ENTRY_PATH:
            candidate = source / name
            if candidate.exists() or candidate.is_symlink():
                return candidate
        raise FileNotFoundError(f"No Record entry in {source}: {DIRECTORY_ENTRY_PATH}")
    return source


RecordT = TypeVar("RecordT", bound=TaravRecord)


def load_record(
    path: str | Path,
    *,
    registry: TypeRegistry[RecordT],
    record_class: type[RecordT] | None = None,
) -> RecordT:
    source = entry_file(path)
    with source.open(encoding="utf-8") as stream:
        payload = _json_load_record(stream)
    authority = registry.resolve(payload)
    selected = record_class or authority
    if not issubclass(selected, authority):
        raise RecordTypeMismatch(
            f"{selected.__name__} does not specialize {authority.__name__}"
        )
    if Path(path).expanduser().is_dir() and not issubclass(authority, DirectoryRecord):
        raise RecordTypeMismatch(f"{source} does not declare a DirectoryRecord")
    result = selected(payload)
    result.source = source
    return result
