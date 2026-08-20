# $kw: --from Skw.Network --from Wayfinder.Reference --note [DF] statically resolves addressed Skillware blocks on configured managed code surfaces ^c20260820-5u
"""Skillware-owned Wayfinder resolution for project-managed blocks."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from tarav._core.project import TARAV_PROJECT_ID
from tarav.index_model import BlockHeading, parse_depot
from tarav.skillware._build_core import load_project_skw_config
from tarav.skillware._code_surfaces import (
    DEFAULT_CODE_BACKENDS,
    annotation_point,
    expand_code_surfaces,
)
from tarav.skillware.model import SkwConstruct, SkwDependency, SkwRecipe
from tarav.wayfinder.model import (
    MANAGED_BLOCK_TYPE,
    PROJECT_ROOT_TYPE,
    UnsupportedWayfinderReference,
    WayfinderReference,
    WayfinderReferenceRoot,
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


@dataclass(frozen=True)
class _HostedBlock:
    path: Path
    address: str
    line: int
    end_line: int
    host_kind: str
    host_name: str
    content: str
    relationships: tuple[dict[str, str], ...]


def create_managed_wayfinder(
    registry: WayfinderRegistry | None = None,
) -> Wayfinder:
    """Create a resolver for general project-managed Skillware blocks."""

    return Wayfinder(registry=registry, resolvers=(_cached_resolver(),))


def create_tarav_wayfinder(
    registry: WayfinderRegistry | None = None,
    *,
    project_root: Path | None = None,
) -> Wayfinder:
    """Compose Tarav's Markdown and managed-code block resolvers.

    Passing ``project_root`` records the source project's stable identity in
    Wayfinder. Installed callers may instead provision that registration by
    the normal Wayfinder workflow.
    """

    from tarav.wayfinder.index_blocks import resolve_index_block_reference

    selected = registry or WayfinderRegistry()
    if project_root is not None:
        root = WayfinderReferenceRoot(type=PROJECT_ROOT_TYPE, id=TARAV_PROJECT_ID)
        if selected.get(root) is None:
            selected.register(root, project_root)
    return Wayfinder(
        registry=selected,
        resolvers=(_cached_resolver(), resolve_index_block_reference),
    )


def _cached_resolver():
    discovered: dict[Path, tuple[_HostedBlock, ...]] = {}

    def resolve(
        reference: WayfinderReference,
        registry: WayfinderRegistry,
    ) -> WayfinderResolutionResult | WayfinderResolutionPOI | None:
        return resolve_managed_block_reference(
            reference,
            registry,
            _discovered=discovered,
        )

    return resolve


def resolve_managed_block_reference(
    reference: WayfinderReference,
    registry: WayfinderRegistry,
    *,
    _discovered: dict[Path, tuple[_HostedBlock, ...]] | None = None,
) -> WayfinderResolutionResult | WayfinderResolutionPOI | None:
    if reference.type != MANAGED_BLOCK_TYPE:
        return None
    if reference.root.type != PROJECT_ROOT_TYPE:
        raise UnsupportedWayfinderReference(
            "managed.block references require an agentos.project root"
        )
    if not isinstance(reference.address, str) or not reference.address:
        raise UnsupportedWayfinderReference(
            "managed.block address must be a non-empty string"
        )
    return _resolve(reference, registry, discovered=_discovered)


def _resolve(
    reference: WayfinderReference,
    registry: WayfinderRegistry,
    *,
    discovered: dict[Path, tuple[_HostedBlock, ...]] | None,
) -> WayfinderResolutionResult | WayfinderResolutionPOI:
    trace: list[WayfinderTraceStep] = []
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
            detail={"path": str(registration.path)},
        )
    )
    if not registration.path.is_dir():
        return _poi(
            reference,
            "stale",
            f"remembered project root is no longer reachable: {registration.path}",
            trace,
            registration=registration,
        )

    if discovered is None:
        blocks = _discover(registration.path)
    else:
        blocks = discovered.get(registration.path)
        if blocks is None:
            blocks = _discover(registration.path)
            discovered[registration.path] = blocks
    matches = tuple(
        block
        for block in blocks
        if block.address == reference.address
    )
    trace.append(
        WayfinderTraceStep(
            stage="managed.lookup",
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
    candidates = tuple(_candidate(block, registration.path) for block in matches)
    if not matches:
        return _poi(
            reference,
            "missing",
            f"managed block does not resolve: {reference.address}",
            trace,
            registration=registration,
        )
    if len(matches) > 1:
        return _poi(
            reference,
            "ambiguous",
            f"managed block resolves more than once: {reference.address}",
            trace,
            registration=registration,
            candidates=candidates,
        )

    block = matches[0]
    target = {
        "kind": "managed.block",
        "root": str(registration.path),
        "path": str(block.path),
        "block_path": block.address,
        "start_line": block.line,
        "end_line": block.end_line,
        "host": {"kind": block.host_kind, "name": block.host_name},
        "content": block.content,
        "relationships": list(block.relationships),
    }
    trace.append(
        WayfinderTraceStep(
            stage="managed.verify",
            status="verified",
            detail={
                "path": str(block.path),
                "host_kind": block.host_kind,
                "host_name": block.host_name,
            },
        )
    )
    return WayfinderResolutionResult(
        reference=reference,
        target=target,
        trace=tuple(trace),
    )


def _discover(project_root: Path) -> tuple[_HostedBlock, ...]:
    config = load_project_skw_config(project_root)
    targets = expand_code_surfaces(
        project_root,
        config.code_surfaces,
        backends=DEFAULT_CODE_BACKENDS,
    )
    found: list[_HostedBlock] = []
    for target in targets:
        backend = DEFAULT_CODE_BACKENDS.get(target.language)
        if backend is None:
            continue
        model = backend.model(target.path.read_text(encoding="utf-8", errors="replace"))
        if model.surface.diagnostics:
            continue
        blocks: tuple[SkwRecipe | SkwConstruct | SkwDependency, ...] = (
            *model.annotations.recipes,
            *model.annotations.constructs,
            *model.annotations.dependencies,
        )
        for block in blocks:
            if block.address is None:
                continue
            point = annotation_point(model, block.line)
            if point is None or point[0] not in target.allow_points:
                continue
            notes = tuple(
                note
                for note in model.annotations.notes
                if note.address == block.address
            )
            content_lines = [f"## {block.address}"]
            for note in notes:
                marker = f"[{note.type}] " if note.type is not None else ""
                anchor = f" {note.anchor}" if note.anchor is not None else ""
                content_lines.append(f"- {marker}{note.text}{anchor}")
            host_point = next(
                (
                    candidate
                    for candidate in model.surface.host_points
                    if candidate.kind == point[0] and candidate.name == point[1]
                ),
                None,
            )
            if host_point is not None:
                source_lines = [line.text for line in model.surface.lines]
                hosted_source = "\n".join(
                    source_lines[
                        host_point.span.start_line - 1 : host_point.span.end_line
                    ]
                )
                content_lines.append(
                    f"```{target.language}\n{hosted_source}\n```"
                )
            relationships = tuple(
                {"kind": kind, "address": address}
                for kind, addresses in (("from", block.froms), ("cite", block.cites))
                for address in addresses
            )
            found.append(
                _HostedBlock(
                    path=target.path,
                    address=block.address,
                    line=block.line,
                    end_line=block.decl_span[1],
                    host_kind=point[0],
                    host_name=point[1],
                    content="\n\n".join(content_lines),
                    relationships=relationships,
                )
            )
    from tarav.wayfinder.index_blocks import resolved_index_block_target

    for raw_depot in config.depots:
        depot_root = (project_root / raw_depot).resolve()
        if not (depot_root / "000-INDEX.md").is_file():
            continue
        depot = parse_depot(depot_root)
        for document in depot.documents:
            for node in document.nodes:
                if not isinstance(node, BlockHeading):
                    continue
                address = node.parsed.get("path")
                if not isinstance(address, str) or not address:
                    continue
                target = resolved_index_block_target(document, node, depot_root)
                found.append(
                    _HostedBlock(
                        path=Path(str(target["path"])),
                        address=address,
                        line=int(target["start_line"]),
                        end_line=int(target["end_line"]),
                        host_kind="index.block",
                        host_name=address,
                        content=str(target["content"]),
                        relationships=(),
                    )
                )
    return tuple(sorted(found, key=lambda item: (str(item.path), item.line)))


def _candidate(block: _HostedBlock, root: Path) -> dict[str, object]:
    try:
        path = block.path.relative_to(root)
    except ValueError:
        path = block.path
    return {
        "path": str(path),
        "block_path": block.address,
        "line": block.line,
        "host": {"kind": block.host_kind, "name": block.host_name},
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
        relocation_hints=(
            registration.relocation_hints if registration is not None else ()
        ),
        candidates=candidates,
    )


__all__ = [
    "create_managed_wayfinder",
    "create_tarav_wayfinder",
    "resolve_managed_block_reference",
]
