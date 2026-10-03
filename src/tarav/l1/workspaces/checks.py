"""Nonblocking workspace findings and conservative reset guards."""

from __future__ import annotations

import os
from pathlib import Path

from tarav.l0.kernel import TaravClass, TypeShip
from tarav.l1.checks import Check, CheckPOI, CheckResult
from tarav.l1.git.repository import GitRepository, git_text

from .depot import _destination, _hash
from .model import (
    CopiedDocument, NewDocument, RepositoryWorktree, Workspace,
    WorkspaceSetupRecord, WorkspaceSymlink,
)
from .workflow import WORKSPACES_WORKFLOW_SHIP


class WorkspacePOI(CheckPOI):
    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("9635b752-a8fa-4b5c-a48d-217cf46895ab"),
                          name="Tarav.Workspaces.POI", workflow=WORKSPACES_WORKFLOW_SHIP)


class WorkspaceCheck(Check):
    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("d657953c-4569-42d3-9e97-f88c5fe06cbe"),
                          name="Tarav.Workspaces.Check", workflow=WORKSPACES_WORKFLOW_SHIP)

    def __init__(self, workspace: Workspace, setup: WorkspaceSetupRecord):
        super().__init__()
        if workspace.id != setup.workspace_id or workspace.root is None:
            raise ValueError("WorkspaceCheck requires a bound Workspace and setup record")
        self.workspace = workspace
        self.setup = setup

    def _finding(self, code: str, path: str, message: str, **details) -> WorkspacePOI:
        return WorkspacePOI(
            self, code, message,
            situation={"workspace": str(self.workspace.id), "path": path, "code": code},
            subject={"workspace": str(self.workspace.id), "path": path},
            details=details,
        )


# tarav.breadcrumb 703f434472a801b6b4efe8e15c531fdacc712654766ed7118e9f81197123c2c8
class WorkspaceIntegrityCheck(WorkspaceCheck):
    """Inspect the declared setup without preventing any workspace use."""

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("12608674-4fa5-45b0-9fd4-426e0ca78ae5"),
                          name="Tarav.Workspaces.IntegrityCheck", workflow=WORKSPACES_WORKFLOW_SHIP)

    def _run(self):
        findings = []
        for entry in self.workspace.manifest.entries:
            destination = _destination(self.workspace.root, entry.path)
            observation = self.setup.entries.get(entry.path)
            if observation is None:
                findings.append(self._finding("missing-setup", entry.path,
                                              "Entry has no setup observation"))
                continue
            if isinstance(entry, RepositoryWorktree):
                repository = GitRepository(entry.repository)
                registered = next((item for item in repository.worktrees()
                                   if item.path == destination), None)
                if not destination.is_dir() or registered is None:
                    findings.append(self._finding("missing-worktree", entry.path,
                                                  "Declared worktree is missing or unregistered"))
                elif registered.branch != observation.branch:
                    findings.append(self._finding("worktree-branch", entry.path,
                                                  "Worktree is on a different branch",
                                                  expected=observation.branch,
                                                  actual=registered.branch))
            elif isinstance(entry, CopiedDocument):
                seed = self.workspace.root / "seeds" / entry.path
                if not seed.is_file() or _hash(seed) != observation.content_hash:
                    findings.append(self._finding("seed-changed", entry.path,
                                                  "Retained copy seed is missing or changed"))
                source = Path(entry.source)
                if observation.source_hash is not None and source.is_file() and \
                        _hash(source) != observation.source_hash:
                    findings.append(self._finding("copy-source-changed", entry.path,
                                                  "Copy source changed after setup",
                                                  expected=observation.source_hash,
                                                  actual=_hash(source)))
                elif not source.is_file():
                    findings.append(self._finding("copy-source-missing", entry.path,
                                                  "Copy source is unavailable"))
            elif isinstance(entry, WorkspaceSymlink) and not destination.exists():
                findings.append(self._finding("broken-symlink", entry.path,
                                              "Declared symlink does not resolve"))
            elif isinstance(entry, NewDocument):
                seed = self.workspace.root / "seeds" / entry.seed
                if not seed.is_file() or _hash(seed) != observation.content_hash:
                    findings.append(self._finding("seed-changed", entry.path,
                                                  "Retained document seed is missing or changed"))
        return CheckResult(self, status="completed", pois=findings)


