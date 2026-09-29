"""tarav.l2.unsorted.assessment: extracted legacy definitions; identities and storage labels preserved."""

from __future__ import annotations

from tarav.l2.unsorted.constants import CAPTURE_AUTHORIZATION_ASSERTIONS
from tarav.l2.unsorted.authorization import CaptureAuthorizationGateRecord
from tarav.l2.unsorted.primitives import DiagramError
from tarav.l2.unsorted.primitives import DiagramModelError
from tarav.l2.unsorted.contracts import Finding
from tarav.l2.unsorted.contracts import GateAssessment
from tarav.l2.lines.records import LineAnnotationRecord
from tarav.l2.lines.records import LineEditionRecord
from tarav.l2.lines.records import LineGateAnnotation
from typing import Protocol
from tarav.l2.unsorted.records import TypedAnnotation
from tarav.l2.unsorted.constants import VERBATIM_GATE_ASSERTIONS
from dataclasses import dataclass
import re
import unicodedata
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tarav.l2.unsorted.evidence import ChatlasEvidence
    from tarav.l2.unsorted.contracts import ChatlasTurnReferenceInterface
    from tarav.l2.unsorted.records import DiagramAnnotation
    from collections.abc import Iterable
    from tarav.l2.unsorted.constants import JsonObject
    from tarav.l2.unsorted.contracts import VerbatimGate

@dataclass(frozen=True, slots=True)
class AssertionEvaluation:
    """One evaluator's derived result over an Annotation."""

    evaluator: str
    scores: JsonObject
    findings: tuple[Finding, ...] = ()
    gate_assessments: tuple[GateAssessment, ...] = ()


class MechanicalAssertionEvaluator(Protocol):
    name: str
    assertion_types: tuple[str, ...]

    def evaluate(
        self,
        annotation: TypedAnnotation,
        *,
        evidence: ChatlasEvidence | None,
        path: str,
    ) -> AssertionEvaluation: ...


@dataclass(frozen=True, slots=True)
class AnnotationAssessment:
    """Current derived Assertion state for one Annotation claim edition."""

    annotation_id: str
    assertion_types: tuple[str, ...]
    score_vector: JsonObject
    evaluations: tuple[AssertionEvaluation, ...]

    @property
    def findings(self) -> tuple[Finding, ...]:
        return tuple(
            finding
            for evaluation in self.evaluations
            for finding in evaluation.findings
        )

    @property
    def gate_assessments(self) -> tuple[GateAssessment, ...]:
        return tuple(
            assessment
            for evaluation in self.evaluations
            for assessment in evaluation.gate_assessments
        )

    @property
    def standing(self) -> str:
        return (
            "Asserted"
            if all(
                assertion_type in self.score_vector
                and self.score_vector[assertion_type] is not None
                for assertion_type in self.assertion_types
            )
            else "UnAsserted"
        )

    def assertion_state(self, assertion_type: str) -> str:
        if assertion_type not in self.score_vector:
            return "NotEvaluated"
        score = self.score_vector[assertion_type]
        if score is None:
            return "Unassessable"
        if score is True:
            return "Passed"
        if score is False:
            return "Failed"
        return "Scored"

    def to_dict(self) -> JsonObject:
        return {
            "annotation_id": self.annotation_id,
            "standing": self.standing,
            "score_vector": dict(self.score_vector),
            "assertions": [
                {
                    "type": assertion_type,
                    "state": self.assertion_state(assertion_type),
                    **(
                        {"score": self.score_vector[assertion_type]}
                        if assertion_type in self.score_vector
                        else {}
                    ),
                }
                for assertion_type in self.assertion_types
            ],
            "findings": [item.to_dict() for item in self.findings],
        }


