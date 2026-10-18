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
    """Family, never raised: a Workspace differs from what its manifest and setup declare."""

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("9635b752-a8fa-4b5c-a48d-217cf46895ab"),
                          name="Tarav.Workspaces.POI", workflow=WORKSPACES_WORKFLOW_SHIP)


class WorkspaceSetupMissing(WorkspacePOI):
    """A Workspace entry has no setup observation."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("a373374f-1984-439f-ba8a-73048804b7cb"),
                          name="Tarav.Workspaces.POI.SetupMissing", workflow=WORKSPACES_WORKFLOW_SHIP)


class WorkspaceWorktreeMissing(WorkspacePOI):
    """A declared Workspace worktree is missing or unregistered."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("e857dea9-c0c0-4986-a689-749eeed02144"),
                          name="Tarav.Workspaces.POI.WorktreeMissing", workflow=WORKSPACES_WORKFLOW_SHIP)


class WorkspaceWorktreeBranchChanged(WorkspacePOI):
    """A Workspace worktree is on a different branch than declared."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("af2b126e-e0fa-4b44-b660-655e2e33d0c3"),
                          name="Tarav.Workspaces.POI.WorktreeBranchChanged", workflow=WORKSPACES_WORKFLOW_SHIP)


class WorkspaceSeedChanged(WorkspacePOI):
    """A retained Workspace seed is missing or changed."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("e767039a-96f0-47ee-ab2c-a254bb66bcd7"),
                          name="Tarav.Workspaces.POI.SeedChanged", workflow=WORKSPACES_WORKFLOW_SHIP)


class WorkspaceCopySourceChanged(WorkspacePOI):
    """The source of a Workspace copy changed after setup."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("85981726-4e40-4d96-aa0d-23bc20dbaa86"),
                          name="Tarav.Workspaces.POI.CopySourceChanged", workflow=WORKSPACES_WORKFLOW_SHIP)


class WorkspaceCopySourceMissing(WorkspacePOI):
    """The source of a Workspace copy is unavailable."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("e1481a63-59d8-4447-8866-43e8a6bebecd"),
                          name="Tarav.Workspaces.POI.CopySourceMissing", workflow=WORKSPACES_WORKFLOW_SHIP)


class WorkspaceSymlinkBroken(WorkspacePOI):
    """A declared Workspace symlink does not resolve."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("f9d5bbf9-4494-47c9-83ba-9ba77906baa4"),
                          name="Tarav.Workspaces.POI.SymlinkBroken", workflow=WORKSPACES_WORKFLOW_SHIP)


class WorkspaceWorktreeCommitsAhead(WorkspacePOI):
    """A Workspace worktree has commits beyond its setup state."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("b8c4eeee-d044-4ff0-bb6a-e8b128a9139a"),
                          name="Tarav.Workspaces.POI.WorktreeCommitsAhead", workflow=WORKSPACES_WORKFLOW_SHIP)


class WorkspaceWorktreeDirty(WorkspacePOI):
    """A Workspace worktree has uncommitted changes."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("04783fba-a241-43b5-96de-77ae2c8f3868"),
                          name="Tarav.Workspaces.POI.WorktreeDirty", workflow=WORKSPACES_WORKFLOW_SHIP)


class WorkspaceSymlinkReplaced(WorkspacePOI):
    """A regular file replaced a declared Workspace symlink."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("dbc6ec95-610d-42a0-b064-7543e01f9995"),
                          name="Tarav.Workspaces.POI.SymlinkReplaced", workflow=WORKSPACES_WORKFLOW_SHIP)


class WorkspaceDocumentChanged(WorkspacePOI):
    """A Workspace document differs from its initial copy."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("a2d848d4-bb2f-4353-9658-a240f6d28420"),
                          name="Tarav.Workspaces.POI.DocumentChanged", workflow=WORKSPACES_WORKFLOW_SHIP)


class WorkspaceReferencedByStableSurface(WorkspacePOI):
    """A stable surface refers into a disposable Workspace."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("2307afc8-7fc3-493e-9b09-64bf009882ef"),
                          name="Tarav.Workspaces.POI.ReferencedByStableSurface", workflow=WORKSPACES_WORKFLOW_SHIP)


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

# tarav.breadcrumb 740c4ce06141
    def _poi(self, case: type[WorkspacePOI], path: str, message: str,
                 **details) -> WorkspacePOI:
        return case(
            self, message,
            situation={"workspace": str(self.workspace.id), "path": path},
            details=details,
        )


