# $kw: Index.Capture/Surface.Lines --from Index.Line.Record.Model --note [CT] A grounded line on an SKW annotation is an Index.Line and capture lands its LineRecord through the same workflow as a Markdown-hosted line. ^c20260821-7u
"""Reconcile grounded lines on live Index surfaces into the record depot."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Callable

from tarav._core.errors import CliError
from tarav.chatlas.lossless import lossless_anchory_resolve
from tarav.index_model.identity import index_line_anchor_triplet_hash

from .config import Geography
from .record.model import LineRecord, SupportRef
from .record.store import IndexStore
from .surfaces import SurfaceLine, discover_surfaces, read_surface, resolve_surface_path

DossierResolver = Callable[[str], dict[str, object]]


def _resolve_dossier(label: str) -> dict[str, object]:
    return lossless_anchory_resolve(label.removeprefix("^"))


@dataclass(frozen=True, slots=True)
class CaptureIssue:
    label: str
    reason: str
    surfaces: tuple[str, ...]

    def to_json(self) -> dict[str, object]:
        return {"label": self.label, "reason": self.reason, "surfaces": list(self.surfaces)}


@dataclass(frozen=True, slots=True)
class CaptureReport:
    mode: str
    surface_files: int
    surface_lines: int
    existing: tuple[str, ...]
    created: tuple[str, ...]
    planned: tuple[str, ...]
    unresolved: tuple[CaptureIssue, ...]
    conflicts: tuple[CaptureIssue, ...]

    @property
    def clean(self) -> bool:
        return not self.unresolved and not self.conflicts

    def to_json(self) -> dict[str, object]:
        return {
            "class": "Index.Capture.Run",
            "mode": self.mode,
            "status": "ok" if self.clean else "incomplete",
            "surface_files": self.surface_files,
            "surface_lines": self.surface_lines,
            "existing": list(self.existing),
            "created": list(self.created),
            "planned": list(self.planned),
            "unresolved": [issue.to_json() for issue in self.unresolved],
            "conflicts": [issue.to_json() for issue in self.conflicts],
        }


def _statement(line: SurfaceLine) -> str:
    return f"[{line.line_type}] {line.body}" if line.line_type else line.body


def _support_from(payload: dict[str, object]) -> tuple[SupportRef, ...]:
    members = payload.get("members")
    if not isinstance(members, list) or not members:
        raise ValueError("grounding dossier resolved no support members")
    for member in members:
        if not isinstance(member, dict):
            raise ValueError("grounding dossier returned a malformed support member")
        if member.get("standing") != "MATCHED" or member.get("side") != "user":
            raise ValueError("grounding dossier support is not a matched user message")

    record = payload.get("record")
    if not isinstance(record, dict):
        raise ValueError("grounding dossier has no record")
    relationships = record.get("relationships")
    support = relationships.get("support") if isinstance(relationships, dict) else None
    raw_members = support.get("members") if isinstance(support, dict) else None
    if not isinstance(raw_members, list) or not raw_members:
        raise ValueError("grounding dossier has no support relationship")
    refs: list[SupportRef] = []
    for member in raw_members:
        if not isinstance(member, dict):
            raise ValueError("grounding dossier support relationship is malformed")
        refs.append(
            SupportRef(
                archive="chat",
                session_id=str(member["session"]),
                message_id=str(member["message_address"]),
            )
        )
    return tuple(refs)


def _triplet(payload: dict[str, object]) -> str:
    record = payload.get("record")
    attachment = record.get("attachment") if isinstance(record, dict) else None
    value = attachment.get("triplet_hash") if isinstance(attachment, dict) else None
    if not isinstance(value, str):
        raise ValueError("grounding dossier has no attachment triplet")
    return value


def capture_surface_lines(
    geo: Geography,
    *,
    land: bool,
    labels: Iterable[str] = (),
    dossier_resolver: DossierResolver = _resolve_dossier,
) -> CaptureReport:
    """Preview or land every grounded surface line missing its `LineRecord`.

    Existing labels are checked, never rewritten. A dossier must verify the exact
    ``Line.Type + body + label`` triplet and every support member before a new record is
    constructed. Markdown and SKW hosting kinds enter through the same `SurfaceLine` model.
    """

    surfaces = discover_surfaces(geo, geo.project_root)
    occurrences: dict[str, list[tuple[str, SurfaceLine]]] = {}
    line_count = 0
    for surface in surfaces:
        lines = read_surface(resolve_surface_path(surface, geo.project_root), surface)
        line_count += len(lines)
        for line in lines:
            for label in line.labels:
                occurrences.setdefault(label, []).append((surface, line))

    requested = {label if label.startswith("^") else f"^{label}" for label in labels}
    missing_requested = sorted(requested - set(occurrences))
    if requested:
        occurrences = {
            label: hosted for label, hosted in occurrences.items() if label in requested
        }

    store = IndexStore(geo)
    existing_by_label = {
        record.line.label: record for record in store.all() if record.line.label
    }
    existing: list[str] = []
    created: list[str] = []
    planned: list[str] = []
    unresolved: list[CaptureIssue] = [
        CaptureIssue(label, "selected label is absent from live surfaces", ())
        for label in missing_requested
    ]
    conflicts: list[CaptureIssue] = []
    staged: list[LineRecord] = []

    for label, hosted in sorted(occurrences.items()):
        surfaces_for_label = tuple(sorted({surface for surface, _line in hosted}))
        variants = {(line.line_type, line.body) for _surface, line in hosted}
        if len(variants) != 1:
            conflicts.append(CaptureIssue(label, "surface editions disagree", surfaces_for_label))
            continue
        line = hosted[0][1]
        record = existing_by_label.get(label)
        if record is not None:
            if (record.line.type, record.line.body) != (line.line_type, line.body):
                conflicts.append(CaptureIssue(label, "LineRecord disagrees with surface", surfaces_for_label))
            else:
                existing.append(label)
            continue

        try:
            payload = dossier_resolver(label)
            expected = index_line_anchor_triplet_hash(_statement(line), label)
            if _triplet(payload) != expected:
                raise ValueError("grounding dossier triplet disagrees with surface")
            support = _support_from(payload)
        except (CliError, KeyError, TypeError, ValueError, RuntimeError) as exc:
            unresolved.append(CaptureIssue(label, str(exc), surfaces_for_label))
            continue

        planned.append(label)
        if land:
            staged.append(LineRecord.create(
                line.scope,
                line.line_type,
                line.body,
                support=support,
            ).relabel(label))

    if land and not unresolved and not conflicts:
        for record in staged:
            store.put(record)
            created.append(record.line.label or "")

    return CaptureReport(
        mode="land" if land else "preview",
        surface_files=len(surfaces),
        surface_lines=line_count,
        existing=tuple(existing),
        created=tuple(created),
        planned=tuple(planned),
        unresolved=tuple(unresolved),
        conflicts=tuple(conflicts),
    )


__all__ = ["CaptureIssue", "CaptureReport", "capture_surface_lines"]