@dataclass(frozen=True, slots=True)
class VerbatimGateAssertionEvaluator:
    name: str = "Verbatim.Gate.Assertion.Evaluator"
    assertion_types: tuple[str, ...] = VERBATIM_GATE_ASSERTIONS

    def evaluate(
        self,
        annotation: TypedAnnotation,
        *,
        evidence: ChatlasEvidence | None,
        path: str,
    ) -> AssertionEvaluation:
        if isinstance(annotation, (LineEditionRecord, LineAnnotationRecord)):
            target_id = (
                annotation.current_edition_id
                if isinstance(annotation, LineAnnotationRecord)
                else annotation.id
            )
            assessments = _assess_verbatim_gates(
                annotation_id=annotation.id,
                target_id=target_id,
                target=annotation,
                gates=annotation.gates,
                evidence=evidence,
                path=path,
            )
        elif isinstance(annotation, LineGateAnnotation):
            try:
                target = annotation.target
                target_finding = None
            except (DiagramError, DiagramModelError) as exc:
                target = None
                target_finding = Finding(
                    "line-gate-target-unresolved",
                    f"{path}.target_edition",
                    str(exc),
                )
            assessments = _assess_verbatim_gates(
                annotation_id=annotation.id,
                target_id=annotation.target_edition_id,
                target=target,
                gates=annotation.gates,
                evidence=evidence,
                path=path,
                target_finding=target_finding,
            )
        else:
            assessments = ()
        return AssertionEvaluation(
            self.name,
            {
                assertion_type: _aggregate_assertion_scores(
                    assessment.scores.get(assertion_type) for assessment in assessments
                )
                for assertion_type in self.assertion_types
            },
            tuple(
                finding for assessment in assessments for finding in assessment.findings
            ),
            assessments,
        )


@dataclass(frozen=True, slots=True)
class CaptureAuthorizationAssertionEvaluator:
    name: str = "Capture.Authorization.Assertion.Evaluator"
    assertion_types: tuple[str, ...] = CAPTURE_AUTHORIZATION_ASSERTIONS

    def evaluate(
        self,
        annotation: TypedAnnotation,
        *,
        evidence: ChatlasEvidence | None,
        path: str,
    ) -> AssertionEvaluation:
        if not isinstance(annotation, CaptureAuthorizationGateRecord):
            return AssertionEvaluation(self.name, {})
        if evidence is None:
            return AssertionEvaluation(
                self.name,
                {kind: None for kind in self.assertion_types},
                (
                    Finding(
                        "capture-authorization-unassessable",
                        path,
                        "Capture.Authorization.Gate requires Chatlas evidence.",
                    ),
                ),
            )
        findings: list[Finding] = []
        try:
            turn = evidence.turn(annotation.permission_turn)
            role_score = turn.get("side") == "user"
            token_score = annotation.token in evidence.turn_text(
                annotation.permission_turn
            )
        except DiagramError as exc:
            role_score = None
            token_score = None
            findings.append(
                Finding(
                    "capture-authorization-permission-unresolved",
                    f"{path}.permission_turn",
                    str(exc),
                )
            )
        local_scope = all(
            reference.namespace_id == annotation.annotation.namespace.id
            for reference in annotation.target_scope
        )
        scope_score = (
            all(
                annotation.annotation.namespace.resolves_argument(reference)
                for reference in annotation.target_scope
            )
            if local_scope
            else None
        )
        if role_score is False:
            findings.append(
                Finding(
                    "capture-authorization-permission-not-user",
                    f"{path}.permission_turn",
                    "Capture authorization permission evidence is not a User turn.",
                )
            )
        if token_score is False:
            findings.append(
                Finding(
                    "capture-authorization-token-missing",
                    f"{path}.token",
                    "Authorization token does not occur in its permission evidence.",
                )
            )
        if scope_score is False:
            findings.append(
                Finding(
                    "capture-authorization-scope-unresolved",
                    f"{path}.target_scope",
                    "One or more authorization targets do not resolve.",
                )
            )
        elif scope_score is None:
            findings.append(
                Finding(
                    "capture-authorization-scope-unassessable",
                    f"{path}.target_scope",
                    "Cross-Namespace authorization scope requires Diagram-level resolution.",
                )
            )
        return AssertionEvaluation(
            self.name,
            {
                self.assertion_types[0]: role_score,
                self.assertion_types[1]: token_score,
                self.assertion_types[2]: scope_score,
            },
            tuple(findings),
        )


