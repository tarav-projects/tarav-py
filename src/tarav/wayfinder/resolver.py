# $kw: ^wayfinder-resolver-core --from Dependency.Profile.Split --note [CT] Wayfinder dispatches registered reference resolvers without importing any addressed domain upward --supp ^c20260811-62u
from __future__ import annotations

from collections.abc import Callable, Iterable
import hashlib

from .model import (
    UnsupportedWayfinderReference,
    WayfinderReference,
    WayfinderResolutionPOI,
    WayfinderResolutionResult,
    resolution_poi_id,
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
                if (
                    isinstance(result, WayfinderResolutionResult)
                    and reference.check is not None
                ):
                    check = reference.check
                    content = result.target.get("content")
                    valid = (
                        isinstance(check, dict)
                        and set(check) == {"sha256"}
                        and isinstance(content, str)
                        and hashlib.sha256(content.encode()).hexdigest()
                        == check["sha256"]
                    )
                    if not valid:
                        return WayfinderResolutionPOI(
                            instance_id=resolution_poi_id(
                                reference, "check-failed", remembered_location=None
                            ),
                            kind="check-failed",
                            reference=reference,
                            message="Reference content check failed or is unsupported",
                            trace=result.trace,
                            relocation_hints=(reference.hints,),
                        )
                return result
        raise UnsupportedWayfinderReference(
            f"unsupported Wayfinder reference type: {reference.type}"
        )


__all__ = ["Wayfinder", "WayfinderReferenceResolver"]
