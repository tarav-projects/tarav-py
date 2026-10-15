"""Callable Context namespaces retain explicit namespace composition."""

import pytest

from tarav.l0.kernel import NamespaceBase, TaravClass, TaravObject, TaravType, TypeShip
from tarav.l1.context.groups import ObjectGroup
from tarav.l1.poi import SituationPOI
from tarav.l3.runtime import create_runtime, get_runtime, set_runtime


class Example(TaravObject):
    @classmethod
    def class_entity(cls):
        return TaravClass(
            target=cls, id=TypeShip("3bda9397-2cef-4ff8-8913-d1012638eb4a"),
            name="Test.ContextNamespace.Example",
        )


# tarav.context 473c89a0:8cf85c979321cdcf
def test_named_and_callable_operations_preserve_default_and_selected_views(tmp_path):
    old = get_runtime()
    set_runtime(create_runtime(archive_root=tmp_path / "archive"))
    try:
        obj = Example()
        assert obj.context.obj is obj
        assert Example.context.obj is Example
        assert obj.context.explore().subject is obj
        assert obj.context().subject is obj
        assert Example.context.explore().subject is Example
        assert Example.context().subject is Example
        poi = SituationPOI(message="Context namespace test", situation={"path": "a"})
        assert isinstance(poi.context(type=ObjectGroup), ObjectGroup)
        assert isinstance(poi.context.explore(type=ObjectGroup), ObjectGroup)
        assert not callable(NamespaceBase(obj))
    finally:
        set_runtime(old)


# tarav.context 473c89a0:52d399e8d65f61fc
def test_call_dispatches_through_override_and_super_with_concrete_binding():
    class Custom(Example):
        @classmethod
        def class_entity(cls):
            return TaravClass(
                target=cls, id=TypeShip("53382548-be10-4a58-a899-4bbad010797d"),
                name="Test.ContextNamespace.Custom",
            )

        class Context(Example.Context):
            def explore(self, *, type=None):
                return (self.obj, type, super().model_nodes())

    class Inherited(Custom):
        @classmethod
        def class_entity(cls):
            return TaravClass(
                target=cls, id=TypeShip("727073df-610e-49f1-ab67-e97d716bd4f7"),
                name="Test.ContextNamespace.Inherited",
            )

    obj = Inherited()
    assert obj.context(type=ObjectGroup) == (obj, ObjectGroup, ())
    assert Inherited.context(type=ObjectGroup) == (Inherited, ObjectGroup, ())


def test_independent_class_only_types_require_explicit_context_composition():
    class Left(TaravType):
        @classmethod
        def class_entity(cls):
            return TaravClass(
                target=cls, id=TypeShip("a83fe74d-7b35-4be5-97f4-8dd2fd681cb0"),
                name="Test.ContextNamespace.Left",
            )

        class Context(TaravType.Context):
            def model_nodes(self):
                return (*super().model_nodes(), "left")

    class Right(TaravType):
        @classmethod
        def class_entity(cls):
            return TaravClass(
                target=cls, id=TypeShip("6785ac26-f212-4c06-af63-1ec5bd6b939e"),
                name="Test.ContextNamespace.Right",
            )

        class Context(TaravType.Context):
            def model_nodes(self):
                return (*super().model_nodes(), "right")

    with pytest.raises(TypeError, match="Context drops namespace contribution"):
        class Dropped(Left, Right):
            @classmethod
            def class_entity(cls):
                return TaravClass(
                    target=cls, id=TypeShip("908154e4-c573-4dc2-a850-afc4fdcd19a2"),
                    name="Test.ContextNamespace.Dropped",
                )

    class BothContext(Left.Context, Right.Context):
        pass

    class Both(Left, Right):
        Context = BothContext

        @classmethod
        def class_entity(cls):
            return TaravClass(
                target=cls, id=TypeShip("31e4626a-7e06-40eb-8e16-5ffdce0c417a"),
                name="Test.ContextNamespace.Both",
            )

    assert Both.context.obj is Both
    assert isinstance(Both.context, BothContext)
    assert Both.context.model_nodes() == ("right", "left")
