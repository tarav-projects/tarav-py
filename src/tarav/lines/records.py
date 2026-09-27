"""tarav.lines.records: extracted legacy definitions; identities and storage labels preserved."""

from __future__ import annotations

from tarav.unsorted.constants import BLOCK_EDITION_TYPE
from tarav.unsorted.constants import BLOCK_SHIP_TYPE
from tarav.unsorted.constants import BLOCK_TYPE_ANNOTATION_TYPE
from tarav.unsorted.constants import COLLECTION_EDITION_TYPE
from tarav.unsorted.constants import COLLECTION_SHIP_TYPE
from tarav.unsorted.contracts import ChatlasTurnReferenceInterface
from tarav.unsorted.records import DiagramAnnotation
from tarav.lines.references import DiagramArgumentReferenceInterface
from tarav.lines.references import DiagramBlockLocationInterface
from tarav.lines.references import DiagramLocationInterface
from tarav.unsorted.primitives import DiagramModelError
from tarav.unsorted.contracts import Finding
from tarav.lines.identity import LINES_WORKFLOW_SHIP
from tarav.unsorted.constants import LINE_ANNOTATION_TYPE
from tarav.unsorted.constants import LINE_EDITION_TYPE
from tarav.unsorted.constants import LINE_GATE_ANNOTATION_TYPE
from tarav.unsorted.constants import LINE_SHIP_TYPE
from tarav.unsorted.constants import LINE_SUPPORT_ANNOTATION_TYPE
from tarav.unsorted.constants import LINE_TYPE_ANNOTATION_TYPE
from tarav.models.records import ModelEditionRecord
from tarav.kernel import Ship
from tarav.kernel import TaravClass
from tarav.kernel import TypeShip
from tarav.unsorted.records import TypedAnnotation
from tarav.unsorted.records import TypedShip
from tarav.unsorted.records import UserTouchedAnnotation
from tarav.unsorted.constants import VERBATIM_GATE_ASSERTIONS
from tarav.unsorted.primitives import _array
from tarav.unsorted.primitives import _authorization_gate_ids
from tarav.unsorted.primitives import _edition_id
from tarav.unsorted.primitives import _edition_payload
from tarav.lines.references import _location_ships
from tarav.unsorted.primitives import _object
from tarav.lines.references import _record_host
from tarav.unsorted.primitives import _string
from tarav.unsorted.contracts import _support_members
from tarav.unsorted.primitives import _uuid
from tarav.unsorted.primitives import _validate_editions
from tarav.unsorted.contracts import _verbatim_gates
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any
    from tarav.unsorted.evidence import ChatlasEvidence
    from tarav.lines.references import DiagramHostReferenceInterface
    from tarav.lines.projection import DiagramProjectionBuilder
    from tarav.unsorted.constants import JsonObject
    from collections.abc import Mapping
    from tarav.unsorted.contracts import SupportMemberInterface
    from tarav.unsorted.contracts import VerbatimGate



class BlockShipRecord(TypedShip):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('d091667e-4426-45a2-a22b-ee900d9ca9de'),
            name=BLOCK_SHIP_TYPE,
            workflow=LINES_WORKFLOW_SHIP,
        )

    def _validate_record(self) -> None:
        self._require_record_type()
        _uuid(self._record.get("model_ship"), field="Block.Ship.model_ship")
        _validate_editions(self.editions, field="Block.Ship.editions")

    @property
    def model_ship(self) -> str:
        return _uuid(self._record.get("model_ship"), field="Block.Ship.model_ship")

    def ships(self) -> tuple[Ship, ...]:
        return (
            *super(BlockShipRecord, self).ships(),
            Ship(self.model_ship),
        )

    def edition_annotations(self) -> tuple[DiagramAnnotation, ...]:
        return tuple(
            DiagramAnnotation(
                _edition_id(edition),
                self.namespace,
                {
                    "type": BLOCK_EDITION_TYPE,
                    "location": {
                        "model_ship": self.model_ship,
                        "block_ship": self.id,
                    },
                    **_edition_payload(edition),
                },
            )
            for edition in self.editions
        )