class AssertionEngine:
    """Central evaluator for retained and mechanically derived Assertion scores."""

    def __init__(
        self,
        *,
        evidence: ChatlasEvidence | None = None,
        evaluators: Iterable[MechanicalAssertionEvaluator] | None = None,
    ) -> None:
        self.evidence = evidence
        self._evaluators: dict[str, MechanicalAssertionEvaluator] = {}
        for evaluator in evaluators or (
            VerbatimGateAssertionEvaluator(),
            CaptureAuthorizationAssertionEvaluator(),
        ):
            self.register(evaluator)

    def register(self, evaluator: MechanicalAssertionEvaluator) -> None:
        for assertion_type in evaluator.assertion_types:
            existing = self._evaluators.get(assertion_type)
            if existing is not None and existing is not evaluator:
                raise DiagramError(
                    f"Assertion evaluator already registered for {assertion_type}"
                )
            self._evaluators[assertion_type] = evaluator

    def assess(
        self,
        annotation: DiagramAnnotation | TypedAnnotation,
        *,
        path: str | None = None,
    ) -> AnnotationAssessment:
        generic = (
            annotation.annotation
            if isinstance(annotation, TypedAnnotation)
            else annotation
        )
        typed = (
            annotation
            if isinstance(annotation, TypedAnnotation)
            else generic.specialize()
        )
        assertion_types = tuple(
            assertion_type
            for assertion in generic.assertions()
            if isinstance((assertion_type := assertion.get("type")), str)
        )
        retained = generic.score_vector()
        scores = {
            assertion_type: retained[assertion_type]
            for assertion_type in assertion_types
            if assertion_type in retained
        }
        selected: list[MechanicalAssertionEvaluator] = []
        selected_ids: set[int] = set()
        for assertion_type in assertion_types:
            evaluator = self._evaluators.get(assertion_type)
            if evaluator is not None and id(evaluator) not in selected_ids:
                selected.append(evaluator)
                selected_ids.add(id(evaluator))
        evaluations = tuple(
            evaluator.evaluate(
                typed,
                evidence=self.evidence,
                path=path or f"annotation.{generic.id}",
            )
            for evaluator in selected
        )
        for evaluation in evaluations:
            scores.update(
                {
                    assertion_type: score
                    for assertion_type, score in evaluation.scores.items()
                    if assertion_type in assertion_types
                }
            )
        return AnnotationAssessment(
            generic.id,
            assertion_types,
            scores,
            evaluations,
        )

    def score_vector(
        self, annotation: DiagramAnnotation | TypedAnnotation
    ) -> JsonObject:
        return dict(self.assess(annotation).score_vector)


def _line_target_edition_id(
    target: LineEditionRecord | LineAnnotationRecord,
) -> str:
    return (
        target.current_edition_id
        if isinstance(target, LineAnnotationRecord)
        else target.id
    )


def _assess_verbatim_gates(
    *,
    annotation_id: str,
    target_id: str,
    target: LineEditionRecord | LineAnnotationRecord | None,
    gates: tuple[VerbatimGate, ...],
    evidence: ChatlasEvidence | None,
    path: str,
    target_finding: Finding | None = None,
) -> tuple[GateAssessment, ...]:
    assessments: list[GateAssessment] = []
    for index, gate in enumerate(gates):
        gate_path = f"{path}.gates[{index}]"
        if target is None:
            scores = {name: None for name in VERBATIM_GATE_ASSERTIONS}
            scores["Verbatim.Gate.Target.Assertion"] = False
            assessments.append(
                GateAssessment(
                    annotation_id,
                    target_id,
                    gate,
                    scores,
                    (target_finding,) if target_finding else (),
                )
            )
        elif evidence is None:
            scores = {name: None for name in VERBATIM_GATE_ASSERTIONS}
            scores["Verbatim.Gate.Target.Assertion"] = True
            assessments.append(
                GateAssessment(
                    annotation_id,
                    _line_target_edition_id(target),
                    gate,
                    scores,
                    (
                        Finding(
                            "verbatim-gate-unassessable",
                            gate_path,
                            "Verbatim.Gate requires Chatlas evidence for assessment.",
                        ),
                    ),
                )
            )
        else:
            assessments.append(
                _assess_verbatim_gate(
                    evidence=evidence,
                    annotation_id=annotation_id,
                    target=target,
                    gate=gate,
                    path=gate_path,
                )
            )
    return tuple(assessments)


