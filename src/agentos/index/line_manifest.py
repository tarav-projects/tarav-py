# $kw: --from Index.Line.Manifest --from Index.Line.Anchor --note [IMPL] the foundation manifest assembles parser-owned line identity and block-bounded context while injected applications project relationships --supp ^c20260811-0u
"""Normalized, volatile inspection manifests for selected Index lines."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from agentos._core.errors import CliError

from .anchor_locator import load_index_anchor_locator_selection
from .model import (
    BlockHeading,
    IndexDepotModel,
    KernelLine,
    index_line_body_hash,
    index_line_statement_parts,
    group_index_line_anchor_occurrences,
    kernel_line_anchors,
    normalize_anchor,
    parse_depot,
)


LINE_MANIFEST_SCHEMA = "agentos.index-line-manifest.v3"
LineRelationshipProjector = Callable[[str, str], Mapping[str, object]]


def build_index_line_manifest(
    *,
    depot_root: str | Path,
    anchors: tuple[str, ...] = (),
    scopes: tuple[str | Path, ...] = (),
    neighbors: int = 2,
    limit: int | None = None,
    relationship_projector: LineRelationshipProjector | None = None,
    inputs: Mapping[str, object] | None = None,
    generated_at: str | None = None,
    locator_workspace_root: str | Path | None = None,
) -> dict[str, Any]:
    """Assemble selected lines, their bounded Index context, and relationships."""

    root = Path(depot_root).expanduser().resolve()
    if not root.is_dir():
        raise CliError(f"Index depot is unavailable: {root}")
    if not anchors and not scopes:
        raise CliError("line manifest requires at least one --anchor or --scope selector")
    if neighbors < 0:
        raise CliError("line manifest neighbors must be non-negative")
    if limit is not None and limit < 1:
        raise CliError("line manifest limit must be positive")

    wanted = tuple(dict.fromkeys(normalize_anchor(anchor) for anchor in anchors))
    scope_paths = _resolve_scopes(root, scopes)
    locator = None
    if wanted and not scope_paths:
        locator = load_index_anchor_locator_selection(
            depot_root=root,
            anchors=wanted,
            workspace_root=locator_workspace_root,
        )
    depot = (
        locator.model
        if locator is not None and locator.model is not None
        else parse_depot(root)
    )
    selected = _select_lines(depot, wanted=wanted, scope_paths=scope_paths)
    occurrence_groups = group_index_line_anchor_occurrences(
        selected,
        anchors=wanted,
    )
    anchor_resolution = [
        occurrence_groups[anchor].to_payload(root)
        for anchor in wanted
        if anchor in occurrence_groups
    ]
    ambiguous_anchor_count = sum(
        item["standing"] == "ambiguous" for item in anchor_resolution
    )
    requested_line_count = len(selected)
    emitted = selected[:limit] if limit is not None else selected
    block_index = _block_index(depot)
    source_fingerprints: dict[str, str] = {}
    turns: dict[str, dict[str, Any]] = {}
    verified_sessions: set[str] = set()
    lines: list[dict[str, Any]] = []

    for line in emitted:
        if line.path is None:
            raise CliError("parsed Index line has no source path")
        relative_path = line.path.relative_to(root).as_posix()
        source_fingerprints.setdefault(relative_path, _file_hash(line.path))
        anchors_for_line = kernel_line_anchors(line)
        projected_anchors: list[dict[str, Any]] = []
        for anchor in anchors_for_line:
            if relationship_projector is None:
                projected_anchors.append({"anchor": anchor})
                continue
            projection = dict(relationship_projector(anchor, line.src))
            anchor_entry = projection.get("anchor")
            if not isinstance(anchor_entry, Mapping):
                raise CliError(
                    f"line relationship projector returned no anchor object: {anchor}"
                )
            projected_anchors.append(dict(anchor_entry))
            projected_turns = projection.get("turns", {})
            if not isinstance(projected_turns, Mapping):
                raise CliError(
                    f"line relationship projector returned invalid turns: {anchor}"
                )
            for key, value in projected_turns.items():
                if not isinstance(key, str) or not isinstance(value, Mapping):
                    raise CliError(
                        f"line relationship projector returned invalid turn: {anchor}"
                    )
                normalized = dict(value)
                existing = turns.get(key)
                if existing is not None and existing != normalized:
                    raise CliError(f"conflicting projected turn entry: {key}")
                turns[key] = normalized
            sessions = projection.get("verified_sessions", ())
            if not isinstance(sessions, (list, tuple, set, frozenset)):
                raise CliError(
                    f"line relationship projector returned invalid sessions: {anchor}"
                )
            verified_sessions.update(str(session) for session in sessions)

        lines.append(
            _line_entry(
                root=root,
                line=line,
                projected_anchors=projected_anchors,
                block_index=block_index,
                neighbors=neighbors,
            )
        )

    base_inputs: dict[str, object] = {
        "depot": str(root),
        "anchors": list(wanted),
        "scopes": [path.relative_to(root).as_posix() for path in scope_paths],
        "neighbors": neighbors,
        "limit": limit,
        "source_fingerprints": source_fingerprints,
        "anchor_locator": (
            locator.to_payload()
            if locator is not None
            else {"standing": "not-applicable"}
        ),
    }
    if inputs:
        base_inputs.update(dict(inputs))
    return {
        "schema": LINE_MANIFEST_SCHEMA,
        "status": "ambiguous" if ambiguous_anchor_count else "ok",
        "surface": {"kind": "Volatile.Surface", "authoritative": False},
        "generated_at": generated_at or _utc_now(),
        "inputs": base_inputs,
        "summary": {
            "requested_line_count": requested_line_count,
            "line_count": len(lines),
            "omitted_line_count": requested_line_count - len(lines),
            "anchor_count": sum(len(line["anchors"]) for line in lines),
            "turn_count": len(turns),
            "referenced_session_count": len(
                {
                    str(turn["ref"]["session"])
                    for turn in turns.values()
                    if isinstance(turn.get("ref"), Mapping)
                    and turn["ref"].get("session") is not None
                }
            ),
            "verified_session_count": len(verified_sessions),
            "ambiguous_anchor_count": ambiguous_anchor_count,
        },
        "anchor_resolution": anchor_resolution,
        "lines": lines,
        "turns": dict(sorted(turns.items())),
    }


def format_index_line_manifest_text(manifest: Mapping[str, Any]) -> str:
    """Render the normalized manifest as compact agent-readable text."""

    summary = manifest.get("summary", {})
    lines = [
        "Index.Line.Manifest",
        (
            f"{summary.get('line_count', 0)} line(s), "
            f"{summary.get('anchor_count', 0)} anchor(s), "
            f"{summary.get('turn_count', 0)} projected turn(s)"
        ),
    ]
    if manifest.get("status") == "ambiguous":
        lines.append("anchor resolution: ambiguous; inspect normal Index lint")
    turn_registry = manifest.get("turns", {})
    for line in manifest.get("lines", []):
        source = line["source"]
        statement = line["statement"]
        block = line["block"]
        prefix = f"[{statement['type']}] " if statement.get("type") else ""
        lines.extend(
            (
                "",
                f"{source['path']}:{source['line']} · {block['path']} "
                f"({block['line_ordinal']}/{block['line_count']})",
                f"  {prefix}{statement['body']}",
            )
        )
        context = line["context"]
        if context["before"] or context["after"]:
            lines.append(
                "  context: "
                f"{len(context['before'])} before, {len(context['after'])} after "
                f"({context['omitted_before']}+{context['omitted_after']} omitted)"
            )
            for neighbor in context["before"]:
                lines.append(f"    before {_context_line_text(neighbor)}")
            for neighbor in context["after"]:
                lines.append(f"    after  {_context_line_text(neighbor)}")
        for anchor in line["anchors"]:
            attachment = anchor.get("attachment", {})
            suffix = (
                f"  attachment={attachment.get('standing')}"
                if attachment
                else ""
            )
            lines.append(f"  ^{anchor['anchor']}{suffix}")
            relationships = anchor.get("relationships", {})
            members = relationships.get("support", {}).get("members", [])
            for member in members:
                turn = turn_registry.get(member.get("turn"), {})
                label = turn.get("text") or member.get("turn")
                standing = member.get("verification", "stored")
                lines.append(f"    support [{standing}]: {label}")
            for gate_kind, gates in relationships.get("gates", {}).items():
                for gate in gates:
                    token = f" token={gate['token']}" if gate.get("token") else ""
                    lines.append(f"    gate {gate_kind}:{token}")
                    for position in ("proposal_turn", "approval_turn"):
                        if position not in gate:
                            continue
                        standing = gate.get(f"{position}_verification", "stored")
                        turn = turn_registry.get(gate[position], {})
                        label = turn.get("text") or gate[position]
                        lines.append(f"      {position} [{standing}]: {label}")
            for provenance_kind, value in relationships.get(
                "provenance", {}
            ).items():
                if value:
                    lines.append(
                        f"    provenance {provenance_kind}: "
                        + json.dumps(value, ensure_ascii=False, sort_keys=True)
                    )
    return "\n".join(lines)


def _context_line_text(value: Mapping[str, Any]) -> str:
    statement = value.get("statement", {})
    line_type = statement.get("type")
    prefix = f"[{line_type}] " if line_type else ""
    return f"L{value.get('line')}: {prefix}{statement.get('body', '')}"


def _select_lines(
    depot: IndexDepotModel,
    *,
    wanted: tuple[str, ...],
    scope_paths: tuple[Path, ...],
) -> list[KernelLine]:
    candidates = [
        line
        for line in depot.kernel_lines()
        if line.path is not None and _line_in_scopes(line.path, scope_paths)
    ]
    if wanted:
        selected = [
            line
            for line in candidates
            if set(wanted).intersection(kernel_line_anchors(line))
        ]
        present = {
            anchor for line in selected for anchor in kernel_line_anchors(line)
        }
        missing = [anchor for anchor in wanted if anchor not in present]
        if missing:
            noun = "anchor is" if len(missing) == 1 else "anchors are"
            raise CliError(
                f"requested {noun} absent from the selected Index floor: "
                + ", ".join(missing)
            )
    else:
        selected = candidates
    selected.sort(key=lambda line: (str(line.path), line.start_line))
    return selected


def _block_index(
    depot: IndexDepotModel,
) -> dict[tuple[Path, str], tuple[BlockHeading | None, list[KernelLine]]]:
    result: dict[tuple[Path, str], tuple[BlockHeading | None, list[KernelLine]]] = {}
    for document in depot.documents:
        if document.path is None:
            continue
        headings = {
            str(node.parsed.get("path")): node
            for node in document.nodes
            if isinstance(node, BlockHeading)
        }
        lines_by_block: dict[str, list[KernelLine]] = {}
        for line in document.kernel_lines():
            block_path = str(line.parsed.get("block_path", ""))
            lines_by_block.setdefault(block_path, []).append(line)
        for block_path, block_lines in lines_by_block.items():
            result[(document.path, block_path)] = (
                headings.get(block_path),
                sorted(block_lines, key=lambda line: line.start_line),
            )
    return result


def _line_entry(
    *,
    root: Path,
    line: KernelLine,
    projected_anchors: list[dict[str, Any]],
    block_index: Mapping[
        tuple[Path, str], tuple[BlockHeading | None, list[KernelLine]]
    ],
    neighbors: int,
) -> dict[str, Any]:
    assert line.path is not None
    block_path = str(line.parsed.get("block_path", ""))
    heading, siblings = block_index.get((line.path, block_path), (None, [line]))
    position = next(
        (index for index, sibling in enumerate(siblings) if sibling is line),
        0,
    )
    before_start = max(0, position - neighbors)
    after_end = min(len(siblings), position + neighbors + 1)
    before = siblings[before_start:position]
    after = siblings[position + 1 : after_end]
    line_type, body = index_line_statement_parts(line.src)
    return {
        "source": {
            "path": line.path.relative_to(root).as_posix(),
            "line": line.start_line,
        },
        "text": line.src,
        "statement": {
            "type": line_type,
            "body": body,
            "body_hash": index_line_body_hash(line.src),
        },
        "source_fingerprint": _text_hash(line.src),
        "block": {
            "path": block_path,
            "heading_line": heading.start_line if heading is not None else None,
            "line_ordinal": position + 1,
            "line_count": len(siblings),
        },
        "context": {
            "before": [_context_line(item) for item in before],
            "after": [_context_line(item) for item in after],
            "omitted_before": before_start,
            "omitted_after": len(siblings) - after_end,
        },
        "anchors": projected_anchors,
    }


def _context_line(line: KernelLine) -> dict[str, Any]:
    line_type, body = index_line_statement_parts(line.src)
    return {
        "line": line.start_line,
        "text": line.src,
        "statement": {"type": line_type, "body": body},
        "anchors": list(kernel_line_anchors(line)),
    }


def _resolve_scopes(root: Path, scopes: tuple[str | Path, ...]) -> tuple[Path, ...]:
    resolved: list[Path] = []
    for raw_scope in scopes:
        candidate = Path(raw_scope).expanduser()
        path = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise CliError(f"line manifest scope is outside its Index depot: {raw_scope}") from exc
        if not path.exists():
            raise CliError(f"line manifest scope is unavailable: {raw_scope}")
        resolved.append(path)
    return tuple(dict.fromkeys(resolved))


def _line_in_scopes(path: Path, scopes: tuple[Path, ...]) -> bool:
    return not scopes or any(path == scope or scope in path.parents for scope in scopes)


def _file_hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def _text_hash(value: str) -> str:
    return f"sha256:{sha256(value.encode('utf-8')).hexdigest()}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


__all__ = [
    "LINE_MANIFEST_SCHEMA",
    "LineRelationshipProjector",
    "build_index_line_manifest",
    "format_index_line_manifest_text",
]
