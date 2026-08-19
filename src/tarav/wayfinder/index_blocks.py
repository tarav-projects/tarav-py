# $kw: ^wayfinder-resolver --from Wayfinder.Resolver --from Wayfinder.Reference.Type::Index.Block --note [DF] deterministic registry-to-Index block resolution over the parser-backed model ^c20260729-46u
from __future__ import annotations

from pathlib import Path

from tarav.index_model import BlockHeading, IndexDocument, parse_depot
from tarav.wayfinder.resolver import Wayfinder

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
    if not registration.path.is_dir() or not (
        registration.path / "000-INDEX.md"
    ).is_file():
        trace.append(
            WayfinderTraceStep(
                stage="index.lookup",
                status="stale",
                detail={"path": str(registration.path)},
            )
        )
        return _poi(
            reference,
            "stale",
            f"remembered Index root is no longer reachable: {registration.path}",
            trace,
            registration=registration,
        )

    try:
        model = parse_depot(registration.path)
    except OSError as exc:
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
            f"cannot read Index root {registration.path}: {exc}",
            trace,
            registration=registration,
        )

    matches: list[tuple[IndexDocument, BlockHeading]] = []
    for document in model.documents:
        for node in document.nodes:
            if (
                isinstance(node, BlockHeading)
                and node.parsed.get("path") == reference.address
            ):
                matches.append((document, node))
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
    candidates = tuple(_candidate(document, heading) for document, heading in matches)
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
            candidates=candidates,
        )

    document, heading = matches[0]
    target = _resolved_block_target(document, heading, registration.path)
    trace.append(
        WayfinderTraceStep(
            stage="index.verify",
            status="verified",
            detail={
                "path": target["path"],
                "start_line": target["start_line"],
                "end_line": target["end_line"],
            },
        )
    )
    return WayfinderResolutionResult(
        reference=reference,
        target=target,
        trace=tuple(trace),
    )


def _candidate(
    document: IndexDocument, heading: BlockHeading
) -> dict[str, object]:
    return {
        "path": str(document.path) if document.path is not None else "",
        "block_path": heading.parsed.get("path", ""),
        "line": heading.start_line,
    }


def _resolved_block_target(
    document: IndexDocument,
    heading: BlockHeading,
    root: Path,
) -> dict[str, object]:
    if document.path is None:
        raise RuntimeError("parsed Index block has no source path")
    nodes = document.nodes
    heading_index = nodes.index(heading)
    end_line = max(node.end_line for node in nodes[heading_index:])
    for node in nodes[heading_index + 1 :]:
        if isinstance(node, BlockHeading) or node.type == "Separator":
            end_line = node.start_line - 1
            break
    lines = document.path.read_text(encoding="utf-8").splitlines()
    selected = lines[heading.start_line - 1 : end_line]
    while selected and not selected[-1].strip():
        selected.pop()
    actual_end = heading.start_line + len(selected) - 1
    return {
        "kind": "index.block",
        "root": str(root),
        "path": str(document.path),
        "block_path": heading.parsed["path"],
        "start_line": heading.start_line,
        "end_line": actual_end,
        "content": "\n".join(selected),
    }


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


__all__ = ["create_index_wayfinder", "resolve_index_block_reference"]