def _assess_verbatim_gate(
    *,
    evidence: ChatlasEvidence,
    annotation_id: str,
    target: LineEditionRecord | LineAnnotationRecord,
    gate: VerbatimGate,
    path: str,
) -> GateAssessment:
    scores: JsonObject = {name: None for name in VERBATIM_GATE_ASSERTIONS}
    scores["Verbatim.Gate.Target.Assertion"] = True
    findings: list[Finding] = []
    proposal_path = f"{path}.proposal_turn"
    approval_path = f"{path}.approval_turn"
    proposal = _gate_turn(
        evidence,
        gate.proposal_turn,
        proposal_path,
        "verbatim-gate-proposal-unresolved",
        findings,
    )
    approval = _gate_turn(
        evidence,
        gate.approval_turn,
        approval_path,
        "verbatim-gate-approval-unresolved",
        findings,
    )
    proposal_text: str | None = None
    approval_text: str | None = None
    if proposal is not None:
        proposal_role = proposal.get("side") == "agent"
        scores["Verbatim.Gate.Proposal.Role.Assertion"] = proposal_role
        proposal_text = evidence.turn_text(gate.proposal_turn)
        if not proposal_role:
            findings.append(
                Finding(
                    "verbatim-gate-proposal-not-agent",
                    proposal_path,
                    "Verbatim.Gate proposal is not an Agent turn.",
                )
            )
    if approval is not None:
        approval_role = approval.get("side") == "user"
        scores["Verbatim.Gate.Approval.Role.Assertion"] = approval_role
        approval_text = evidence.turn_text(gate.approval_turn)
        if not approval_role:
            findings.append(
                Finding(
                    "verbatim-gate-approval-not-user",
                    approval_path,
                    "Verbatim.Gate approval is not a User turn.",
                )
            )

    if proposal_text is not None and approval_text is not None:
        token_matches = gate.token in proposal_text and _explicitly_approves_token(
            approval_text, gate.token
        )
        scores["Verbatim.Gate.Token.Assertion"] = token_matches
        if not token_matches:
            findings.append(
                Finding(
                    "verbatim-gate-token-mismatch",
                    path,
                    "Gate token is not present in the proposal and explicitly approved by the User.",
                )
            )

    if proposal is not None and approval is not None:
        same_session = (
            gate.proposal_turn.session_identity == gate.approval_turn.session_identity
        )
        ordered = False
        if same_session:
            try:
                ordered = evidence.position(gate.proposal_turn) < evidence.position(
                    gate.approval_turn
                )
            except DiagramError:
                ordered = False
        scores["Verbatim.Gate.Order.Assertion"] = same_session and ordered
        if not same_session or not ordered:
            findings.append(
                Finding(
                    "verbatim-gate-order-mismatch",
                    path,
                    "Verbatim.Gate approval does not follow its proposal in one chat.",
                )
            )

    if proposal_text is not None:
        content_matches = _canonical_review_content(
            target.text
        ) in _canonical_review_content(proposal_text)
        scores["Verbatim.Gate.Content.Assertion"] = content_matches
        if not content_matches:
            findings.append(
                Finding(
                    "verbatim-gate-content-mismatch",
                    path,
                    "The proposal turn does not contain materially equivalent Line wording.",
                )
            )

    return GateAssessment(
        annotation_id,
        _line_target_edition_id(target),
        gate,
        scores,
        tuple(findings),
    )


def _gate_turn(
    evidence: ChatlasEvidence,
    reference: ChatlasTurnReferenceInterface,
    path: str,
    code: str,
    findings: list[Finding],
) -> JsonObject | None:
    try:
        return evidence.turn(reference)
    except (DiagramError, ValueError) as exc:
        findings.append(Finding(code, path, str(exc)))
        return None


def _aggregate_assertion_scores(scores: Iterable[object]) -> object:
    values = tuple(scores)
    if any(value is False for value in values):
        return False
    if values and all(value is True for value in values):
        return True
    return None


def _explicitly_approves_token(text: str, token: str) -> bool:
    return re.search(rf"(?m)^\s*::approve\s+{re.escape(token)}\s*$", text) is not None


def _canonical_review_content(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return "".join(character for character in normalized if not character.isspace())
