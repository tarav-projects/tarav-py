"""Recent, workflow-attributed traces offered as examples to agents."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import logging
from pathlib import Path
from typing import Mapping

from filelock import FileLock
import jmespath

from tarav.l0._core.data_root import default_tarav_data_root
from tarav.l0.kernel import LiteRecord, Ship, TaravClass, TaravEntity, TaravType, TypeShip, WorkflowShip, entity
from tarav.l0.kernel.workflows import TaravWorkflow
from tarav.l1.archive.records import ArchiveFolder, ArchivePartition


USAGE_WORKFLOW_SHIP = WorkflowShip("f1589494-1e42-4d12-969a-f167d08b56e4")
DEFAULT_WINDOW_DAYS = 7
_LOG = logging.getLogger(__name__)


class UsageRegistryWorkflow(TaravWorkflow):
    workflow_name = "usage"
    constitution = (
        "Retain recent workflow-attributed usage traces for discovery. "
        "Daily trace files older than the configured window may be removed."
    )

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("82681b2e-21a2-45c4-afc8-b63c4ed8a3f2"),
            name="Tarav.Workflow.Usage",
            workflow=USAGE_WORKFLOW_SHIP,
        )

    @classmethod
    def _workflow_id(cls) -> WorkflowShip:
        return USAGE_WORKFLOW_SHIP


# tarav.breadcrumb 8c814524ab7806d18fc6774a923a01d4f5b22061aa7d27efc70672022b041c17
class UsageTrace(TaravType):
    """A trusted Type describes how its retained usage rows are presented."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("d8a80919-79f9-42b5-a0ad-e2bc0c70f0fa"),
            name="Tarav.Usage.Trace",
            workflow=USAGE_WORKFLOW_SHIP,
        )

    @classmethod
    def render_trace(cls, row: Mapping[str, object]) -> tuple[str, ...]:
        stamp = str(row.get("recorded_at", ""))[:16].replace("T", " ")
        return (f"  {stamp}  {row.get('subject', '')}",)


# tarav.breadcrumb b6575c66c1fa47b85dc84368182072438d35f09fa8b3ff0a7b003a2017127331


def _workflow_ship(workflow: type[TaravWorkflow] | TaravWorkflow | WorkflowShip) -> WorkflowShip:
    if isinstance(workflow, WorkflowShip):
        return workflow
    if isinstance(workflow, TaravWorkflow):
        return workflow.id
    if isinstance(workflow, type) and issubclass(workflow, TaravWorkflow):
        return workflow().id
    raise TypeError("workflow must identify a TaravWorkflow")


def _project_ship(project: TaravEntity | Ship | None) -> Ship | None:
    if project is None or isinstance(project, Ship):
        return project
    if isinstance(project, TaravEntity):
        return project.id
    raise TypeError("project must be an Entity or Ship")


