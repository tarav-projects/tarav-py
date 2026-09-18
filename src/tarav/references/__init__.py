"""Typed references. Hints are evidence for consumers, never resolver inputs."""

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from tarav.harness.records import FileRecord
from tarav.harness.ships import TypeShip
from tarav.harness.types import TaravPOIInstance


@dataclass(frozen=True)
class ReferenceFinding(TaravPOIInstance):
    code: str
    message: str
    hints: object


@dataclass(frozen=True)
class ReferenceResult:
    target: object | None
    status: str
    message: str = ""
    hints: object = None

    @property
    def ok(self) -> bool:
        return self.status == "resolved"

    @property
    def findings(self) -> tuple[ReferenceFinding, ...]:
        return (
            ()
            if self.ok
            else (ReferenceFinding(self.status, self.message, self.hints),)
        )


class Reference(FileRecord):
    type_ship = TypeShip("946c9a30-a7ef-4b52-ac29-86adbf97ec63")
    type_name = "Tarav.Reference"

    @property
    def locator(self) -> object:
        return self.record["locator"]

    @property
    def check(self) -> object:
        return self.record.get("check")

    @property
    def hints(self) -> object:
        return self.record.get("hints", {})

    def locate(self, locator: object) -> object:
        raise NotImplementedError

    def check_target(self, target: object, check: object) -> bool:
        raise NotImplementedError

    def resolve(self) -> ReferenceResult:
        """Locate once, check once, report. Never search hints or repair state."""
        try:
            target = self.locate(self.locator)
            if not self.check_target(target, self.check):
                return ReferenceResult(
                    target, "mismatch", "Reference check failed", self.hints
                )
            return ReferenceResult(target, "resolved", hints=self.hints)
        except (OSError, ValueError, TypeError, KeyError) as exc:
            return ReferenceResult(None, "unresolvable", str(exc), self.hints)


class FileReference(Reference):
    type_ship = TypeShip("24ee35fb-fd60-4187-b0aa-07d1585a2645")
    type_name = "Tarav.Reference.File"

    def __init__(self, record: Mapping | str | Path, *, check=None, hints=None):
        if not isinstance(record, Mapping):
            path = Path(record).expanduser().absolute()
            observed = {"name": path.name}
            try:
                stat = path.stat()
                observed.update(size=stat.st_size, mtime_ns=stat.st_mtime_ns)
            except OSError as exc:
                observed["unavailable"] = str(exc)
            if hints is not None:
                observed.update(hints)
            record = {
                "type": self.type_name,
                "locator": str(path),
                "check": check,
                "hints": observed,
            }
        elif check is not None or hints is not None:
            raise ValueError("Loading retained data cannot override check or hints")
        super().__init__(record)

    def locate(self, locator: object) -> Path:
        if not isinstance(locator, str) or not locator:
            raise ValueError("File locator must be a nonempty path")
        path = Path(locator).expanduser()
        if not path.is_absolute():
            if self.source is None:
                raise ValueError(
                    "Relative locator requires a retained reference source"
                )
            path = self.source.parent / path
        if not path.is_file():
            raise FileNotFoundError(path)
        return path

    def check_target(self, target: object, check: object) -> bool:
        if check is None:
            return True
        if not isinstance(check, Mapping) or set(check) != {"sha256"}:
            raise ValueError("File check must contain exactly sha256")
        expected = check["sha256"]
        if not isinstance(expected, str) or len(expected) != 64:
            raise ValueError("sha256 must be a 64-character hexadecimal digest")
        int(expected, 16)
        with Path(target).open("rb") as stream:
            actual = hashlib.file_digest(stream, "sha256").hexdigest()
        return actual == expected.lower()