class LineShipRecord(TypedShip):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('18dd06c0-bdcb-48ac-b5a6-3388a601084c'),
            name=LINE_SHIP_TYPE,
            workflow=LINES_WORKFLOW_SHIP,
        )

    def _validate_record(self) -> None:
        self._require_record_type()
        _uuid(self._record.get("model_ship"), field="Line.Ship.model_ship")
        _uuid(self._record.get("block_ship"), field="Line.Ship.block_ship")
        _validate_editions(self.editions, field="Line.Ship.editions")

    @property
    def model_ship(self) -> str:
        return _uuid(self._record.get("model_ship"), field="Line.Ship.model_ship")

    @property
    def block_ship(self) -> str:
        return _uuid(self._record.get("block_ship"), field="Line.Ship.block_ship")

    def ships(self) -> tuple[Ship, ...]:
        return (
            *super(LineShipRecord, self).ships(),
            Ship(self.model_ship),
            Ship(self.block_ship),
        )

    def edition_annotations(self) -> tuple[DiagramAnnotation, ...]:
        return tuple(
            DiagramAnnotation(
                _edition_id(edition),
                self.namespace,
                {
                    "type": LINE_EDITION_TYPE,
                    "location": {
                        "model_ship": self.model_ship,
                        "block_ship": self.block_ship,
                        "line_ship": self.id,
                    },
                    **_edition_payload(edition),
                },
            )
            for edition in self.editions
        )


class CollectionShipRecord(TypedShip):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('5af5946f-2fa7-4d27-af37-c5bbbf271ff0'),
            name=COLLECTION_SHIP_TYPE,
            workflow=LINES_WORKFLOW_SHIP,
        )

    def _validate_record(self) -> None:
        self._require_record_type()
        _uuid(self._record.get("model_ship"), field="Collection.Ship.model_ship")
        _validate_editions(self.editions, field="Collection.Ship.editions")

    @property
    def model_ship(self) -> str:
        return _uuid(self._record.get("model_ship"), field="Collection.Ship.model_ship")

    def ships(self) -> tuple[Ship, ...]:
        return (
            *super(CollectionShipRecord, self).ships(),
            Ship(self.model_ship),
        )

    def edition_annotations(self) -> tuple[DiagramAnnotation, ...]:
        return tuple(
            DiagramAnnotation(
                _edition_id(edition),
                self.namespace,
                {
                    "type": COLLECTION_EDITION_TYPE,
                    "model_ship": self.model_ship,
                    "collection_ship": self.id,
                    **_edition_payload(edition),
                },
            )
            for edition in self.editions
        )