class UsageRegistry:
    """A small append/query service; callers decide what their traces reveal."""

    def __init__(self, archive_root: Path | None = None, *, window_days: int = DEFAULT_WINDOW_DAYS):
        if window_days < 1:
            raise ValueError("window_days must be positive")
        self.archive_root = (archive_root or default_tarav_data_root() / "archive").expanduser().resolve()
        self.window_days = window_days

    @property
    def partition(self) -> ArchivePartition:
        return ArchivePartition(self.archive_root, USAGE_WORKFLOW_SHIP)

    def _folder(self, workflow: WorkflowShip) -> ArchiveFolder:
        path = self.partition.directory / str(workflow)
        if path.is_dir():
            return ArchiveFolder.from_path(path)
        self.partition.directory.mkdir(parents=True, exist_ok=True)
        with FileLock(str(self.partition.directory / ".usage-create.lock")):
            if path.is_dir():
                return ArchiveFolder.from_path(path)
            return self.partition.create_archive(
                str(workflow), ArchiveFolder,
                constitution="Recent usage traces supplied by this workflow.",
            )

    def record(
        self,
        *,
        trace_type: type[UsageTrace],
        workflow: type[TaravWorkflow] | TaravWorkflow | WorkflowShip,
        subject: str,
        payload: Mapping[str, object] | LiteRecord,
        project: TaravEntity | Ship | None = None,
    ) -> bool:
        """Best effort: failure never changes the caller's outcome."""
        try:
            if not isinstance(trace_type, type) or not issubclass(trace_type, UsageTrace):
                raise TypeError("trace_type must be a UsageTrace class")
            if not isinstance(subject, str) or not subject:
                raise ValueError("subject must be nonempty text")
            workflow_id = _workflow_ship(workflow)
            project_id = _project_ship(project)
            now = datetime.now(timezone.utc)
            row = {
                "type": entity(trace_type).name,
                "recorded_at": now.isoformat(),
                "workflow": str(workflow_id),
                "subject": subject,
                "project": str(project_id) if project_id is not None else None,
                "payload": (payload if isinstance(payload, LiteRecord) else LiteRecord(payload)).to_json_value(),
            }
            folder = self._folder(workflow_id)
            target = folder.root / f"{now:%Y-%m-%d}-usage.jsonl"
            with FileLock(str(folder.root / ".usage-write.lock")):
                with target.open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")
            self.trim(now=now, workflow=workflow_id)
            return True
        except Exception:
            _LOG.warning("Could not retain usage trace", exc_info=True)
            return False

    def trim(
        self, *, now: datetime | None = None,
        workflow: type[TaravWorkflow] | TaravWorkflow | WorkflowShip | None = None,
    ) -> None:
        """Remove only complete day files preceding the retention window."""
        current = now or datetime.now(timezone.utc)
        cutoff = (current - timedelta(days=self.window_days)).date()
        if workflow is None:
            directories = (folder.child_directory for folder in self.partition.ls())
        else:
            directories = (self.partition.directory / str(_workflow_ship(workflow)),)
        for directory in directories:
            if directory is None or not directory.is_dir():
                continue
            for path in directory.glob("????-??-??-usage.jsonl"):
                try:
                    day = datetime.strptime(path.name[:10], "%Y-%m-%d").date()
                except ValueError:
                    continue
                if day < cutoff and path.is_file() and not path.is_symlink():
                    path.unlink()

    def query(
        self,
        *,
        workflow: type[TaravWorkflow] | TaravWorkflow | WorkflowShip | None = None,
        project: TaravEntity | Ship | None = None,
        subject: str | None = None,
        trace_type: type[UsageTrace] | str | None = None,
        since: datetime | None = None,
        expression: str | None = None,
        limit: int | None = None,
    ) -> tuple[dict[str, object], ...]:
        if limit is not None and limit < 0:
            raise ValueError("limit must not be negative")
        if limit == 0:
            return ()
        selected_workflow = str(_workflow_ship(workflow)) if workflow is not None else None
        selected_project = str(_project_ship(project)) if project is not None else None
        if isinstance(trace_type, type) and issubclass(trace_type, UsageTrace):
            selected_type = entity(trace_type).name
        elif trace_type is None or isinstance(trace_type, str) and trace_type:
            selected_type = trace_type
        else:
            raise TypeError("trace_type must be a UsageTrace class or nonempty label")
        retention_boundary = datetime.now(timezone.utc) - timedelta(days=self.window_days)
        if since is not None:
            since = (since.replace(tzinfo=timezone.utc) if since.tzinfo is None
                     else since.astimezone(timezone.utc))
        since = max(since, retention_boundary) if since is not None else retention_boundary
        predicate = jmespath.compile(expression) if expression else None
        rows: list[dict[str, object]] = []
        partition = self.partition.directory
        if not partition.is_dir():
            return ()
        folders = [partition / selected_workflow] if selected_workflow else sorted(partition.iterdir())
        for folder in folders:
            if not folder.is_dir() or folder.is_symlink() or not (folder / "main.json").is_file():
                continue
            for day_file in sorted(folder.glob("????-??-??-usage.jsonl"), reverse=True):
                if day_file.is_symlink():
                    continue
                for line in day_file.read_text(encoding="utf-8").splitlines():
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(row, dict):
                        continue
                    if selected_workflow and row.get("workflow") != selected_workflow:
                        continue
                    if selected_project and row.get("project") != selected_project:
                        continue
                    if selected_type is not None and row.get("type") != selected_type:
                        continue
                    if subject is not None and row.get("subject") != subject:
                        continue
                    if str(row.get("recorded_at", "")) < since.isoformat():
                        continue
                    if predicate is not None and not predicate.search(row):
                        continue
                    rows.append(row)
        rows.sort(key=lambda item: str(item.get("recorded_at", "")), reverse=True)
        return tuple(rows[:limit]) if limit is not None else tuple(rows)


# tarav.breadcrumb 49d903a04560c26555691aa1371dedd6f28f61ccb04a0d5c845c9bfd2bd89e87
def describe_text(
    text: str, *, edge: int = 20, inline_limit: int = 80,
) -> str | dict[str, object]:
    """Keep short text verbatim; stand for longer text by size, edges, and hash."""
    if len(text) <= inline_limit:
        return text
    return {
        "chars": len(text),
        "head": text[:edge],
        "tail": text[-edge:] if len(text) > edge else "",
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
    }


def describe_file(path: str | Path) -> dict[str, object]:
    """Optional helper: stand for a file by its path and content hash."""
    target = Path(path).expanduser()
    try:
        digest: str | None = hashlib.sha256(target.read_bytes()).hexdigest()
    except OSError:
        digest = None
    return {"path": str(target), "sha256": digest}


def record_usage(
    workflow: type[TaravWorkflow] | TaravWorkflow | WorkflowShip,
    subject: str,
    payload: Mapping[str, object] | LiteRecord,
    *,
    trace_type: type[UsageTrace],
    project: TaravEntity | Ship | None = None,
) -> bool:
    return UsageRegistry().record(
        trace_type=trace_type, workflow=workflow, subject=subject,
        payload=payload, project=project,
    )


__all__ = [
    "UsageRegistry", "UsageRegistryWorkflow", "UsageTrace", "record_usage", "describe_text",
    "describe_file", "DEFAULT_WINDOW_DAYS",
]
