"""Typed references. Hints are evidence for consumers, never resolver inputs."""

from tarav.l0.kernel import TaravClass, entity

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

from pydantic import ConfigDict, Field, JsonValue, model_validator

from tarav.l0.kernel.identity import TypeShip
from tarav.l0.kernel.records import FileRecord, TaravObject, _json_object
from tarav.l1.poi import IdentifiedPOI
from tarav.l1.references.identity import REFERENCES_WORKFLOW_SHIP


# tarav.breadcrumb 3c3e9e1c1b19de808006014b3cf685ebb28509c8865341fa023223530d94ba77
# tarav.breadcrumb de146a92d0c7301624402ae9cb446816fba032e65301d5e5a4ad47fa3ef76a45
class ReferenceResolutionPOI(IdentifiedPOI):
    """Family of failed Reference resolutions."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('cd189772-73f1-4ddb-9fdd-610bc12a7fd3'),
            name='Tarav.References.Resolution.POI',
            workflow=REFERENCES_WORKFLOW_SHIP,
        )


class ReferenceMismatch(ReferenceResolutionPOI):
    """The target exists but fails the Reference's declared check."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip('a6774890-e2f7-41c0-855c-5e89d3f10f99'),
                          name='Tarav.References.Resolution.Mismatch',
                          workflow=REFERENCES_WORKFLOW_SHIP)


class ReferenceUnresolvable(ReferenceResolutionPOI):
    """The declared target cannot currently be resolved."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip('28ba074b-6670-43d8-8db4-6ba13fc3b974'),
                          name='Tarav.References.Resolution.Unresolvable',
                          workflow=REFERENCES_WORKFLOW_SHIP)


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
    def pois(self) -> tuple[ReferenceResolutionPOI, ...]:
        return (
            ()
            if self.ok
            else ((ReferenceMismatch if self.status == "mismatch" else ReferenceUnresolvable)(
                self.message, situation={"message": self.message},
                evidence={"hints": self.hints}),)
        )


class Sha256Check(TaravObject.RecordInterface):
    """Exact content check shared by file-backed References."""

    model_config = ConfigDict(strict=True, extra="forbid")

    sha256: Annotated[str, Field(pattern=r"^[0-9a-fA-F]{64}$")]


RecordTypeValue = str | dict[str, JsonValue]


class ReferenceTaravMetadata(TaravObject.RecordInterface):
    model_config = ConfigDict(strict=True, extra="allow")

    type: RecordTypeValue


class Reference(FileRecord):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('946c9a30-a7ef-4b52-ac29-86adbf97ec63'),
            name='Tarav.Reference',
            workflow=REFERENCES_WORKFLOW_SHIP,
        )

    class RecordInterface(FileRecord.RecordInterface):
        type: RecordTypeValue | None = None
        tarav_metadata: ReferenceTaravMetadata | None = Field(
            default=None,
            alias="__tarav__",
        )
        locator: JsonValue
        check: JsonValue | None = None
        hints: JsonValue | None = None

        @model_validator(mode="after")
        def require_type_declaration(self):
            if self.type is None and self.tarav_metadata is None:
                raise ValueError("Reference requires type or __tarav__.type")
            return self

    class Records(FileRecord.Records):
        def record_example(self) -> dict[str, object]:
            cls = self._owner
            return {"type": entity(cls).name, "locator": "example"}


    @property
    def locator(self) -> object:
        if self._record is None:
            raise RuntimeError("Reference has no runtime representation")
        return self._record["locator"]

    @property
    def check(self) -> object:
        if self._record is None:
            raise RuntimeError("Reference has no runtime representation")
        return self._record.get("check")

    @property
    def hints(self) -> object:
        if self._record is None:
            raise RuntimeError("Reference has no runtime representation")
        return self._record.get("hints")

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
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('24ee35fb-fd60-4187-b0aa-07d1585a2645'),
            name='Tarav.Reference.File',
        )

    class RecordInterface(Reference.RecordInterface):
        locator: Annotated[str, Field(min_length=1)]
        check: Sha256Check | None = None

    class Records(Reference.Records):
        def record_example(self) -> dict[str, object]:
            cls = self._owner
            return {"type": entity(cls).name, "locator": "/example/file.txt"}


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
                "type": entity(type(self)).name,
                "locator": str(path),
                "hints": observed,
            }
            if check is not None:
                record["check"] = check
        elif check is not None or hints is not None:
            raise ValueError("Loading retained data cannot override check or hints")
        elif "type" not in record and "__tarav__" not in record:
            record = {"type": entity(type(self)).name, **record}
        super().__init__()
        self._record = _json_object(record)

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


from .positions import (  # noqa: E402  (Reference bases must exist first)
    FilePositionCheck,
    FilePositionLocator,
    FilePositionReference,
    FilePositionTarget,
)


__all__ = [
    "FilePositionCheck",
    "FilePositionLocator",
    "FilePositionReference",
    "FilePositionTarget",
    "FileReference",
    "Reference",
    "ReferenceResolutionPOI",
    "ReferenceMismatch",
    "ReferenceUnresolvable",
    "ReferenceResult",
    "ReferenceTaravMetadata",
    "Sha256Check",
]
