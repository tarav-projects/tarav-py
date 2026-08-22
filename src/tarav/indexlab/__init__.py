# $kw: --from User.Touched --from Agentos.Bloberia
"""Experimental recording kernel for context-attached Touched.Index records."""

from .model import (
    RECORD_SCHEMA,
    EvidenceNeighborhood,
    IndexRecord,
    MessageRef,
    Operation,
    RecordContext,
    RecordModelError,
    SupportSet,
    TurnRef,
)
from .workspace import (
    WORKSPACE_MARKER,
    WORKSPACE_SCHEMA,
    CargoDefect,
    IndexLabWorkspace,
    RecordStore,
    WorkspaceError,
)
from .projection import (
    PROJECTION_SCHEMA,
    ProjectedBlock,
    ProjectedLine,
    ProjectionError,
    SemanticProjection,
    fold_records,
    project_records,
    union_support,
)
from .touch import (
    ChatlasTouchSource,
    Resolution,
    TouchContext,
    TouchMessage,
    UserTouchMock,
    UserTouchSource,
)
from .linter import LintFinding, LintReport, lint_records, lint_store

__all__ = [
    "RECORD_SCHEMA",
    "PROJECTION_SCHEMA",
    "WORKSPACE_MARKER",
    "WORKSPACE_SCHEMA",
    "CargoDefect",
    "EvidenceNeighborhood",
    "ChatlasTouchSource",
    "IndexLabWorkspace",
    "IndexRecord",
    "LintFinding",
    "LintReport",
    "MessageRef",
    "Operation",
    "ProjectedBlock",
    "ProjectedLine",
    "ProjectionError",
    "RecordContext",
    "RecordModelError",
    "RecordStore",
    "Resolution",
    "SupportSet",
    "SemanticProjection",
    "TouchContext",
    "TouchMessage",
    "TurnRef",
    "UserTouchMock",
    "UserTouchSource",
    "WorkspaceError",
    "fold_records",
    "project_records",
    "lint_records",
    "lint_store",
    "union_support",
]
