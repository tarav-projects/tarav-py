from uuid import uuid4

import pytest
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from tarav.harness import (
    InvalidRecordJSON,
    TaravObject,
    TypeRegistry,
    TypeShip,
    isrecordsubclass,
    issubrecord,
)


class A(TaravObject):
    type_name = 'Example.A'
    type_ship = TypeShip(str(uuid4()))

    class RecordInterface(TaravObject.RecordInterface):
        name: str

    def label(self):
        return self.record_data.name


class B(A):
    type_name = 'Example.B'
    type_ship = TypeShip(str(uuid4()))

    class RecordInterface(A.RecordInterface):
        path: str


class C(B):
    type_ship = TypeShip(str(uuid4()))


class D(A):
    type_name = 'Example.D'
    type_ship = TypeShip(str(uuid4()))

    class RecordInterface(BaseModel):
        model_config = ConfigDict(extra='allow')
        title: str

    def label(self):
        return self.record_data.title


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
    for value in ({'type': 'Example.B', 'name': 'Calculator', 'path': 'calc.py'},
                  {'type': 'Example.D', 'title': 'Calculator'}):
        obj = registry.from_json(value)
        assert obj.label() == 'Calculator'
        assert obj.to_json() == value
    with pytest.raises(ValidationError):
        B.from_json({'path': 'calc.py'})
    with pytest.raises(ValidationError):
        A.from_json({'name': 1})
    assert 'name' in B.RecordInterface.model_json_schema()['required']


def test_all_direct_tarav_parents():
    class Both(B, D):
        type_ship = TypeShip(str(uuid4()))

    assert not Both.preserves_parent_record_interface()
    assert isrecordsubclass(Both, B)

    class Combined(B, D):
        type_ship = TypeShip(str(uuid4()))

        class RecordInterface(B.RecordInterface, D.RecordInterface):
            pass

    assert Combined.preserves_parent_record_interface()


def test_record_relationship_can_be_inspected_separately_from_behavior():
    class SharedRecord(D):
        type_ship = TypeShip(str(uuid4()))

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
        type_ship = TypeShip(str(uuid4()))

        class RecordInterface(B.RecordInterface):
            model_config = ConfigDict(extra='forbid')

    value = {'name': 'Calculator', 'path': 'calc.py'}
    assert Closed.from_json(value).to_json() == value
    with pytest.raises(ValidationError):
        Closed.from_json({**value, 'unexpected': True})


def test_no_coercion_discard_or_default_insertion():
    class Defaults(A):
        type_ship = TypeShip(str(uuid4()))

        class RecordInterface(A.RecordInterface):
            count: int = 1

    obj = Defaults.from_json({'name': 'x', 'unknown': [1]})
    assert obj.record_data.count == 1
    assert obj.to_json() == {'name': 'x', 'unknown': [1]}
    with pytest.raises(InvalidRecordJSON):
        A.from_json({'name': 'x', 'hints': {1: 'a', '1': 'b'}})

    class Transform(A):
        type_ship = TypeShip(str(uuid4()))

        class RecordInterface(A.RecordInterface):
            @field_validator('name')
            @classmethod
            def uppercase(cls, value):
                return value.upper()

    with pytest.raises(InvalidRecordJSON, match='transform'):
        Transform.from_json({'name': 'x'})
    obj.record['name'] = 1
    with pytest.raises(ValidationError):
        obj.to_json()
