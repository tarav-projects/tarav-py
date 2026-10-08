"""Exact one-based positions in files."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

from pydantic import ConfigDict, Field

from tarav.l0.kernel import TaravClass, entity
from tarav.l0.kernel import TaravObject, TypeShip

from . import FileReference, Reference


class FilePositionLocator(TaravObject.RecordInterface):
    """Mechanical locator; richer file identity remains optional."""

    # tarav.breadcrumb 6ef7a9f004286661577a2eec94c89187a44099fa2007019daa7707edff58420d
    model_config = ConfigDict(strict=True, extra="forbid")

    file: str | FileReference.RecordInterface
    line: Annotated[int, Field(ge=1)]


class FilePositionCheck(TaravObject.RecordInterface):
    model_config = ConfigDict(strict=True, extra="forbid")

    contains: Annotated[str, Field(min_length=1)]


@dataclass(frozen=True, slots=True)
class FilePositionTarget:
    path: Path
    line: int
    text: str


class FilePositionReference(Reference):
    # tarav.breadcrumb 87a69f83f5a3abd468c5e47ee04225622e066ec4eab4cf2d6ce479c7427ed40a
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('ecb603a6-ef9b-4673-98ea-9e93569e321c'),
            name='Tarav.Reference.FilePosition',
        )

    class RecordInterface(Reference.RecordInterface):
        locator: FilePositionLocator
        check: FilePositionCheck | None = None

    class Records(Reference.Records):
        def record_example(self) -> dict[str, object]:
            cls = self._owner
            return {
                "type": entity(cls).name,
                "locator": {"file": "/example/file.txt", "line": 1},
            }


    def locate(self, locator: object) -> FilePositionTarget:
        if not isinstance(locator, Mapping):
            raise ValueError("File-position locator must be an object")
        file_value = locator.get("file")
        line = locator.get("line")
        if not isinstance(line, int) or isinstance(line, bool) or line < 1:
            raise ValueError("File-position line must be a positive integer")
        if isinstance(file_value, str):
            file_reference = FileReference.records.from_record(
                {"type": entity(FileReference).name, "locator": file_value}
            )
        elif isinstance(file_value, Mapping):
            file_reference = FileReference.records.from_record(file_value)
        else:
            raise ValueError("File-position file must be a path or File Reference")
        file_reference.source = self.source
        result = file_reference.resolve()
        if not result.ok or not isinstance(result.target, Path):
            raise ValueError(result.message or "File-position file did not resolve")
        lines = result.target.read_text(encoding="utf-8").splitlines()
        if line > len(lines):
            raise ValueError(
                f"File-position line {line} is outside {result.target} ({len(lines)} lines)"
            )
        return FilePositionTarget(result.target, line, lines[line - 1])

    def check_target(self, target: object, check: object) -> bool:
        if not isinstance(target, FilePositionTarget):
            raise TypeError("File-position target has an invalid runtime shape")
        if check is None:
            return True
        if not isinstance(check, Mapping) or set(check) != {"contains"}:
            raise ValueError("File-position check must contain exactly 'contains'")
        contains = check["contains"]
        if not isinstance(contains, str) or not contains:
            raise ValueError("File-position contains check must be nonempty")
        return contains in target.text


__all__ = [
    "FilePositionCheck",
    "FilePositionLocator",
    "FilePositionReference",
    "FilePositionTarget",
]
