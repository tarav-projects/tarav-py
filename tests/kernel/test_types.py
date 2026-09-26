from __future__ import annotations

from tarav.kernel import TaravClass

import pytest

from tarav.kernel import (
    DuplicateTypeRegistration,
    InvalidRecordType,
    TaravObject,
    TypeRegistrationError,
    TypeRegistry,
    TypeShip,
    UnknownRecordType,
)


class ExampleRecord(TaravObject):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('11111111-1111-4111-8111-111111111111'),
            name='Example.Record',
        )


class OtherRecord(TaravObject):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('22222222-2222-4222-8222-222222222222'),
            name='Other.Record',
        )


def test_registry_resolves_only_explicit_exact_record_types() -> None:
    registry = TypeRegistry(TaravObject, (ExampleRecord, OtherRecord))

    assert (
        registry.resolve({"type": "Example.Record", "application": "opaque"})
        is ExampleRecord
    )
    assert registry.resolve_type("Other.Record") is OtherRecord
    assert registry.types() == (ExampleRecord, OtherRecord)


def test_registry_rejects_unknown_or_malformed_top_level_types() -> None:
    registry = TypeRegistry(TaravObject, (ExampleRecord,))

    with pytest.raises(UnknownRecordType):
        registry.resolve({"type": "example.module.DynamicImport"})
    with pytest.raises(InvalidRecordType):
        registry.resolve({})
    with pytest.raises(InvalidRecordType):
        registry.resolve({"type": 3})


def test_registry_rejects_duplicate_and_incompatible_classes() -> None:
    registry = TypeRegistry(TaravObject, (ExampleRecord,))

    with pytest.raises(DuplicateTypeRegistration):
        registry.register(ExampleRecord)

    class NotARecord:
        type_name = "Not.A.Record"

    with pytest.raises(TypeRegistrationError):
        registry.register(NotARecord)  # type: ignore[arg-type]