class LineAnnotationRecord(TypedAnnotation):
    """One free-standing Index.Line with explicit Diagram arguments."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('212bab37-f204-4ad7-b174-c339812c7876'),
            name=LINE_ANNOTATION_TYPE,
            workflow=LINES_WORKFLOW_SHIP,
        )

    def _validate_record(self) -> None:
        self._require_record_type()
        _uuid(self._record.get("model_ship"), field="Line.Annotation.model_ship")
        _validate_editions(self.editions, field="Line.Annotation.editions")
        if not self.editions:
            raise DiagramModelError("Line.Annotation must contain an edition")
        for index, edition in enumerate(self.editions):
            _validate_line_annotation_edition(
                edition, field=f"Line.Annotation.editions[{index}]"
            )

    @property
    def model_ship(self) -> str:
        return _uuid(self._record.get("model_ship"), field="Line.Annotation.model_ship")

    @property
    def editions(self) -> tuple[JsonObject, ...]:
        return tuple(
            _object(item, field="Line.Annotation.editions[]")
            for item in _array(
                self._record.get("editions", []), field="Line.Annotation.editions"
            )
        )

    @property
    def current_edition(self) -> JsonObject:
        return self.editions[-1]

    @property
    def current_edition_id(self) -> str:
        return _edition_id(self.current_edition)

    @property
    def arguments(self) -> tuple[DiagramArgumentReferenceInterface, ...]:
        return tuple(
            DiagramArgumentReferenceInterface.model_validate(item)
            for item in _array(
                self.current_edition.get("arguments", []),
                field="Line.Annotation.Edition.arguments",
            )
        )

    @property
    def text(self) -> str:
        return _string(
            _object(
                self.current_edition.get("data", {}),
                field="Line.Annotation.Edition.data",
            ).get("text"),
            field="Line.Annotation.Edition.data.text",
        )

    @property
    def has_producer(self) -> bool:
        return self.current_edition.get("producer") is not None

    @property
    def producer(self) -> ChatlasTurnReferenceInterface:
        return ChatlasTurnReferenceInterface.model_validate(
            self.current_edition.get("producer")
        )

    @property
    def support(self) -> tuple[SupportMemberInterface, ...]:
        return _support_members(self.current_edition.get("support", []))

    @property
    def gates(self) -> tuple[VerbatimGate, ...]:
        return _verbatim_gates(self.current_edition.get("gates", []))

    @property
    def retained_assertions(self) -> tuple[JsonObject, ...]:
        return tuple(
            _object(item, field="Line.Annotation.Edition.assertions[]")
            for item in _array(
                self.current_edition.get("assertions", []),
                field="Line.Annotation.Edition.assertions",
            )
        )

    def score_vector(self) -> JsonObject:
        value = self.current_edition.get(
            "score_vector", self._record.get("score_vector", {})
        )
        return value if isinstance(value, dict) else {}

    def references(self, identity: str) -> bool:
        _uuid(identity, field="Argument.Reference.id")
        return any(
            reference.id == identity
            for edition in self.editions
            for reference in _line_annotation_arguments(edition)
        )

    def render_support(self, evidence: ChatlasEvidence) -> list[JsonObject]:
        return [evidence.render_member(item) for item in self.support]

    def model_location(self) -> tuple[str, str]:
        return self.model_ship, "model_ship"

    def type_assertions(self) -> tuple[JsonObject, ...]:
        assertions: tuple[JsonObject, ...] = (
            {"type": "Line.Continuity.Assertion"},
            {"type": "Argument.Context.Assertion"},
            {"type": "Model.Scope.Assertion"},
            *self.retained_assertions,
        )
        if self.gates:
            assertions += tuple({"type": kind} for kind in VERBATIM_GATE_ASSERTIONS)
        return tuple(
            {assertion["type"]: assertion for assertion in assertions}.values()
        )

    def ships(self) -> tuple[Ship, ...]:
        return (
            *super(LineAnnotationRecord, self).ships(),
            Ship(self.id),
            Ship(self.model_ship),
            *(
                Ship(reference.id)
                for reference in self.arguments
                if reference.kind == "ship"
            ),
        )

    def type_findings(
        self,
        *,
        path: str,
        evidence: ChatlasEvidence | None,
    ) -> tuple[Finding, ...]:
        findings: list[Finding] = []
        namespace = self.namespace
        for index, reference in enumerate(self.arguments):
            if reference.namespace_id != namespace.id:
                continue
            if not namespace.resolves_argument(reference):
                findings.append(
                    Finding(
                        "line-annotation-argument-unresolved",
                        f"{path}.editions[-1].arguments[{index}]",
                        (
                            "Line.Annotation argument does not resolve in its "
                            f"Namespace: {reference.kind} {reference.id}."
                        ),
                    )
                )
        if self.support:
            if not self.has_producer:
                findings.append(
                    Finding(
                        "line-annotation-producer-missing",
                        f"{path}.editions[-1].producer",
                        "Supported Line.Annotation edition has no producer Turn.",
                    )
                )
            elif evidence is not None:
                findings.extend(evidence.check(self, path=f"{path}.editions[-1]"))
            findings.append(
                Finding(
                    "archive-grounding-unassessable",
                    path,
                    "Chatlas-to-Archive grounding is not yet mechanically assessable.",
                )
            )
        return tuple(findings)


class LineEditionRecord(UserTouchedAnnotation):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('075a399c-4285-4cc2-b6f2-d0c315d4a137'),
            name=LINE_EDITION_TYPE,
            workflow=LINES_WORKFLOW_SHIP,
        )

    def _validate_record(self) -> None:
        self._require_record_type()
        DiagramLocationInterface.model_validate(self._record.get("location"))
        _string(
            _object(self._record.get("data", {}), field="data").get("text"),
            field="data.text",
        )
        _verbatim_gates(self._record.get("gates", []))
        self.host
        self.authorization_gates

    @property
    def location(self) -> DiagramLocationInterface:
        return DiagramLocationInterface.model_validate(self._record.get("location"))

    @property
    def text(self) -> str:
        return _string(
            _object(self._record.get("data", {}), field="data").get("text"),
            field="data.text",
        )

    @property
    def gates(self) -> tuple[VerbatimGate, ...]:
        return _verbatim_gates(self._record.get("gates", []))

    @property
    def line_type(self) -> str | None:
        value = self._record.get("line_type")
        return _string(value, field="line_type") if value is not None else None

    @property
    def host(self) -> DiagramHostReferenceInterface:
        return _record_host(self._record, self.location.model_ship)

    @property
    def authorization_gates(self) -> tuple[str, ...]:
        return _authorization_gate_ids(self._record)

    def ships(self) -> tuple[Ship, ...]:
        return (
            *super(LineEditionRecord, self).ships(),
            *_location_ships(self.location),
        )

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


class BlockEditionRecord(TypedAnnotation):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('81ca3e71-1432-48af-afa5-2446042a40f9'),
            name=BLOCK_EDITION_TYPE,
            workflow=LINES_WORKFLOW_SHIP,
        )

    def _validate_record(self) -> None:
        self._require_record_type()
        DiagramBlockLocationInterface.model_validate(self._record.get("location"))
        _string(
            _object(self._record.get("data", {}), field="data").get("label"),
            field="data.label",
        )
        self.host
        self.authorization_gates

    @property
    def location(self) -> DiagramBlockLocationInterface:
        return DiagramBlockLocationInterface.model_validate(self._record.get("location"))

    @property
    def label(self) -> str:
        return _string(
            _object(self._record.get("data", {}), field="data").get("label"),
            field="data.label",
        )

    @property
    def block_type(self) -> str | None:
        value = self._record.get("block_type")
        return _string(value, field="block_type") if value is not None else None

    @property
    def host(self) -> DiagramHostReferenceInterface:
        return _record_host(self._record, self.location.model_ship)

    @property
    def authorization_gates(self) -> tuple[str, ...]:
        return _authorization_gate_ids(self._record)

    def ships(self) -> tuple[Ship, ...]:
        return (
            *super(BlockEditionRecord, self).ships(),
            *_location_ships(self.location),
        )

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


class CollectionEditionRecord(TypedAnnotation):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('fa0413e9-88e6-4b8b-8606-5d3ef397ea61'),
            name=COLLECTION_EDITION_TYPE,
            workflow=LINES_WORKFLOW_SHIP,
        )

    def _validate_record(self) -> None:
        self._require_record_type()
        _uuid(self._record.get("model_ship"), field="Collection.Edition.model_ship")
        _uuid(
            self._record.get("collection_ship"),
            field="Collection.Edition.collection_ship",
        )
        _string(self._record.get("collection_type"), field="collection_type")
        _string(
            _object(self._record.get("data", {}), field="data").get("label"),
            field="data.label",
        )
        self.host
        self.references
        self.authorization_gates

    @property
    def model_ship(self) -> str:
        return _uuid(self._record.get("model_ship"), field="model_ship")

    @property
    def collection_ship(self) -> str:
        return _uuid(self._record.get("collection_ship"), field="collection_ship")

    @property
    def collection_type(self) -> str:
        return _string(self._record.get("collection_type"), field="collection_type")

    @property
    def label(self) -> str:
        return _string(
            _object(self._record.get("data", {}), field="data").get("label"),
            field="data.label",
        )

    @property
    def data(self) -> JsonObject:
        return _object(self._record.get("data", {}), field="data")

    @property
    def host(self) -> DiagramHostReferenceInterface:
        return _record_host(self._record, self.model_ship)

    @property
    def references(self) -> tuple[DiagramArgumentReferenceInterface, ...]:
        return tuple(
            DiagramArgumentReferenceInterface.model_validate(item)
            for item in _array(self._record.get("references", []), field="references")
        )

    @property
    def authorization_gates(self) -> tuple[str, ...]:
        return _authorization_gate_ids(self._record)

    def ships(self) -> tuple[Ship, ...]:
        return (
            *super(CollectionEditionRecord, self).ships(),
            Ship(self.model_ship),
            Ship(self.collection_ship),
        )

    def model_location(self) -> tuple[str, str]:
        return self.model_ship, "model_ship"

    def type_assertions(self) -> tuple[JsonObject, ...]:
        return (
            {"type": "Collection.Continuity.Assertion"},
            {"type": "Collection.Type.Conformance.Assertion"},
            {"type": "Model.Scope.Assertion"},
        )

    def contribute(self, projector: DiagramProjectionBuilder) -> None:
        projector.add_collection_edition(self)


class BlockTypeAnnotation(TypedAnnotation):
    """Assigns an Object.Type to an existing Block without adding content."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('cbd91ead-be95-4679-b94a-ac16d351dcc9'),
            name=BLOCK_TYPE_ANNOTATION_TYPE,
            workflow=LINES_WORKFLOW_SHIP,
        )

    def _validate_record(self) -> None:
        self._require_record_type()
        DiagramBlockLocationInterface.model_validate(self._record.get("location"))
        _string(self._record.get("block_type"), field="block_type")

    @property
    def location(self) -> DiagramBlockLocationInterface:
        return DiagramBlockLocationInterface.model_validate(self._record.get("location"))

    @property
    def block_type(self) -> str:
        return _string(self._record.get("block_type"), field="block_type")

    def ships(self) -> tuple[Ship, ...]:
        return (
            *super(BlockTypeAnnotation, self).ships(),
            *_location_ships(self.location),
        )

    def model_location(self) -> tuple[str, str]:
        return self.location.model_ship, "location.model_ship"

    def type_assertions(self) -> tuple[JsonObject, ...]:
        return ({"type": "Block.Type.Conformance.Assertion"},)

    def contribute(self, projector: DiagramProjectionBuilder) -> None:
        projector.add_block_annotation(self)


