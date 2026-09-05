"""Assertion-owned construction of Ranking Tasks."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar, Mapping, Protocol, Sequence

from tarav._core.project import require_agentos_project
from tarav.diagram import ChatlasEvidence, DiagramConfiguration, DiagramError

from .model import (
    DIAGRAM_LINE_EDITION_REFERENCE_TYPE,
    GROUNDING_ASSERTION_REFERENCE_TYPE,
    GROUNDING_ASSERTION_TYPE,
    GROUNDING_TASK_TYPE,
    POOL_TYPE,
    JsonObject,
    ScoringError,
    new_record,
    pool_matches,
    record_reference,
    validate_record,
)


class RankingTaskProducer(Protocol):
    task_type: str

    def create(
        self,
        *,
        pool: Mapping[str, object],
        candidates: Sequence[Mapping[str, object]],
        appendix: Sequence[str] = (),
    ) -> JsonObject: ...


class AssertionRankingType(Protocol):
    assertion_type: str
    task_producers: tuple[RankingTaskProducer, ...]

    def producer(self, task_type: str) -> RankingTaskProducer: ...


@dataclass(frozen=True, slots=True)
class IndexLineGroundingRankingTaskProducer:
    """Produce one fair comparison among Line-grounding Assertions."""

    task_type: ClassVar[str] = GROUNDING_TASK_TYPE

    def create(
        self,
        *,
        pool: Mapping[str, object],
        candidates: Sequence[Mapping[str, object]],
        appendix: Sequence[str] = (),
    ) -> JsonObject:
        validate_record(pool)
        if pool["type"] != POOL_TYPE:
            raise ScoringError("grounding Task requires an Assertion.Pool")
        candidate_records = [dict(item) for item in candidates]
        if len(candidate_records) < 2:
            raise ScoringError("a Ranking Task requires at least two candidates")
        ids = [_candidate_id(item) for item in candidate_records]
        if len(set(ids)) != len(ids):
            raise ScoringError("Ranking Task candidate IDs must be unique")
        for candidate in candidate_records:
            assertion_ref = _candidate_assertion_ref(candidate)
            if assertion_ref.get("type") != GROUNDING_ASSERTION_REFERENCE_TYPE:
                raise ScoringError(
                    "Index.Line grounding Tasks require grounding Assertion references"
                )
            if not pool_matches(pool, assertion_ref):
                raise ScoringError(
                    "Ranking Task candidate does not belong to the selected Pool: "
                    f"{_candidate_id(candidate)}"
                )
        return new_record(
            GROUNDING_TASK_TYPE,
            pool_ref=record_reference(pool),
            background=(
                "Each candidate is an Index.Line together with the Block context "
                "in which it must be interpreted and its declared Support.Set."
            ),
            question=(
                "Rank the candidates by how completely their declared Support.Set "
                "supports the Line's full semantic claim in its Block context."
            ),
            appendix=list(appendix),
            candidates=candidate_records,
            response_contract={
                "outcomes": ["ranked", "abstained"],
                "ranking": (
                    "ordered tiers; comma-separated labels within one tier are tied"
                ),
            },
        )


@dataclass(frozen=True, slots=True)
class IndexLineGroundingAssertionType:
    """Ranking capabilities owned by Index.Line grounding Assertions."""

    assertion_type: ClassVar[str] = GROUNDING_ASSERTION_TYPE
    task_producers: ClassVar[tuple[RankingTaskProducer, ...]] = (
        IndexLineGroundingRankingTaskProducer(),
    )

    def producer(self, task_type: str) -> RankingTaskProducer:
        matches = [item for item in self.task_producers if item.task_type == task_type]
        if len(matches) != 1:
            raise ScoringError(
                f"Assertion Type {self.assertion_type} cannot produce {task_type}"
            )
        return matches[0]

    def candidate(
        self,
        *,
        line_ship: str,
        namespace_id: str,
        projection: Any,
        evidence: ChatlasEvidence,
    ) -> JsonObject:
        try:
            line = projection.line(line_ship)
            block = projection.block(line.block_ship)
        except DiagramError as exc:
            raise ScoringError(
                f"Line {line_ship} does not belong to the current Diagram Model"
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
        return {
            "id": edition.annotation.id,
            "assertion_ref": {
                "type": GROUNDING_ASSERTION_REFERENCE_TYPE,
                "subject_ref": {
                    "type": DIAGRAM_LINE_EDITION_REFERENCE_TYPE,
                    "namespace_id": namespace_id,
                    "line_ship": line.ship,
                    "edition_id": edition.annotation.id,
                },
            },
            "presentation": _render_candidate(
                line_text=edition.text,
                block_label=block.current_label,
                peer_lines=peer_lines,
                support=support,
            ),
            "appendix": [],
        }


class AssertionRankingRegistry:
    """Resolve ranking behavior from the Assertion Type—not from its Pool."""

    def __init__(self, assertion_types: Sequence[AssertionRankingType] = ()) -> None:
        self._types: dict[str, AssertionRankingType] = {}
        for assertion_type in assertion_types:
            self.register(assertion_type)

    def register(self, assertion_type: AssertionRankingType) -> None:
        type_id = assertion_type.assertion_type
        if type_id in self._types:
            raise ScoringError(f"Assertion Ranking Type already registered: {type_id}")
        self._types[type_id] = assertion_type

    def resolve(self, assertion_type: str) -> AssertionRankingType:
        try:
            return self._types[assertion_type]
        except KeyError as exc:
            raise ScoringError(
                f"Assertion Type has no Ranking.Task producers: {assertion_type}"
            ) from exc


DEFAULT_ASSERTION_RANKING_REGISTRY = AssertionRankingRegistry(
    (IndexLineGroundingAssertionType(),)
)


def create_grounding_task(
    *,
    pool: Mapping[str, object],
    candidates: Sequence[Mapping[str, object]],
    appendix: Sequence[str] = (),
    registry: AssertionRankingRegistry = DEFAULT_ASSERTION_RANKING_REGISTRY,
) -> JsonObject:
    """Create a Task through its Assertion Type's registered producer."""

    assertion_type = registry.resolve(GROUNDING_ASSERTION_TYPE)
    return assertion_type.producer(GROUNDING_TASK_TYPE).create(
        pool=pool,
        candidates=candidates,
        appendix=appendix,
    )


