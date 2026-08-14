# $kw: ^skillware-public --from Skw.Edition.History.Service --note [DF] public Skillware imports including EditionHistoryService, its support-resolver boundary, and value objects ^c20260725-12u --supp live Chatlas resolution authorized ^c20260725-15u
"""Skillware: the skill-development compilation system.

`.skillware/src/**/*.skw.md` sources compile to a skill's runnable files;
`tarav skillware build/check/status` is the deterministic toolchain.
"""

from tarav.skillware.model import SkwFinding, SkwRecipe, SkwSource, parse_skw_source
from tarav.skillware.context import (
    ContextReachabilityAudit,
    ContextLoadingEdge,
    ProjectedContextDependency,
    ProjectedContextPath,
    ProjectedContextReport,
    ProjectedContextStep,
    RuntimeFileRef,
    audit_context,
    project_context,
)
from tarav.skillware.edition_history import (
    AmendEditionSessionResult,
    EditionFile,
    EditionHistory,
    EditionHistoryCheckResult,
    EditionHistoryEntry,
    EditionHistoryError,
    EditionHistoryFinding,
    EditionHistoryService,
    EditionSession,
    EditionSupportResolutionError,
    EditionSupportResolver,
    RecordEditionSessionResult,
)

__all__ = [
    "AmendEditionSessionResult",
    "EditionFile",
    "EditionHistory",
    "EditionHistoryCheckResult",
    "EditionHistoryEntry",
    "EditionHistoryError",
    "EditionHistoryFinding",
    "EditionHistoryService",
    "EditionSession",
    "EditionSupportResolutionError",
    "EditionSupportResolver",
    "RecordEditionSessionResult",
    "ContextLoadingEdge",
    "ContextReachabilityAudit",
    "ProjectedContextDependency",
    "ProjectedContextPath",
    "ProjectedContextReport",
    "ProjectedContextStep",
    "RuntimeFileRef",
    "SkwFinding",
    "SkwRecipe",
    "SkwSource",
    "parse_skw_source",
    "audit_context",
    "project_context",
]
