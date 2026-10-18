from typing import Literal, Self

import pytest

from tarav.l0.kernel import (
    TaravClass,
    TaravObject,
    TaravTypeDeclarationError,
    TypeShip,
    entity,
)
from tarav.l3.runtime import create_runtime
from tarav.l0.kernel import LoadedRecord


class RuntimeProjection(TaravObject):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("8540991c-f4d2-4a8d-868d-03f40cc06c7c"),
            name="Test.RuntimeProjection",
        )

    class RecordInterface(TaravObject.RecordInterface):
        type: Literal["Test.RuntimeProjection"]
        value: int

    def __init__(self, value: int) -> None:
        super().__init__()
        self.value = value

    @classmethod
    def _from_record(cls, loaded: LoadedRecord) -> Self:
        return cls(loaded.data.value)

    def _to_record(self) -> dict[str, object]:
        return {"type": entity(type(self)).name, "value": self.value}


def test_registered_runtime_objects_round_trip_their_record_examples() -> None:
    registry = create_runtime().records

    for object_type in registry.record_types:
        example = object_type.records.record_example()
        first = registry.from_record(example)
        encoded = first.records.to_record()
        assert encoded == example, object_type.__name__
        second = registry.from_record(encoded)

        assert type(first) is object_type, object_type.__name__
        assert type(second) is object_type, object_type.__name__
        assert second.records.to_record() == encoded, object_type.__name__


def test_runtime_object_projects_state_without_a_loaded_record() -> None:
    subject = RuntimeProjection(7)

    assert not hasattr(subject, "_record")
    assert not hasattr(subject, "record")
    assert not hasattr(subject, "record_data")
    assert subject.records.to_record() == {"type": "Test.RuntimeProjection", "value": 7}


def test_loaded_record_is_input_material_not_the_objects_source_of_truth() -> None:
    supplied = {"type": "Test.RuntimeProjection", "value": 7}
    subject = RuntimeProjection.records.from_record(supplied)

    supplied["value"] = 99
    assert not hasattr(subject, "_record")
    assert subject.value == 7
    assert subject.records.to_record() == {"type": "Test.RuntimeProjection", "value": 7}


def test_default_projection_is_the_types_minimal_record() -> None:
    class Minimal(TaravObject):
        @classmethod
        def class_entity(cls) -> TaravClass:
            return TaravClass(
                target=cls,
                id=TypeShip("327fe3bd-206f-4d56-be52-2b07728982f6"),
                name="Test.Minimal",
            )

    subject = Minimal()

    assert not hasattr(subject, "_record")
    assert subject.records.to_record() == {"type": "Test.Minimal"}


def test_tarav_owns_the_public_record_loading_boundary() -> None:
    with pytest.raises(TaravTypeDeclarationError, match="selected Records namespace"):

        class InvalidLoader(TaravObject):
            @classmethod
            def class_entity(cls) -> TaravClass:
                return TaravClass(
                    target=cls,
                    id=TypeShip("6128b2f8-6e0a-4579-ac7c-2a66be5ea605"),
                    name="Test.InvalidLoader",
                )

            @classmethod
            def from_record(cls, value):
                return cls()


@pytest.mark.parametrize("name", ("to_record", "parse_record", "record_example"))
def test_record_extensions_must_use_the_selected_namespace(name: str) -> None:
    with pytest.raises(TaravTypeDeclarationError, match="selected Records namespace"):
        type(
            "InvalidRecordExtension",
            (TaravObject,),
            {
                "class_entity": classmethod(
                    lambda cls: TaravClass(
                        target=cls,
                        id=TypeShip("2ac0c5aa-d8fc-4df9-8fa8-9530aab571a4"),
                        name="Test.InvalidRecordExtension",
                    )
                ),
                name: lambda self, value=None: value,
            },
        )


def test_objects_project_their_state_not_their_loaded_record() -> None:
    # tarav.breadcrumb c3e31a009b49
    registry = create_runtime().records

    for object_type in registry.record_types:
        example = object_type.records.record_example()
        subject = registry.from_record(example)

        assert not hasattr(subject, "_record"), object_type.__name__
        assert subject.records.to_record() == example, object_type.__name__
