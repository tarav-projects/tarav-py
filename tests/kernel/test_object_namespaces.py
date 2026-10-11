"""Object namespace composition and the Record projection entry point."""

import pytest

from tarav.l0.kernel import (
    NamespaceBase,
    TaravClass,
    TaravObject,
    TypeShip,
)


class PX(NamespaceBase[TaravObject]):
    def x(self) -> str:
        return f"x:{type(self.obj).__name__}"


class PY(NamespaceBase[TaravObject]):
    def y(self) -> str:
        return f"y:{type(self.obj).__name__}"


class PXY(PX, PY):
    pass
# tarav.breadcrumb 8c030914f2f144c4f81e7d88b30508b45efb6f9c1faca0eb4c1ccf2ecd6c95be


class BaseX(TaravObject):
    P = PX

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("3172f43d-d40c-4aa2-a19d-741dcc833631"),
            name="Test.BaseX",
        )

    @property
    def p(self) -> PX:
        return type(self).P(self)


class BaseY(TaravObject):
    P = PY

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("b5acbf41-a2f9-40d7-b67b-73a4e92c1120"),
            name="Test.BaseY",
        )


class Combined(BaseX, BaseY):
    P = PXY

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("f2d916e7-8895-409f-bf89-d9b1852deabd"),
            name="Test.Combined",
        )


def test_two_independent_bases_contribute_to_one_bound_namespace() -> None:
    obj = Combined()
    assert Combined.P is PXY
    assert isinstance(obj.p, PXY)
    assert obj.p.obj is obj
    assert obj.p.x() == "x:Combined"
    assert obj.p.y() == "y:Combined"


def test_inherited_namespace_needs_no_redeclaration() -> None:
    class Derived(BaseX):
        @classmethod
        def class_entity(cls) -> TaravClass:
            return TaravClass(
                target=cls,
                id=TypeShip("bf46e148-4a55-48f6-9e9f-1268dfb6dc5c"),
                name="Test.Derived",
            )

    assert Derived().p.x() == "x:Derived"


def test_missing_explicit_composition_is_rejected_at_class_creation() -> None:
    # tarav.breadcrumb f3eec17fb3f9840eaf1bbde76248ab08595a9fdb91a03aee8a4af6c1f972e585
    with pytest.raises(TypeError, match="P drops namespace contribution"):

        class Dropped(BaseX, BaseY):
            @classmethod
            def class_entity(cls) -> TaravClass:
                return TaravClass(
                    target=cls,
                    id=TypeShip("dba8c642-2c2e-4086-ac16-c1233228f342"),
                    name="Test.Dropped",
                )


def test_record_namespace_uses_the_existing_projection() -> None:
    obj = Combined()
    assert obj.records.obj is obj
    assert obj.records.to_record() == {"type": "Test.Combined"}


# tarav.breadcrumb 39175d7f24002b4b04f89a0ad24c150174cabd1fa53a8de58b495e0445549778
def test_record_namespace_binds_inherited_class_loading() -> None:
    assert Combined.records.obj is Combined
    loaded = Combined.records.from_record({"type": "Test.Combined"})
    assert type(loaded) is Combined
    assert loaded.records.to_record() == {"type": "Test.Combined"}

    with pytest.raises(TypeError, match="requires an object instance"):
        Combined.records.to_record()
    with pytest.raises(TypeError, match="not an opaque JSON wrapper"):
        TaravObject.records.from_record({})


# tarav.breadcrumb f4ec8f4bcffb99b7116dd27486141b249dbfb1a4151c3d635fc3961c56204184
def test_record_namespace_preserves_specialized_validation_and_examples() -> None:
    # tarav.breadcrumb a3b9281034cb89b3ee020c4e3ac2e95717556d214885396afd08c48a7c81dabf
    from tarav.l1.actions import Closing
    from tarav.l1.actions.blessing import Blessing
    from tarav.l1.decisions.records import Decision

    assert Combined.records.record_example() == {"type": "Test.Combined"}
    assert Combined.records.validate_record({"type": "Test.Combined"})

    decision = Decision.records.record_example()
    assert decision["type"] == "Tarav.Decisions.Decision"
    assert Decision.records.validate_record(decision).created_at == decision["created_at"]
    without_timezone = {**decision, "created_at": "2026-10-07T12:00:00"}
    with pytest.raises(ValueError, match="timezone"):
        Decision.records.validate_record(without_timezone)
    with pytest.raises(ValueError, match="timezone"):
        Decision.records.from_record(without_timezone)

    blessing = Blessing.records.record_example()
    assert blessing["type"] == "Tarav.Blessings.Blessing"
    assert issubclass(Blessing.Records, Closing.Records)
    assert type(Blessing.records.from_record(blessing)) is Blessing
    with pytest.raises(ValueError, match="reason"):
        Blessing.records.validate_record({**blessing, "reason": " "})
