# $kw: --from Anchory.System --from Index.Line.Anchor
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Literal

from agentos._core.errors import CliError
from agentos._core.persistence import atomic_write_text

from .model import (
    IndexDepotModel,
    IndexDocument,
    KernelLine,
    group_index_line_anchor_occurrences,
    normalize_anchor,
    parse_index_file,
)


INDEX_ANCHOR_LOCATOR_SCHEMA = "agentos.index-anchor-locator.v1"
AnchorLocatorStanding = Literal["hit", "missing", "stale"]


@dataclass(frozen=True)
class IndexAnchorLocatorSelection:
    standing: AnchorLocatorStanding
    path: Path
    model: IndexDepotModel | None = None
    generated_at: str | None = None
    anchors: tuple[dict[str, object], ...] = ()
    reason: str | None = None

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "standing": self.standing,
            "path": str(self.path),
        }
        if self.generated_at is not None:
            payload["generated_at"] = self.generated_at
        if self.reason is not None:
            payload["reason"] = self.reason
        return payload


def index_anchor_locator_path(
    depot_root: str | Path,
    *,
    workspace_root: str | Path | None = None,
) -> Path:
    depot = Path(depot_root).expanduser().resolve()
    workspace = (
        Path(workspace_root).expanduser().resolve()
        if workspace_root is not None
        else Path.cwd().resolve()
    )
    depot_key = sha256(str(depot).encode("utf-8")).hexdigest()[:16]
    return (
        workspace
        / ".agentos"
        / "state"
        / "index-anchor-locators"
        / f"{depot_key}.json"
    )


def build_index_anchor_locator(
    *,
    depot_root: str | Path,
    lines: tuple[KernelLine, ...] | list[KernelLine],
    generated_at: str | None = None,
) -> dict[str, Any]:
    root = Path(depot_root).expanduser().resolve()
    groups = group_index_line_anchor_occurrences(lines)
    source_paths = sorted(
        {
            occurrence.line.path
            for group in groups.values()
            for occurrence in group.occurrences
            if occurrence.line.path is not None
        }
    )
    sources: dict[str, str] = {}
    for path in source_paths:
        assert path is not None
        try:
            relative = path.relative_to(root).as_posix()
        except ValueError as exc:
            raise CliError(
                f"Index anchor locator source is outside its depot: {path}"
            ) from exc
        sources[relative] = _file_hash(path)
    return {
        "schema": INDEX_ANCHOR_LOCATOR_SCHEMA,
        "surface": {"kind": "Volatile.Surface", "authoritative": False},
        "generated_at": generated_at or _utc_now(),
        "depot": str(root),
        "sources": sources,
        "anchors": {
            anchor: group.to_payload(root) for anchor, group in groups.items()
        },
    }


def materialize_index_anchor_locator(
    *,
    depot_root: str | Path,
    lines: tuple[KernelLine, ...] | list[KernelLine],
    workspace_root: str | Path | None = None,
    generated_at: str | None = None,
) -> dict[str, object]:
    payload = build_index_anchor_locator(
        depot_root=depot_root,
        lines=lines,
        generated_at=generated_at,
    )
    path = index_anchor_locator_path(depot_root, workspace_root=workspace_root)
    serialized = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    atomic_write_text(path, serialized)
    return {
        "path": str(path),
        "depot": payload["depot"],
        "generated_at": payload["generated_at"],
        "anchor_count": len(payload["anchors"]),
    }


def load_index_anchor_locator_selection(
    *,
    depot_root: str | Path,
    anchors: tuple[str, ...],
    workspace_root: str | Path | None = None,
) -> IndexAnchorLocatorSelection:
    root = Path(depot_root).expanduser().resolve()
    path = index_anchor_locator_path(root, workspace_root=workspace_root)
    if not path.is_file():
        return IndexAnchorLocatorSelection("missing", path, reason="locator unavailable")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return IndexAnchorLocatorSelection("stale", path, reason=str(exc))
    if not isinstance(payload, dict):
        return IndexAnchorLocatorSelection("stale", path, reason="invalid locator payload")
    if payload.get("schema") != INDEX_ANCHOR_LOCATOR_SCHEMA:
        return IndexAnchorLocatorSelection("stale", path, reason="unsupported locator schema")
    if payload.get("depot") != str(root):
        return IndexAnchorLocatorSelection("stale", path, reason="locator depot mismatch")
    raw_anchors = payload.get("anchors")
    raw_sources = payload.get("sources")
    if not isinstance(raw_anchors, dict) or not isinstance(raw_sources, dict):
        return IndexAnchorLocatorSelection("stale", path, reason="invalid locator indexes")

    wanted = tuple(dict.fromkeys(normalize_anchor(anchor) for anchor in anchors))
    selected: list[dict[str, object]] = []
    relative_paths: set[str] = set()
    for anchor in wanted:
        raw_group = raw_anchors.get(anchor)
        if not isinstance(raw_group, dict):
            return IndexAnchorLocatorSelection(
                "stale", path, reason=f"anchor absent from locator: {anchor}"
            )
        occurrences = raw_group.get("occurrences")
        if not isinstance(occurrences, list) or not occurrences:
            return IndexAnchorLocatorSelection(
                "stale", path, reason=f"anchor has no locator occurrences: {anchor}"
            )
        for occurrence in occurrences:
            if not isinstance(occurrence, dict) or not isinstance(
                occurrence.get("path"), str
            ):
                return IndexAnchorLocatorSelection(
                    "stale", path, reason=f"anchor has invalid locator occurrences: {anchor}"
                )
            relative_paths.add(str(occurrence["path"]))
        selected.append(dict(raw_group))

    documents: list[IndexDocument] = []
    for relative in sorted(relative_paths):
        source = (root / relative).resolve()
        try:
            source.relative_to(root)
        except ValueError:
            return IndexAnchorLocatorSelection(
                "stale", path, reason=f"locator source escapes depot: {relative}"
            )
        expected = raw_sources.get(relative)
        if not isinstance(expected, str) or not source.is_file():
            return IndexAnchorLocatorSelection(
                "stale", path, reason=f"locator source unavailable: {relative}"
            )
        if _file_hash(source) != expected:
            return IndexAnchorLocatorSelection(
                "stale", path, reason=f"locator source changed: {relative}"
            )
        documents.append(parse_index_file(source))

    model = IndexDepotModel(root=root, documents=tuple(documents))
    observed = group_index_line_anchor_occurrences(
        model.kernel_lines(), anchors=wanted
    )
    if any(anchor not in observed for anchor in wanted):
        return IndexAnchorLocatorSelection(
            "stale", path, reason="locator occurrences no longer parse"
        )
    return IndexAnchorLocatorSelection(
        "hit",
        path,
        model=model,
        generated_at=str(payload.get("generated_at") or "") or None,
        anchors=tuple(selected),
    )


def _file_hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


__all__ = [
    "INDEX_ANCHOR_LOCATOR_SCHEMA",
    "IndexAnchorLocatorSelection",
    "build_index_anchor_locator",
    "index_anchor_locator_path",
    "load_index_anchor_locator_selection",
    "materialize_index_anchor_locator",
]
