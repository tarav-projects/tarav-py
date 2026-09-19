from __future__ import annotations

from io import StringIO

import pytest

from tarav.harness import (
    InvalidRecordJSON,
    RecordTypeMismatch,
    TaravObject,
    TypeRegistry,
    TypeShip,
)


class RegisteredRecord(TaravObject):
    type_ship = TypeShip("12345678-1234-4234-8234-1234567890ab")
    type_name = "Registered.Record"


class SpecializedRecord(RegisteredRecord):
    type_ship = TypeShip("abcdefab-cdef-4abc-8def-abcdefabcdef")
    type_name = "Specialized.Record"


class OtherRecord(TaravObject):
    type_ship = TypeShip("fedcbafe-dcba-4fed-8cba-fedcbafedcba")
    type_name = "Other.Record"


class RoutedRecord(TaravObject):
    type_ship = TypeShip("7890abcd-1234-4567-890a-bcdef1234567")
    type_name = "Routed.Record"

    @classmethod
    def from_json(cls, value):
        result = super().from_json(value)
        result.constructed_by = "from_json"
        return result


@pytest.fixture
def registry() -> TypeRegistry[TaravObject]:
    return TypeRegistry(TaravObject, (RegisteredRecord, OtherRecord))


def record_json() -> StringIO:
    return StringIO('{"type": "Registered.Record", "value": 7}')


def test_registry_json_load_constructs_exact_registered_class(
    registry: TypeRegistry[TaravObject],
) -> None:
    loaded = registry.json_load(record_json())

    assert type(loaded) is RegisteredRecord
    assert loaded.record == {"type": "Registered.Record", "value": 7}


def test_registry_from_json_routes_through_selected_class(
    registry: TypeRegistry[TaravObject],
) -> None:
    loaded = registry.from_json({"type": "Registered.Record", "value": 7})

    assert type(loaded) is RegisteredRecord
    assert loaded.to_json() == {"type": "Registered.Record", "value": 7}
    assert loaded.to_json() is not loaded.record


def test_registry_construction_calls_the_selected_class_from_json() -> None:
    registry = TypeRegistry(TaravObject, (RoutedRecord,))

    loaded = registry.from_json({"type": "Routed.Record"})

    assert loaded.constructed_by == "from_json"


def test_registered_class_json_load_constructs_calling_class(
    registry: TypeRegistry[TaravObject],
) -> None:
    loaded = RegisteredRecord.json_load(record_json(), registry=registry)

    assert type(loaded) is RegisteredRecord


def test_subclass_json_load_specializes_registered_authority(
    registry: TypeRegistry[TaravObject],
) -> None:
    loaded = SpecializedRecord.json_load(record_json(), registry=registry)

    assert type(loaded) is SpecializedRecord
    assert loaded.record["value"] == 7


def test_class_json_load_rejects_unrelated_or_unregistered_ancestor(
    registry: TypeRegistry[TaravObject],
) -> None:
    with pytest.raises(RecordTypeMismatch):
        OtherRecord.json_load(record_json(), registry=registry)

    with pytest.raises(RecordTypeMismatch):
        TaravObject.json_load(record_json(), registry=registry)


def test_json_load_requires_a_root_object(
    registry: TypeRegistry[TaravObject],
) -> None:
    with pytest.raises(InvalidRecordJSON):
        registry.json_load(StringIO("[]"))


def test_tarav_object_is_not_an_opaque_wrapper() -> None:
    with pytest.raises(TypeError, match="not an opaque JSON wrapper"):
        TaravObject({"unregistered": True})
