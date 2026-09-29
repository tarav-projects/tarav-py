"""Assertion-owned construction of Ranking Tasks."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, Mapping, Sequence

from tarav.l0._core.project import require_agentos_project
from tarav.l2.unsorted.evidence import ChatlasEvidence
from tarav.l2.unsorted.storage import DiagramConfiguration
from tarav.l2.unsorted.primitives import DiagramError
from tarav.l0.kernel import TaravClass, TaravType, TypeShip, entity
from tarav.l2.lines.assertions import LineGroundingAssertion
from .assertions import Assertion
from .identity import SCORING_WORKFLOW_SHIP

from .model import (
    GROUNDING_ASSERTION_TYPE,
    GROUNDING_POOL_TYPE,
    GROUNDING_TASK_TYPE,
    POOL_ENROLLMENT_TYPE,
    JsonObject,
    ScoringError,
    create_pool_enrollment,
    new_record,
    record_reference,
    validate_record,
)


class AssertionPool(TaravType, ABC):
    """Code-level base for concrete retained Assertion Pool Types."""

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls,
                          id=TypeShip('b21fbc0b-aad3-45df-aea3-2413e835bdbb'),
                          name='Tarav.Scoring.AssertionPool', workflow=SCORING_WORKFLOW_SHIP)

    record_type: ClassVar[str]
    task_type: ClassVar[str]

    def create(self, *, name: str) -> JsonObject:
        return new_record(self.record_type, name=name)

    def validate(self, pool: Mapping[str, object]) -> None:
        validate_record(pool)
        if pool["type"] != self.record_type:
            raise ScoringError(f"expected a {self.record_type} Record")

    @abstractmethod
    def create_task(
        self,
        *,
        pool: Mapping[str, object],
        enrollments: Sequence[Mapping[str, object]],
        candidates: Sequence[Mapping[str, object]],
        appendix: Sequence[str] = (),
    ) -> JsonObject: ...


@dataclass(frozen=True, slots=True)
class IndexLineGroundingRankingPool(AssertionPool):
    """Comparative mechanics for one population of grounding Assertions."""

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls,
                          id=TypeShip('876ca1c7-e0bb-4437-b83e-15cfe51b0a3f'),
                          name='Tarav.Scoring.LineGroundingRankingPool')

    record_type: ClassVar[str] = GROUNDING_POOL_TYPE
    task_type: ClassVar[str] = GROUNDING_TASK_TYPE

    def create_task(
        self,
        *,
        pool: Mapping[str, object],
        enrollments: Sequence[Mapping[str, object]],
        candidates: Sequence[Mapping[str, object]],
        appendix: Sequence[str] = (),
    ) -> JsonObject:
        self.validate(pool)
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


class AssertionRankingRegistry:
    """Resolve Assertion-owned adaptation into Pool candidate contracts."""

    def __init__(self, assertion_types: Sequence[type[Assertion]] = ()) -> None:
        self._types: dict[str, type[Assertion]] = {}
        for assertion_type in assertion_types:
            self.register(assertion_type)

    def register(self, assertion_type: type[Assertion]) -> None:
        if not isinstance(assertion_type, type) or not issubclass(assertion_type, Assertion):
            raise TypeError('Expected an Assertion subclass')
        type_id = entity(assertion_type).name
        if type_id in self._types:
            raise ScoringError(f"Assertion Ranking Type already registered: {type_id}")
        self._types[type_id] = assertion_type

    def resolve(self, assertion_type: str) -> type[Assertion]:
        try:
            return self._types[assertion_type]
        except KeyError as exc:
            raise ScoringError(
                f"Assertion Type has no Ranking.Task producers: {assertion_type}"
            ) from exc


DEFAULT_ASSERTION_RANKING_REGISTRY = AssertionRankingRegistry(
    (LineGroundingAssertion,)
)


class RankingPoolRegistry:
    """Resolve Pool-owned comparative Task mechanics."""

    def __init__(self, pool_classes: Sequence[AssertionPool] = ()) -> None:
        self._classes: dict[str, AssertionPool] = {}
        for pool_class in pool_classes:
            self.register(pool_class)

    def register(self, pool_class: AssertionPool) -> None:
        type_id = pool_class.record_type
        if type_id in self._classes:
            raise ScoringError(f"Ranking Pool Class already registered: {type_id}")
        self._classes[type_id] = pool_class

    def resolve(self, pool_type: str) -> AssertionPool:
        try:
            return self._classes[pool_type]
        except KeyError as exc:
            raise ScoringError(f"unknown Ranking Pool Type: {pool_type}") from exc


DEFAULT_RANKING_POOL_REGISTRY = RankingPoolRegistry((IndexLineGroundingRankingPool(),))


def create_grounding_task(
    *,
    pool: Mapping[str, object],
    enrollments: Sequence[Mapping[str, object]],
    candidates: Sequence[Mapping[str, object]],
    appendix: Sequence[str] = (),
    pool_registry: RankingPoolRegistry = DEFAULT_RANKING_POOL_REGISTRY,
) -> JsonObject:
    """Create a Task through the Pool Class governing its population."""

    pool_class = pool_registry.resolve(str(pool.get("type", "")))
    return pool_class.create_task(
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
    assertion_registry: AssertionRankingRegistry = DEFAULT_ASSERTION_RANKING_REGISTRY,
    pool_registry: RankingPoolRegistry = DEFAULT_RANKING_POOL_REGISTRY,
) -> JsonObject:
    """Adapt Assertions into candidates, then let the Pool assemble its Task."""

    project = require_agentos_project(project=project_path)
    pool_class = pool_registry.resolve(str(pool.get("type", "")))
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
            assertion_class = assertion_registry.resolve(
                _assertion_type_id(assertion_ref)
            )
            assertion_class.supports_pool(pool_class.record_type)
            candidates.append(
                assertion_class.from_reference(assertion_ref).candidate(
                    enrollment=enrollment,
                    pool_type=pool_class.record_type,
                    projection=projection,
                    evidence=resolved_evidence,
                )
            )
    except (DiagramError, ValueError) as exc:
        raise ScoringError(str(exc)) from exc
    return pool_class.create_task(
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
            pool_type=str(pool.get("type", "")),
        )
    )


def line_grounding_assertion_references(
    *,
    project_path: Path,
    line_ships: Sequence[str],
    diagram_config: Path | None = None,
    registry: AssertionRankingRegistry = DEFAULT_ASSERTION_RANKING_REGISTRY,
    pool_type: str = GROUNDING_POOL_TYPE,
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
    assertion_class.supports_pool(pool_type)
    return tuple(
        assertion_class.from_line(
            line_ship=line_ship,
            namespace_id=model.namespace.id,
            projection=projection,
        ).reference()
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


__all__ = [
    "DEFAULT_ASSERTION_RANKING_REGISTRY",
    "DEFAULT_RANKING_POOL_REGISTRY",
    "AssertionRankingRegistry",
    "AssertionPool",
    "IndexLineGroundingRankingPool",
    "RankingPoolRegistry",
    "create_grounding_task",
    "create_line_grounding_enrollments",
    "create_line_grounding_task",
    "line_grounding_assertion_references",
]
