"""Create, inspect, reset, and remove manifest-backed working folders."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import shutil
from uuid import uuid4

from tarav.l0.kernel import Ship
from tarav.l1.git.repository import GitRepository

from .model import (
    CopiedDocument, EntryObservation, NewDocument, RepositoryWorktree,
    Workspace, WorkspaceManifest, WorkspaceSetupRecord, WorkspaceSymlink,
)
from .root import resolve_workspaces_root


class WorkspaceError(ValueError):
    def __init__(self, message: str, *, pois: tuple = ()):
        super().__init__(message)
        self.pois = pois


def _hash(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _destination(root: Path, relative: str) -> Path:
    destination = root / relative
    if not destination.parent.resolve().is_relative_to(root.resolve()):
        raise WorkspaceError(f"Workspace destination escapes its root: {relative}")
    return destination


def _write_json(path: Path, value: dict) -> None:
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


# tarav.breadcrumb c1bdbcdaed7f73d3e33254249413d3aed237f8a32f1ffe4ddbfe59062e061270
class WorkspaceDepot:
    """One configured root; reads never create it."""

    def __init__(self, root: Path | str | None = None):
        self.root = resolve_workspaces_root(root)

    def open(self, identity: Ship | str) -> Workspace:
        selected = Ship(str(identity))
        path = self.root / str(selected)
        if path.is_symlink() or not path.is_dir():
            raise WorkspaceError(f"Workspace directory is missing or redirected: {path}")
        try:
            record = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise WorkspaceError(f"Cannot read Workspace manifest: {path}") from error
        workspace = Workspace.records.from_record(record)
        if workspace.id != selected:
            raise WorkspaceError("Workspace directory and manifest identities disagree")
        workspace.root = path
        workspace.source = path / "manifest.json"
        return workspace

    def list(self, *, project_id: Ship | str | None = None,
             status: str | None = None) -> tuple[Workspace, ...]:
        if not self.root.is_dir():
            return ()
        result = []
        for path in sorted(self.root.iterdir()):
            if not path.is_dir():
                continue
            workspace = self.open(path.name)
            if project_id is not None and Ship(str(project_id)) not in workspace.manifest.project_ids:
                continue
            if status is not None and workspace.manifest.status != status:
                continue
            result.append(workspace)
        return tuple(result)

    def create(self, manifest: WorkspaceManifest, *, seed_root: Path | str | None = None,
               require_copy_seeds: bool = False) -> Workspace:
        """Create one new identity. Copies and new documents retain local seeds."""
        if not isinstance(manifest, WorkspaceManifest):
            raise TypeError("create requires a WorkspaceManifest")
        root = self.root / str(manifest.id)
        if root.exists():
            raise WorkspaceError(f"Workspace already exists: {manifest.id}")
        self.root.mkdir(parents=True, exist_ok=True)
        root.mkdir()
        source_seeds = Path(seed_root) if seed_root is not None else None
        created_worktrees: list[tuple[GitRepository, Path]] = []
        observations: dict[str, EntryObservation] = {}
        try:
            for entry in manifest.entries:
                destination = _destination(root, entry.path)
                destination.parent.mkdir(parents=True, exist_ok=True)
                if isinstance(entry, CopiedDocument):
                    seed = root / "seeds" / entry.path
                    seed.parent.mkdir(parents=True, exist_ok=True)
                    retained_seed = source_seeds / entry.path if source_seeds else None
                    if require_copy_seeds and (retained_seed is None or not retained_seed.is_file()):
                        raise WorkspaceError(f"Retained copy seed is missing: {entry.path}")
                    shutil.copy2(
                        retained_seed if retained_seed is not None and retained_seed.is_file()
                        else Path(entry.source), seed,
                    )
                    shutil.copy2(seed, destination)
                    observations[entry.path] = EntryObservation(
                        content_hash=_hash(seed),
                        source_hash=_hash(seed),
                    )
                elif isinstance(entry, NewDocument):
                    if source_seeds is None:
                        raise WorkspaceError(f"New document requires a seed root: {entry.path}")
                    seed = root / "seeds" / entry.seed
                    seed.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source_seeds / entry.seed, seed)
                    shutil.copy2(seed, destination)
                    observations[entry.path] = EntryObservation(content_hash=_hash(seed))
                elif isinstance(entry, WorkspaceSymlink):
                    destination.symlink_to(entry.target)
                    observations[entry.path] = EntryObservation(
                        content_hash=_hash(destination) if destination.is_file() else None
                    )
                elif isinstance(entry, RepositoryWorktree):
                    repository = GitRepository(entry.repository)
                    branch = f"tarav/workspace/{str(manifest.id)[:12]}/{sha256(entry.path.encode()).hexdigest()[:12]}"
                    worktree = repository.add_worktree(destination, commit=entry.commit, branch=branch)
                    created_worktrees.append((repository, destination))
                    observations[entry.path] = EntryObservation(
                        commit=worktree.commit, branch=branch
                    )
            _write_json(root / "manifest.json", manifest.model_dump(mode="json"))
            _write_json(root / "setup.json", WorkspaceSetupRecord(
                workspace_id=manifest.id, entries=observations
            ).model_dump(mode="json"))
        except Exception:
            for repository, destination in reversed(created_worktrees):
                repository.remove_worktree(destination)
            shutil.rmtree(root)
            raise
        return self.open(manifest.id)

    def clone(self, workspace: Workspace, *, label: str) -> Workspace:
        """Reapply a recipe and its retained seeds with a fresh Workspace Ship."""
        if workspace.root is None:
            raise WorkspaceError("Detached Workspace cannot be cloned")
        data = workspace.records.to_record()
        data["id"] = str(uuid4())
        data["label"] = label
        data["status"] = "open"
        data["extracted"] = "none"
        return self.create(WorkspaceManifest.model_validate(data, strict=True),
                           seed_root=workspace.root / "seeds", require_copy_seeds=True)

    def setup_record(self, workspace: Workspace) -> WorkspaceSetupRecord:
        if workspace.root is None:
            raise WorkspaceError("Detached Workspace has no setup record")
        record = json.loads((workspace.root / "setup.json").read_text(encoding="utf-8"))
        result = WorkspaceSetupRecord.model_validate(record, strict=True)
        if result.workspace_id != workspace.id:
            raise WorkspaceError("Setup record belongs to a different workspace")
        return result

    def reset(self, workspace: Workspace) -> WorkspaceSetupRecord:
        """Restore recorded seed bytes and base commits only when no work is lost."""
        from .checks import WorkspaceResetCheck

        result = WorkspaceResetCheck(workspace, self.setup_record(workspace)).run()
        if result.pois():
            raise WorkspaceError("Workspace has changes; reset refused", pois=result.pois())
        root = workspace.root
        assert root is not None
        observations = {}
        prior = self.setup_record(workspace)
        for entry in workspace.manifest.entries:
            destination = _destination(root, entry.path)
            if isinstance(entry, RepositoryWorktree):
                repository = GitRepository(entry.repository)
                previous = prior.entries[entry.path]
                assert previous.branch is not None
                repository.remove_worktree(destination)
                worktree = repository.attach_worktree(destination, branch=previous.branch)
                observations[entry.path] = EntryObservation(
                    commit=worktree.commit, branch=previous.branch)
            elif isinstance(entry, WorkspaceSymlink):
                destination.unlink(missing_ok=True)
                destination.symlink_to(entry.target)
                observations[entry.path] = EntryObservation(
                    content_hash=_hash(destination) if destination.is_file() else None)
            else:
                seed_name = entry.path if isinstance(entry, CopiedDocument) else entry.seed
                seed = root / "seeds" / seed_name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(seed, destination)
                observations[entry.path] = EntryObservation(
                    content_hash=_hash(seed),
                    source_hash=_hash(seed) if isinstance(entry, CopiedDocument) else None,
                )
        record = WorkspaceSetupRecord(workspace_id=workspace.id, entries=observations)
        _write_json(root / "setup.json", record.model_dump(mode="json"))
        return record

    def remove(self, workspace: Workspace) -> None:
        """Refuse active or dirty work; clean up registrations before the folder."""
        from .checks import WorkspaceRemovalCheck

        if workspace.root is None:
            raise WorkspaceError("Detached Workspace cannot be removed")
        if workspace.manifest.status == "open":
            raise WorkspaceError("Open Workspace cannot be removed; mark it harvested or abandoned")
        if workspace.manifest.status == "harvested" and workspace.manifest.extracted == "none":
            raise WorkspaceError("Harvested Workspace must record where work was extracted")
        record = self.setup_record(workspace)
        result = WorkspaceRemovalCheck(workspace, record).run()
        if result.pois():
            raise WorkspaceError("Workspace has work that may be lost; removal refused",
                                 pois=result.pois())
        for entry in workspace.manifest.entries:
            if isinstance(entry, RepositoryWorktree):
                GitRepository(entry.repository).remove_worktree(
                    _destination(workspace.root, entry.path))
        shutil.rmtree(workspace.root)

    def set_status(self, workspace: Workspace, status: str, *, extracted: str | None = None) -> Workspace:
        data = workspace.records.to_record()
        data["status"] = status
        if extracted is not None:
            data["extracted"] = extracted
        updated = WorkspaceManifest.model_validate(data, strict=True)
        assert workspace.root is not None
        _write_json(workspace.root / "manifest.json", updated.model_dump(mode="json"))
        return self.open(workspace.id)

    def reference_check(self, *, source: Path, target: Path):
        """Bind the nonblocking reminder to an explicitly known file reference."""
        from .checks import WorkspaceReferenceCheck

        return WorkspaceReferenceCheck(depot_root=self.root, source=source, target=target)


__all__ = ["WorkspaceDepot", "WorkspaceError"]
