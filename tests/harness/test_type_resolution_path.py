from __future__ import annotations

import pytest

from tarav.harness import (
    TYPE_RESOLUTION_PATH,
    InvalidRecordType,
    RecordTypeLocation,
    TaravRecord,
    TypeRegistry,
    TypeShip,
    UnknownRecordType,
    locate_record_type,
)

SHIP = "6e2b1d40-9a73-4c58-8b12-7f0d3a4e5c61"
OTHER = "7f3c2e51-ab84-4d69-9c23-80e1b4f5d672"


class Located(TaravRecord):
    type_ship = TypeShip(SHIP)
    type_name = "Located.Record"


@pytest.fixture
def registry() -> TypeRegistry[TaravRecord]:
    return TypeRegistry(TaravRecord, (Located,))


def test_the_resolution_path_is_the_reserved_namespace_then_root_type() -> None:
    assert TYPE_RESOLUTION_PATH == (("__tarav__", "type"), ("type",))


def test_the_reserved_namespace_wins_over_root_type(
    registry: TypeRegistry[TaravRecord],
) -> None:
    record = {
        "__tarav__": {"type": "Located.Record"},
        "type": "an application field of its own",
    }

    assert locate_record_type(record) == RecordTypeLocation(
        ("__tarav__", "type"), "Located.Record"
    )
    assert registry.resolve(record) is Located


def test_root_type_is_used_when_the_reserved_namespace_omits_it(
    registry: TypeRegistry[TaravRecord],
) -> None:
    assert registry.resolve({"__tarav__": {}, "type": "Located.Record"}) is Located
    assert registry.resolve({"type": "Located.Record"}) is Located


def test_a_present_but_unusable_reference_is_never_shadowed(
    registry: TypeRegistry[TaravRecord],
) -> None:
    for shadowing in ({"type": None}, {"type": ""}, {"type": 7}):
        record = {"__tarav__": shadowing, "type": "Located.Record"}

        assert locate_record_type(record).path == ("__tarav__", "type")
        with pytest.raises(InvalidRecordType, match="__tarav__.type"):
            registry.resolve(record)


def test_a_record_with_no_reference_names_every_path(
    registry: TypeRegistry[TaravRecord],
) -> None:
    assert locate_record_type({}) is None
    with pytest.raises(InvalidRecordType, match="__tarav__.type, type"):
        registry.resolve({})

    assert registry.record_findings({})[0].code == "record-type-component-missing"


def test_an_unregistered_type_reports_the_path_that_supplied_it(
    registry: TypeRegistry[TaravRecord],
) -> None:
    with pytest.raises(UnknownRecordType, match=r"at __tarav__\.type"):
        registry.resolve({"__tarav__": {"type": {"uuid": OTHER, "label": "Absent"}}})
    with pytest.raises(UnknownRecordType, match=r"at type"):
        registry.resolve({"type": "Absent.Record"})


def test_record_findings_report_against_the_selected_path(
    registry: TypeRegistry[TaravRecord],
) -> None:
    drifted = {"__tarav__": {"type": {"uuid": SHIP, "label": "Renamed.Record"}}}
    (finding,) = registry.record_findings(drifted)

    assert finding.code == "record-type-label-conflict"
    assert finding.field == "__tarav__.type.label"


def test_the_resolution_path_is_not_configurable(
    registry: TypeRegistry[TaravRecord],
) -> None:
    class DeclaresItsOwnPath(TaravRecord):
        type_ship = TypeShip(OTHER)
        type_name = "Declares.Own.Path"
        type_resolution_path = (("kind",),)

    scoped: TypeRegistry[TaravRecord] = TypeRegistry(
        TaravRecord, (DeclaresItsOwnPath,)
    )

    with pytest.raises(InvalidRecordType):
        scoped.resolve({"kind": "Declares.Own.Path"})
    assert scoped.resolve({"type": "Declares.Own.Path"}) is DeclaresItsOwnPath
