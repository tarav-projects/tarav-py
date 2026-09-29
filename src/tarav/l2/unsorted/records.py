"""tarav.l2.unsorted.records: extracted legacy definitions; identities and storage labels preserved."""

from __future__ import annotations

from tarav.l2.unsorted.constants import BLOCK_EDITION_TYPE
from tarav.l2.unsorted.constants import BLOCK_SHIP_TYPE
from tarav.l2.unsorted.constants import BLOCK_TYPE_ANNOTATION_TYPE
from tarav.l2.unsorted.constants import CAPTURE_AUTHORIZATION_GATE_TYPE
from tarav.l2.unsorted.constants import COLLECTION_EDITION_TYPE
from tarav.l2.unsorted.constants import COLLECTION_SHIP_TYPE
from tarav.l2.unsorted.contracts import ChatlasTurnReferenceInterface
from tarav.l2.unsorted.constants import DIAGRAM_BLOCK_OBJECT_TYPE
from tarav.l2.unsorted.constants import DIAGRAM_COLLECTION_OBJECT_TYPE
from tarav.l2.unsorted.constants import DIAGRAM_LINE_OBJECT_TYPE
from tarav.l2.unsorted.primitives import DiagramAnnotationSpecializationError
from tarav.l2.unsorted.primitives import DiagramModelError
from tarav.l0.kernel import FileRecord
from tarav.l2.unsorted.constants import LINE_ANNOTATION_TYPE
from tarav.l2.unsorted.constants import LINE_EDITION_TYPE
from tarav.l2.unsorted.constants import LINE_GATE_ANNOTATION_TYPE
from tarav.l2.unsorted.constants import LINE_SHIP_TYPE
from tarav.l2.unsorted.constants import LINE_SUPPORT_ANNOTATION_TYPE
from tarav.l2.unsorted.constants import LINE_TYPE_ANNOTATION_TYPE
from tarav.l2.unsorted.constants import MODEL_EDITION_TYPE
from tarav.l0.kernel import Ship
from tarav.l0.kernel import TaravClass
from tarav.l0.kernel import TypeShip
from tarav.l2.unsorted.identity import UNSORTED_WORKFLOW_SHIP
from tarav.l2.unsorted.constants import VERBATIM_GATE_TYPE
from tarav.l2.unsorted.constants import _EXAMPLE_BLOCK
from tarav.l2.unsorted.constants import _EXAMPLE_COLLECTION
from tarav.l2.unsorted.constants import _EXAMPLE_DIGEST
from tarav.l2.unsorted.constants import _EXAMPLE_EDITION
from tarav.l2.unsorted.constants import _EXAMPLE_LINE
from tarav.l2.unsorted.constants import _EXAMPLE_MODEL
from tarav.l2.unsorted.constants import _EXAMPLE_NAMESPACE
from tarav.l2.unsorted.primitives import _array
from tarav.l0.kernel.records import _json_object
from tarav.l2.unsorted.primitives import _object
from tarav.l2.unsorted.primitives import _record_type_name
from tarav.l2.unsorted.primitives import _record_type_reference
from tarav.l2.unsorted.contracts import _support_members
from tarav.l2.unsorted.primitives import _uuid
from dataclasses import dataclass
from tarav.l0.kernel import entity
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pydantic import BaseModel
    from tarav.l2.unsorted.evidence import ChatlasEvidence
    from tarav.l2.unsorted.storage import DiagramNamespace
    from tarav.l2.lines.projection import DiagramProjectionBuilder
    from tarav.l2.unsorted.contracts import Finding
    from collections.abc import Iterable
    from tarav.l2.unsorted.constants import JsonObject
    from collections.abc import Mapping
    from tarav.l0.kernel import RecordTypeReference
    from typing import Self
    from tarav.l2.unsorted.contracts import SupportMemberInterface

@dataclass(frozen=True, slots=True)
class DiagramShip:
    """Address and Namespace binding for one retained Ship Record."""

    id: str
    namespace: DiagramNamespace
    record: JsonObject

    def __post_init__(self) -> None:
        _uuid(self.id, field="Ship.id")
        copied = _object(self.record, field="Ship.Record")
        _record_type_reference(copied, field="Ship")
        object.__setattr__(self, "record", copied)

    @property
    def type_reference(self) -> RecordTypeReference:
        return _record_type_reference(self.record, field="Ship")

    @property
    def type(self) -> str:
        return _record_type_name(self.record, field="Ship")

    def to_record(self) -> JsonObject:
        return dict(self.record)

    def specialize(self) -> TypedShip:
        return self.namespace.specialize_ship(self)


