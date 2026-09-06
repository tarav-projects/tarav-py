from __future__ import annotations

import pytest

from tarav.harness import (
    DuplicateTypeRegistration,
    RecordTypeDeclarationError,
    TaravRecordType,
    TypeRegistry,
    TypeShip,
)

BASE = "4d0f1a2b-3c4d-4e5f-8a9b-0c1d2e3f4a5b"
OTHER = "5e1a2b3c-4d5e-4f60-9a1b-2c3d4e5f6071"


class DeclaredRecord(TaravRecordType):
    type_ship = TypeShip(BASE)
    type_name = "Declared.Record"


def test_subclass_must_declare_a_class_local_type_ship() -> None:
    with pytest.raises(RecordTypeDeclarationError):

        class MissingShip(TaravRecordType):
            type_name = "Missing.Ship"

    with pytest.raises(RecordTypeDeclarationError):

        class WrongShipValue(TaravRecordType):
            type_ship = BASE  # type: ignore[assignment]
            type_name = "Wrong.Ship.Value"


def test_intermediate_base_type_ship_is_never_inherited() -> None:
    with pytest.raises(RecordTypeDeclarationError):

        class InheritedOnly(DeclaredRecord):
            type_name = "Inherited.Only"


def test_registry_rejects_duplicate_type_ships_and_names() -> None:
    class SameShip(TaravRecordType):
        type_ship = TypeShip(BASE)
        type_name = "Same.Ship"

    class SameName(TaravRecordType):
        type_ship = TypeShip(OTHER)
        type_name = "Declared.Record"

    registry: TypeRegistry[TaravRecordType] = TypeRegistry(
        TaravRecordType, (DeclaredRecord,)
    )

    with pytest.raises(DuplicateTypeRegistration):
        registry.register(SameShip)
    with pytest.raises(DuplicateTypeRegistration):
        registry.register(SameName)
