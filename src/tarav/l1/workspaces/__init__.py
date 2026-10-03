"""Manifest-backed, identified working folders outside Project roots."""

from .checks import (
    WorkspaceIntegrityCheck, WorkspacePOI, WorkspaceReferenceCheck,
    WorkspaceRemovalCheck, WorkspaceResetCheck,
)
from .depot import WorkspaceDepot, WorkspaceError
from .model import (
    WORKSPACE_RECORD_TYPES, CopiedDocument, NewDocument, RepositoryWorktree,
    Workspace, WorkspaceManifest, WorkspaceSetupRecord, WorkspaceSymlink,
)
from .root import resolve_workspaces_root
from .workflow import WorkspacesWorkflow

__all__ = [
    "CopiedDocument", "NewDocument", "RepositoryWorktree", "Workspace",
    "WorkspaceDepot", "WorkspaceError", "WorkspaceIntegrityCheck",
    "WorkspaceManifest", "WorkspacePOI", "WorkspaceReferenceCheck",
    "WorkspaceRemovalCheck", "WorkspaceResetCheck",
    "WorkspaceSetupRecord", "WorkspaceSymlink", "WorkspacesWorkflow",
    "WORKSPACE_RECORD_TYPES", "resolve_workspaces_root",
]