class TypedShip(FileRecord):
    """Registered Ship Record interpreter, optionally bound to Diagram storage."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('f495fc94-a511-4a9f-b058-7e2957890529'),
            name="Tarav.Diagram.TypedShip",
            workflow=UNSORTED_WORKFLOW_SHIP,
        )
    def __init__(self, record: Mapping[str, object] | DiagramShip) -> None:
        if isinstance(record, DiagramShip):
            self.ship: DiagramShip | None = record
            retained = record.record
        else:
            self.ship = None
            retained = _object(record, field="Ship.Record")
        super().__init__()
        self._record = _json_object(retained)
        type(self).validate_record(self._record)
        self._validate_record()

    @classmethod
    def _from_record(cls, record_data: BaseModel) -> Self:
        return cls(
            record_data.model_dump(mode="json", exclude_unset=True, by_alias=True)
        )

    def _validate_record(self) -> None:
        return None

    @classmethod
    def record_example(cls) -> JsonObject:
        example = super().record_example()
        if entity(cls).name in {BLOCK_SHIP_TYPE, LINE_SHIP_TYPE, COLLECTION_SHIP_TYPE}:
            example["model_ship"] = _EXAMPLE_MODEL
        if entity(cls).name == LINE_SHIP_TYPE:
            example["block_ship"] = _EXAMPLE_BLOCK
        return example

    def _binding(self) -> DiagramShip:
        if self.ship is None:
            raise DiagramModelError(
                f"{type(self).__name__} requires a Diagram Ship storage binding"
            )
        return self.ship

    @property
    def id(self) -> str:
        return self._binding().id

    @property
    def type(self) -> str:
        return _record_type_name(self._record, field="Ship")

    @property
    def namespace(self) -> DiagramNamespace:
        return self._binding().namespace

    @property
    def editions(self) -> tuple[JsonObject, ...]:
        subject = self.ship.id if self.ship is not None else type(self).__name__
        return tuple(
            _object(item, field=f"Ship.{subject}.editions[]")
            for item in _array(self._record.get("editions", []), field="Ship.editions")
        )

    def _require_record_type(self) -> None:
        reference = _record_type_reference(self._record, field="Ship")
        if not type(self).matches(reference):
            raise DiagramModelError(
                f"not a {entity(type(self)).name}: {reference.describe()}"
            )

    def ships(self) -> tuple[Ship, ...]:
        return (
            *super(TypedShip, self).ships(),
            Ship(self.id),
        )

    def edition_annotations(self) -> tuple[DiagramAnnotation, ...]:
        return ()


@dataclass(frozen=True, slots=True)
class DiagramAnnotation:
    """Address and Namespace binding for an Annotation or edition adapter."""

    id: str
    namespace: DiagramNamespace
    record: JsonObject

    def __post_init__(self) -> None:
        _uuid(self.id, field="Annotation.id")
        copied = _object(self.record, field="Annotation.Record")
        _record_type_reference(copied, field="Annotation")
        object.__setattr__(self, "record", copied)

    @property
    def type_reference(self) -> RecordTypeReference:
        return _record_type_reference(self.record, field="Annotation")

    @property
    def type(self) -> str:
        return _record_type_name(self.record, field="Annotation")

    @property
    def standing(self) -> str:
        return "Asserted" if self.score_vector() else "UnAsserted"

    def assertions(self) -> tuple[JsonObject, ...]:
        return self.namespace.assertions_for(self)

    def score_vector(self) -> JsonObject:
        try:
            return self.specialize().score_vector()
        except DiagramAnnotationSpecializationError:
            pass
        value = self.record.get("score_vector", {})
        return value if isinstance(value, dict) else {}

    def to_record(self) -> JsonObject:
        return dict(self.record)

    def specialize(self) -> TypedAnnotation:
        return self.namespace.specialize(self)


class TypedAnnotation(FileRecord):
    """Registered Annotation interpreter, optionally bound to Diagram storage."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('e01f77fb-4155-4efd-94f7-a0abcecadc27'),
            name="Tarav.Diagram.TypedAnnotation",
            workflow=UNSORTED_WORKFLOW_SHIP,
        )
    def __init__(self, record: Mapping[str, object] | DiagramAnnotation) -> None:
        if isinstance(record, DiagramAnnotation):
            self.annotation: DiagramAnnotation | None = record
            retained = record.record
        else:
            self.annotation = None
            retained = _object(record, field="Annotation.Record")
        super().__init__()
        self._record = _json_object(retained)
        type(self).validate_record(self._record)
        self._validate_record()

    @classmethod
    def _from_record(cls, record_data: BaseModel) -> Self:
        return cls(
            record_data.model_dump(mode="json", exclude_unset=True, by_alias=True)
        )

    def _validate_record(self) -> None:
        return None

    @classmethod
    def record_example(cls) -> JsonObject:
        example = super().record_example()
        location = {
            "model_ship": _EXAMPLE_MODEL,
            "block_ship": _EXAMPLE_BLOCK,
            "line_ship": _EXAMPLE_LINE,
        }
        if entity(cls).name == MODEL_EDITION_TYPE:
            example["model_ship"] = _EXAMPLE_MODEL
        elif entity(cls).name == LINE_ANNOTATION_TYPE:
            example.update(
                model_ship=_EXAMPLE_MODEL,
                editions=[
                    {
                        "id": _EXAMPLE_EDITION,
                        "arguments": [
                            {
                                "namespace_id": _EXAMPLE_NAMESPACE,
                                "kind": "ship",
                                "id": _EXAMPLE_LINE,
                            }
                        ],
                        "data": {"text": "Example line"},
                    }
                ],
            )
        elif entity(cls).name == LINE_EDITION_TYPE:
            example.update(location=location, data={"text": "Example line"})
        elif entity(cls).name == BLOCK_EDITION_TYPE:
            example.update(
                location={key: location[key] for key in ("model_ship", "block_ship")},
                data={"label": "Example block"},
            )
        elif entity(cls).name == COLLECTION_EDITION_TYPE:
            example.update(
                model_ship=_EXAMPLE_MODEL,
                collection_ship=_EXAMPLE_COLLECTION,
                collection_type=DIAGRAM_COLLECTION_OBJECT_TYPE,
                data={"label": "Example collection"},
            )
        elif entity(cls).name == CAPTURE_AUTHORIZATION_GATE_TYPE:
            turn = {
                "session_identity": _EXAMPLE_DIGEST,
                "turn_address": _EXAMPLE_DIGEST,
                "turn_hash": _EXAMPLE_DIGEST,
            }
            example.update(
                model_ship=_EXAMPLE_MODEL,
                token="example-authorization",
                workflow="example",
                permission_turn=turn,
                operations=["example"],
                target_scope=[
                    {
                        "namespace_id": _EXAMPLE_NAMESPACE,
                        "kind": "ship",
                        "id": _EXAMPLE_MODEL,
                    }
                ],
            )
        elif entity(cls).name == BLOCK_TYPE_ANNOTATION_TYPE:
            example.update(
                location={key: location[key] for key in ("model_ship", "block_ship")},
                block_type=DIAGRAM_BLOCK_OBJECT_TYPE,
            )
        elif entity(cls).name == LINE_SUPPORT_ANNOTATION_TYPE:
            example["location"] = location
        elif entity(cls).name == LINE_TYPE_ANNOTATION_TYPE:
            example.update(location=location, line_type=DIAGRAM_LINE_OBJECT_TYPE)
        elif entity(cls).name == LINE_GATE_ANNOTATION_TYPE:
            turn = {
                "session_identity": _EXAMPLE_DIGEST,
                "turn_address": _EXAMPLE_DIGEST,
                "turn_hash": _EXAMPLE_DIGEST,
            }
            example.update(
                target_edition=_EXAMPLE_EDITION,
                gates=[
                    {
                        "type": VERBATIM_GATE_TYPE,
                        "token": "example-gate",
                        "proposal_turn": turn,
                        "approval_turn": turn,
                    }
                ],
            )
        return example

    def _binding(self) -> DiagramAnnotation:
        if self.annotation is None:
            raise DiagramModelError(
                f"{type(self).__name__} requires an Annotation storage binding"
            )
        return self.annotation

    @property
    def id(self) -> str:
        return self._binding().id

    @property
    def type(self) -> str:
        return _record_type_name(self._record, field="Annotation")

    @property
    def namespace(self) -> DiagramNamespace:
        return self._binding().namespace

    def model_location(self) -> tuple[str, str] | None:
        """Return the owning Model and the record path that establishes it."""

        return None

    def type_assertions(self) -> tuple[JsonObject, ...]:
        return ()

    def score_vector(self) -> JsonObject:
        value = self._record.get("score_vector", {})
        return value if isinstance(value, dict) else {}

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

    def _require_record_type(self) -> None:
        reference = _record_type_reference(self._record, field="Annotation")
        if not type(self).matches(reference):
            raise DiagramModelError(
                f"not a {entity(type(self)).name}: {reference.describe()}"
            )


class UserTouchedAnnotation(TypedAnnotation):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('35958f0b-e78f-4b94-b5d2-d1e74c56b355'),
            name="Tarav.Diagram.UserTouchedAnnotation",
            workflow=UNSORTED_WORKFLOW_SHIP,
        )

    @property
    def producer(self) -> ChatlasTurnReferenceInterface:
        return ChatlasTurnReferenceInterface.model_validate(self._record.get("producer"))

    @property
    def support(self) -> tuple[SupportMemberInterface, ...]:
        return _support_members(self._record.get("support", []))

    def render_support(self, evidence: ChatlasEvidence) -> list[JsonObject]:
        return [evidence.render_member(item) for item in self.support]


def _sort_annotations(
    annotations: Iterable[DiagramAnnotation],
) -> tuple[DiagramAnnotation, ...]:
    return tuple(
        sorted(
            annotations,
            key=lambda item: (str(item.to_record().get("recorded_at", "")), item.id),
        )
    )


def _sort_typed(
    annotations: Iterable[TypedAnnotation],
) -> tuple[TypedAnnotation, ...]:
    return tuple(
        sorted(
            annotations,
            key=lambda item: (str(item.to_record().get("recorded_at", "")), item.id),
        )
    )
