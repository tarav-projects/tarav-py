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
    GROUNDING_RANKING_METHOD,
    GROUNDING_TASK_TYPE,
    POOL_ENROLLMENT_TYPE,
    POOL_TYPE,
    JsonObject,
    ScoringError,
    create_pool_enrollment,
    new_record,
    record_reference,
    validate_record,
)


class ScoringMethod(Protocol):
    method_type: str
    task_type: str

    def create(
        self,
        *,
        pool: Mapping[str, object],
        enrollments: Sequence[Mapping[str, object]],
        candidates: Sequence[Mapping[str, object]],
        appendix: Sequence[str] = (),
    ) -> JsonObject: ...


class AssertionRankingType(Protocol):
    assertion_type: str
    scoring_methods: tuple[ScoringMethod, ...]

    def method(self, method_type: str) -> ScoringMethod: ...


@dataclass(frozen=True, slots=True)
class IndexLineGroundingRankingMethod:
    """Produce one fair comparison among enrolled Line-grounding Assertions."""

    method_type: ClassVar[str] = GROUNDING_RANKING_METHOD
    task_type: ClassVar[str] = GROUNDING_TASK_TYPE

    def create(
        self,
        *,
        pool: Mapping[str, object],
        enrollments: Sequence[Mapping[str, object]],
        candidates: Sequence[Mapping[str, object]],
        appendix: Sequence[str] = (),
    ) -> JsonObject:
        validate_record(pool)
        if pool["type"] != POOL_TYPE:
            raise ScoringError("grounding Task requires an Assertion.Pool")
        if pool.get("scoring_method") != self.method_type:
            raise ScoringError(f"Assertion Pool does not organize {self.method_type}")
        enrollment_records = [dict(item) for item in enrollments]
        candidate_records = [dict(item) for item in candidates]
        if len(enrollment_records) != len(candidate_records):
            raise ScoringError("Ranking Task requires one Enrollment per candidate")
        if len(candidate_records) < 2:
            raise ScoringError("a Ranking Task requires at least two candidates")
        ids = [_candidate_id(item) for item in candidate_records]
        if len(set(ids)) != len(ids):
            raise ScoringError("Ranking Task candidate IDs must be unique")
        expected_enrollments: dict[str, Mapping[str, object]] = {}
        for enrollment in enrollment_records:
            validate_record(enrollment)
            if enrollment.get("type") != POOL_ENROLLMENT_TYPE:
                raise ScoringError("grounding Task requires Pool Enrollments")
            if _reference_id(enrollment.get("pool_ref")) != pool.get("id"):
                raise ScoringError("Enrollment belongs to another Assertion Pool")
            assertion_ref = _enrollment_assertion_ref(enrollment)
            if assertion_ref.get("type") != GROUNDING_ASSERTION_REFERENCE_TYPE:
                raise ScoringError(
                    "Index.Line grounding Tasks require grounding Assertion references"
                )
            expected_enrollments[_assertion_instance_id(assertion_ref)] = enrollment
        for candidate in candidate_records:
            candidate_id = _candidate_id(candidate)
            enrollment = expected_enrollments.get(candidate_id)
            if enrollment is None:
                raise ScoringError(
                    "Ranking Task candidate is not explicitly enrolled: " + candidate_id
                )
            if candidate.get("enrollment_ref") != record_reference(enrollment):
                raise ScoringError("candidate Enrollment reference is not exact")
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
    scoring_methods: ClassVar[tuple[ScoringMethod, ...]] = (
        IndexLineGroundingRankingMethod(),
    )

    def method(self, method_type: str) -> ScoringMethod:
        matches = [
            item for item in self.scoring_methods if item.method_type == method_type
        ]
        if len(matches) != 1:
            raise ScoringError(
                f"Assertion Type {self.assertion_type} does not support {method_type}"
            )
        return matches[0]

    def reference(
        self,
        *,
        line_ship: str,
        namespace_id: str,
        projection: Any,
    ) -> JsonObject:
        try:
            line = projection.line(line_ship)
        except DiagramError as exc:
            raise ScoringError(
                f"Line {line_ship} does not belong to the current Diagram Model"
            ) from exc
        edition = line.current_edition
        if edition is None:
            raise ScoringError(f"Line has no current edition: {line_ship}")
        return {
            "type": GROUNDING_ASSERTION_REFERENCE_TYPE,
            "subject_ref": {
                "type": DIAGRAM_LINE_EDITION_REFERENCE_TYPE,
                "namespace_id": namespace_id,
                "line_ship": line.ship,
                "edition_id": edition.annotation.id,
            },
        }

    def candidate(
        self,
        *,
        assertion_ref: Mapping[str, object],
        enrollment: Mapping[str, object],
        projection: Any,
        evidence: ChatlasEvidence,
    ) -> JsonObject:
        subject_ref = assertion_ref.get("subject_ref")
        if not isinstance(subject_ref, dict):
            raise ScoringError("grounding Assertion has no subject Reference")
        line_ship = str(subject_ref.get("line_ship", ""))
        edition_id = str(subject_ref.get("edition_id", ""))
        try:
            line = projection.line(line_ship)
            block = projection.block(line.block_ship)
        except DiagramError as exc:
            raise ScoringError(
                f"Line {line_ship} does not belong to the current Diagram Model"
            ) from exc
        editions = tuple(
            item for item in line.editions if item.annotation.id == edition_id
        )
        if len(editions) != 1:
            raise ScoringError(f"Line Edition does not resolve: {edition_id}")
        edition = editions[0]
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
            "enrollment_ref": record_reference(enrollment),
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
    enrollments: Sequence[Mapping[str, object]],
    candidates: Sequence[Mapping[str, object]],
    appendix: Sequence[str] = (),
    registry: AssertionRankingRegistry = DEFAULT_ASSERTION_RANKING_REGISTRY,
) -> JsonObject:
    """Create a Task through its Assertion Type's registered producer."""

    assertion_type = registry.resolve(GROUNDING_ASSERTION_TYPE)
    return assertion_type.method(GROUNDING_RANKING_METHOD).create(
        pool=pool,
        enrollments=enrollments,
        candidates=candidates,
        appendix=appendix,
    )


