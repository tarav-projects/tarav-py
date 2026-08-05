from __future__ import annotations

from dataclasses import dataclass

from .model.nodes import IndexSurfaceKind


@dataclass(frozen=True)
class IndexSurfacePolicy:
    kind: IndexSurfaceKind
    reviewed_surface: bool
    requires_typed_lines: bool
    requires_grounding: bool
    issue_blocks: bool = False


_POLICIES: dict[IndexSurfaceKind, IndexSurfacePolicy] = {
    "router": IndexSurfacePolicy("router", True, False, False),
    "chapter": IndexSurfacePolicy("chapter", True, False, False),
    "appendix": IndexSurfacePolicy("appendix", True, False, False),
    "agendix": IndexSurfacePolicy("agendix", False, True, True),
    "issues": IndexSurfacePolicy("issues", False, True, True, issue_blocks=True),
    "unknown": IndexSurfacePolicy("unknown", False, False, False),
}


def surface_policy(kind: IndexSurfaceKind) -> IndexSurfacePolicy:
    return _POLICIES[kind]


def reserved_surface_folders() -> frozenset[str]:
    return frozenset({"appendix", "agendix", "issues"})

