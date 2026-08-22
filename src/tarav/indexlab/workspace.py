# $kw: --from Agentos.Bloberia
from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, replace
from pathlib import Path
from uuid import UUID, uuid4

from tarav._core.persistence import atomic_write_json
from tarav.bloberia import BloberiaDepot, PUBLIC_DEPOT_ROOT, TYPE_SHARDS

from .model import IndexRecord, RecordModelError


LIBRARY_SCHEMA = "tarav.index-library.v1"
LIBRARY_MARKER = "library.json"
WORKSPACE_SCHEMA = "tarav.index-workspace.v1"
WORKSPACE_MARKER = "workspace.json"
DEFAULT_INDEX_LIBRARY_ROOT = PUBLIC_DEPOT_ROOT / "tarav-index"
TOUCH_ADAPTERS = ("chatlas", "mock")
_WORKSPACE_NAME = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")


class WorkspaceError(RuntimeError):
    """An Index operation crossed or violated its explicit workspace boundary."""


def _resolved_directory(root: Path | str, *, kind: str, marker: str) -> Path:
    resolved = Path(root).expanduser().resolve()
    if resolved.exists():
        if not resolved.is_dir():
            raise WorkspaceError(f"{kind} path is not a directory: {resolved}")
        if not (resolved / marker).is_file() and tuple(resolved.iterdir()):
            raise WorkspaceError(
                f"refusing to initialize non-empty directory as {kind}: {resolved}"
            )
    else:
        resolved.mkdir(parents=True)
    return resolved