class WorkspaceResetCheck(WorkspaceCheck):
    """Identify content that reset or removal would discard."""

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("fdf2696b-6bd2-4cbc-ab3f-558b92dcc0c5"),
                          name="Tarav.Workspaces.ResetCheck", workflow=WORKSPACES_WORKFLOW_SHIP)

    def _run(self):
        findings = []
        for entry in self.workspace.manifest.entries:
            destination = _destination(self.workspace.root, entry.path)
            observation = self.setup.entries.get(entry.path)
            if observation is None:
                findings.append(self._finding("missing-setup", entry.path,
                                              "Cannot prove reset safety without setup data"))
                continue
            if isinstance(entry, RepositoryWorktree):
                repository = GitRepository(entry.repository)
                registered = next((item for item in repository.worktrees()
                                   if item.path == destination), None)
                if not destination.is_dir() or registered is None:
                    findings.append(self._finding("missing-worktree", entry.path,
                                                  "Cannot safely reset a missing worktree"))
                    continue
                if registered.branch != observation.branch:
                    findings.append(self._finding("worktree-branch", entry.path,
                                                  "Worktree branch changed"))
                if registered.commit != observation.commit:
                    findings.append(self._finding("worktree-commits", entry.path,
                                                  "Worktree has commits beyond its setup state",
                                                  initial=observation.commit,
                                                  current=registered.commit))
                if git_text(destination, "status", "--porcelain"):
                    findings.append(self._finding("dirty-worktree", entry.path,
                                                  "Worktree has uncommitted changes"))
            elif isinstance(entry, WorkspaceSymlink):
                if destination.exists() and not destination.is_symlink():
                    findings.append(self._finding("replaced-symlink", entry.path,
                                                  "A regular file replaced the declared symlink"))
            elif isinstance(entry, (CopiedDocument, NewDocument)):
                seed_name = entry.path if isinstance(entry, CopiedDocument) else entry.seed
                seed = self.workspace.root / "seeds" / seed_name
                if (not seed.is_file() or observation.content_hash is None or
                        _hash(seed) != observation.content_hash):
                    findings.append(self._finding("seed-changed", entry.path,
                                                  "Reset seed no longer matches setup"))
                if destination.exists() and (
                    not destination.is_file() or observation.content_hash is None or
                    _hash(destination) != observation.content_hash
                ):
                    findings.append(self._finding("changed-document", entry.path,
                                                  "Document differs from the initial copy"))
        return CheckResult(self, status="completed", pois=findings)


class WorkspaceRemovalCheck(WorkspaceCheck):
    """A completed workspace may leave commits on branches, but no dirty work."""

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("91c334aa-93bb-4a4f-b642-16311079293d"),
                          name="Tarav.Workspaces.RemovalCheck", workflow=WORKSPACES_WORKFLOW_SHIP)

    def _run(self):
        findings = []
        for entry in self.workspace.manifest.entries:
            if not isinstance(entry, RepositoryWorktree):
                continue
            destination = _destination(self.workspace.root, entry.path)
            repository = GitRepository(entry.repository)
            if not destination.is_dir() or not any(
                item.path == destination for item in repository.worktrees()
            ):
                findings.append(self._finding("missing-worktree", entry.path,
                                              "Worktree must be repaired before removal"))
            elif git_text(destination, "status", "--porcelain"):
                findings.append(self._finding("dirty-worktree", entry.path,
                                              "Worktree has uncommitted changes"))
        return CheckResult(self, status="completed", pois=findings)


# tarav.breadcrumb 78296941a115dbb68a0f8267930317269994eaf8d984d3055514cc1a244e0435
class WorkspaceReferenceCheck(Check):
    """Check one supplied file reference; no global reference scan is inferred."""

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("78a90f65-b35d-49c4-a506-294945a95b4e"),
                          name="Tarav.Workspaces.ReferenceCheck",
                          workflow=WORKSPACES_WORKFLOW_SHIP)

    def __init__(self, *, depot_root: Path, source: Path, target: Path):
        super().__init__()
        self.depot_root = Path(os.path.abspath(depot_root))
        self.source = Path(os.path.abspath(source))
        self.target = Path(os.path.abspath(target))

    def _run(self):
        try:
            relative = self.target.relative_to(self.depot_root)
        except ValueError:
            return CheckResult(self, status="completed")
        if len(relative.parts) < 2:
            return CheckResult(self, status="completed")
        workspace_root = self.depot_root / relative.parts[0]
        if self.source.is_relative_to(workspace_root):
            return CheckResult(self, status="completed")
        if not (workspace_root / "manifest.json").is_file():
            return CheckResult(self, status="completed")
        from .depot import WorkspaceDepot

        workspace = WorkspaceDepot(self.depot_root).open(relative.parts[0])
        poi = WorkspacePOI(
            self, "workspace-reference", "Stable surface refers into a Workspace",
            situation={"workspace": str(workspace.id), "source": str(self.source),
                       "target": str(self.target)},
            subject={"source": str(self.source), "target": str(self.target)},
        )
        return CheckResult(self, status="completed", pois=(poi,))


__all__ = [
    "WorkspaceIntegrityCheck", "WorkspacePOI", "WorkspaceReferenceCheck", "WorkspaceRemovalCheck",
    "WorkspaceResetCheck",
]
