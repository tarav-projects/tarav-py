from __future__ import annotations

import pytest

from tarav.harness import (
    InvalidRecordType,
    RecordTypeReference,
    TaravRecordType,
    TypeReferenceFinding,
    TypeRegistry,
    TypeShip,
    UnknownRecordType,
)

SHIP = "7a2c9e10-51b4-4a2f-9d31-6b8e0f4c2a77"
UNKNOWN_SHIP = "0b6f4d21-9c3a-4e58-8f10-2d7a5b3c9e44"


class ReferencedRecord(TaravRecordType):
    type_ship = TypeShip(SHIP)
    type_name = "Referenced.Record"


@pytest.fixture
def registry() -> TypeRegistry[TaravRecordType]:
    return TypeRegistry(TaravRecordType, (ReferencedRecord,))


def test_structured_and_legacy_references_resolve_to_the_same_class(
    registry: TypeRegistry[TaravRecordType],
) -> None:
    structured = {"type": {"uuid": SHIP, "label": "Referenced.Record"}}
    legacy = {"type": "Referenced.Record"}

    assert registry.resolve(structured) is ReferencedRecord
    assert registry.resolve(legacy) is ReferencedRecord


def test_a_known_type_ship_resolves_independently_of_label_drift(
    registry: TypeRegistry[TaravRecordType],
) -> None:
    drifted = {"type": {"uuid": SHIP, "label": "Renamed.Record"}}

    assert registry.resolve(drifted) is ReferencedRecord
    assert registry.record_findings(drifted) == (
        TypeReferenceFinding(
            "record-type-label-conflict",
            "type.label",
            f"Record Type Ship {SHIP} resolves to Referenced.Record, "
            "not Renamed.Record.",
        ),
    )


def test_an_unknown_ship_never_falls_back_to_a_registered_label(
    registry: TypeRegistry[TaravRecordType],
) -> None:
    record = {"type": {"uuid": UNKNOWN_SHIP, "label": "Referenced.Record"}}

    with pytest.raises(UnknownRecordType):
        registry.resolve(record)
    codes = tuple(finding.code for finding in registry.record_findings(record))
    assert codes == ("record-type-ship-unknown",)


def test_missing_and_unknown_reference_components_are_reported(
    registry: TypeRegistry[TaravRecordType],
) -> None:
    def codes(record: dict[str, object]) -> tuple[str, ...]:
        return tuple(finding.code for finding in registry.record_findings(record))

    assert codes({}) == ("record-type-component-missing",)
    assert codes({"type": {"id": "not-a-uuid"}}) == ("record-type-component-missing",)
    assert codes({"type": {"uuid": SHIP}}) == ("record-type-component-missing",)
    assert codes({"type": "Absent.Record"}) == ("record-type-label-unknown",)
    assert codes({"type": {"uuid": SHIP, "label": "Referenced.Record"}}) == ()
    assert codes({"type": "Referenced.Record"}) == ()

    with pytest.raises(InvalidRecordType):
        registry.resolve({"type": {"label": ""}})


def test_reference_parsing_keeps_usable_components_only() -> None:
    assert RecordTypeReference.parse("Referenced.Record") == RecordTypeReference(
        None, "Referenced.Record"
    )
    assert RecordTypeReference.parse({"uuid": SHIP, "label": 4}) == RecordTypeReference(
        TypeShip(SHIP), None
    )
    assert RecordTypeReference.parse(7) == RecordTypeReference()
