from __future__ import annotations

import pytest

from tarav.l0.kernel import FileRecord, TaravClass, TaravObject, TaravType, TaravTypeDeclarationError, TypeShip, entity
from tarav.l1.context import Context, ContextFolder, ContextBuilder, ContextExplorer, explore as context


class ContextExample(TaravObject):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("d6a484dc-2858-4623-8d48-69c75e42b76a"),
            name="Test.Context.Example",
        )

    class_context_calls = 0
    obj_context_calls = 0
    opened = 0

    @classmethod
    def class_context(cls, builder: ContextBuilder) -> None:
        cls.class_context_calls += 1
        builder.add("guide", opener=cls.open_leaf)

    @classmethod
    def open_leaf(cls) -> FileRecord:
        cls.opened += 1
        return FileRecord()

    def obj_context(self, builder: ContextBuilder) -> None:
        type(self).obj_context_calls += 1
        builder.add("state", opener=type(self).open_leaf)
        builder.add(
            "folder",
            opener=lambda: ContextFolder(
                self,
                lambda nested: nested.add("leaf", opener=type(self).open_leaf),
            ),
        )


def test_class_context_lists_without_opening_and_reifies_python_class() -> None:
    ContextExample.class_context_calls = 0
    ContextExample.opened = 0
    view = context(ContextExample)

    assert ContextExample.class_context_calls == 0
    assert [entry.name for entry in view.ls()] == ["entity", "guide"]
    assert ContextExample.class_context_calls == 1
    assert ContextExample.opened == 0
    assert [entry.name for entry in view.ls()] == ["entity", "guide"]
    assert ContextExample.class_context_calls == 1

    class_representation = view.open("entity")
    assert isinstance(class_representation, TaravClass)
    assert class_representation.target is ContextExample
    assert class_representation.id == entity(ContextExample).id
    assert isinstance(view.open("guide"), FileRecord)
    assert ContextExample.opened == 1


def test_object_context_is_a_read_only_cursor_over_nested_contexts() -> None:
    ContextExample.obj_context_calls = 0
    ContextExample.opened = 0
    subject = ContextExample.from_record({"state": "ready"})
    view = context(subject)

    assert ContextExample.obj_context_calls == 0
    assert [entry.name for entry in view.ls()] == ["class", "state", "folder"]
    assert ContextExample.obj_context_calls == 1
    assert ContextExample.opened == 0
    assert isinstance(view.open("state"), FileRecord)
    assert view.pwd() == "/"

    class_view = view.open("class")
    assert isinstance(class_view, Context)
    assert class_view.subject is ContextExample

    assert view.cd("folder") is view
    assert view.pwd() == "/folder"
    assert [entry.name for entry in view.ls()] == ["leaf"]
    assert isinstance(view.open("leaf"), FileRecord)
    with pytest.raises(NotADirectoryError):
        view.cd("leaf")
    assert view.pwd() == "/folder"
    view.cd("..").cd("..")
    assert view.pwd() == "/"
    view.cd("folder").cd("/")
    assert view.pwd() == "/"


def test_context_folders_are_tarav_objects() -> None:
    assert issubclass(Context, TaravType)
    assert issubclass(Context, TaravObject)
    assert issubclass(ContextExplorer, TaravType)

    class_view = context(Context)
    class_representation = class_view.open("entity")
    assert isinstance(class_representation, TaravClass)
    assert class_representation.target is Context
    assert class_representation.id == entity(Context).id

    assert context(class_view.root).subject is class_view.root


def test_entry_context_uses_its_explorer_and_direct_context_starts_another() -> None:
    subject = ContextExample()
    explorer = context(subject)
    origin = explorer.get("class")

    assert context(origin) is explorer
    assert explorer.subject is ContextExample
    assert explorer.pwd() == "/class"
    assert explorer.back() is explorer
    assert explorer.subject is subject
    assert explorer.pwd() == "/"

    independent = context(ContextExample)
    assert independent is not explorer
    assert independent.subject is ContextExample
    assert explorer.subject is subject
    with pytest.raises(ValueError, match="another explorer"):
        independent.follow(origin)


def test_entry_remembers_its_origin_after_explorer_moves() -> None:
    explorer = context(ContextExample())
    entry = explorer.get("state")
    explorer.cd("folder")
    assert explorer.pwd() == "/folder"

    assert context(entry) is explorer
    assert isinstance(explorer.subject, FileRecord)
    assert explorer.pwd() == "/"
    explorer.back()
    assert explorer.pwd() == "/"
    assert isinstance(explorer.subject, ContextExample)


def test_context_builder_rejects_duplicate_or_unsafe_names() -> None:
    builder = ContextBuilder(ContextExample)
    builder.add("entry", opener=FileRecord)

    with pytest.raises(ValueError, match="Duplicate Context entry"):
        builder.add("entry", opener=FileRecord)
    with pytest.raises(ValueError, match="ordinary path segment"):
        builder.add("..", opener=FileRecord)
    with pytest.raises(ValueError, match="ordinary path segment"):
        builder.add("nested/path", opener=FileRecord)


def test_runtime_type_never_inherits_class_entity() -> None:
    with pytest.raises(TaravTypeDeclarationError, match="class-local class_entity"):

        class UnidentifiedType(TaravType):
            pass
