"""Namespace-rooted Tarav2 Diagram mechanics."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
from typing import Any, Protocol
import unicodedata
from uuid import UUID, uuid4

from tarav._core.persistence import atomic_write_json
from tarav._core.project import load_project_marker, project_marker_path
from tarav.chatlas.normal_model import (
    provide_normal_model,
    resolve_chat_message_ref,
    resolve_chat_turn_ref,
    resolve_event_ref,
)

NAMESPACE_CLASS = "Tarav.Diagram.Namespace"
DIAGRAM_CONFIG_CLASS = "Tarav.Diagram.Configuration"
CAPTURE_MANIFEST_CLASS = "Tarav.Diagram.Capture.Manifest"
USER_TOUCHED_CHATLAS_INDEX = "User.Touched.Chatlas.Index"
DIAGRAM_ATTIC = "Diagram.Attic"
MODEL_ANNOTATION_TYPE = "Diagram.Model.Annotation"
BLOCK_ANNOTATION_TYPE = "Diagram.Block.Annotation"
BLOCK_TYPE_ANNOTATION_TYPE = "Diagram.Block.Type.Annotation"
LINE_ANNOTATION_TYPE = "Diagram.Line.Annotation"
LINE_TYPE_ANNOTATION_TYPE = "Diagram.Line.Type.Annotation"
LINE_SUPPORT_ANNOTATION_TYPE = "Diagram.Line.Support.Annotation"
LINE_GATE_ANNOTATION_TYPE = "Diagram.Line.Gate.Annotation"
VERBATIM_GATE_TYPE = "Verbatim.Gate"
DIAGRAM_BLOCK_OBJECT_TYPE = "Diagram.Block"
DESIGN_BLOCK_OBJECT_TYPE = "Design.Block"
IMPL_REQ_BLOCK_OBJECT_TYPE = "Impl.Req.Block"
ISSUE_BLOCK_OBJECT_TYPE = "Issue.Block"
DIAGRAM_LINE_OBJECT_TYPE = "Diagram.Line"
DESIGN_LINE_DEFINITION_TYPE = "Design.Line.Definition"
DESIGN_LINE_DECISION_TYPE = "Design.Line.Decision"
DESIGN_LINE_CONSTRAINT_TYPE = "Design.Line.Constraint"
DESIGN_LINE_REJECTION_TYPE = "Design.Line.Rejection"
DESIGN_LINE_PRINCIPLE_TYPE = "Design.Line.Principle"
DESIGN_LINE_FREEDOM_TYPE = "Design.Line.Freedom"
DESIGN_LINE_EXAMPLE_TYPE = "Design.Line.Example"
ISSUE_LINE_RESOLVE_TYPE = "Issue.Line.Resolve"
DESIGN_LINE_OBJECT_TYPES = (
    DESIGN_LINE_DEFINITION_TYPE,
    DESIGN_LINE_DECISION_TYPE,
    DESIGN_LINE_CONSTRAINT_TYPE,
    DESIGN_LINE_REJECTION_TYPE,
    DESIGN_LINE_PRINCIPLE_TYPE,
    DESIGN_LINE_FREEDOM_TYPE,
    DESIGN_LINE_EXAMPLE_TYPE,
)
DIAGRAM_BLOCK_TYPE_DEFINITION_BLOCK_SHIP = (
    "7b2bb6ef-37b8-47e0-8c6b-2ff5ccbdd82d"
)
DESIGN_BLOCK_TYPE_DEFINITION_BLOCK_SHIP = (
    "aa26bfa3-49f6-406d-b74f-f071ec3d11fa"
)
IMPL_REQ_BLOCK_TYPE_DEFINITION_BLOCK_SHIP = (
    "f6dfcbcb-6eb5-468c-a3f8-7f7034334b94"
)
ISSUE_BLOCK_TYPE_DEFINITION_BLOCK_SHIP = (
    "4864c2cc-9542-49ea-8295-a566eea29164"
)
ISSUE_LINE_RESOLVE_TYPE_DEFINITION_BLOCK_SHIP = (
    "3753a425-04e7-4d62-9d44-01f42af5b5e4"
)
DESIGN_LINE_TYPE_DEFINITION_BLOCK_SHIPS = {
    DESIGN_LINE_DEFINITION_TYPE: "00a33f68-90a7-4a92-87c4-c3862e879bc5",
    DESIGN_LINE_DECISION_TYPE: "7cf2af24-e6d9-46b7-a09a-c43db69ccd68",
    DESIGN_LINE_CONSTRAINT_TYPE: "9b0bea0f-1408-483e-85cf-504e2009ad25",
    DESIGN_LINE_REJECTION_TYPE: "2d3dd161-b4c2-4810-9e2b-4fda1a6c8743",
    DESIGN_LINE_PRINCIPLE_TYPE: "6c43fce3-dd2d-40d3-b676-4e58df8195ee",
    DESIGN_LINE_FREEDOM_TYPE: "1894d99c-ddca-491d-a586-1a7a53e9c4b0",
    DESIGN_LINE_EXAMPLE_TYPE: "1366fc61-a9fe-4ef5-91dc-6f13f0447e30",
}
CHATLAS_INDEX_NAMESPACES = frozenset((USER_TOUCHED_CHATLAS_INDEX, DIAGRAM_ATTIC))
CHATLAS_INDEX_ANNOTATION_TYPES = (
    MODEL_ANNOTATION_TYPE,
    BLOCK_ANNOTATION_TYPE,
    BLOCK_TYPE_ANNOTATION_TYPE,
    LINE_ANNOTATION_TYPE,
    LINE_TYPE_ANNOTATION_TYPE,
    LINE_SUPPORT_ANNOTATION_TYPE,
    LINE_GATE_ANNOTATION_TYPE,
)
SCHEMA_VERSION = 1
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
JsonObject = dict[str, Any]


class DiagramError(RuntimeError):
    pass


class DiagramModelError(ValueError):
    pass


class DiagramAnnotationSpecializationError(DiagramError):
    pass


@dataclass(frozen=True, slots=True)
class Finding:
    code: str
    path: str
    message: str

    def to_dict(self) -> JsonObject:
        return {
            "class": "Tarav.POI.Instance",
            "code": self.code,
            "path": self.path,
            "message": self.message,
        }


@dataclass(frozen=True, slots=True)
class ChatlasTurnReference:
    session_identity: str
    turn_address: str
    turn_hash: str

    def __post_init__(self) -> None:
        _digest(self.session_identity, field="Chatlas.Reference.session_identity")
        _digest(self.turn_address, field="Chatlas.Reference.turn_address")
        _digest(self.turn_hash, field="Chatlas.Reference.turn_hash")

    def to_dict(self) -> dict[str, str]:
        return {
            "session_identity": self.session_identity,
            "turn_address": self.turn_address,
            "turn_hash": self.turn_hash,
        }

    @classmethod
    def from_dict(cls, value: object) -> ChatlasTurnReference:
        data = _object(value, field="Chatlas.Reference")
        return cls(
            _string(data.get("session_identity"), field="session_identity"),
            _string(data.get("turn_address"), field="turn_address"),
            _string(data.get("turn_hash"), field="turn_hash"),
        )


@dataclass(frozen=True, slots=True)
class VerbatimGate:
    token: str
    proposal_turn: ChatlasTurnReference
    approval_turn: ChatlasTurnReference

    def __post_init__(self) -> None:
        _string(self.token, field="Verbatim.Gate.token")

    def to_dict(self) -> JsonObject:
        return {
            "type": VERBATIM_GATE_TYPE,
            "token": self.token,
            "proposal_turn": self.proposal_turn.to_dict(),
            "approval_turn": self.approval_turn.to_dict(),
        }

    @classmethod
    def from_dict(cls, value: object) -> VerbatimGate:
        data = _object(value, field="Verbatim.Gate")
        if data.get("type") != VERBATIM_GATE_TYPE:
            raise DiagramModelError(f"unsupported Line Gate type: {data.get('type')}")
        return cls(
            _string(data.get("token"), field="Verbatim.Gate.token"),
            ChatlasTurnReference.from_dict(data.get("proposal_turn")),
            ChatlasTurnReference.from_dict(data.get("approval_turn")),
        )


VERBATIM_GATE_ASSERTIONS = (
    "Verbatim.Gate.Target.Assertion",
    "Verbatim.Gate.Proposal.Role.Assertion",
    "Verbatim.Gate.Approval.Role.Assertion",
    "Verbatim.Gate.Token.Assertion",
    "Verbatim.Gate.Order.Assertion",
    "Verbatim.Gate.Content.Assertion",
)


@dataclass(frozen=True, slots=True)
class GateAssessment:
    annotation_id: str
    target_annotation_id: str
    gate: VerbatimGate
    scores: JsonObject
    findings: tuple[Finding, ...]

    @property
    def standing(self) -> str:
        values = tuple(self.scores.values())
        if values and all(value is True for value in values):
            return "Passed"
        if any(value is False for value in values):
            return "Failed"
        return "Unassessable"

    def to_dict(self) -> JsonObject:
        return {
            "annotation_id": self.annotation_id,
            "target_annotation_id": self.target_annotation_id,
            "gate": self.gate.to_dict(),
            "standing": self.standing,
            "scores": dict(self.scores),
            "findings": [item.to_dict() for item in self.findings],
        }


@dataclass(frozen=True, slots=True)
class LineReview:
    line_ship: str
    standing: str
    assessments: tuple[GateAssessment, ...]
    findings: tuple[Finding, ...]

    def to_dict(self) -> JsonObject:
        return {
            "line_ship": self.line_ship,
            "standing": self.standing,
            "assessments": [item.to_dict() for item in self.assessments],
            "findings": [item.to_dict() for item in self.findings],
        }


@dataclass(frozen=True, slots=True)
class IssueAssessment:
    block_ship: str
    state: str
    resolution_line_ships: tuple[str, ...]
    gate_assessments: tuple[GateAssessment, ...]
    findings: tuple[Finding, ...]

    def to_dict(self) -> JsonObject:
        return {
            "block_ship": self.block_ship,
            "state": self.state,
            "resolution_line_ships": list(self.resolution_line_ships),
            "gate_assessments": [item.to_dict() for item in self.gate_assessments],
            "findings": [item.to_dict() for item in self.findings],
        }


@dataclass(frozen=True, slots=True)
class SupportMember:
    root: ChatlasTurnReference
    neighborhood: tuple[ChatlasTurnReference, ...] = ()

    def to_dict(self) -> JsonObject:
        return {
            "root": self.root.to_dict(),
            "neighborhood": [item.to_dict() for item in self.neighborhood],
        }

    @classmethod
    def from_dict(cls, value: object) -> SupportMember:
        data = _object(value, field="Support.Member")
        return cls(
            ChatlasTurnReference.from_dict(data.get("root")),
            tuple(
                ChatlasTurnReference.from_dict(item)
                for item in _array(data.get("neighborhood", []), field="neighborhood")
            ),
        )


@dataclass(frozen=True, slots=True)
class SupportSet:
    members: tuple[SupportMember, ...]

    def to_list(self) -> list[JsonObject]:
        return [item.to_dict() for item in self.members]

    @classmethod
    def from_list(cls, value: object) -> SupportSet:
        return cls(
            tuple(
                SupportMember.from_dict(item)
                for item in _array(value, field="Annotation.support")
            )
        )


@dataclass(frozen=True, slots=True)
class DiagramLocation:
    model_ship: str
    block_ship: str
    line_ship: str

    def __post_init__(self) -> None:
        for key, value in self.to_dict().items():
            _uuid(value, field=f"Annotation.location.{key}")

    def to_dict(self) -> dict[str, str]:
        return {
            "model_ship": self.model_ship,
            "block_ship": self.block_ship,
            "line_ship": self.line_ship,
        }

    @classmethod
    def from_dict(cls, value: object) -> DiagramLocation:
        data = _object(value, field="Annotation.location")
        return cls(
            *(
                _string(data.get(key), field=f"Annotation.location.{key}")
                for key in ("model_ship", "block_ship", "line_ship")
            )
        )


@dataclass(frozen=True, slots=True)
class DiagramBlockLocation:
    model_ship: str
    block_ship: str

    def __post_init__(self) -> None:
        for key, value in self.to_dict().items():
            _uuid(value, field=f"Annotation.location.{key}")

    def to_dict(self) -> dict[str, str]:
        return {
            "model_ship": self.model_ship,
            "block_ship": self.block_ship,
        }

    @classmethod
    def from_dict(cls, value: object) -> DiagramBlockLocation:
        data = _object(value, field="Annotation.location")
        return cls(
            *(
                _string(data.get(key), field=f"Annotation.location.{key}")
                for key in ("model_ship", "block_ship")
            )
        )


@dataclass(frozen=True, slots=True)
class AnnotationDraft:
    id: str
    record: JsonObject

    def __post_init__(self) -> None:
        _uuid(self.id, field="Annotation.id")
        copied = _object(self.record, field="Annotation")
        _string(copied.get("type"), field="Annotation.type")
        object.__setattr__(self, "record", copied)

    def to_dict(self) -> JsonObject:
        return {"id": self.id, **self.record}

    @classmethod
    def from_dict(cls, value: object) -> AnnotationDraft:
        data = _object(value, field="Capture.Annotation")
        annotation_id = data.pop("id", None)
        return cls(_string(annotation_id, field="Annotation.id"), data)


@dataclass(frozen=True, slots=True)
class DiagramAnnotation:
    """Opaque Annotation. Only ``type`` is universal."""

    id: str
    namespace: DiagramNamespace
    record: JsonObject

    def __post_init__(self) -> None:
        _uuid(self.id, field="Annotation.id")
        copied = _object(self.record, field="Annotation.Record")
        _string(copied.get("type"), field="Annotation.type")
        object.__setattr__(self, "record", copied)

    @property
    def type(self) -> str:
        return _string(self.record.get("type"), field="Annotation.type")

    @property
    def standing(self) -> str:
        return "Asserted" if self.record.get("score_vector") else "UnAsserted"

    def assertions(self) -> tuple[JsonObject, ...]:
        return self.namespace.assertions_for(self)

    def score_vector(self) -> JsonObject:
        value = self.record.get("score_vector", {})
        return value if isinstance(value, dict) else {}

    def to_record(self) -> JsonObject:
        return dict(self.record)

    def specialize(self) -> TypedAnnotation:
        return self.namespace.specialize(self)


@dataclass(frozen=True, slots=True)
class TypedAnnotation:
    annotation: DiagramAnnotation

    @property
    def id(self) -> str:
        return self.annotation.id

    @property
    def type(self) -> str:
        return self.annotation.type

    @property
    def record(self) -> JsonObject:
        return self.annotation.record

    def model_location(self) -> tuple[str, str] | None:
        """Return the owning Model and the record path that establishes it."""

        return None

    def type_assertions(self) -> tuple[JsonObject, ...]:
        return ()

    def type_findings(
        self,
        *,
        path: str,
        evidence: ChatlasEvidence | None,
    ) -> tuple[Finding, ...]:
        return ()

    def contribute(self, projector: DiagramProjectionBuilder) -> None:
        """Contribute this Annotation to the canonical object projection."""

        return None


@dataclass(frozen=True, slots=True)
class ModelAnnotation(TypedAnnotation):
    def __post_init__(self) -> None:
        if self.type != MODEL_ANNOTATION_TYPE:
            raise DiagramModelError(f"not a Model Annotation: {self.type}")
        _uuid(self.record.get("model_ship"), field="Model.Annotation.model_ship")

    @property
    def model_ship(self) -> str:
        return _string(self.record.get("model_ship"), field="model_ship")

    def model_location(self) -> tuple[str, str]:
        return self.model_ship, "model_ship"

    def type_assertions(self) -> tuple[JsonObject, ...]:
        return ({"type": "Model.Derived.Support.Assertion"},)


@dataclass(frozen=True, slots=True)
class UserTouchedAnnotation(TypedAnnotation):
    @property
    def producer(self) -> ChatlasTurnReference:
        return ChatlasTurnReference.from_dict(self.record.get("producer"))

    @property
    def support(self) -> SupportSet:
        return SupportSet.from_list(self.record.get("support", []))

    def render_support(self, evidence: ChatlasEvidence) -> list[JsonObject]:
        return [evidence.render_member(item) for item in self.support.members]


@dataclass(frozen=True, slots=True)
class LineAnnotation(UserTouchedAnnotation):
    def __post_init__(self) -> None:
        if self.type != LINE_ANNOTATION_TYPE:
            raise DiagramModelError(f"not a Line Annotation: {self.type}")
        DiagramLocation.from_dict(self.record.get("location"))
        _string(
            _object(self.record.get("data", {}), field="data").get("text"),
            field="data.text",
        )
        _verbatim_gates(self.record.get("gates", []))

    @property
    def location(self) -> DiagramLocation:
        return DiagramLocation.from_dict(self.record.get("location"))

    @property
    def text(self) -> str:
        return _string(
            _object(self.record.get("data", {}), field="data").get("text"),
            field="data.text",
        )

    @property
    def gates(self) -> tuple[VerbatimGate, ...]:
        return _verbatim_gates(self.record.get("gates", []))

    @property
    def line_type(self) -> str | None:
        value = self.record.get("line_type")
        return _string(value, field="line_type") if value is not None else None

    def model_location(self) -> tuple[str, str]:
        return self.location.model_ship, "location.model_ship"

    def type_assertions(self) -> tuple[JsonObject, ...]:
        assertions = tuple(
            {"type": kind}
            for kind in (
                "Line.Continuity.Assertion",
                "Block.Context.Assertion",
                "Model.Scope.Assertion",
            )
        )
        if self.gates:
            assertions += tuple({"type": kind} for kind in VERBATIM_GATE_ASSERTIONS)
        if self.line_type is not None:
            assertions += ({"type": "Line.Type.Conformance.Assertion"},)
        return assertions

    def contribute(self, projector: DiagramProjectionBuilder) -> None:
        projector.add_line_annotation(self)

    def type_findings(
        self,
        *,
        path: str,
        evidence: ChatlasEvidence | None,
    ) -> tuple[Finding, ...]:
        return ()


@dataclass(frozen=True, slots=True)
class BlockAnnotation(TypedAnnotation):
    def __post_init__(self) -> None:
        if self.type != BLOCK_ANNOTATION_TYPE:
            raise DiagramModelError(f"not a Block Annotation: {self.type}")
        DiagramBlockLocation.from_dict(self.record.get("location"))
        _string(
            _object(self.record.get("data", {}), field="data").get("label"),
            field="data.label",
        )

    @property
    def location(self) -> DiagramBlockLocation:
        return DiagramBlockLocation.from_dict(self.record.get("location"))

    @property
    def label(self) -> str:
        return _string(
            _object(self.record.get("data", {}), field="data").get("label"),
            field="data.label",
        )

    @property
    def block_type(self) -> str | None:
        value = self.record.get("block_type")
        return _string(value, field="block_type") if value is not None else None

    def model_location(self) -> tuple[str, str]:
        return self.location.model_ship, "location.model_ship"

    def type_assertions(self) -> tuple[JsonObject, ...]:
        assertions = tuple(
            {"type": kind}
            for kind in (
                "Block.Continuity.Assertion",
                "Model.Scope.Assertion",
            )
        )
        if self.block_type is not None:
            assertions += ({"type": "Block.Type.Conformance.Assertion"},)
        return assertions

    def contribute(self, projector: DiagramProjectionBuilder) -> None:
        projector.add_block_annotation(self)


@dataclass(frozen=True, slots=True)
class BlockTypeAnnotation(TypedAnnotation):
    """Assigns an Object.Type to an existing Block without adding content."""

    def __post_init__(self) -> None:
        if self.type != BLOCK_TYPE_ANNOTATION_TYPE:
            raise DiagramModelError(f"not a Block Type Annotation: {self.type}")
        DiagramBlockLocation.from_dict(self.record.get("location"))
        _string(self.record.get("block_type"), field="block_type")

    @property
    def location(self) -> DiagramBlockLocation:
        return DiagramBlockLocation.from_dict(self.record.get("location"))

    @property
    def block_type(self) -> str:
        return _string(self.record.get("block_type"), field="block_type")

    def model_location(self) -> tuple[str, str]:
        return self.location.model_ship, "location.model_ship"

    def type_assertions(self) -> tuple[JsonObject, ...]:
        return ({"type": "Block.Type.Conformance.Assertion"},)

    def contribute(self, projector: DiagramProjectionBuilder) -> None:
        projector.add_block_annotation(self)


@dataclass(frozen=True, slots=True)
class LineSupportAnnotation(UserTouchedAnnotation):
    def __post_init__(self) -> None:
        if self.type != LINE_SUPPORT_ANNOTATION_TYPE:
            raise DiagramModelError(f"not a Line Support Annotation: {self.type}")
        DiagramLocation.from_dict(self.record.get("location"))

    @property
    def location(self) -> DiagramLocation:
        return DiagramLocation.from_dict(self.record.get("location"))

    def model_location(self) -> tuple[str, str]:
        return self.location.model_ship, "location.model_ship"

    def type_assertions(self) -> tuple[JsonObject, ...]:
        return tuple(
            {"type": kind}
            for kind in (
                "Line.Continuity.Assertion",
                "Block.Context.Assertion",
                "Model.Scope.Assertion",
            )
        )

    def contribute(self, projector: DiagramProjectionBuilder) -> None:
        projector.add_line_annotation(self)


@dataclass(frozen=True, slots=True)
class LineTypeAnnotation(TypedAnnotation):
    """Assigns an Object.Type to an existing Line without adding wording."""

    def __post_init__(self) -> None:
        if self.type != LINE_TYPE_ANNOTATION_TYPE:
            raise DiagramModelError(f"not a Line Type Annotation: {self.type}")
        DiagramLocation.from_dict(self.record.get("location"))
        _string(self.record.get("line_type"), field="line_type")

    @property
    def location(self) -> DiagramLocation:
        return DiagramLocation.from_dict(self.record.get("location"))

    @property
    def line_type(self) -> str:
        return _string(self.record.get("line_type"), field="line_type")

    def model_location(self) -> tuple[str, str]:
        return self.location.model_ship, "location.model_ship"

    def type_assertions(self) -> tuple[JsonObject, ...]:
        return ({"type": "Line.Type.Conformance.Assertion"},)

    def contribute(self, projector: DiagramProjectionBuilder) -> None:
        projector.add_line_annotation(self)


@dataclass(frozen=True, slots=True)
class LineGateAnnotation(TypedAnnotation):
    """Adds review evidence to one immutable Line wording Annotation."""

    def __post_init__(self) -> None:
        if self.type != LINE_GATE_ANNOTATION_TYPE:
            raise DiagramModelError(f"not a Line Gate Annotation: {self.type}")
        _uuid(
            self.record.get("target_annotation"),
            field="Line.Gate.Annotation.target_annotation",
        )
        gates = _verbatim_gates(self.record.get("gates"))
        if len(gates) != 1:
            raise DiagramModelError(
                "Line.Gate.Annotation must contain exactly one Gate"
            )

    @property
    def target_annotation_id(self) -> str:
        return _uuid(
            self.record.get("target_annotation"),
            field="Line.Gate.Annotation.target_annotation",
        )

    @property
    def gates(self) -> tuple[VerbatimGate, ...]:
        return _verbatim_gates(self.record.get("gates"))

    @property
    def target(self) -> LineAnnotation:
        annotation = self.annotation.namespace.annotation(self.target_annotation_id)
        typed = annotation.specialize()
        if not isinstance(typed, LineAnnotation):
            raise DiagramModelError(
                "Line.Gate.Annotation target is not a Diagram.Line.Annotation"
            )
        return typed

    @property
    def location(self) -> DiagramLocation:
        return self.target.location

    def model_location(self) -> tuple[str, str]:
        return self.location.model_ship, "target_annotation"

    def type_assertions(self) -> tuple[JsonObject, ...]:
        return tuple({"type": kind} for kind in VERBATIM_GATE_ASSERTIONS)

    def type_findings(
        self,
        *,
        path: str,
        evidence: ChatlasEvidence | None,
    ) -> tuple[Finding, ...]:
        return (
            Finding(
                "archive-grounding-unassessable",
                path,
                "Chatlas-to-Archive grounding is not yet mechanically assessable.",
            ),
        )

    def contribute(self, projector: DiagramProjectionBuilder) -> None:
        projector.add_line_gate_annotation(self)


@dataclass(frozen=True, slots=True)
class DiagramObjectAssertion:
    """One assertion exposed by a projected object without duplicating evaluation."""

    annotation_id: str
    assertion_type: str

    @property
    def id(self) -> str:
        return f"annotation:{self.annotation_id}:{self.assertion_type}"

    def to_dict(self) -> JsonObject:
        return {
            "id": self.id,
            "annotation_id": self.annotation_id,
            "type": self.assertion_type,
        }


@dataclass(frozen=True, slots=True)
class DiagramLineType:
    id: str
    short_code: str
    edition_class: type[DiagramLineEdition]
    ship_class: type[DiagramLineShip]
    definition_block_ship: str | None = None

    def to_dict(self) -> JsonObject:
        return {
            "id": self.id,
            "short_code": self.short_code,
            "edition_class": self.edition_class.__name__,
            "ship_class": self.ship_class.__name__,
            "definition_block_ship": self.definition_block_ship,
        }


@dataclass(frozen=True, slots=True)
class DiagramBlockType:
    id: str
    block_class: type[DiagramBlock]
    line_types: tuple[DiagramLineType, ...]
    require_line_type: bool = True
    definition_block_ship: str | None = None

    def line_type(self, type_id: str) -> DiagramLineType | None:
        return next((item for item in self.line_types if item.id == type_id), None)

    def to_dict(self) -> JsonObject:
        return {
            "id": self.id,
            "class": self.block_class.__name__,
            "definition_block_ship": self.definition_block_ship,
            "require_line_type": self.require_line_type,
            "line_types": [item.to_dict() for item in self.line_types],
        }


@dataclass(frozen=True, slots=True)
class DiagramObjectTypeRegistry:
    block_types: tuple[DiagramBlockType, ...]

    def block_type(self, type_id: str) -> DiagramBlockType | None:
        return next((item for item in self.block_types if item.id == type_id), None)

    def line_type(self, type_id: str) -> DiagramLineType | None:
        return next(
            (
                line_type
                for block_type in self.block_types
                for line_type in block_type.line_types
                if line_type.id == type_id
            ),
            None,
        )

    def types(self) -> tuple[DiagramBlockType | DiagramLineType, ...]:
        return tuple(
            dict.fromkeys(
                (
                    *self.block_types,
                    *(
                        line_type
                        for block_type in self.block_types
                        for line_type in block_type.line_types
                    ),
                )
            )
        )

    def definition_findings(
        self, resolve_block: Callable[[str], object]
    ) -> tuple[Finding, ...]:
        findings: list[Finding] = []
        for object_type in self.types():
            path = f"object_type.{object_type.id}.definition_block_ship"
            if object_type.definition_block_ship is None:
                findings.append(
                    Finding(
                        "object-type-definition-block-missing",
                        path,
                        f"Object.Type {object_type.id} has no Definition.Block.",
                    )
                )
                continue
            try:
                resolve_block(object_type.definition_block_ship)
            except DiagramError:
                findings.append(
                    Finding(
                        "object-type-definition-block-unresolved",
                        path,
                        (
                            f"Definition.Block does not resolve for Object.Type "
                            f"{object_type.id}: {object_type.definition_block_ship}."
                        ),
                    )
                )
        return tuple(findings)

    def to_dict(self) -> JsonObject:
        return {"block_types": [item.to_dict() for item in self.block_types]}


@dataclass(frozen=True, slots=True)
class DiagramLineEdition:
    annotation: LineAnnotation
    object_type: DiagramLineType

    @property
    def text(self) -> str:
        return self.annotation.text


class DesignLineDefinition(DiagramLineEdition):
    pass


class DesignLineDecision(DiagramLineEdition):
    pass


class DesignLineConstraint(DiagramLineEdition):
    pass


class DesignLineRejection(DiagramLineEdition):
    pass


class DesignLinePrinciple(DiagramLineEdition):
    pass


class DesignLineFreedom(DiagramLineEdition):
    pass


class DesignLineExample(DiagramLineEdition):
    pass


class IssueLineResolve(DiagramLineEdition):
    pass


@dataclass(frozen=True, slots=True)
class DiagramLineShip:
    ship: str
    block_ship: str
    annotations: tuple[TypedAnnotation, ...]
    editions: tuple[DiagramLineEdition, ...]
    type_ids: tuple[str, ...]
    findings: tuple[Finding, ...]

    @property
    def object_type(self) -> str | None:
        return self.type_ids[-1] if len(self.type_ids) == 1 else None

    def assertions(self) -> tuple[DiagramObjectAssertion, ...]:
        return _object_assertions(self.annotations)


class DesignLineShip(DiagramLineShip):
    pass


class DesignDefinitionLineShip(DesignLineShip):
    pass


class DesignDecisionLineShip(DesignLineShip):
    pass


class DesignConstraintLineShip(DesignLineShip):
    pass


class DesignRejectionLineShip(DesignLineShip):
    pass


class DesignPrincipleLineShip(DesignLineShip):
    pass


class DesignFreedomLineShip(DesignLineShip):
    pass


class DesignExampleLineShip(DesignLineShip):
    pass


class IssueResolveLineShip(DiagramLineShip):
    pass


@dataclass(frozen=True, slots=True)
class DiagramBlock:
    ship: str
    model_ship: str
    annotations: tuple[TypedAnnotation, ...]
    lines: tuple[DiagramLineShip, ...]
    type_ids: tuple[str, ...]
    findings: tuple[Finding, ...]

    @property
    def object_type(self) -> str | None:
        return self.type_ids[-1] if len(self.type_ids) == 1 else None

    @property
    def labels(self) -> tuple[str, ...]:
        return tuple(
            item.label for item in self.annotations if isinstance(item, BlockAnnotation)
        )

    def assertions(self) -> tuple[DiagramObjectAssertion, ...]:
        return _dedupe_object_assertions(
            (
                *_object_assertions(self.annotations),
                *(assertion for line in self.lines for assertion in line.assertions()),
            )
        )

    def mechanical_findings(
        self, assertion_engine: AssertionEngine
    ) -> tuple[Finding, ...]:
        return ()


class DesignBlock(DiagramBlock):
    pass


class ImplReqBlock(DiagramBlock):
    pass


class IssueBlock(DiagramBlock):
    def assess(self, assertion_engine: AssertionEngine) -> IssueAssessment:
        resolution_lines = tuple(
            line for line in self.lines if isinstance(line, IssueResolveLineShip)
        )
        assessments = tuple(
            gate_assessment
            for line in resolution_lines
            for annotation in line.annotations
            if isinstance(annotation, (LineAnnotation, LineGateAnnotation))
            for gate_assessment in assertion_engine.assess(annotation).gate_assessments
        )
        closed = any(item.standing == "Passed" for item in assessments)
        findings = tuple(
            finding for assessment in assessments for finding in assessment.findings
        )
        if not closed:
            findings = (
                *findings,
                Finding(
                    "issue-open",
                    f"block.{self.ship}",
                    "Issue.Block has no reviewed Issue.Line.Resolve with a passing Verbatim.Gate.",
                ),
            )
        return IssueAssessment(
            self.ship,
            "Closed" if closed else "Open",
            tuple(line.ship for line in resolution_lines),
            assessments,
            _dedupe_findings(findings),
        )

    def mechanical_findings(
        self, assertion_engine: AssertionEngine
    ) -> tuple[Finding, ...]:
        return self.assess(assertion_engine).findings


@dataclass(frozen=True, slots=True)
class DiagramProjection:
    model_ship: str
    namespace_id: str
    blocks: tuple[DiagramBlock, ...]
    findings: tuple[Finding, ...]

    def block(self, block_ship: str) -> DiagramBlock:
        matches = tuple(item for item in self.blocks if item.ship == block_ship)
        if len(matches) != 1:
            raise DiagramError(f"Projected Block does not resolve: {block_ship}")
        return matches[0]

    def line(self, line_ship: str) -> DiagramLineShip:
        matches = tuple(
            line for block in self.blocks for line in block.lines if line.ship == line_ship
        )
        if len(matches) != 1:
            raise DiagramError(f"Projected Line does not resolve: {line_ship}")
        return matches[0]

    def to_dict(self) -> JsonObject:
        return {
            "model_ship": self.model_ship,
            "namespace_id": self.namespace_id,
            "blocks": [
                {
                    "ship": block.ship,
                    "object_type": block.object_type,
                    "labels": list(block.labels),
                    "lines": [
                        {
                            "ship": line.ship,
                            "object_type": line.object_type,
                            "type_history": list(line.type_ids),
                            "annotations": [item.id for item in line.annotations],
                        }
                        for line in block.lines
                    ],
                    "annotations": [item.id for item in block.annotations],
                }
                for block in self.blocks
            ],
            "findings": [item.to_dict() for item in self.findings],
        }


class DiagramProjectionBuilder:
    """Canonical full projector. Annotation classes own their contributions."""

    def __init__(
        self,
        namespace: DiagramNamespace,
        model_ship: str,
        annotations: Iterable[TypedAnnotation],
    ) -> None:
        self.namespace = namespace
        self.model_ship = model_ship
        self.registry = namespace.object_types()
        self.typed_by_id = {item.id: item for item in annotations}
        self.block_annotations: dict[str, list[TypedAnnotation]] = {}
        self.line_annotations: dict[tuple[str, str], list[TypedAnnotation]] = {}
        self.findings: list[Finding] = []

    def add_block_annotation(
        self, annotation: BlockAnnotation | BlockTypeAnnotation
    ) -> None:
        self.block_annotations.setdefault(annotation.location.block_ship, []).append(
            annotation
        )

    def add_line_annotation(
        self,
        annotation: LineAnnotation | LineSupportAnnotation | LineTypeAnnotation,
    ) -> None:
        location = annotation.location
        self.line_annotations.setdefault(
            (location.block_ship, location.line_ship), []
        ).append(annotation)

    def add_line_gate_annotation(self, annotation: LineGateAnnotation) -> None:
        target = self.typed_by_id.get(annotation.target_annotation_id)
        if target is None:
            try:
                target = self.namespace.annotation(
                    annotation.target_annotation_id
                ).specialize()
            except (DiagramError, DiagramModelError):
                target = None
        if not isinstance(target, LineAnnotation):
            self.findings.append(
                Finding(
                    "line-gate-target-unresolved",
                    f"annotation.{annotation.id}.target_annotation",
                    "Line Gate target does not resolve to a Line Annotation.",
                )
            )
            return
        location = target.location
        self.line_annotations.setdefault(
            (location.block_ship, location.line_ship), []
        ).append(annotation)

    def build(self) -> DiagramProjection:
        block_ships = tuple(
            dict.fromkeys(
                (*self.block_annotations, *(key[0] for key in self.line_annotations))
            )
        )
        blocks = tuple(self._block(ship) for ship in block_ships)
        findings = _dedupe_findings(
            (
                *self.findings,
                *(finding for block in blocks for finding in block.findings),
                *(
                    finding
                    for block in blocks
                    for line in block.lines
                    for finding in line.findings
                ),
            )
        )
        return DiagramProjection(
            self.model_ship, self.namespace.id, blocks, findings
        )

    def _block(self, ship: str) -> DiagramBlock:
        annotations = _sort_typed(self.block_annotations.get(ship, ()))
        declarations = tuple(
            item for item in annotations if isinstance(item, BlockAnnotation)
        )
        type_annotations = tuple(
            item for item in annotations if isinstance(item, BlockTypeAnnotation)
        )
        findings: list[Finding] = []
        type_ids = tuple(
            dict.fromkeys(
                item.block_type
                for item in (*declarations, *type_annotations)
                if item.block_type is not None
            )
        )
        if not declarations:
            findings.append(
                Finding(
                    "block-declaration-missing",
                    f"block.{ship}",
                    "Lines name a Block ship with no Block Annotation.",
                )
            )
        if declarations and not type_ids and self.namespace.require_block_type:
            findings.append(
                Finding(
                    "block-type-missing",
                    f"block.{ship}",
                    "Block Annotations do not retain a Block.Type.",
                )
            )
        if len(type_ids) > 1:
            findings.append(
                Finding(
                    "block-type-selection-unresolved",
                    f"block.{ship}",
                    "Block lineage contains several Block.Types.",
                )
            )
        selected_id = type_ids[-1] if len(type_ids) == 1 else DIAGRAM_BLOCK_OBJECT_TYPE
        block_type = self.registry.block_type(selected_id)
        if block_type is None:
            findings.append(
                Finding(
                    "block-type-unknown",
                    f"block.{ship}.block_type",
                    f"Block.Type is not registered: {selected_id}.",
                )
            )
            block_type = self.registry.block_type(DIAGRAM_BLOCK_OBJECT_TYPE)
        if (
            type_ids
            and self.namespace.allowed_block_types
            and selected_id not in self.namespace.allowed_block_types
        ):
            findings.append(
                Finding(
                    "block-type-not-allowed",
                    f"block.{ship}.block_type",
                    f"Namespace {self.namespace.name} does not allow Block.Type {selected_id}.",
                )
            )
        assert block_type is not None
        lines = tuple(
            self._line(ship, line_ship, block_type)
            for block_ship, line_ship in self.line_annotations
            if block_ship == ship
        )
        return block_type.block_class(
            ship,
            self.model_ship,
            annotations,
            lines,
            type_ids,
            tuple(findings),
        )

    def _line(
        self, block_ship: str, ship: str, block_type: DiagramBlockType
    ) -> DiagramLineShip:
        annotations = _sort_typed(self.line_annotations[(block_ship, ship)])
        wordings = tuple(
            item for item in annotations if isinstance(item, LineAnnotation)
        )
        type_annotations = tuple(
            item for item in annotations if isinstance(item, LineTypeAnnotation)
        )
        findings: list[Finding] = []
        type_ids = tuple(
            dict.fromkeys(
                item.line_type
                for item in (*wordings, *type_annotations)
                if item.line_type is not None
            )
        )
        if not wordings:
            findings.append(
                Finding(
                    "line-wording-missing",
                    f"line.{ship}",
                    "Line annotations name a Line ship with no wording Annotation.",
                )
            )
        if wordings and not type_ids and block_type.require_line_type:
            findings.append(
                Finding(
                    "line-type-missing",
                    f"line.{ship}",
                    "Line Annotations do not retain a Line.Type.",
                )
            )
        if len(type_ids) > 1:
            findings.append(
                Finding(
                    "line-type-selection-unresolved",
                    f"line.{ship}",
                    "Line lineage contains several Line.Types.",
                )
            )
        line_type = None
        if len(type_ids) == 1:
            selected_id = type_ids[0]
            line_type = block_type.line_type(selected_id)
            if line_type is None:
                known = self.registry.line_type(selected_id)
                findings.append(
                    Finding(
                        (
                            "line-type-not-allowed-by-block"
                            if known
                            else "line-type-unknown"
                        ),
                        f"line.{ship}.line_type",
                        (
                            f"Block.Type {block_type.id} does not allow "
                            f"Line.Type {selected_id}."
                            if known
                            else f"Line.Type is not registered: {selected_id}."
                        ),
                    )
                )
        if line_type is None:
            line_type = self.registry.line_type(DIAGRAM_LINE_OBJECT_TYPE)
        assert line_type is not None
        editions = tuple(line_type.edition_class(item, line_type) for item in wordings)
        return line_type.ship_class(
            ship,
            block_ship,
            annotations,
            editions,
            type_ids,
            tuple(findings),
        )


def default_diagram_object_types() -> DiagramObjectTypeRegistry:
    generic_line = DiagramLineType(
        DIAGRAM_LINE_OBJECT_TYPE,
        "",
        DiagramLineEdition,
        DiagramLineShip,
        DIAGRAM_BLOCK_TYPE_DEFINITION_BLOCK_SHIP,
    )
    design_lines = (
        DiagramLineType(
            DESIGN_LINE_DEFINITION_TYPE,
            "DF",
            DesignLineDefinition,
            DesignDefinitionLineShip,
            DESIGN_LINE_TYPE_DEFINITION_BLOCK_SHIPS[DESIGN_LINE_DEFINITION_TYPE],
        ),
        DiagramLineType(
            DESIGN_LINE_DECISION_TYPE,
            "DC",
            DesignLineDecision,
            DesignDecisionLineShip,
            DESIGN_LINE_TYPE_DEFINITION_BLOCK_SHIPS[DESIGN_LINE_DECISION_TYPE],
        ),
        DiagramLineType(
            DESIGN_LINE_CONSTRAINT_TYPE,
            "CT",
            DesignLineConstraint,
            DesignConstraintLineShip,
            DESIGN_LINE_TYPE_DEFINITION_BLOCK_SHIPS[DESIGN_LINE_CONSTRAINT_TYPE],
        ),
        DiagramLineType(
            DESIGN_LINE_REJECTION_TYPE,
            "RJ",
            DesignLineRejection,
            DesignRejectionLineShip,
            DESIGN_LINE_TYPE_DEFINITION_BLOCK_SHIPS[DESIGN_LINE_REJECTION_TYPE],
        ),
        DiagramLineType(
            DESIGN_LINE_PRINCIPLE_TYPE,
            "PR",
            DesignLinePrinciple,
            DesignPrincipleLineShip,
            DESIGN_LINE_TYPE_DEFINITION_BLOCK_SHIPS[DESIGN_LINE_PRINCIPLE_TYPE],
        ),
        DiagramLineType(
            DESIGN_LINE_FREEDOM_TYPE,
            "FR",
            DesignLineFreedom,
            DesignFreedomLineShip,
            DESIGN_LINE_TYPE_DEFINITION_BLOCK_SHIPS[DESIGN_LINE_FREEDOM_TYPE],
        ),
        DiagramLineType(
            DESIGN_LINE_EXAMPLE_TYPE,
            "EX",
            DesignLineExample,
            DesignExampleLineShip,
            DESIGN_LINE_TYPE_DEFINITION_BLOCK_SHIPS[DESIGN_LINE_EXAMPLE_TYPE],
        ),
    )
    issue_resolve = DiagramLineType(
        ISSUE_LINE_RESOLVE_TYPE,
        "RESOLVE",
        IssueLineResolve,
        IssueResolveLineShip,
        ISSUE_LINE_RESOLVE_TYPE_DEFINITION_BLOCK_SHIP,
    )
    return DiagramObjectTypeRegistry(
        (
            DiagramBlockType(
                DIAGRAM_BLOCK_OBJECT_TYPE,
                DiagramBlock,
                (generic_line,),
                definition_block_ship=DIAGRAM_BLOCK_TYPE_DEFINITION_BLOCK_SHIP,
            ),
            DiagramBlockType(
                DESIGN_BLOCK_OBJECT_TYPE,
                DesignBlock,
                design_lines,
                definition_block_ship=DESIGN_BLOCK_TYPE_DEFINITION_BLOCK_SHIP,
            ),
            DiagramBlockType(
                IMPL_REQ_BLOCK_OBJECT_TYPE,
                ImplReqBlock,
                design_lines,
                definition_block_ship=IMPL_REQ_BLOCK_TYPE_DEFINITION_BLOCK_SHIP,
            ),
            DiagramBlockType(
                ISSUE_BLOCK_OBJECT_TYPE,
                IssueBlock,
                (*design_lines, issue_resolve),
                definition_block_ship=ISSUE_BLOCK_TYPE_DEFINITION_BLOCK_SHIP,
            ),
        )
    )


def _object_assertions(
    annotations: Iterable[TypedAnnotation],
) -> tuple[DiagramObjectAssertion, ...]:
    return _dedupe_object_assertions(
        tuple(
            DiagramObjectAssertion(item.id, assertion_type)
            for item in annotations
            for assertion in item.annotation.assertions()
            if isinstance((assertion_type := assertion.get("type")), str)
        )
    )


def _dedupe_object_assertions(
    assertions: Iterable[DiagramObjectAssertion],
) -> tuple[DiagramObjectAssertion, ...]:
    return tuple({item.id: item for item in assertions}.values())


def _dedupe_findings(findings: Iterable[Finding]) -> tuple[Finding, ...]:
    return tuple(
        {
            (item.code, item.path, item.message): item
            for item in findings
        }.values()
    )


def _sort_annotations(
    annotations: Iterable[DiagramAnnotation],
) -> tuple[DiagramAnnotation, ...]:
    return tuple(
        sorted(
            annotations,
            key=lambda item: (str(item.record.get("recorded_at", "")), item.id),
        )
    )


def _sort_typed(
    annotations: Iterable[TypedAnnotation],
) -> tuple[TypedAnnotation, ...]:
    return tuple(
        sorted(
            annotations,
            key=lambda item: (str(item.record.get("recorded_at", "")), item.id),
        )
    )


@dataclass(frozen=True, slots=True)
class CaptureManifest:
    model_ship: str
    annotations: tuple[AnnotationDraft, ...]

    def __post_init__(self) -> None:
        _uuid(self.model_ship, field="Capture.Manifest.model_ship")

    def to_dict(self) -> JsonObject:
        return {
            "class": CAPTURE_MANIFEST_CLASS,
            "schema_version": SCHEMA_VERSION,
            "model_ship": self.model_ship,
            "annotations": [item.to_dict() for item in self.annotations],
        }

    @classmethod
    def from_dict(cls, value: object) -> CaptureManifest:
        data = _object(value, field="Capture.Manifest")
        if (
            data.get("class") != CAPTURE_MANIFEST_CLASS
            or data.get("schema_version") != SCHEMA_VERSION
        ):
            raise DiagramModelError("unsupported Tarav Diagram Capture.Manifest")
        return cls(
            _string(data.get("model_ship"), field="model_ship"),
            tuple(
                AnnotationDraft.from_dict(item)
                for item in _array(data.get("annotations"), field="annotations")
            ),
        )

    @classmethod
    def read(cls, path: Path) -> CaptureManifest:
        return cls.from_dict(_read_json(path))

    @classmethod
    def template(
        cls,
        *,
        model_ship: str,
    ) -> CaptureManifest:
        return cls(model_ship, ())

    def check(
        self, namespace: DiagramNamespace, *, evidence: ChatlasEvidence | None = None
    ) -> tuple[Finding, ...]:
        findings: list[Finding] = []
        seen: dict[str, JsonObject] = {}
        draft_annotations: list[DiagramAnnotation] = []
        for index, draft in enumerate(self.annotations):
            path = f"annotations[{index}]"
            if draft.id in seen:
                findings.append(
                    Finding(
                        "duplicate-annotation-id",
                        f"{path}.id",
                        "Capture.Manifest repeats one Annotation identity.",
                    )
                )
                if seen[draft.id] != draft.record:
                    findings.append(
                        Finding(
                            "annotation-identity-rebound",
                            f"{path}.id",
                            "One Annotation identity names different content.",
                        )
                    )
            seen[draft.id] = draft.record
            annotation = DiagramAnnotation(draft.id, namespace, draft.record)
            draft_annotations.append(annotation)
            findings.extend(
                namespace.findings(annotation, path=path, evidence=evidence)
            )
            try:
                model_location = annotation.specialize().model_location()
            except (DiagramError, DiagramModelError):
                model_location = None
            if model_location is not None and model_location[0] != self.model_ship:
                findings.append(
                    Finding(
                        "capture-model-mismatch",
                        f"{path}.{model_location[1]}",
                        "Annotation is not located in the Capture.Manifest Model.",
                    )
                )
        projection = namespace.project(self.model_ship, extra=draft_annotations)
        findings.extend(projection.findings)
        assertion_engine = namespace.assertion_engine(evidence=evidence)
        findings.extend(
            finding
            for block in projection.blocks
            for finding in block.mechanical_findings(assertion_engine)
        )
        return _dedupe_findings(findings)


@dataclass(frozen=True, slots=True)
class CaptureReceipt:
    namespace_id: str
    created: tuple[str, ...]
    existing: tuple[str, ...]
    findings: tuple[Finding, ...]
    committed: bool
    base_commit: str
    commit: str | None

    def to_dict(self) -> JsonObject:
        return {
            "class": "Tarav.Diagram.Capture.Receipt",
            "namespace_id": self.namespace_id,
            "created": list(self.created),
            "existing": list(self.existing),
            "findings": [item.to_dict() for item in self.findings],
            "committed": self.committed,
            "base_commit": self.base_commit,
            "commit": self.commit,
        }


class ChatlasEvidence:
    def __init__(
        self,
        *,
        model_loader: Callable[[str], JsonObject] | None = None,
        chatlas_root: Path | None = None,
    ) -> None:
        self.model_loader = model_loader or (
            lambda identity: provide_normal_model(
                identity_hash=identity, chatlas_root=chatlas_root
            )
        )
        self._models: dict[str, JsonObject] = {}

    def model(self, identity: str) -> JsonObject:
        if identity not in self._models:
            model = self.model_loader(identity)
            if not isinstance(model, dict):
                raise DiagramError("Chatlas Normal Model loader returned no object")
            self._models[identity] = model
        return self._models[identity]

    def resolve(self, ref: ChatlasTurnReference) -> JsonObject:
        turns = self.model(ref.session_identity).get("turns")
        if not isinstance(turns, list):
            raise DiagramError("Chatlas Normal Model has no turns collection")
        return resolve_chat_turn_ref(
            turns, {"turn_address": ref.turn_address, "turn_hash": ref.turn_hash}
        )

    def check(self, annotation: UserTouchedAnnotation, *, path: str) -> list[Finding]:
        findings: list[Finding] = []
        producer = self._matched(
            annotation.producer,
            f"{path}.producer",
            "producer-turn-unresolved",
            findings,
        )
        if producer is not None and producer.get("side") != "agent":
            findings.append(
                Finding(
                    "producer-turn-not-agent",
                    f"{path}.producer",
                    "Annotation producer is not an Agent turn.",
                )
            )
        for index, member in enumerate(annotation.support.members):
            member_path = f"{path}.support[{index}]"
            root_path = f"{member_path}.root"
            root = self._matched(
                member.root, root_path, "support-root-unresolved", findings
            )
            if root is not None and root.get("side") != "user":
                findings.append(
                    Finding(
                        "support-root-not-user",
                        root_path,
                        "Support.Member root is not a User turn.",
                    )
                )
            for neighbor_index, reference in enumerate(member.neighborhood):
                self._matched(
                    reference,
                    f"{member_path}.neighborhood[{neighbor_index}]",
                    "support-neighborhood-turn-unresolved",
                    findings,
                )
            for reference in (member.root, *member.neighborhood):
                if producer is None:
                    continue
                try:
                    available = self.was_available(annotation.producer, reference)
                except (DiagramError, ValueError) as exc:
                    findings.append(
                        Finding(
                            "support-context-unassessable",
                            member_path,
                            str(exc),
                        )
                    )
                    continue
                if not available:
                    findings.append(
                        Finding(
                            "support-not-in-producer-context",
                            member_path,
                            "Selected support content was not present before the Annotation producer turn.",
                        )
                    )
        return findings

    def was_available(
        self, producer: ChatlasTurnReference, support: ChatlasTurnReference
    ) -> bool:
        producer_position = self._position(producer)
        if producer.session_identity == support.session_identity:
            return self._position(support) < producer_position
        support_text = self.turn_text(support)
        if not support_text:
            return False
        preceding_text = "\n".join(
            self._turn_text(producer.session_identity, turn)
            for turn in self._turns(producer.session_identity)[:producer_position]
        )
        return support_text in preceding_text

    def render_member(self, member: SupportMember) -> JsonObject:
        refs = list((member.root, *member.neighborhood))
        if all(ref.session_identity == member.root.session_identity for ref in refs):
            refs.sort(key=self._position)
        return {
            "root": member.root.to_dict(),
            "turns": [
                {
                    "reference": ref.to_dict(),
                    "side": self._turn(ref).get("side"),
                    "text": self.turn_text(ref),
                    "root": ref == member.root,
                }
                for ref in refs
            ],
        }

    def turn_text(self, ref: ChatlasTurnReference) -> str:
        return self._turn_text(ref.session_identity, self._turn(ref))

    def turn(self, ref: ChatlasTurnReference) -> JsonObject:
        return self._turn(ref)

    def position(self, ref: ChatlasTurnReference) -> int:
        return self._position(ref)

    def _turn_text(self, identity: str, turn: JsonObject) -> str:
        model = self.model(identity)
        messages = model.get("messages")
        chunks: list[str] = []
        if isinstance(messages, list):
            for message_ref in turn.get("message_refs", []):
                if isinstance(message_ref, dict):
                    resolved = resolve_chat_message_ref(messages, message_ref)
                    message = resolved.get("message")
                    if (
                        resolved.get("standing") == "MATCHED"
                        and isinstance(message, dict)
                        and isinstance(message.get("text"), str)
                    ):
                        chunks.append(message["text"])
        events = model.get("events")
        if not chunks and isinstance(events, list):
            for event_ref in turn.get("event_refs", []):
                if not isinstance(event_ref, dict):
                    continue
                resolved = resolve_event_ref(events, event_ref)
                event = resolved.get("event")
                content = event.get("content") if isinstance(event, dict) else None
                text = content.get("text") if isinstance(content, dict) else None
                if resolved.get("standing") == "MATCHED" and isinstance(text, str):
                    chunks.append(text)
        return "\n".join(chunks)

    def _turns(self, identity: str) -> list[JsonObject]:
        turns = self.model(identity).get("turns")
        if not isinstance(turns, list) or not all(
            isinstance(turn, dict) for turn in turns
        ):
            raise DiagramError("Chatlas Normal Model has no valid turns collection")
        return turns

    def _position(self, ref: ChatlasTurnReference) -> int:
        for index, turn in enumerate(self._turns(ref.session_identity)):
            if turn.get("turn_address") == ref.turn_address:
                if turn.get("turn_hash") != ref.turn_hash:
                    raise DiagramError(
                        "Chatlas Turn reference resolves to an amended turn"
                    )
                return index
        raise DiagramError("Chatlas Turn reference is missing")

    def _matched(
        self, ref: ChatlasTurnReference, path: str, code: str, findings: list[Finding]
    ) -> JsonObject | None:
        try:
            resolved = self.resolve(ref)
        except Exception as exc:
            findings.append(Finding(code, path, str(exc)))
            return None
        turn = resolved.get("turn")
        if resolved.get("standing") != "MATCHED" or not isinstance(turn, dict):
            findings.append(
                Finding(
                    code,
                    path,
                    f"Chatlas Turn reference standing is {resolved.get('standing')}.",
                )
            )
            return None
        return turn

    def _turn(self, ref: ChatlasTurnReference) -> JsonObject:
        findings: list[Finding] = []
        turn = self._matched(ref, "reference", "turn-unresolved", findings)
        if turn is None:
            raise DiagramError(findings[0].message)
        return turn


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
    """Current derived Assertion state for one immutable Annotation record."""

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
        if isinstance(annotation, LineAnnotation):
            assessments = _assess_verbatim_gates(
                annotation_id=annotation.id,
                target_id=annotation.id,
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
                    f"{path}.target_annotation",
                    str(exc),
                )
            assessments = _assess_verbatim_gates(
                annotation_id=annotation.id,
                target_id=annotation.target_annotation_id,
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
                    assessment.scores.get(assertion_type)
                    for assessment in assessments
                )
                for assertion_type in self.assertion_types
            },
            tuple(
                finding
                for assessment in assessments
                for finding in assessment.findings
            ),
            assessments,
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
        for evaluator in evaluators or (VerbatimGateAssertionEvaluator(),):
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
        typed = annotation if isinstance(annotation, TypedAnnotation) else generic.specialize()
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


@dataclass(frozen=True, slots=True)
class DiagramNamespace:
    root: Path
    id: str
    name: str
    allowed_types: tuple[str, ...]
    allowed_block_types: tuple[str, ...] = ()
    require_block_type: bool = False

    @property
    def annotations_root(self) -> Path:
        return self.root / "annotations"

    @classmethod
    def create(
        cls,
        root: Path,
        *,
        name: str,
        namespace_id: str | None = None,
        allowed_types: Iterable[str] = (),
        allowed_block_types: Iterable[str] = (),
        require_block_type: bool = False,
    ) -> DiagramNamespace:
        resolved = root.expanduser().resolve()
        if resolved.exists() and any(resolved.iterdir()):
            return cls.open(resolved)
        resolved.mkdir(parents=True, exist_ok=True)
        (resolved / "annotations").mkdir()
        _run_git(resolved, "init", "-q")
        atomic_write_json(
            resolved / "namespace.json",
            {
                "class": NAMESPACE_CLASS,
                "schema_version": SCHEMA_VERSION,
                "id": namespace_id or str(uuid4()),
                "name": name,
                "allowed_types": list(allowed_types),
                "allowed_block_types": list(allowed_block_types),
                "require_block_type": require_block_type,
            },
        )
        _commit_paths(
            resolved,
            (Path("namespace.json"),),
            message="diagram(namespace): initialize",
        )
        return cls.open(resolved)

    @classmethod
    def create_user_touched_chatlas_index(cls, root: Path) -> DiagramNamespace:
        return cls.create(
            root,
            name=USER_TOUCHED_CHATLAS_INDEX,
            allowed_types=CHATLAS_INDEX_ANNOTATION_TYPES,
            allowed_block_types=(
                DIAGRAM_BLOCK_OBJECT_TYPE,
                DESIGN_BLOCK_OBJECT_TYPE,
                IMPL_REQ_BLOCK_OBJECT_TYPE,
                ISSUE_BLOCK_OBJECT_TYPE,
            ),
            require_block_type=True,
        )

    @classmethod
    def create_diagram_attic(cls, root: Path) -> DiagramNamespace:
        return cls.create(
            root,
            name=DIAGRAM_ATTIC,
            allowed_types=CHATLAS_INDEX_ANNOTATION_TYPES,
            allowed_block_types=(
                DIAGRAM_BLOCK_OBJECT_TYPE,
                DESIGN_BLOCK_OBJECT_TYPE,
                IMPL_REQ_BLOCK_OBJECT_TYPE,
                ISSUE_BLOCK_OBJECT_TYPE,
            ),
            require_block_type=True,
        )

    @classmethod
    def open(cls, root: Path) -> DiagramNamespace:
        resolved = root.expanduser().resolve()
        if not (resolved / ".git").is_dir() or not (resolved / "annotations").is_dir():
            raise DiagramError(f"Diagram Namespace repository is invalid: {resolved}")
        data = _read_json(resolved / "namespace.json")
        if (
            data.get("class") != NAMESPACE_CLASS
            or data.get("schema_version") != SCHEMA_VERSION
        ):
            raise DiagramError(f"Diagram Namespace definition is invalid: {resolved}")
        name = _string(data.get("name"), field="Namespace.name")
        default_block_types = (
            (
                DIAGRAM_BLOCK_OBJECT_TYPE,
                DESIGN_BLOCK_OBJECT_TYPE,
                IMPL_REQ_BLOCK_OBJECT_TYPE,
                ISSUE_BLOCK_OBJECT_TYPE,
            )
            if name in CHATLAS_INDEX_NAMESPACES
            else ()
        )
        return cls(
            resolved,
            _uuid(data.get("id"), field="Namespace.id"),
            name,
            tuple(
                _string(item, field="allowed_types[]")
                for item in _array(data.get("allowed_types", []), field="allowed_types")
            ),
            tuple(
                _string(item, field="allowed_block_types[]")
                for item in _array(
                    data.get("allowed_block_types") or list(default_block_types),
                    field="allowed_block_types",
                )
            ),
            (
                bool(data["require_block_type"])
                if data.get("require_block_type") is not None
                else name in CHATLAS_INDEX_NAMESPACES
            ),
        )

    def object_types(self) -> DiagramObjectTypeRegistry:
        return default_diagram_object_types()

    def annotation(self, annotation_id: str) -> DiagramAnnotation:
        annotation_id = _uuid(annotation_id, field="Annotation.id")
        path = self.annotations_root / f"{annotation_id}.json"
        if not path.is_file():
            raise DiagramError(f"Diagram Annotation not found: {annotation_id}")
        return DiagramAnnotation(annotation_id, self, _read_json(path))

    def annotations(self) -> tuple[DiagramAnnotation, ...]:
        return tuple(
            DiagramAnnotation(path.stem, self, _read_json(path))
            for path in sorted(self.annotations_root.glob("*.json"))
        )

    def assertions_for(self, annotation: DiagramAnnotation) -> tuple[JsonObject, ...]:
        if self.name not in CHATLAS_INDEX_NAMESPACES:
            return ()
        typed = self.specialize(annotation)
        if isinstance(typed, ModelAnnotation):
            return typed.type_assertions()
        assertions: tuple[JsonObject, ...] = (
            {"type": "Annotation.Representation.Assertion"},
        )
        if isinstance(typed, UserTouchedAnnotation):
            assertions += ({"type": "User.Touch.Support.Assertion"},)
        return (*assertions, *typed.type_assertions())

    def assertion_engine(
        self, *, evidence: ChatlasEvidence | None = None
    ) -> AssertionEngine:
        return AssertionEngine(evidence=evidence)

    def specialize(self, annotation: DiagramAnnotation) -> TypedAnnotation:
        classes = (
            {
                MODEL_ANNOTATION_TYPE: ModelAnnotation,
                BLOCK_ANNOTATION_TYPE: BlockAnnotation,
                BLOCK_TYPE_ANNOTATION_TYPE: BlockTypeAnnotation,
                LINE_ANNOTATION_TYPE: LineAnnotation,
                LINE_TYPE_ANNOTATION_TYPE: LineTypeAnnotation,
                LINE_SUPPORT_ANNOTATION_TYPE: LineSupportAnnotation,
                LINE_GATE_ANNOTATION_TYPE: LineGateAnnotation,
            }
            if self.name in CHATLAS_INDEX_NAMESPACES
            else {}
        )
        annotation_class = classes.get(annotation.type)
        if annotation_class is None:
            raise DiagramAnnotationSpecializationError(
                f"Annotation type is not registered in Namespace {self.name}: {annotation.type}"
            )
        try:
            return annotation_class(annotation)
        except DiagramModelError as exc:
            raise DiagramAnnotationSpecializationError(
                f"Annotation {annotation.id} cannot be specialized as {annotation.type}: {exc}"
            ) from exc

    def findings(
        self,
        annotation: DiagramAnnotation,
        *,
        path: str,
        evidence: ChatlasEvidence | None = None,
    ) -> tuple[Finding, ...]:
        findings: list[Finding] = []
        built_in_chatlas_types = set(CHATLAS_INDEX_ANNOTATION_TYPES)
        allowed = annotation.type in self.allowed_types or (
            self.name in CHATLAS_INDEX_NAMESPACES
            and annotation.type in built_in_chatlas_types
        )
        if self.allowed_types and not allowed:
            findings.append(
                Finding(
                    "annotation-type-not-allowed",
                    f"{path}.type",
                    f"Namespace {self.name} does not allow Annotation type {annotation.type}.",
                )
            )
        try:
            typed = self.specialize(annotation)
        except DiagramAnnotationSpecializationError as exc:
            findings.append(
                Finding(
                    "annotation-specialization-unavailable", f"{path}.type", str(exc)
                )
            )
            return tuple(findings)
        if isinstance(typed, UserTouchedAnnotation):
            if not typed.support.members:
                findings.append(
                    Finding(
                        "empty-support-set",
                        f"{path}.support",
                        "Annotation has no rooted User.Turn support.",
                    )
                )
            if evidence is not None:
                findings.extend(evidence.check(typed, path=path))
            findings.append(
                Finding(
                    "archive-grounding-unassessable",
                    path,
                    "Chatlas-to-Archive grounding is not yet mechanically assessable.",
                )
            )
        findings.extend(typed.type_findings(path=path, evidence=evidence))
        assessment = self.assertion_engine(evidence=evidence).assess(
            typed, path=path
        )
        findings.extend(assessment.findings)
        if assessment.standing == "UnAsserted":
            findings.append(
                Finding(
                    "annotation-unasserted",
                    path,
                    "Annotation.Score.Vector is missing one or more required Assertion scores.",
                )
            )
        return tuple(findings)

    def append(
        self,
        drafts: Iterable[AnnotationDraft],
        *,
        findings: Iterable[Finding] = (),
        message: str = "diagram: append annotations",
        commit: bool = True,
    ) -> CaptureReceipt:
        base_commit = _run_git(self.root, "rev-parse", "HEAD")
        created: list[str] = []
        existing: list[str] = []
        pending: list[tuple[Path, JsonObject]] = []
        claimed: dict[str, JsonObject] = {}
        for draft in drafts:
            if draft.id in claimed:
                if claimed[draft.id] != draft.record:
                    raise DiagramError(
                        f"Diagram Annotation identity cannot be rebound: {draft.id}"
                    )
                continue
            claimed[draft.id] = draft.record
            path = self.annotations_root / f"{draft.id}.json"
            if path.exists():
                if _semantic_record(_read_json(path)) != _semantic_record(draft.record):
                    raise DiagramError(
                        f"Diagram Annotation identity cannot be rebound: {draft.id}"
                    )
                existing.append(draft.id)
            else:
                pending.append((path, {**draft.record, "recorded_at": _timestamp()}))
        for path, record in pending:
            atomic_write_json(path, record, ensure_ascii=False)
            created.append(path.stem)
        committed = bool(pending) and commit
        if committed:
            _commit_paths(
                self.root,
                (path.relative_to(self.root) for path, _ in pending),
                message=message,
            )
        return CaptureReceipt(
            self.id,
            tuple(created),
            tuple(existing),
            tuple(findings),
            committed,
            base_commit,
            _run_git(self.root, "rev-parse", "HEAD") if committed else None,
        )

    def create_model(
        self, *, model_ship: str | None = None, label: str | None = None
    ) -> DiagramModel:
        ship = model_ship or str(uuid4())
        draft = AnnotationDraft(
            str(uuid4()),
            {
                "type": MODEL_ANNOTATION_TYPE,
                "model_ship": ship,
                "data": {"label": label} if label else {},
            },
        )
        self.append((draft,), message="diagram(model): create")
        return DiagramModel(ship, self, draft.id)

    def model(self, model_ship: str) -> DiagramModel:
        ship = _uuid(model_ship, field="Model.ship")
        roots = [
            item
            for item in self.annotations()
            if item.type == MODEL_ANNOTATION_TYPE
            and item.record.get("model_ship") == ship
        ]
        if len(roots) != 1:
            raise DiagramError(
                f"Diagram Model does not resolve uniquely in Namespace {self.name}: {ship}"
            )
        return DiagramModel(ship, self, roots[0].id)

    def models(self) -> tuple[DiagramModel, ...]:
        return tuple(
            DiagramModel(
                _uuid(item.record.get("model_ship"), field="Model.ship"),
                self,
                item.id,
            )
            for item in self.annotations()
            if item.type == MODEL_ANNOTATION_TYPE
        )

    def apply(
        self,
        manifest: CaptureManifest,
        *,
        evidence: ChatlasEvidence | None = None,
        commit: bool = True,
    ) -> CaptureReceipt:
        self.model(manifest.model_ship)
        return self.append(
            manifest.annotations,
            findings=manifest.check(self, evidence=evidence),
            message=f"diagram(capture): add {len(manifest.annotations)} annotation(s)",
            commit=commit,
        )

    def model_annotations(self, model_ship: str) -> tuple[DiagramAnnotation, ...]:
        ship = _uuid(model_ship, field="Model.ship")
        direct = tuple(
            item
            for item in self.annotations()
            if isinstance(item.record.get("location"), dict)
            and item.record["location"].get("model_ship") == ship
        )
        return self._with_line_gate_annotations(direct)

    def project(
        self,
        model_ship: str,
        *,
        extra: Iterable[DiagramAnnotation] = (),
    ) -> DiagramProjection:
        ship = _uuid(model_ship, field="Model.ship")
        combined = {
            item.id: item for item in (*self.model_annotations(ship), *tuple(extra))
        }
        typed: list[TypedAnnotation] = []
        for annotation in _sort_annotations(combined.values()):
            try:
                specialized = self.specialize(annotation)
            except DiagramAnnotationSpecializationError:
                continue
            try:
                location = specialized.model_location()
            except (DiagramError, DiagramModelError):
                location = None
            if location is None or location[0] == ship:
                typed.append(specialized)
        builder = DiagramProjectionBuilder(self, ship, typed)
        for annotation in typed:
            annotation.contribute(builder)
        return builder.build()

    def block_annotations(self, block_ship: str) -> tuple[DiagramAnnotation, ...]:
        ship = _uuid(block_ship, field="Block.ship")
        direct = tuple(
            item
            for item in self.annotations()
            if isinstance(item.record.get("location"), dict)
            and item.record["location"].get("block_ship") == ship
        )
        return self._with_line_gate_annotations(direct)

    def _with_line_gate_annotations(
        self, direct: tuple[DiagramAnnotation, ...]
    ) -> tuple[DiagramAnnotation, ...]:
        direct_ids = {item.id for item in direct}
        gates = tuple(
            item
            for item in self.annotations()
            if item.type == LINE_GATE_ANNOTATION_TYPE
            and item.record.get("target_annotation") in direct_ids
        )
        return (*direct, *gates)

    def line(self, line_ship: str) -> tuple[TypedAnnotation, ...]:
        ship = _uuid(line_ship, field="Line.ship")
        result: list[TypedAnnotation] = []
        for annotation in self.annotations():
            if annotation.type in (
                LINE_ANNOTATION_TYPE,
                LINE_TYPE_ANNOTATION_TYPE,
                LINE_SUPPORT_ANNOTATION_TYPE,
                LINE_GATE_ANNOTATION_TYPE,
            ):
                typed = self.specialize(annotation)
                if (
                    isinstance(
                        typed,
                        (
                            LineAnnotation,
                            LineTypeAnnotation,
                            LineSupportAnnotation,
                            LineGateAnnotation,
                        ),
                    )
                    and typed.location.line_ship == ship
                ):
                    result.append(typed)
        return tuple(result)

    def line_review(
        self,
        line_ship: str,
        *,
        evidence: ChatlasEvidence | None,
        assertion_engine: AssertionEngine | None = None,
    ) -> LineReview:
        ship = _uuid(line_ship, field="Line.ship")
        annotations = self.line(ship)
        if not any(isinstance(item, LineAnnotation) for item in annotations):
            raise DiagramError(f"Diagram Line not found: {ship}")
        engine = assertion_engine or self.assertion_engine(evidence=evidence)
        assessments = tuple(
            gate_assessment
            for item in annotations
            if isinstance(item, (LineAnnotation, LineGateAnnotation))
            for gate_assessment in engine.assess(item).gate_assessments
        )
        findings = tuple(
            finding for assessment in assessments for finding in assessment.findings
        )
        reviewed = any(item.standing == "Passed" for item in assessments)
        if not reviewed:
            findings = (
                *findings,
                Finding(
                    "line-unreviewed",
                    f"line.{ship}",
                    "Line ship has no Annotation with a passing Verbatim.Gate.",
                ),
            )
        return LineReview(
            ship,
            "Reviewed" if reviewed else "Unreviewed",
            assessments,
            findings,
        )


@dataclass(frozen=True, slots=True)
class DiagramModel:
    ship: str
    namespace: DiagramNamespace
    root_annotation_id: str

    def annotations(self) -> tuple[DiagramAnnotation, ...]:
        return self.namespace.model_annotations(self.ship)

    def project(self) -> DiagramProjection:
        return self.namespace.project(self.ship)


@dataclass(frozen=True, slots=True)
class DiagramConfiguration:
    path: Path
    namespace_locations: tuple[Path, ...]
    default_namespace_id: str | None = None

    @staticmethod
    def default_path() -> Path:
        return (Path.home() / ".tarav" / "diagram.json").resolve()

    @classmethod
    def load(
        cls, path: Path | None = None, *, create: bool = False
    ) -> DiagramConfiguration:
        resolved = (path or cls.default_path()).expanduser().resolve()
        if not resolved.exists():
            if not create:
                raise DiagramError(f"Diagram configuration not found: {resolved}")
            resolved.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_json(
                resolved,
                {
                    "class": DIAGRAM_CONFIG_CLASS,
                    "schema_version": SCHEMA_VERSION,
                    "namespace_locations": [],
                    "default_namespace_id": None,
                },
            )
        data = _read_json(resolved)
        if (
            data.get("class") != DIAGRAM_CONFIG_CLASS
            or data.get("schema_version") != SCHEMA_VERSION
        ):
            raise DiagramError(f"Diagram configuration is invalid: {resolved}")
        default = data.get("default_namespace_id")
        return cls(
            resolved,
            tuple(
                Path(_string(item, field="namespace_locations[]"))
                .expanduser()
                .resolve()
                for item in _array(
                    data.get("namespace_locations", []), field="namespace_locations"
                )
            ),
            _uuid(default, field="default_namespace_id")
            if default is not None
            else None,
        )

    def mount(
        self, namespace: DiagramNamespace, *, default: bool = False
    ) -> DiagramConfiguration:
        locations = list(self.namespace_locations)
        if namespace.root not in locations:
            locations.append(namespace.root)
        default_id = namespace.id if default else self.default_namespace_id
        atomic_write_json(
            self.path,
            {
                "class": DIAGRAM_CONFIG_CLASS,
                "schema_version": SCHEMA_VERSION,
                "namespace_locations": [str(item) for item in locations],
                "default_namespace_id": default_id,
            },
        )
        return DiagramConfiguration.load(self.path)

    def diagram(self) -> Diagram:
        return Diagram(
            tuple(DiagramNamespace.open(path) for path in self.namespace_locations),
            self.default_namespace_id,
        )


@dataclass(frozen=True, slots=True)
class Diagram:
    namespaces: tuple[DiagramNamespace, ...]
    default_namespace_id: str | None = None

    def namespace(self, selector: str | None = None) -> DiagramNamespace:
        selector = selector or self.default_namespace_id
        if selector is None and len(self.namespaces) == 1:
            return self.namespaces[0]
        matches = [item for item in self.namespaces if selector in (item.id, item.name)]
        if len(matches) != 1:
            raise DiagramError(
                f"Diagram Namespace does not resolve uniquely: {selector}"
            )
        return matches[0]

    def assertion_engine(
        self, *, evidence: ChatlasEvidence | None = None
    ) -> AssertionEngine:
        return AssertionEngine(evidence=evidence)

    def object_type_definition_findings(
        self, registry: DiagramObjectTypeRegistry | None = None
    ) -> tuple[Finding, ...]:
        active_registry = registry or default_diagram_object_types()
        return active_registry.definition_findings(self.projected_block)

    def annotation(
        self, annotation_id: str, *, namespace: str | None = None
    ) -> DiagramAnnotation:
        if namespace:
            return self.namespace(namespace).annotation(annotation_id)
        matches = [
            space.annotation(annotation_id)
            for space in self.namespaces
            if (space.annotations_root / f"{annotation_id}.json").is_file()
        ]
        if not matches:
            raise DiagramError(f"Diagram Annotation not found: {annotation_id}")
        return matches[0]

    def model(self, model_ship: str) -> DiagramModel:
        matches = []
        for space in self.namespaces:
            roots = [
                item
                for item in space.annotations()
                if item.type == MODEL_ANNOTATION_TYPE
                and item.record.get("model_ship") == model_ship
            ]
            matches.extend(DiagramModel(model_ship, space, item.id) for item in roots)
        if len(matches) != 1:
            raise DiagramError(f"Diagram Model does not resolve uniquely: {model_ship}")
        return matches[0]

    def models(self, *, namespace: str | None = None) -> tuple[DiagramModel, ...]:
        spaces = (self.namespace(namespace),) if namespace else self.namespaces
        return tuple(model for space in spaces for model in space.models())

    def apply(
        self,
        manifest: CaptureManifest,
        *,
        evidence: ChatlasEvidence | None = None,
        commit: bool = True,
    ) -> CaptureReceipt:
        return self.model(manifest.model_ship).namespace.apply(
            manifest, evidence=evidence, commit=commit
        )

    def line(
        self, line_ship: str, *, namespace: str | None = None
    ) -> tuple[TypedAnnotation, ...]:
        spaces = (self.namespace(namespace),) if namespace else self.namespaces
        return tuple(item for space in spaces for item in space.line(line_ship))

    def projected_line(
        self, line_ship: str, *, namespace: str | None = None
    ) -> DiagramLineShip:
        spaces = (self.namespace(namespace),) if namespace else self.namespaces
        matches: list[DiagramLineShip] = []
        for space in spaces:
            for model in space.models():
                try:
                    matches.append(model.project().line(line_ship))
                except DiagramError:
                    pass
        if len(matches) != 1:
            raise DiagramError(f"Diagram Line does not resolve uniquely: {line_ship}")
        return matches[0]

    def block_annotations(
        self, block_ship: str, *, namespace: str | None = None
    ) -> tuple[DiagramAnnotation, ...]:
        spaces = (self.namespace(namespace),) if namespace else self.namespaces
        matches = tuple(
            (space, space.block_annotations(block_ship)) for space in spaces
        )
        populated = tuple((space, values) for space, values in matches if values)
        if len(populated) != 1:
            raise DiagramError(f"Diagram Block does not resolve uniquely: {block_ship}")
        return populated[0][1]

    def projected_block(
        self, block_ship: str, *, namespace: str | None = None
    ) -> DiagramBlock:
        spaces = (self.namespace(namespace),) if namespace else self.namespaces
        matches: list[DiagramBlock] = []
        for space in spaces:
            for model in space.models():
                try:
                    matches.append(model.project().block(block_ship))
                except DiagramError:
                    pass
        if len(matches) != 1:
            raise DiagramError(f"Diagram Block does not resolve uniquely: {block_ship}")
        return matches[0]

    def line_review(
        self,
        line_ship: str,
        *,
        namespace: str | None = None,
        evidence: ChatlasEvidence | None,
    ) -> LineReview:
        spaces = (self.namespace(namespace),) if namespace else self.namespaces
        matches = []
        for space in spaces:
            if any(isinstance(item, LineAnnotation) for item in space.line(line_ship)):
                matches.append(space)
        if len(matches) != 1:
            raise DiagramError(f"Diagram Line does not resolve uniquely: {line_ship}")
        return matches[0].line_review(
            line_ship,
            evidence=evidence,
            assertion_engine=self.assertion_engine(evidence=evidence),
        )

    def ensure_project_model(self, project_root: Path) -> DiagramModel:
        marker_path = project_marker_path(project_root.expanduser().resolve())
        marker = load_project_marker(marker_path)
        setting = marker.get("diagram")
        if isinstance(setting, dict) and isinstance(setting.get("main_model"), str):
            return self.model(setting["main_model"])
        namespace = (
            self.namespace(USER_TOUCHED_CHATLAS_INDEX)
            if any(item.name == USER_TOUCHED_CHATLAS_INDEX for item in self.namespaces)
            else self.namespace()
        )
        model = namespace.create_model(label=project_root.name)
        marker["diagram"] = {"main_model": model.ship}
        atomic_write_json(marker_path, marker, ensure_ascii=False)
        return model

    def project_model(self, project_root: Path) -> DiagramModel:
        marker = load_project_marker(
            project_marker_path(project_root.expanduser().resolve())
        )
        setting = marker.get("diagram")
        if not isinstance(setting, dict) or not isinstance(
            setting.get("main_model"), str
        ):
            raise DiagramError(
                f"Project has no Diagram main Model: {project_root.expanduser().resolve()}"
            )
        return self.model(setting["main_model"])

    def set_project_main_model(
        self, project_root: Path, model_ship: str
    ) -> DiagramModel:
        """Point one Project at an existing Model without implying ownership."""
        model = self.model(model_ship)
        marker_path = project_marker_path(project_root.expanduser().resolve())
        marker = load_project_marker(marker_path)
        current = marker.get("diagram")
        diagram_data = dict(current) if isinstance(current, dict) else {}
        diagram_data["main_model"] = model.ship
        marker["diagram"] = diagram_data
        atomic_write_json(marker_path, marker, ensure_ascii=False)
        return model


def _semantic_record(record: Mapping[str, Any]) -> JsonObject:
    return {key: value for key, value in record.items() if key != "recorded_at"}


def _verbatim_gates(value: object) -> tuple[VerbatimGate, ...]:
    return tuple(
        VerbatimGate.from_dict(item) for item in _array(value, field="Annotation.gates")
    )


def _assess_verbatim_gates(
    *,
    annotation_id: str,
    target_id: str,
    target: LineAnnotation | None,
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
                    target.id,
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
    target: LineAnnotation,
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
        target.id,
        gate,
        scores,
        tuple(findings),
    )


def _gate_turn(
    evidence: ChatlasEvidence,
    reference: ChatlasTurnReference,
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


def _object(value: object, *, field: str) -> JsonObject:
    if not isinstance(value, dict):
        raise DiagramModelError(f"{field} must be an object")
    return dict(value)


def _array(value: object, *, field: str) -> list[object]:
    if not isinstance(value, list):
        raise DiagramModelError(f"{field} must be an array")
    return value


def _string(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise DiagramModelError(f"{field} must be a non-empty string")
    return value


def _digest(value: object, *, field: str) -> str:
    text = _string(value, field=field)
    if not _SHA256.fullmatch(text):
        raise DiagramModelError(f"{field} must be a lowercase SHA-256 digest")
    return text


def _uuid(value: object, *, field: str) -> str:
    text = _string(value, field=field)
    try:
        parsed = UUID(text)
    except ValueError as exc:
        raise DiagramModelError(f"{field} must be a UUID") from exc
    if str(parsed) != text:
        raise DiagramModelError(f"{field} must be a canonical lowercase UUID")
    return text


def _read_json(path: Path) -> JsonObject:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DiagramError(f"cannot read Diagram JSON {path}: {exc}") from exc
    return _object(value, field=str(path))


def _run_git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ("git", "-C", str(repo), *args), capture_output=True, text=True, check=False
    )
    if result.returncode:
        raise DiagramError(
            f"Git failed for {repo}: {result.stderr.strip() or result.stdout.strip()}"
        )
    return result.stdout.strip()


def _commit_paths(repo: Path, paths: Iterable[Path], *, message: str) -> None:
    values = tuple(path.as_posix() for path in paths)
    _run_git(repo, "add", "--", *values)
    _run_git(
        repo,
        "-c",
        "user.name=Tarav Diagram",
        "-c",
        "user.email=diagram@tarav.invalid",
        "commit",
        "-q",
        "--only",
        "-m",
        message,
        "--",
        *values,
    )


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


__all__ = [
    name
    for name in globals()
    if name.startswith(("Diagram", "Design"))
    or name
    in {
        "AnnotationDraft",
        "AnnotationAssessment",
        "AssertionEngine",
        "AssertionEvaluation",
        "CaptureManifest",
        "CaptureReceipt",
        "ChatlasEvidence",
        "ChatlasTurnReference",
        "Finding",
        "GateAssessment",
        "IssueAssessment",
        "LineReview",
        "SupportMember",
        "SupportSet",
        "TypedAnnotation",
        "UserTouchedAnnotation",
        "BlockAnnotation",
        "BlockTypeAnnotation",
        "LineAnnotation",
        "LineGateAnnotation",
        "LineSupportAnnotation",
        "LineTypeAnnotation",
        "ModelAnnotation",
        "MechanicalAssertionEvaluator",
        "VerbatimGate",
        "VerbatimGateAssertionEvaluator",
        "BLOCK_ANNOTATION_TYPE",
        "BLOCK_TYPE_ANNOTATION_TYPE",
        "DIAGRAM_BLOCK_OBJECT_TYPE",
        "DIAGRAM_LINE_OBJECT_TYPE",
        "DESIGN_BLOCK_OBJECT_TYPE",
        "DESIGN_LINE_CONSTRAINT_TYPE",
        "DESIGN_LINE_DECISION_TYPE",
        "DESIGN_LINE_DEFINITION_TYPE",
        "DESIGN_LINE_EXAMPLE_TYPE",
        "DESIGN_LINE_FREEDOM_TYPE",
        "DESIGN_LINE_OBJECT_TYPES",
        "DESIGN_LINE_PRINCIPLE_TYPE",
        "DESIGN_LINE_REJECTION_TYPE",
        "IMPL_REQ_BLOCK_OBJECT_TYPE",
        "ISSUE_BLOCK_OBJECT_TYPE",
        "ISSUE_LINE_RESOLVE_TYPE",
        "DIAGRAM_ATTIC",
        "LINE_ANNOTATION_TYPE",
        "LINE_GATE_ANNOTATION_TYPE",
        "LINE_SUPPORT_ANNOTATION_TYPE",
        "LINE_TYPE_ANNOTATION_TYPE",
        "MODEL_ANNOTATION_TYPE",
        "USER_TOUCHED_CHATLAS_INDEX",
        "VERBATIM_GATE_TYPE",
        "ImplReqBlock",
        "IssueBlock",
        "IssueLineResolve",
        "IssueResolveLineShip",
        "default_diagram_object_types",
    }
]
