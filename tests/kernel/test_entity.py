from __future__ import annotations

from tarav.l0.kernel import TaravClass, entity


import pytest
from pydantic import ValidationError

from tarav.l0.kernel import (
    DirectoryRecord,
    FileRecord,
    InvalidRecordJSON,
    Ship,
    TaravEntity,
    TypeShip,
)

ENTITY_ID = "11c94ee8-b6f9-48e5-8a66-8518fce3076b"


class ExampleEntity(TaravEntity):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('88753ba4-c804-4c16-89ae-c66f55d94265'),
            name='Example.Entity',
        )


def test_entity_keeps_json_identity_and_exposes_a_typed_ship() -> None:
    subject = ExampleEntity.from_record({"id": ENTITY_ID, "label": "example"})

    assert subject._record == {"id": ENTITY_ID, "label": "example"}
    assert type(subject.id) is Ship
    assert subject.id == Ship(ENTITY_ID)
    assert not hasattr(subject, "record_data")
    assert subject.to_record() == {"id": ENTITY_ID, "label": "example"}
    assert ExampleEntity.from_record(subject.to_record()).id == subject.id
    assert subject.ships() == (entity(ExampleEntity).id, Ship(ENTITY_ID))


def test_runtime_entity_projects_its_explicit_identity() -> None:
    subject = ExampleEntity(Ship(ENTITY_ID))

    assert subject.id == Ship(ENTITY_ID)
    assert subject.to_record() == {
        "type": "Example.Entity",
        "id": ENTITY_ID,
    }
    with pytest.raises(AttributeError):
        subject.id = Ship("3ccdb900-c788-4496-9fc6-9e966c606c83")


def test_entity_requires_a_json_uuid_string_identity() -> None:
    with pytest.raises(ValidationError):
        ExampleEntity.from_record({})
    with pytest.raises(ValidationError):
        ExampleEntity.from_record({"id": "not-a-uuid"})
    with pytest.raises(InvalidRecordJSON, match="transform"):
        ExampleEntity.from_record({"id": ENTITY_ID.replace("-", "")})
    with pytest.raises(InvalidRecordJSON):
        ExampleEntity.from_record({"id": Ship(ENTITY_ID)})


@pytest.mark.parametrize("storage_base", [FileRecord, DirectoryRecord])
def test_entity_identity_composes_with_record_storage_shapes(storage_base) -> None:
    class StoredEntity(TaravEntity, storage_base):
        @classmethod
        def class_entity(cls) -> TaravClass:
            return TaravClass(
                target=cls,
                id=TypeShip("63c91d8e-d58a-49a2-9ee9-49666e2120ad"),
                name=f'Example.{storage_base.__name__}.Entity',
            )

        class RecordInterface(
            TaravEntity.RecordInterface,
            storage_base.RecordInterface,
        ):
            pass

    subject = StoredEntity.from_record({"id": ENTITY_ID})

    assert StoredEntity.preserves_parent_record_interface()
    assert isinstance(subject, TaravEntity)
    assert isinstance(subject, storage_base)
    assert subject.ships() == (entity(StoredEntity).id, Ship(ENTITY_ID))