def create_line_grounding_task(
    *,
    pool: JsonObject,
    enrollments: Sequence[Mapping[str, object]],
    project_path: Path,
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
        candidates = []
        for enrollment in enrollments:
            assertion_ref = _enrollment_assertion_ref(enrollment)
            assertion_class = registry.resolve(_assertion_type_id(assertion_ref))
            assertion_class.method(str(pool.get("scoring_method", "")))
            if not isinstance(assertion_class, IndexLineGroundingAssertionType):
                raise ScoringError("grounding Pool contains an incompatible Assertion")
            candidates.append(
                assertion_class.candidate(
                    assertion_ref=assertion_ref,
                    enrollment=enrollment,
                    projection=projection,
                    evidence=resolved_evidence,
                )
            )
    except (DiagramError, ValueError) as exc:
        raise ScoringError(str(exc)) from exc
    return assertion_type.method(GROUNDING_RANKING_METHOD).create(
        pool=pool,
        enrollments=enrollments,
        candidates=candidates,
        appendix=appendix,
    )


def _candidate_id(candidate: Mapping[str, object]) -> str:
    value = candidate.get("id")
    if not isinstance(value, str) or not value:
        raise ScoringError("Ranking Task candidate id must be a non-empty string")
    return value


def create_line_grounding_enrollments(
    *,
    pool: JsonObject,
    project_path: Path,
    line_ships: Sequence[str],
    diagram_config: Path | None = None,
    registry: AssertionRankingRegistry = DEFAULT_ASSERTION_RANKING_REGISTRY,
) -> tuple[JsonObject, ...]:
    """Resolve current Line Assertions and request explicit Pool enrollment."""

    return tuple(
        create_pool_enrollment(
            pool=pool,
            assertion_ref=assertion_ref,
        )
        for assertion_ref in line_grounding_assertion_references(
            project_path=project_path,
            line_ships=line_ships,
            diagram_config=diagram_config,
            registry=registry,
            scoring_method=str(pool.get("scoring_method", "")),
        )
    )


def line_grounding_assertion_references(
    *,
    project_path: Path,
    line_ships: Sequence[str],
    diagram_config: Path | None = None,
    registry: AssertionRankingRegistry = DEFAULT_ASSERTION_RANKING_REGISTRY,
    scoring_method: str = GROUNDING_RANKING_METHOD,
) -> tuple[JsonObject, ...]:
    """Resolve current Line-grounding Assertion instances through their class."""

    project = require_agentos_project(project=project_path)
    try:
        model = (
            DiagramConfiguration.load(diagram_config)
            .diagram()
            .project_model(project.root)
        )
        projection = model.project(include_collection_content=True)
    except (DiagramError, ValueError) as exc:
        raise ScoringError(str(exc)) from exc
    assertion_class = registry.resolve(GROUNDING_ASSERTION_TYPE)
    if not isinstance(assertion_class, IndexLineGroundingAssertionType):
        raise ScoringError("registered grounding Assertion Type has an invalid class")
    assertion_class.method(scoring_method)
    return tuple(
        assertion_class.reference(
            line_ship=line_ship,
            namespace_id=model.namespace.id,
            projection=projection,
        )
        for line_ship in line_ships
    )


def _enrollment_assertion_ref(
    enrollment: Mapping[str, object],
) -> Mapping[str, object]:
    value = enrollment.get("assertion_ref")
    if not isinstance(value, dict):
        raise ScoringError("Pool Enrollment assertion_ref must be an object")
    return value


def _assertion_type_id(assertion_ref: Mapping[str, object]) -> str:
    reference_type = assertion_ref.get("type")
    if not isinstance(reference_type, str) or not reference_type.endswith(".Reference"):
        raise ScoringError("Assertion Reference has no resolvable Type")
    return reference_type.removesuffix(".Reference")


def _assertion_instance_id(assertion_ref: Mapping[str, object]) -> str:
    subject_ref = assertion_ref.get("subject_ref")
    if not isinstance(subject_ref, dict):
        raise ScoringError("Assertion Reference has no subject Reference")
    edition_id = subject_ref.get("edition_id")
    if not isinstance(edition_id, str) or not edition_id:
        raise ScoringError("Assertion subject Reference has no edition id")
    return edition_id


def _reference_id(value: object) -> str | None:
    return value.get("id") if isinstance(value, dict) else None


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
    "IndexLineGroundingRankingMethod",
    "create_grounding_task",
    "create_line_grounding_enrollments",
    "create_line_grounding_task",
    "line_grounding_assertion_references",
]
