# $kw: Related.Surface.Resolution --from Skw.Network --from Wayfinder.Resolver
# --note [DC] related-surface resolution is a bounded general workflow over explicit managed-block relationships ^c20260820-5u
"""Bounded traversal of explicit relationships between managed surfaces."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from tarav.wayfinder import (
    Wayfinder,
    WayfinderReference,
    WayfinderResolutionPOI,
    WayfinderResolutionResult,
    parse_reference,
)


Projection = Literal["root", "direct", "reachable"]


@dataclass(frozen=True)
class RelatedSurfaceNode:
    reference: WayfinderReference
    target: dict[str, object]
    depth: int

    def as_dict(self) -> dict[str, object]:
        return {
            "reference": self.reference.as_dict(),
            "target": self.target,
            "depth": self.depth,
        }


@dataclass(frozen=True)
class RelatedSurfaceDiagnostic:
    reference: WayfinderReference
    source: WayfinderReference | None
    relationship: str | None
    kind: str
    message: str

    def as_dict(self) -> dict[str, object]:
        return {
            "reference": self.reference.as_dict(),
            "source": self.source.as_dict() if self.source is not None else None,
            "relationship": self.relationship,
            "kind": self.kind,
            "message": self.message,
        }


@dataclass(frozen=True)
class RelatedSurfaceProjection:
    projection: Projection
    nodes: tuple[RelatedSurfaceNode, ...]
    diagnostics: tuple[RelatedSurfaceDiagnostic, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "projection": self.projection,
            "nodes": [node.as_dict() for node in self.nodes],
            "diagnostics": [item.as_dict() for item in self.diagnostics],
        }


class RelatedSurfaceResolver:
    """Resolve root, direct, or reachable context without parsing host files."""

    def __init__(self, wayfinder: Wayfinder) -> None:
        self._wayfinder = wayfinder

    def resolve(
        self,
        reference: WayfinderReference,
        *,
        projection: Projection = "root",
        max_depth: int = 8,
        max_nodes: int = 256,
    ) -> RelatedSurfaceProjection:
        if projection not in {"root", "direct", "reachable"}:
            raise ValueError(f"unknown related-surface projection: {projection}")
        if max_depth < 1:
            raise ValueError("max_depth must be at least 1")
        if max_nodes < 1:
            raise ValueError("max_nodes must be at least 1")

        depth_limit = 0 if projection == "root" else 1 if projection == "direct" else max_depth
        pending: list[tuple[int, WayfinderReference, WayfinderReference | None, str | None]] = [
            (0, reference, None, None)
        ]
        seen: set[str] = set()
        cache: dict[str, WayfinderResolutionResult | WayfinderResolutionPOI] = {}
        nodes: list[RelatedSurfaceNode] = []
        diagnostics: list[RelatedSurfaceDiagnostic] = []

        while pending and len(nodes) < max_nodes:
            depth, current, source, relationship = pending.pop(0)
            key = current.to_json()
            if key in seen:
                continue
            seen.add(key)
            result = cache.setdefault(key, self._wayfinder.resolve(current))
            if isinstance(result, WayfinderResolutionPOI):
                diagnostics.append(
                    RelatedSurfaceDiagnostic(
                        reference=current,
                        source=source,
                        relationship=relationship,
                        kind=result.kind,
                        message=result.message,
                    )
                )
                continue
            nodes.append(
                RelatedSurfaceNode(
                    reference=current,
                    target=result.target,
                    depth=depth,
                )
            )
            if depth >= depth_limit:
                continue
            edges = _relationships(result.target, current)
            pending.extend(
                (depth + 1, target, current, kind)
                for kind, target in sorted(
                    edges,
                    key=lambda item: (item[0], item[1].to_json()),
                )
            )

        return RelatedSurfaceProjection(
            projection=projection,
            nodes=tuple(nodes),
            diagnostics=tuple(diagnostics),
        )


def _relationships(
    target: dict[str, object],
    source: WayfinderReference,
) -> tuple[tuple[str, WayfinderReference], ...]:
    raw = target.get("relationships", ())
    if not isinstance(raw, (list, tuple)):
        return ()
    edges: list[tuple[str, WayfinderReference]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        kind = item.get("kind")
        address = item.get("address")
        if not isinstance(kind, str) or not isinstance(address, str) or not address:
            continue
        reference = (
            parse_reference(address)
            if "://" in address or address.lstrip().startswith("{")
            else WayfinderReference(
                type=source.type,
                root=source.root,
                address=address,
            )
        )
        edges.append((kind, reference))
    return tuple(edges)


__all__ = [
    "RelatedSurfaceDiagnostic",
    "RelatedSurfaceNode",
    "RelatedSurfaceProjection",
    "RelatedSurfaceResolver",
]
