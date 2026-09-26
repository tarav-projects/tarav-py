from __future__ import annotations

import pytest

from tarav.kernel import (
    DuplicateTypeRegistration,
    TaravClass,
    TaravObject,
    TaravType,
    TaravTypeDeclarationError,
    TypeRegistry,
    TypeShip,
    entity,
)

BASE = "4d0f1a2b-3c4d-4e5f-8a9b-0c1d2e3f4a5b"
OTHER = "5e1a2b3c-4d5e-4f60-9a1b-2c3d4e5f6071"


class DeclaredRecord(TaravObject):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip(BASE), name="Declared.Record")


def test_subclass_must_define_a_class_local_class_entity() -> None:
    with pytest.raises(TaravTypeDeclarationError, match="class-local class_entity"):

        class MissingClassEntity(TaravObject):
            pass

    class WrongClassEntity(TaravObject):
        @classmethod
        def class_entity(cls):
            return object()

    with pytest.raises(TaravTypeDeclarationError, match="must return a TaravClass"):
        entity(WrongClassEntity)


def test_class_entity_must_represent_the_exact_python_class() -> None:
    class WrongTarget(TaravType):
        @classmethod
        def class_entity(cls) -> TaravClass:
            return TaravClass(
                target=DeclaredRecord,
                id=TypeShip(OTHER),
                name="Wrong",
            )

    with pytest.raises(TaravTypeDeclarationError, match="exact class"):
        entity(WrongTarget)


def test_intermediate_base_class_entity_is_never_inherited() -> None:
    with pytest.raises(TaravTypeDeclarationError, match="class-local class_entity"):

        class InheritedOnly(DeclaredRecord):
            pass


def test_registry_rejects_duplicate_type_ships_and_names() -> None:
    class SameShip(TaravObject):
        @classmethod
        def class_entity(cls) -> TaravClass:
            return TaravClass(target=cls, id=TypeShip(BASE), name="Same.Ship")

    class SameName(TaravObject):
        @classmethod
        def class_entity(cls) -> TaravClass:
            return TaravClass(target=cls, id=TypeShip(OTHER), name="Declared.Record")

    registry: TypeRegistry[TaravObject] = TypeRegistry(TaravObject, (DeclaredRecord,))

    with pytest.raises(DuplicateTypeRegistration):
        registry.register(SameShip)
    with pytest.raises(DuplicateTypeRegistration):
        registry.register(SameName)
