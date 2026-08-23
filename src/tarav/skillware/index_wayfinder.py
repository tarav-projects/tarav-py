# $kw: ^wayfinder-resolver --from Wayfinder.Resolver --from Wayfinder.Reference.Type::Index.Block --from Index.Primary.Surface --note [DF] deterministic registry-to-Index block resolution over the record corpus ^c20260729-46u --note [DC] an Index block resolves to record coordinates and carries no path or line range, because the record stream is the Index.Primary.Surface and a file offset would name a projection instead of the thing itself
from __future__ import annotations

from tarav.indexlab import IndexResolutionError, IndexResolver, line_type
from tarav.indexlab.projection import ProjectedBlock
from tarav.wayfinder.model import (
    INDEX_BLOCK_TYPE,
    PACKAGE_SKILL_ROOT_TYPE,
    UnsupportedWayfinderReference,
    WayfinderReference,
    WayfinderResolutionPOI,
    WayfinderResolutionResult,
    WayfinderTraceStep,
    resolution_poi_id,
)
from tarav.wayfinder.registry import (
    CorruptWayfinderRegistry,
    WayfinderRegistration,
    WayfinderRegistry,
)
from tarav.wayfinder.resolver import Wayfinder


def create_index_wayfinder(
    registry: WayfinderRegistry | None = None,
) -> Wayfinder:
    return Wayfinder(
        registry=registry,
        resolvers=(resolve_index_block_reference,),
    )


def resolve_index_block_reference(
    reference: WayfinderReference,
    registry: WayfinderRegistry,
) -> WayfinderResolutionResult | WayfinderResolutionPOI | None:
    if reference.type != INDEX_BLOCK_TYPE:
        return None
    if reference.root.type != PACKAGE_SKILL_ROOT_TYPE:
        raise UnsupportedWayfinderReference(
            "index.block references require a package.skill root"
        )
    return _resolve_index_block(reference, registry)


def _resolve_index_block(
    reference: WayfinderReference,
    registry: WayfinderRegistry,
) -> WayfinderResolutionResult | WayfinderResolutionPOI:
    trace: list[WayfinderTraceStep] = []
    if not isinstance(reference.address, str) or not reference.address:
        raise UnsupportedWayfinderReference(
            "index.block reference address must be a non-empty string"
        )
    try:
        registration = registry.get(reference.root)
    except CorruptWayfinderRegistry as exc:
        trace.append(
            WayfinderTraceStep(
                stage="registry.lookup",
                status="malformed",
                detail={"registry": str(registry.path), "error": str(exc)},
            )
        )
        return _poi(reference, "malformed", str(exc), trace)
    if registration is None:
        trace.append(
            WayfinderTraceStep(
                stage="registry.lookup",
                status="missing",
                detail={"root": reference.root.as_dict()},
            )
        )
        return _poi(
            reference,
            "missing",
            f"no Wayfinder registration for root {reference.root.id!r}",
            trace,
        )
    trace.append(
        WayfinderTraceStep(
            stage="registry.lookup",
            status="resolved",
            detail={
                "root": reference.root.as_dict(),
                "path": str(registration.path),
                "verified_at": registration.verified_at,
            },
        )
    )

    try:
        resolver = IndexResolver.for_path(registration.path)
    except IndexResolutionError as exc:
        trace.append(
            WayfinderTraceStep(
                stage="index.lookup",
                status="unreachable",
                detail={"path": str(registration.path), "error": str(exc)},
            )
        )
        return _poi(
            reference,
            "unreachable",
            f"cannot read the Index records for {registration.path}: {exc}",
            trace,
            registration=registration,
        )

    matches = tuple(
        block for block in resolver.blocks() if block.name == reference.address
    )
    trace.append(
        WayfinderTraceStep(
            stage="index.lookup",
            status=(
                "resolved"
                if len(matches) == 1
                else "missing"
                if not matches
                else "ambiguous"
            ),
            detail={"block_path": reference.address, "match_count": len(matches)},
        )
    )
    if not matches:
        return _poi(
            reference,
            "missing",
            f"Index block does not resolve: {reference.address}",
            trace,
            registration=registration,
        )
    if len(matches) > 1:
        return _poi(
            reference,
            "ambiguous",
            f"Index block resolves more than once: {reference.address}",
            trace,
            registration=registration,
            candidates=tuple(_candidate(block) for block in matches),
        )

    target = resolved_index_block_target(resolver, matches[0])
    trace.append(
        WayfinderTraceStep(
            stage="index.verify",
            status="verified",
            detail={
                "block_id": target["block_id"],
                "isoblock_id": target["isoblock_id"],
                "line_count": len(target["line_ids"]),
            },
        )
    )
    return WayfinderResolutionResult(
        reference=reference,
        target=target,
        trace=tuple(trace),
    )


def _candidate(block: ProjectedBlock) -> dict[str, object]:
    return {
        "block_path": block.name,
        "block_id": block.id,
        "isoblock_id": block.isoblock_id,
    }


def resolved_index_block_target(
    resolver: IndexResolver,
    block: ProjectedBlock,
) -> dict[str, object]:
    """The block's record coordinates and its `Kernel.Writing` rendering."""
    lines = resolver.content_lines(block.name)
    return {
        "kind": "index.block",
        "block_path": block.name,
        "block_id": block.id,
        "isoblock_id": block.isoblock_id,
        "line_ids": [line.id for line in lines],
        "content": render_block(block, lines),
    }


def render_block(block: ProjectedBlock, lines) -> str:
    """One block as readable `Kernel.Writing`: a heading and its typed lines."""
    body = [f"## {block.name}"]
    body.extend(f"- [{line_type(line)}] {line.text}" for line in lines)
    return "\n".join(body)


def _poi(
    reference: WayfinderReference,
    kind: str,
    message: str,
    trace: list[WayfinderTraceStep],
    *,
    registration: WayfinderRegistration | None = None,
    candidates: tuple[dict[str, object], ...] = (),
) -> WayfinderResolutionPOI:
    remembered = str(registration.path) if registration is not None else None
    hints = registration.relocation_hints if registration is not None else ()
    return WayfinderResolutionPOI(
        instance_id=resolution_poi_id(
            reference,
            kind,
            remembered_location=remembered,
            candidates=candidates,
        ),
        kind=kind,
        reference=reference,
        message=message,
        trace=tuple(trace),
        remembered_location=remembered,
        relocation_hints=hints,
        candidates=candidates,
    )


__all__ = [
    "create_index_wayfinder",
    "render_block",
    "resolve_index_block_reference",
    "resolved_index_block_target",
]
