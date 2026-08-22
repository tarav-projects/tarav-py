# $kw: --from Agentos.Bloberia
from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path

from tarav._core.persistence import atomic_write_json
from tarav.bloberia import BloberiaDepot, TYPE_SHARDS

from .model import IndexRecord, RecordModelError


WORKSPACE_SCHEMA = "tarav.indexlab-workspace.v1"
WORKSPACE_MARKER = ".indexlab-workspace.json"


class WorkspaceError(RuntimeError):
    """An IndexLab operation crossed or violated its explicit workspace boundary."""


@dataclass(frozen=True, slots=True)
class IndexLabWorkspace:
    root: Path

    def __post_init__(self) -> None:
        root = self.root.expanduser().resolve()
        object.__setattr__(self, "root", root)
        _validate_marker(root)

    @property
    def records_root(self) -> Path:
        return self.root / "records"

    @classmethod
    def initialize(cls, root: Path | str) -> IndexLabWorkspace:
        resolved = Path(root).expanduser().resolve()
        if resolved.exists():
            if not resolved.is_dir():
                raise WorkspaceError(f"workspace path is not a directory: {resolved}")
            if (resolved / WORKSPACE_MARKER).is_file():
                return cls.open(resolved)
            if tuple(resolved.iterdir()):
                raise WorkspaceError(
                    f"refusing to initialize non-empty directory as IndexLab workspace: {resolved}"
                )
        else:
            resolved.mkdir(parents=True)
        atomic_write_json(
            resolved / WORKSPACE_MARKER,
            {"schema": WORKSPACE_SCHEMA},
        )
        return cls(resolved)

    @classmethod
    def open(cls, root: Path | str) -> IndexLabWorkspace:
        return cls(Path(root))


def _validate_marker(root: Path) -> None:
    marker = root / WORKSPACE_MARKER
    if not marker.is_file():
        raise WorkspaceError(f"not an initialized IndexLab workspace: {root}")
    try:
        payload = json.loads(marker.read_text("utf-8"))
    except (OSError, ValueError) as exc:
        raise WorkspaceError(f"unreadable IndexLab workspace marker {marker}: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("schema") != WORKSPACE_SCHEMA:
        raise WorkspaceError(f"unsupported IndexLab workspace marker: {marker}")


@dataclass(frozen=True, slots=True)
class CargoDefect:
    """One stored cargo that cannot be read back as an Index.Record."""

    record_id: str | None
    error: str

    def to_dict(self) -> dict[str, object]:
        return {"record_id": self.record_id, "error": self.error}


def _cargo_id(cargo: object) -> str | None:
    if isinstance(cargo, dict):
        value = cargo.get("id")
        if isinstance(value, str) and value.strip():
            return value
    return None


class RecordStore:
    """Curated Index.Record persistence confined to one initialized lab workspace."""

    def __init__(self, workspace: IndexLabWorkspace) -> None:
        if not isinstance(workspace, IndexLabWorkspace):
            raise TypeError("RecordStore requires an explicit IndexLabWorkspace")
        _validate_marker(workspace.root)
        self.workspace = workspace
        self._depot = BloberiaDepot(
            workspace.records_root,
            depot_type=TYPE_SHARDS,
            key="id",
        )

    def list(self) -> tuple[IndexRecord, ...]:
        records: list[IndexRecord] = []
        try:
            for cargo in self._depot.iterate():
                records.append(IndexRecord.from_dict(cargo))
        except RecordModelError as exc:
            raise WorkspaceError(f"invalid Index.Record cargo: {exc}") from exc
        return tuple(sorted(records, key=lambda record: (record.ordinal, record.id)))

    def load(self) -> tuple[tuple[IndexRecord, ...], tuple[CargoDefect, ...]]:
        """Read every record, reporting unloadable cargo instead of raising."""

        records: list[IndexRecord] = []
        defects: list[CargoDefect] = []
        for cargo in self._depot.iterate():
            try:
                records.append(IndexRecord.from_dict(cargo))
            except RecordModelError as exc:
                defects.append(
                    CargoDefect(record_id=_cargo_id(cargo), error=str(exc))
                )
        records.sort(key=lambda record: (record.ordinal, record.id))
        defects.sort(key=lambda defect: (defect.record_id or "", defect.error))
        return tuple(records), tuple(defects)

    def get(self, record_id: str) -> IndexRecord | None:
        cargo = self._depot.first({"id": {"equals": record_id}})
        if cargo is None:
            return None
        try:
            return IndexRecord.from_dict(cargo)
        except RecordModelError as exc:
            raise WorkspaceError(f"invalid Index.Record {record_id!r}: {exc}") from exc

    def append(self, record: IndexRecord) -> IndexRecord:
        if record.ordinal != 0:
            raise WorkspaceError("new Index.Record ordinal must be zero before append")
        if self.get(record.id) is not None:
            raise WorkspaceError(f"Index.Record already exists: {record.id}")
        records = self.list()
        ordinal = max((item.ordinal for item in records), default=0) + 1
        stored = replace(record, ordinal=ordinal)
        self._depot.insert(stored.to_dict())
        return stored

    def append_many(self, records: tuple[IndexRecord, ...]) -> tuple[IndexRecord, ...]:
        ids = [record.id for record in records]
        if len(set(ids)) != len(ids):
            raise WorkspaceError("capture batch contains duplicate Index.Record ids")
        for record in records:
            if record.ordinal != 0:
                raise WorkspaceError("new Index.Record ordinal must be zero before append")
            if self.get(record.id) is not None:
                raise WorkspaceError(f"Index.Record already exists: {record.id}")
        stored: list[IndexRecord] = []
        try:
            for record in records:
                stored.append(self.append(record))
        except Exception:
            for record in reversed(stored):
                self._depot.delete({"id": {"equals": record.id}})
            raise
        return tuple(stored)

    def replace(self, record: IndexRecord) -> None:
        current = self.get(record.id)
        if current is None:
            raise WorkspaceError(f"Index.Record does not exist: {record.id}")
        if record.ordinal != current.ordinal:
            raise WorkspaceError("record replacement must preserve original order")
        if record.context != current.context:
            raise WorkspaceError("record replacement must preserve original Record.Context")
        replaced = self._depot.replace(
            {"id": {"equals": record.id}},
            record.to_dict(),
        )
        if replaced != 1:
            raise WorkspaceError(
                f"expected one Index.Record replacement for {record.id}, found {replaced}"
            )

    def purge(self, record_id: str) -> None:
        deleted = self._depot.delete({"id": {"equals": record_id}})
        if deleted != 1:
            raise WorkspaceError(
                f"expected one Index.Record purge for {record_id}, found {deleted}"
            )


__all__ = [
    "WORKSPACE_MARKER",
    "WORKSPACE_SCHEMA",
    "CargoDefect",
    "IndexLabWorkspace",
    "RecordStore",
    "WorkspaceError",
]
