from __future__ import annotations

import pytest

from tarav.harness import (
    DuplicateTypeRegistration,
    InvalidRecordType,
    TaravRecordType,
    TypeRegistrationError,
    TypeRegistry,
    UnknownRecordType,
)


class ExampleRecord(TaravRecordType):
    type_name = "Example.Record"


class OtherRecord(TaravRecordType):
    type_name = "Other.Record"


def test_registry_resolves_only_explicit_exact_record_types() -> None:
    registry = TypeRegistry(TaravRecordType, (ExampleRecord, OtherRecord))

    assert (
        registry.resolve({"type": "Example.Record", "application": "opaque"})
        is ExampleRecord
    )
    assert registry.resolve_type("Other.Record") is OtherRecord
    assert registry.types() == (ExampleRecord, OtherRecord)


def test_registry_rejects_unknown_or_malformed_top_level_types() -> None:
    registry = TypeRegistry(TaravRecordType, (ExampleRecord,))

    with pytest.raises(UnknownRecordType):
        registry.resolve({"type": "example.module.DynamicImport"})
    with pytest.raises(InvalidRecordType):
        registry.resolve({})
    with pytest.raises(InvalidRecordType):
        registry.resolve({"type": 3})


def test_registry_rejects_duplicate_and_incompatible_classes() -> None:
    registry = TypeRegistry(TaravRecordType, (ExampleRecord,))

    with pytest.raises(DuplicateTypeRegistration):
        registry.register(ExampleRecord)

    class NotARecord:
        type_name = "Not.A.Record"

    with pytest.raises(TypeRegistrationError):
        registry.register(NotARecord)  # type: ignore[arg-type]
