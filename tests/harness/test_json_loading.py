from __future__ import annotations

from io import StringIO

import pytest

from tarav.harness import (
    InvalidRecordJSON,
    RecordTypeMismatch,
    TaravRecord,
    TypeRegistry,
    TypeShip,
)


class RegisteredRecord(TaravRecord):
    type_ship = TypeShip("12345678-1234-4234-8234-1234567890ab")
    type_name = "Registered.Record"


class SpecializedRecord(RegisteredRecord):
    type_ship = TypeShip("abcdefab-cdef-4abc-8def-abcdefabcdef")
    type_name = "Specialized.Record"


class OtherRecord(TaravRecord):
    type_ship = TypeShip("fedcbafe-dcba-4fed-8cba-fedcbafedcba")
    type_name = "Other.Record"


@pytest.fixture
def registry() -> TypeRegistry[TaravRecord]:
    return TypeRegistry(TaravRecord, (RegisteredRecord, OtherRecord))


def record_json() -> StringIO:
    return StringIO('{"type": "Registered.Record", "value": 7}')


def test_registry_json_load_constructs_exact_registered_class(
    registry: TypeRegistry[TaravRecord],
) -> None:
    loaded = registry.json_load(record_json())

    assert type(loaded) is RegisteredRecord
    assert loaded.record == {"type": "Registered.Record", "value": 7}


def test_registered_class_json_load_constructs_calling_class(
    registry: TypeRegistry[TaravRecord],
) -> None:
    loaded = RegisteredRecord.json_load(record_json(), registry=registry)

    assert type(loaded) is RegisteredRecord


def test_subclass_json_load_specializes_registered_authority(
    registry: TypeRegistry[TaravRecord],
) -> None:
    loaded = SpecializedRecord.json_load(record_json(), registry=registry)

    assert type(loaded) is SpecializedRecord
    assert loaded.record["value"] == 7


def test_class_json_load_rejects_unrelated_or_unregistered_ancestor(
    registry: TypeRegistry[TaravRecord],
) -> None:
    with pytest.raises(RecordTypeMismatch):
        OtherRecord.json_load(record_json(), registry=registry)

    with pytest.raises(RecordTypeMismatch):
        TaravRecord.json_load(record_json(), registry=registry)


def test_json_load_requires_a_root_object(
    registry: TypeRegistry[TaravRecord],
) -> None:
    with pytest.raises(InvalidRecordJSON):
        registry.json_load(StringIO("[]"))


def test_tarav_record_is_not_an_opaque_wrapper() -> None:
    with pytest.raises(TypeError, match="not an opaque Record wrapper"):
        TaravRecord({"unregistered": True})
