"""tarav.l2.unsorted.contracts: extracted legacy definitions; identities and storage labels preserved."""

from __future__ import annotations

# tarav.breadcrumb 5a32dd5b546e

from pydantic import ConfigDict
from tarav.l2.unsorted.primitives import DiagramModelError
from pydantic import Field
from tarav.l2.unsorted.constants import JsonObject
from pydantic import JsonValue
from tarav.l0.kernel import TaravAssertion
from tarav.l0.kernel import TaravClass
from tarav.l0.kernel import TaravObject
from tarav.l2.unsorted.pois import DiagramPOI
from tarav.l0.kernel import TypeShip
from tarav.l2.unsorted.identity import UNSORTED_WORKFLOW_SHIP
from tarav.l2.unsorted.constants import VERBATIM_GATE_TYPE
from tarav.l2.unsorted.primitives import _array
from tarav.l2.unsorted.primitives import _object
from tarav.l2.unsorted.primitives import _record_type_reference
from tarav.l2.unsorted.primitives import _string
from tarav.l2.unsorted.primitives import _uuid
from dataclasses import dataclass
from pydantic import field_validator
from pydantic import model_validator
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any
    from collections.abc import Iterable
    from collections.abc import Mapping
    from tarav.l2.unsorted.records import TypedAnnotation

class ChatlasTurnReferenceInterface(TaravObject.RecordInterface):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    session_identity: str = Field(pattern=r"^[0-9a-f]{64}$")
    turn_address: str = Field(pattern=r"^[0-9a-f]{64}$")
    turn_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class VerbatimGate:
    token: str
    proposal_turn: ChatlasTurnReferenceInterface
    approval_turn: ChatlasTurnReferenceInterface

    def __post_init__(self) -> None:
        _string(self.token, field="Verbatim.Gate.token")

    def to_dict(self) -> JsonObject:
        return {
            "type": VERBATIM_GATE_TYPE,
            "token": self.token,
            "proposal_turn": self.proposal_turn.model_dump(mode="json"),
            "approval_turn": self.approval_turn.model_dump(mode="json"),
        }

    @classmethod
    def from_dict(cls, value: object) -> VerbatimGate:
        data = _object(value, field="Verbatim.Gate")
        if data.get("type") != VERBATIM_GATE_TYPE:
            raise DiagramModelError(f"unsupported Line Gate type: {data.get('type')}")
        return cls(
            _string(data.get("token"), field="Verbatim.Gate.token"),
            ChatlasTurnReferenceInterface.model_validate(data.get("proposal_turn")),
            ChatlasTurnReferenceInterface.model_validate(data.get("approval_turn")),
        )


@dataclass(frozen=True, slots=True)
class GateAssessment:
    annotation_id: str
    target_edition_id: str
    gate: VerbatimGate
    scores: JsonObject
    pois: tuple[DiagramPOI, ...]

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
            "target_edition_id": self.target_edition_id,
            "gate": self.gate.to_dict(),
            "standing": self.standing,
            "scores": dict(self.scores),
            "pois": [item.records.to_record() for item in self.pois],
        }


@dataclass(frozen=True, slots=True)
class LineReview:
    line_ship: str
    standing: str
    assessments: tuple[GateAssessment, ...]
    pois: tuple[DiagramPOI, ...]

    def to_dict(self) -> JsonObject:
        return {
            "line_ship": self.line_ship,
            "standing": self.standing,
            "assessments": [item.to_dict() for item in self.assessments],
            "pois": [item.records.to_record() for item in self.pois],
        }


@dataclass(frozen=True, slots=True)
class IssueAssessment:
    block_ship: str
    state: str
    resolution_line_ships: tuple[str, ...]
    gate_assessments: tuple[GateAssessment, ...]
    pois: tuple[DiagramPOI, ...]

    def to_dict(self) -> JsonObject:
        return {
            "block_ship": self.block_ship,
            "state": self.state,
            "resolution_line_ships": list(self.resolution_line_ships),
            "gate_assessments": [item.to_dict() for item in self.gate_assessments],
            "pois": [item.records.to_record() for item in self.pois],
        }


class SupportMemberInterface(TaravObject.RecordInterface):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    root: ChatlasTurnReferenceInterface
    neighborhood: list[ChatlasTurnReferenceInterface] = Field(default_factory=list)


def _support_members(value: object) -> tuple[SupportMemberInterface, ...]:
    return tuple(
        SupportMemberInterface.model_validate(item)
        for item in _array(value, field="Annotation.support")
    )


class AnnotationDraftInterface(TaravObject.RecordInterface):
    model_config = ConfigDict(strict=True, extra="allow", frozen=True)

    id: str
    type: str | dict[str, JsonValue] | None = None

    @field_validator("id")
    @classmethod
    def validate_uuid(cls, value: str) -> str:
        return _uuid(value, field="Annotation.id")

    @model_validator(mode="after")
    def validate_record_type(self) -> AnnotationDraftInterface:
        _record_type_reference(self.record, field="Annotation")
        return self

    @property
    def record(self) -> JsonObject:
        return self.model_dump(mode="json", exclude={"id"}, exclude_unset=True)

    @classmethod
    def from_record(
        cls, identity: str, record: Mapping[str, Any]
    ) -> AnnotationDraftInterface:
        copied = _object(record, field="Annotation")
        _record_type_reference(copied, field="Annotation")
        return cls.model_validate({**copied, "id": identity})


class ShipDraftInterface(TaravObject.RecordInterface):
    """One complete or incremental typed Ship record supplied by Capture."""

    model_config = ConfigDict(strict=True, extra="allow", frozen=True)

    id: str
    type: str | dict[str, JsonValue] | None = None
    editions: list[JsonObject] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def validate_uuid(cls, value: str) -> str:
        return _uuid(value, field="Ship.id")

    @model_validator(mode="after")
    def validate_record_type(self) -> ShipDraftInterface:
        _record_type_reference(self.record, field="Ship")
        _array(self.record.get("editions", []), field="Ship.editions")
        return self

    @property
    def record(self) -> JsonObject:
        return self.model_dump(mode="json", exclude={"id"}, exclude_unset=True)

    @classmethod
    def from_record(
        cls, identity: str, record: Mapping[str, Any]
    ) -> ShipDraftInterface:
        copied = _object(record, field="Ship")
        _record_type_reference(copied, field="Ship")
        _array(copied.get("editions", []), field="Ship.editions")
        return cls.model_validate({**copied, "id": identity})


@dataclass(frozen=True, slots=True)
class DiagramObjectAssertion(TaravAssertion):
    """One assertion exposed by a projected object without duplicate evaluation."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('53d7a115-51c1-4d1b-b309-93abf43f13f8'),
            name='Tarav.Diagram.Object.Assertion',
            workflow=UNSORTED_WORKFLOW_SHIP,
        )
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


def _dedupe_pois(pois: Iterable[DiagramPOI]) -> tuple[DiagramPOI, ...]:
    return tuple(
        {item.identity: item for item in pois}.values()
    )


def _verbatim_gates(value: object) -> tuple[VerbatimGate, ...]:
    return tuple(
        VerbatimGate.from_dict(item) for item in _array(value, field="Annotation.gates")
    )
