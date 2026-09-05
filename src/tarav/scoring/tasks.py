"""Assertion-owned construction of Ranking Tasks."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from tarav._core.project import require_agentos_project
from tarav.diagram import ChatlasEvidence, DiagramConfiguration, DiagramError

from .model import JsonObject, ScoringError, create_grounding_task


def create_line_grounding_task(
    *,
    pool: JsonObject,
    project_path: Path,
    line_ships: Sequence[str],
    diagram_config: Path | None = None,
    chatlas_root: Path | None = None,
    appendix: Sequence[str] = (),
    evidence: ChatlasEvidence | None = None,
) -> JsonObject:
    """Resolve exact current Line editions and render their grounding cases."""

    project = require_agentos_project(project=project_path)
    try:
        model = DiagramConfiguration.load(diagram_config).diagram().project_model(
            project.root
        )
        projection = model.project(include_collection_content=True)
        resolved_evidence = evidence or ChatlasEvidence(chatlas_root=chatlas_root)
        candidates = [
            _line_candidate(
                line_ship=line_ship,
                model_ship=model.ship,
                namespace_id=model.namespace.id,
                project_id=project.project_id,
                project_root=project.root,
                projection=projection,
                evidence=resolved_evidence,
            )
            for line_ship in line_ships
        ]
    except (DiagramError, ValueError) as exc:
        raise ScoringError(str(exc)) from exc
    return create_grounding_task(pool=pool, candidates=candidates, appendix=appendix)


def _line_candidate(
    *,
    line_ship: str,
    model_ship: str,
    namespace_id: str,
    project_id: str,
    project_root: Path,
    projection,
    evidence: ChatlasEvidence,
) -> JsonObject:
    try:
        line = projection.line(line_ship)
        block = projection.block(line.block_ship)
    except DiagramError as exc:
        raise ScoringError(
            f"Line {line_ship} does not belong to the Project's current Diagram Model"
        ) from exc
    edition = line.current_edition
    if edition is None:
        raise ScoringError(f"Line has no current edition: {line_ship}")
    wording = edition.annotation
    support = wording.render_support(evidence)
    if not support:
        raise ScoringError(f"Line has no declared Support.Set: {line_ship}")
    peer_lines = [
        peer.current_edition.text
        for peer in block.lines
        if peer.ship != line_ship and peer.current_edition is not None
    ]
    presentation = _render_candidate(
        line_text=edition.text,
        block_label=block.current_label,
        peer_lines=peer_lines,
        support=support,
    )
    return {
        "id": edition.annotation.id,
        "assertion": {
            "type": "Index.Line.Grounding.Assertion",
            "subject": {
                "namespace_id": namespace_id,
                "project_id": project_id,
                "project_root": str(project_root),
                "model_ship": model_ship,
                "block_ship": line.block_ship,
                "line_ship": line.ship,
                "line_edition_id": edition.annotation.id,
            },
        },
        "presentation": presentation,
        "appendix": [],
    }


def _render_candidate(
    *,
    line_text: str,
    block_label: str | None,
    peer_lines: Sequence[str],
    support: Sequence[JsonObject],
) -> str:
    sections = [
        f"Block: {block_label or '(unlabeled Block)'}",
        "",
        "Line claim:",
        line_text,
    ]
    if peer_lines:
        sections.extend(("", "Peer Lines establishing Block context:"))
        sections.extend(f"- {text}" for text in peer_lines)
    sections.extend(("", "Declared Support.Set:"))
    for member_index, member in enumerate(support, start=1):
        sections.append(f"\nSupport member {member_index}:")
        turns = member.get("turns", [])
        if not isinstance(turns, list):
            continue
        for turn in turns:
            if not isinstance(turn, dict):
                continue
            side = turn.get("side", "unknown")
            role = "root" if turn.get("root") else "context"
            sections.extend((f"[{role}; {side}]", str(turn.get("text", ""))))
    return "\n".join(sections)


__all__ = ["create_line_grounding_task"]