class LineSupportAnnotation(UserTouchedAnnotation):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('d8215a2f-0cdb-4940-95c9-fd071a9d7735'),
            name=LINE_SUPPORT_ANNOTATION_TYPE,
            workflow=LINES_WORKFLOW_SHIP,
        )

    def _validate_record(self) -> None:
        self._require_record_type()
        DiagramLocationInterface.model_validate(self._record.get("location"))

    @property
    def location(self) -> DiagramLocationInterface:
        return DiagramLocationInterface.model_validate(self._record.get("location"))

    def ships(self) -> tuple[Ship, ...]:
        return (
            *super(LineSupportAnnotation, self).ships(),
            *_location_ships(self.location),
        )

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


class LineTypeAnnotation(TypedAnnotation):
    """Assigns an Object.Type to an existing Line without adding wording."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('30013ead-fec7-4584-9b03-4de96c941f58'),
            name=LINE_TYPE_ANNOTATION_TYPE,
            workflow=LINES_WORKFLOW_SHIP,
        )

    def _validate_record(self) -> None:
        self._require_record_type()
        DiagramLocationInterface.model_validate(self._record.get("location"))
        _string(self._record.get("line_type"), field="line_type")

    @property
    def location(self) -> DiagramLocationInterface:
        return DiagramLocationInterface.model_validate(self._record.get("location"))

    @property
    def line_type(self) -> str:
        return _string(self._record.get("line_type"), field="line_type")

    def ships(self) -> tuple[Ship, ...]:
        return (
            *super(LineTypeAnnotation, self).ships(),
            *_location_ships(self.location),
        )

    def model_location(self) -> tuple[str, str]:
        return self.location.model_ship, "location.model_ship"

    def type_assertions(self) -> tuple[JsonObject, ...]:
        return ({"type": "Line.Type.Conformance.Assertion"},)

    def contribute(self, projector: DiagramProjectionBuilder) -> None:
        projector.add_line_annotation(self)


class LineGateAnnotation(TypedAnnotation):
    """Adds review evidence to one immutable Line edition."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('3bf237e7-0251-4106-8166-dfbba1046b7c'),
            name=LINE_GATE_ANNOTATION_TYPE,
            workflow=LINES_WORKFLOW_SHIP,
        )

    def _validate_record(self) -> None:
        self._require_record_type()
        _uuid(
            self._record.get("target_edition"),
            field="Line.Gate.Annotation.target_edition",
        )
        gates = _verbatim_gates(self._record.get("gates"))
        if len(gates) != 1:
            raise DiagramModelError(
                "Line.Gate.Annotation must contain exactly one Gate"
            )

    @property
    def target_edition_id(self) -> str:
        return _uuid(
            self._record.get("target_edition"),
            field="Line.Gate.Annotation.target_edition",
        )

    @property
    def gates(self) -> tuple[VerbatimGate, ...]:
        return _verbatim_gates(self._record.get("gates"))

    @property
    def target(self) -> LineEditionRecord:
        annotation = self.namespace.edition(self.target_edition_id)
        typed = annotation.specialize()
        if not isinstance(typed, LineEditionRecord):
            raise DiagramModelError(
                "Line.Gate.Annotation target is not a Diagram.Line.Ship edition"
            )
        return typed

    @property
    def location(self) -> DiagramLocationInterface:
        return self.target.location

    def model_location(self) -> tuple[str, str]:
        return self.location.model_ship, "target_edition"

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


