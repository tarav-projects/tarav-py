# $kw: ^wayfinder-resolver-core --from Dependency.Profile.Split --note [CT] Wayfinder dispatches registered reference resolvers without importing any addressed domain upward --supp ^c20260811-62u
from __future__ import annotations

from collections.abc import Callable, Iterable

from .model import (
    UnsupportedWayfinderReference,
    WayfinderReference,
    WayfinderResolutionPOI,
    WayfinderResolutionResult,
)
from .registry import WayfinderRegistry


WayfinderReferenceResolver = Callable[
    [WayfinderReference, WayfinderRegistry],
    WayfinderResolutionResult | WayfinderResolutionPOI | None,
]


class Wayfinder:
    def __init__(
        self,
        registry: WayfinderRegistry | None = None,
        *,
        resolvers: Iterable[WayfinderReferenceResolver] = (),
    ) -> None:
        self.registry = registry or WayfinderRegistry()
        self.resolvers = tuple(resolvers)

    def resolve(
        self,
        reference: WayfinderReference,
    ) -> WayfinderResolutionResult | WayfinderResolutionPOI:
        for resolver in self.resolvers:
            result = resolver(reference, self.registry)
            if result is not None:
                return result
        raise UnsupportedWayfinderReference(
            f"unsupported Wayfinder reference type: {reference.type}"
        )


__all__ = ["Wayfinder", "WayfinderReferenceResolver"]