def create_line_grounding_task(
    *,
    pool: JsonObject,
    project_path: Path,
    line_ships: Sequence[str],
    diagram_config: Path | None = None,
    chatlas_root: Path | None = None,
    appendix: Sequence[str] = (),
    evidence: ChatlasEvidence | None = None,
    registry: AssertionRankingRegistry = DEFAULT_ASSERTION_RANKING_REGISTRY,
) -> JsonObject:
    """Resolve exact Line editions through the registered Assertion Type."""

    project = require_agentos_project(project=project_path)
    assertion_type = registry.resolve(GROUNDING_ASSERTION_TYPE)
    if not isinstance(assertion_type, IndexLineGroundingAssertionType):
        raise ScoringError(
            "registered Index.Line grounding Assertion Type has an invalid class"
        )
    try:
        model = (
            DiagramConfiguration.load(diagram_config)
            .diagram()
            .project_model(project.root)
        )
        projection = model.project(include_collection_content=True)
        resolved_evidence = evidence or ChatlasEvidence(chatlas_root=chatlas_root)
        candidates = [
            assertion_type.candidate(
                line_ship=line_ship,
                namespace_id=model.namespace.id,
                projection=projection,
                evidence=resolved_evidence,
            )
            for line_ship in line_ships
        ]
    except (DiagramError, ValueError) as exc:
        raise ScoringError(str(exc)) from exc
    return assertion_type.producer(GROUNDING_TASK_TYPE).create(
        pool=pool,
        candidates=candidates,
        appendix=appendix,
    )


def _candidate_id(candidate: Mapping[str, object]) -> str:
    value = candidate.get("id")
    if not isinstance(value, str) or not value:
        raise ScoringError("Ranking Task candidate id must be a non-empty string")
    return value


def _candidate_assertion_ref(candidate: Mapping[str, object]) -> Mapping[str, object]:
    value = candidate.get("assertion_ref")
    if not isinstance(value, dict):
        raise ScoringError("Ranking Task candidate assertion_ref must be an object")
    return value


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


__all__ = [
    "DEFAULT_ASSERTION_RANKING_REGISTRY",
    "AssertionRankingRegistry",
    "IndexLineGroundingAssertionType",
    "IndexLineGroundingRankingTaskProducer",
    "create_grounding_task",
    "create_line_grounding_task",
]