CHATLAS_INDEX_EDITION_RECORD_TYPES: tuple[type[TypedAnnotation], ...] = (
    ModelEditionRecord,
    BlockEditionRecord,
    LineEditionRecord,
    CollectionEditionRecord,
)


def _line_annotation_editions(record: Mapping[str, Any]) -> tuple[JsonObject, ...]:
    return tuple(
        _object(item, field="Line.Annotation.editions[]")
        for item in _array(record.get("editions", []), field="Line.Annotation.editions")
    )


def _line_annotation_arguments(
    edition: Mapping[str, Any],
) -> tuple[DiagramArgumentReferenceInterface, ...]:
    return tuple(
        DiagramArgumentReferenceInterface.model_validate(item)
        for item in _array(
            edition.get("arguments", []),
            field="Line.Annotation.Edition.arguments",
        )
    )


def _validate_line_annotation_edition(
    edition: Mapping[str, Any], *, field: str
) -> None:
    _edition_id(edition)
    arguments = _line_annotation_arguments(edition)
    if not arguments:
        raise DiagramModelError(f"{field}.arguments must not be empty")
    keys = tuple((item.namespace_id, item.kind, item.id) for item in arguments)
    if len(keys) != len(set(keys)):
        raise DiagramModelError(f"{field}.arguments contains duplicates")
    _string(
        _object(edition.get("data", {}), field=f"{field}.data").get("text"),
        field=f"{field}.data.text",
    )
    if edition.get("producer") is not None:
        ChatlasTurnReferenceInterface.model_validate(edition.get("producer"))
    if edition.get("support") is not None:
        _support_members(edition.get("support"))
    _verbatim_gates(edition.get("gates", []))
    for index, assertion in enumerate(
        _array(edition.get("assertions", []), field=f"{field}.assertions")
    ):
        _string(
            _object(assertion, field=f"{field}.assertions[{index}]").get("type"),
            field=f"{field}.assertions[{index}].type",
        )
    score_vector = edition.get("score_vector")
    if score_vector is not None:
        _object(score_vector, field=f"{field}.score_vector")
