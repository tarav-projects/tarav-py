from tarav.l0.kernel import TaravClass


import pytest
from pydantic import BaseModel, ConfigDict, ValidationError

from tarav.l0.kernel import (
    InvalidRecordJSON,
    TaravObject,
    TypeRegistry,
    TypeShip,
    isrecordsubclass,
    issubrecord,
)


class A(TaravObject):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("110f8113-78c4-4d1e-a999-28f82d622ef7"),
            name='Example.A',
        )

    class RecordInterface(TaravObject.RecordInterface):
        name: str

    @classmethod
    def _from_record(cls, record_data: BaseModel):
        result = super()._from_record(record_data)
        result.name = record_data.name
        return result

    def label(self):
        return self.name


class B(A):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("b8b3688c-6ef9-4341-8097-7508b7d70a34"),
            name='Example.B',
        )

    class RecordInterface(A.RecordInterface):
        path: str


class C(B):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("e9609cce-622a-4e26-999b-69cc50179a7c"),
            name='Test.C',
        )


class D(A):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("7931ccb0-af96-441d-8d92-da74979d6bbc"),
            name='Example.D',
        )

    class RecordInterface(BaseModel):
        model_config = ConfigDict(extra="allow")
        title: str

    @classmethod
    def _from_record(cls, record_data: BaseModel):
        result = cls.__new__(cls)
        TaravObject.__init__(result)
        result.title = record_data.title
        return result

    def label(self):
        return self.title


def test_inherited_and_independent_representations():
    assert issubrecord(B, A)
    assert isrecordsubclass(B, A)
    assert issubrecord(A, A)
    assert isrecordsubclass(A, A)
    assert C.preserves_parent_record_interface()
    assert C.RecordInterface is B.RecordInterface
    assert not issubrecord(D, A)
    assert not isrecordsubclass(D, A)
    assert not D.preserves_parent_record_interface()
    assert not issubrecord(A, B)
    assert not isrecordsubclass(A, B)
    assert TaravObject.preserves_parent_record_interface()
    registry = TypeRegistry(TaravObject, (B, D))
    for value in (
        {"type": "Example.B", "name": "Calculator", "path": "calc.py"},
        {"type": "Example.D", "title": "Calculator"},
    ):
        obj = registry.from_record(value)
        assert obj.label() == "Calculator"
        assert obj.records.to_record() == value
    with pytest.raises(ValidationError):
        B.records.from_record({"path": "calc.py"})
    with pytest.raises(ValidationError):
        A.records.from_record({"name": 1})
    assert "name" in B.RecordInterface.model_json_schema()["required"]


def test_all_direct_tarav_parents():
    class Both(B, D):
        @classmethod
        def class_entity(cls) -> TaravClass:
            return TaravClass(
                target=cls,
                id=TypeShip("1f0775ea-4c32-45e4-abb1-832a57f1e292"),
                name='Test.Both',
            )

    assert not Both.preserves_parent_record_interface()
    assert isrecordsubclass(Both, B)

    class Combined(B, D):
        @classmethod
        def class_entity(cls) -> TaravClass:
            return TaravClass(
                target=cls,
                id=TypeShip("fd8057f2-b9da-42fc-9f96-17ab8d879227"),
                name='Test.Combined',
            )

        class RecordInterface(B.RecordInterface, D.RecordInterface):
            pass

    assert Combined.preserves_parent_record_interface()


def test_record_relationship_can_be_inspected_separately_from_behavior():
    class SharedRecord(D):
        @classmethod
        def class_entity(cls) -> TaravClass:
            return TaravClass(
                target=cls,
                id=TypeShip("a2547411-2b77-4fd5-9c36-ed021a7d9e11"),
                name='Test.SharedRecord',
            )

        RecordInterface = B.RecordInterface

    assert issubrecord(SharedRecord, B)
    assert not issubclass(SharedRecord, B)
    assert not isrecordsubclass(SharedRecord, B)

    for invalid in (None, object(), BaseModel):
        with pytest.raises(TypeError):
            issubrecord(B, invalid)
        with pytest.raises(TypeError):
            issubrecord(invalid, A)
        with pytest.raises(TypeError):
            isrecordsubclass(B, invalid)
        with pytest.raises(TypeError):
            isrecordsubclass(invalid, A)


def test_closed_child_accepts_inherited_fields_and_rejects_extras():
    class Closed(B):
        @classmethod
        def class_entity(cls) -> TaravClass:
            return TaravClass(
                target=cls,
                id=TypeShip("5ea9cb2e-e5d3-40a5-a106-6135385610d4"),
                name='Test.Closed',
            )

        class RecordInterface(B.RecordInterface):
            model_config = ConfigDict(extra="forbid")

    value = {"name": "Calculator", "path": "calc.py"}
    assert Closed.records.from_record(value).records.to_record() == value
    with pytest.raises(ValidationError):
        Closed.records.from_record({**value, "unexpected": True})


def test_no_coercion_discard_or_default_insertion():
    class Defaults(A):
        @classmethod
        def class_entity(cls) -> TaravClass:
            return TaravClass(
                target=cls,
                id=TypeShip("46e8cede-95d6-4c1e-9651-e67e95a672a4"),
                name='Test.Defaults',
            )

        class RecordInterface(A.RecordInterface):
            count: int = 1

    obj = Defaults.records.from_record({"name": "x", "unknown": [1]})
    assert Defaults.records.parse_record(obj.records.to_record()).count == 1
    assert obj.records.to_record() == {"name": "x", "unknown": [1]}
    with pytest.raises(InvalidRecordJSON):
        A.records.from_record({"name": "x", "hints": {1: "a", "1": "b"}})

    assert obj._record is not None
    obj._record["name"] = 1
    with pytest.raises(ValidationError):
        obj.records.to_record()