# tarav.breadcrumb 703f434472a8
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
                findings.append(self._poi(WorkspaceSetupMissing, entry.path,
                                              "Entry has no setup observation"))
                continue
            if isinstance(entry, RepositoryWorktree):
                repository = GitRepository(entry.repository)
                registered = next((item for item in repository.worktrees()
                                   if item.path == destination), None)
                if not destination.is_dir() or registered is None:
                    findings.append(self._poi(WorkspaceWorktreeMissing, entry.path,
                                                  "Declared worktree is missing or unregistered"))
                elif registered.branch != observation.branch:
                    findings.append(self._poi(WorkspaceWorktreeBranchChanged, entry.path,
                                                  "Worktree is on a different branch",
                                                  expected=observation.branch,
                                                  actual=registered.branch))
            elif isinstance(entry, CopiedDocument):
                seed = self.workspace.root / "seeds" / entry.path
                if not seed.is_file() or _hash(seed) != observation.content_hash:
                    findings.append(self._poi(WorkspaceSeedChanged, entry.path,
                                                  "Retained copy seed is missing or changed"))
                source = Path(entry.source)
                if observation.source_hash is not None and source.is_file() and \
                        _hash(source) != observation.source_hash:
                    findings.append(self._poi(WorkspaceCopySourceChanged, entry.path,
                                                  "Copy source changed after setup",
                                                  expected=observation.source_hash,
                                                  actual=_hash(source)))
                elif not source.is_file():
                    findings.append(self._poi(WorkspaceCopySourceMissing, entry.path,
                                                  "Copy source is unavailable"))
            elif isinstance(entry, WorkspaceSymlink) and not destination.exists():
                findings.append(self._poi(WorkspaceSymlinkBroken, entry.path,
                                              "Declared symlink does not resolve"))
            elif isinstance(entry, NewDocument):
                seed = self.workspace.root / "seeds" / entry.seed
                if not seed.is_file() or _hash(seed) != observation.content_hash:
                    findings.append(self._poi(WorkspaceSeedChanged, entry.path,
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
                findings.append(self._poi(WorkspaceSetupMissing, entry.path,
                                              "Cannot prove reset safety without setup data"))
                continue
            if isinstance(entry, RepositoryWorktree):
                repository = GitRepository(entry.repository)
                registered = next((item for item in repository.worktrees()
                                   if item.path == destination), None)
                if not destination.is_dir() or registered is None:
                    findings.append(self._poi(WorkspaceWorktreeMissing, entry.path,
                                                  "Cannot safely reset a missing worktree"))
                    continue
                if registered.branch != observation.branch:
                    findings.append(self._poi(WorkspaceWorktreeBranchChanged, entry.path,
                                                  "Worktree branch changed"))
                if registered.commit != observation.commit:
                    findings.append(self._poi(WorkspaceWorktreeCommitsAhead, entry.path,
                                                  "Worktree has commits beyond its setup state",
                                                  initial=observation.commit,
                                                  current=registered.commit))
                if git_text(destination, "status", "--porcelain"):
                    findings.append(self._poi(WorkspaceWorktreeDirty, entry.path,
                                                  "Worktree has uncommitted changes"))
            elif isinstance(entry, WorkspaceSymlink):
                if destination.exists() and not destination.is_symlink():
                    findings.append(self._poi(WorkspaceSymlinkReplaced, entry.path,
                                                  "A regular file replaced the declared symlink"))
            elif isinstance(entry, (CopiedDocument, NewDocument)):
                seed_name = entry.path if isinstance(entry, CopiedDocument) else entry.seed
                seed = self.workspace.root / "seeds" / seed_name
                if (not seed.is_file() or observation.content_hash is None or
                        _hash(seed) != observation.content_hash):
                    findings.append(self._poi(WorkspaceSeedChanged, entry.path,
                                                  "Reset seed no longer matches setup"))
                if destination.exists() and (
                    not destination.is_file() or observation.content_hash is None or
                    _hash(destination) != observation.content_hash
                ):
                    findings.append(self._poi(WorkspaceDocumentChanged, entry.path,
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
                findings.append(self._poi(WorkspaceWorktreeMissing, entry.path,
                                              "Worktree must be repaired before removal"))
            elif git_text(destination, "status", "--porcelain"):
                findings.append(self._poi(WorkspaceWorktreeDirty, entry.path,
                                              "Worktree has uncommitted changes"))
        return CheckResult(self, status="completed", pois=findings)


# tarav.breadcrumb 78296941a115
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
        poi = WorkspaceReferencedByStableSurface(
            self, "Stable surface refers into a Workspace",
            situation={"workspace": str(workspace.id), "source": str(self.source),
                       "target": str(self.target)},
        )
        return CheckResult(self, status="completed", pois=(poi,))


WORKSPACE_POI_TYPES = (
    WorkspacePOI,
    WorkspaceSetupMissing,
    WorkspaceWorktreeMissing,
    WorkspaceWorktreeBranchChanged,
    WorkspaceSeedChanged,
    WorkspaceCopySourceChanged,
    WorkspaceCopySourceMissing,
    WorkspaceSymlinkBroken,
    WorkspaceWorktreeCommitsAhead,
    WorkspaceWorktreeDirty,
    WorkspaceSymlinkReplaced,
    WorkspaceDocumentChanged,
    WorkspaceReferencedByStableSurface,
)

__all__ = [
    "WORKSPACE_POI_TYPES",
    "WorkspaceIntegrityCheck", "WorkspacePOI", "WorkspaceReferenceCheck", "WorkspaceRemovalCheck",
    "WorkspaceResetCheck",
]
