from __future__ import annotations

from tarav.l0.kernel import TaravClass

import json
from typing import ClassVar

import pytest
from pydantic import BaseModel

from tarav.l0.kernel import (
    InvalidRecordJSON,
    RecordTypeMismatch,
    TaravObject,
    TypeRegistry,
    TypeShip,
    entity,
)


class RegisteredRecord(TaravObject):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('12345678-1234-4234-8234-1234567890ab'),
            name='Registered.Record',
        )


class SpecializedRecord(RegisteredRecord):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('abcdefab-cdef-4abc-8def-abcdefabcdef'),
            name='Specialized.Record',
        )


class OtherRecord(TaravObject):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('fedcbafe-dcba-4fed-8cba-fedcbafedcba'),
            name='Other.Record',
        )


class RoutedRecord(TaravObject):
    construction_count: ClassVar[int] = 0

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('7890abcd-1234-4567-890a-bcdef1234567'),
            name='Routed.Record',
        )

    @classmethod
    def _from_record(cls, record_data: BaseModel):
        cls.construction_count += 1
        result = super()._from_record(record_data)
        result.constructed_by = "_from_record"
        return result


@pytest.fixture
def registry() -> TypeRegistry[TaravObject]:
    return TypeRegistry(TaravObject, (RegisteredRecord, OtherRecord))


def test_registry_path_load_constructs_exact_registered_class(
    registry: TypeRegistry[TaravObject], tmp_path
) -> None:
    path = tmp_path / "record.json"
    path.write_text('{"type": "Registered.Record", "value": 7}')
    loaded = registry.load(path)

    assert type(loaded) is RegisteredRecord
    assert loaded._record == {"type": "Registered.Record", "value": 7}


def test_registry_from_record_routes_through_selected_class(
    registry: TypeRegistry[TaravObject],
) -> None:
    loaded = registry.from_record({"type": "Registered.Record", "value": 7})

    assert type(loaded) is RegisteredRecord
    assert loaded.to_record() == {"type": "Registered.Record", "value": 7}
    assert loaded.to_record() is not loaded._record


def test_registry_construction_calls_the_selected_class_hook() -> None:
    registry = TypeRegistry(TaravObject, (RoutedRecord,))
    RoutedRecord.construction_count = 0

    loaded = registry.from_record({"type": "Routed.Record"})

    assert loaded.constructed_by == "_from_record"
    assert RoutedRecord.construction_count == 1


def test_expected_type_requires_the_exact_registered_class(
    tmp_path,
) -> None:
    registry = TypeRegistry(TaravObject, (SpecializedRecord,))
    path = tmp_path / "record.json"
    path.write_text(json.dumps({"type": "Specialized.Record", "value": 7}))

    with pytest.raises(RecordTypeMismatch, match="expected exact Type"):
        registry.load(path, expected_type=RegisteredRecord)

    loaded = registry.load(path, expected_type=SpecializedRecord)

    assert type(loaded) is SpecializedRecord
    assert loaded._record is not None
    assert loaded._record["value"] == 7


def test_expected_type_rejects_before_object_construction(tmp_path) -> None:
    registry = TypeRegistry(TaravObject, (RoutedRecord,))
    RoutedRecord.construction_count = 0
    path = tmp_path / "record.json"
    path.write_text('{"type":"Routed.Record"}')

    with pytest.raises(RecordTypeMismatch):
        registry.load(path, expected_type=OtherRecord)
    assert RoutedRecord.construction_count == 0


def test_direct_class_loading_rejects_a_child_type_before_construction() -> None:
    RoutedRecord.construction_count = 0

    with pytest.raises(RecordTypeMismatch, match="expected exact Type"):
        RegisteredRecord.from_record({"type": "Specialized.Record"})
    with pytest.raises(RecordTypeMismatch, match="expected exact Type"):
        RoutedRecord.from_record({"type": "Other.Record"})

    assert RoutedRecord.construction_count == 0


def test_direct_class_loading_uses_ship_authority_and_path_precedence() -> None:
    ship = str(entity(RegisteredRecord).id)
    drifted = {"type": {"uuid": ship, "label": "Renamed.Record"}}

    assert RegisteredRecord.from_record(drifted).to_record() == drifted
    with pytest.raises(RecordTypeMismatch):
        RegisteredRecord.from_record(
            {"type": {"uuid": str(entity(OtherRecord).id), "label": "Registered.Record"}}
        )
    with pytest.raises(RecordTypeMismatch, match="__tarav__.type"):
        RegisteredRecord.from_record(
            {"__tarav__": {"type": "Other.Record"}, "type": "Registered.Record"}
        )


def test_writing_rejects_a_record_that_identifies_another_type() -> None:
    loaded = RegisteredRecord.from_record({"type": "Registered.Record"})
    assert loaded._record is not None
    loaded._record["type"] = "Specialized.Record"

    with pytest.raises(RecordTypeMismatch, match="expected exact Type"):
        loaded.to_record()


def test_direct_class_loading_can_use_a_record_without_type_reference() -> None:
    loaded = RegisteredRecord.from_record({"value": 7})

    assert loaded.to_record() == {"value": 7}


def test_path_load_requires_a_root_object(
    registry: TypeRegistry[TaravObject], tmp_path
) -> None:
    path = tmp_path / "record.json"
    path.write_text("[]")

    with pytest.raises(InvalidRecordJSON):
        registry.load(path)


def test_tarav_object_is_not_an_opaque_wrapper() -> None:
    with pytest.raises(TypeError, match="not an opaque JSON wrapper"):
        TaravObject()