def _read_object(path: Path, *, kind: str) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError) as exc:
        raise WorkspaceError(f"unreadable {kind} marker {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise WorkspaceError(f"{kind} marker is not an object: {path}")
    return payload


def _canonical_uuid(value: object, *, field: str) -> str:
    if not isinstance(value, str):
        raise WorkspaceError(f"{field} must be a UUID")
    try:
        parsed = UUID(value)
    except ValueError as exc:
        raise WorkspaceError(f"{field} must be a UUID: {value!r}") from exc
    canonical = str(parsed)
    if value != canonical:
        raise WorkspaceError(f"{field} must use canonical UUID spelling: {value!r}")
    return canonical


def _validate_touch_adapter(value: object) -> str:
    if value not in TOUCH_ADAPTERS:
        raise WorkspaceError(
            f"touch_adapter must be one of {', '.join(TOUCH_ADAPTERS)}: {value!r}"
        )
    return str(value)


def _initialize_git(root: Path) -> None:
    result = subprocess.run(
        ("git", "-C", str(root), "init", "-q"),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip() or "unknown git error"
        raise WorkspaceError(f"cannot initialize workspace Git repository: {detail}")


@dataclass(frozen=True, slots=True)
class IndexWorkspace:
    """One configured Index instance and its exact Bloberia/Git root."""

    root: Path
    id: str
    touch_adapter: str

    @classmethod
    def initialize(
        cls,
        root: Path | str,
        *,
        workspace_id: str,
        touch_adapter: str = "chatlas",
    ) -> IndexWorkspace:
        resolved = _resolved_directory(
            root, kind="Index.Workspace", marker=WORKSPACE_MARKER
        )
        if (resolved / WORKSPACE_MARKER).is_file():
            workspace = cls.open(resolved)
            expected_id = _canonical_uuid(workspace_id, field="workspace_id")
            expected_adapter = _validate_touch_adapter(touch_adapter)
            if workspace.id != expected_id or workspace.touch_adapter != expected_adapter:
                raise WorkspaceError(
                    "existing Index.Workspace configuration does not match initialization request"
                )
            return workspace

        canonical_id = _canonical_uuid(workspace_id, field="workspace_id")
        adapter = _validate_touch_adapter(touch_adapter)
        _initialize_git(resolved)
        (resolved / ".gitignore").write_text(".bloberia.lock\n", "utf-8")
        atomic_write_json(
            resolved / WORKSPACE_MARKER,
            {
                "schema": WORKSPACE_SCHEMA,
                "id": canonical_id,
                "touch_adapter": adapter,
            },
        )
        BloberiaDepot(
            resolved,
            depot_type=TYPE_SHARDS,
            key="id",
            git=".",
        ).initialize()
        return cls.open(resolved)

    @classmethod
    def open(cls, root: Path | str) -> IndexWorkspace:
        resolved = Path(root).expanduser().resolve()
        marker = resolved / WORKSPACE_MARKER
        if not marker.is_file():
            raise WorkspaceError(f"not an initialized Index.Workspace: {resolved}")
        payload = _read_object(marker, kind="Index.Workspace")
        if payload.get("schema") != WORKSPACE_SCHEMA:
            raise WorkspaceError(f"unsupported Index.Workspace marker: {marker}")
        workspace_id = _canonical_uuid(payload.get("id"), field="workspace id")
        touch_adapter = _validate_touch_adapter(payload.get("touch_adapter"))
        if not (resolved / ".git").is_dir():
            raise WorkspaceError(f"Index.Workspace has no Git repository: {resolved}")
        depot = BloberiaDepot(resolved, depot_type=TYPE_SHARDS, key="id")
        if depot.git is None or depot.git.repo != resolved:
            raise WorkspaceError(
                f"Index.Workspace Bloberia depot is not tracked by its own root: {resolved}"
            )
        return cls(root=resolved, id=workspace_id, touch_adapter=touch_adapter)


@dataclass(frozen=True, slots=True)
class WorkspaceEntry:
    name: str
    workspace: IndexWorkspace

    @property
    def id(self) -> str:
        return self.workspace.id

    @property
    def root(self) -> Path:
        return self.workspace.root


@dataclass(frozen=True, slots=True)
class IndexLibrary:
    """A user-level name registry for independently rooted Index.Workspaces."""

    root: Path

    @property
    def workspaces_root(self) -> Path:
        return self.root / "workspaces"

    @classmethod
    def initialize(cls, root: Path | str) -> IndexLibrary:
        resolved = _resolved_directory(root, kind="Index.Library", marker=LIBRARY_MARKER)
        marker = resolved / LIBRARY_MARKER
        if not marker.is_file():
            atomic_write_json(
                marker,
                {"schema": LIBRARY_SCHEMA, "workspaces": {}},
            )
        return cls.open(resolved)

    @classmethod
    def open(cls, root: Path | str) -> IndexLibrary:
        resolved = Path(root).expanduser().resolve()
        marker = resolved / LIBRARY_MARKER
        if not marker.is_file():
            raise WorkspaceError(f"not an initialized Index.Library: {resolved}")
        _read_registry(marker)
        return cls(root=resolved)

    def create_workspace(
        self, name: str, *, touch_adapter: str = "chatlas"
    ) -> IndexWorkspace:
        _validate_workspace_name(name)
        registry = self._registry()
        if name in registry or name in registry.values():
            raise WorkspaceError(f"Index.Workspace name already exists: {name}")
        workspace_id = str(uuid4())
        workspace = IndexWorkspace.initialize(
            self.workspaces_root / workspace_id,
            workspace_id=workspace_id,
            touch_adapter=touch_adapter,
        )
        registry[name] = workspace_id
        self._write_registry(registry)
        return workspace

    def resolve(self, selector: str) -> IndexWorkspace:
        registry = self._registry()
        workspace_id = registry.get(selector)
        if workspace_id is None and selector in registry.values():
            workspace_id = selector
        if workspace_id is None:
            raise WorkspaceError(f"unknown Index.Workspace: {selector}")
        workspace = IndexWorkspace.open(self.workspaces_root / workspace_id)
        if workspace.id != workspace_id:
            raise WorkspaceError(
                f"Index.Workspace registry identity mismatch for {selector!r}"
            )
        return workspace

    def list_workspaces(self) -> tuple[WorkspaceEntry, ...]:
        return tuple(
            WorkspaceEntry(name=name, workspace=self.resolve(name))
            for name in sorted(self._registry())
        )

    def _registry(self) -> dict[str, str]:
        return _read_registry(self.root / LIBRARY_MARKER)

    def _write_registry(self, workspaces: dict[str, str]) -> None:
        atomic_write_json(
            self.root / LIBRARY_MARKER,
            {"schema": LIBRARY_SCHEMA, "workspaces": dict(sorted(workspaces.items()))},
        )


def _validate_workspace_name(name: object) -> str:
    if not isinstance(name, str) or not _WORKSPACE_NAME.fullmatch(name):
        raise WorkspaceError(f"invalid workspace name: {name!r}")
    return name


def _read_registry(path: Path) -> dict[str, str]:
    payload = _read_object(path, kind="Index.Library")
    if payload.get("schema") != LIBRARY_SCHEMA:
        raise WorkspaceError(f"unsupported Index.Library marker: {path}")
    raw = payload.get("workspaces")
    if not isinstance(raw, dict):
        raise WorkspaceError(f"Index.Library workspaces must be an object: {path}")
    registry: dict[str, str] = {}
    for name, workspace_id in raw.items():
        registry[_validate_workspace_name(name)] = _canonical_uuid(
            workspace_id, field=f"workspace id for {name!r}"
        )
    if len(set(registry.values())) != len(registry):
        raise WorkspaceError(f"Index.Library assigns one workspace to multiple names: {path}")
    return registry


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
    """Curated Index.Record persistence confined to one explicit workspace."""

    def __init__(self, workspace: IndexWorkspace) -> None:
        if not isinstance(workspace, IndexWorkspace):
            raise TypeError("RecordStore requires an explicit IndexWorkspace")
        self.workspace = IndexWorkspace.open(workspace.root)
        self._depot = BloberiaDepot(
            self.workspace.root,
            depot_type=TYPE_SHARDS,
            key="id",
        )

    @property
    def depot_root(self) -> Path:
        return self._depot.root

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
                defects.append(CargoDefect(record_id=_cargo_id(cargo), error=str(exc)))
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
    "DEFAULT_INDEX_LIBRARY_ROOT",
    "LIBRARY_MARKER",
    "LIBRARY_SCHEMA",
    "TOUCH_ADAPTERS",
    "WORKSPACE_MARKER",
    "WORKSPACE_SCHEMA",
    "CargoDefect",
    "IndexLibrary",
    "IndexWorkspace",
    "RecordStore",
    "WorkspaceEntry",
    "WorkspaceError",
]
