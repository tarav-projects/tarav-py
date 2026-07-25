# $kw: ^skillware-public --from Skw.Edition.History.Service --note [DF] public Skillware imports including EditionHistoryService, its support-resolver boundary, and value objects ^c20260725-12u --supp live Chatlas resolution authorized ^c20260725-15u
"""Skillware: the skill-development compilation system.

`.skillware/src/**/*.skw.md` sources compile to a skill's runnable files;
`agentos skillware build/check/status` is the deterministic toolchain.
"""

from agentos.skillware.model import SkwFinding, SkwRecipe, SkwSource, parse_skw_source
from agentos.skillware.edition_history import (
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
    "SkwFinding",
    "SkwRecipe",
    "SkwSource",
    "parse_skw_source",
]
