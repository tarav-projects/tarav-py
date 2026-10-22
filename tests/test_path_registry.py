"""Computed Views stay separate from maintained path identity and Project actions."""
# tarav.breadcrumb 51b11609a061

import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from tarav.l0.kernel import Ship, TaravClass, TaravObject, TypeShip, entity
from tarav.l1.lines import Block, Line
from tarav.l1.path_registry import JSONView, PathDocumentation, PathEntry, PathRegistry, json_paths
from tarav.l1.path_registry.checks import (
    DuplicatePath, IdentityConflict, PathMissing, PathUndeclared, PathUnregistered,
    RegistryCheck, SchemaChanged, ViewMissing,
)
from tarav.l1.project.types import TypesManager
from tarav.l1.records import RecordRegistry
from tarav.l2.project import Project
from tarav.l3.runtime import create_runtime, get_runtime, set_runtime


class Subject(TaravObject):
    schema = {"properties": {"old": {"type": "string"}}}

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("b260113b-f29e-40f7-8e19-0871b602e641"), name="Test.Paths.Subject")

    @classmethod
    def view_schemas(cls):
        return {"record": cls.schema}


class TestProject(Project):
    __test__ = False

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("e288ee69-470d-48e1-893d-fad81ab49790"), name="Test.Paths.Project")

    class Types(Project.Types):
        def all(self):
            return (Subject,)

    class Checks(Project.Checks):
        def suite(self):
            return self.obj.paths.suite()

    class Records(Project.Records):
        @property
        def registry(self):
            return RecordRegistry(self.obj.root / "actions", records=self.types)


@pytest.fixture
def project(tmp_path):
    old = get_runtime()
    set_runtime(create_runtime(record_types=(Subject, TestProject)))
    (tmp_path / ".tarav").mkdir()
    (tmp_path / ".tarav/project.json").write_text(json.dumps({
        "project_id": str(uuid4()), "created_at": "2026-10-22T00:00:00Z"}))
    Subject.schema = {"properties": {"old": {"type": "string"}}}
    try:
        yield TestProject.from_path(tmp_path)
    finally:
        set_runtime(old)


def test_default_views_are_computed_from_record_and_instance_declarations():
    record, instance = Line.view_schemas()["record"], Line.view_schemas()["instance"]
    assert set(record["properties"]) == {"type", "id", "text", "scope_ship"}
    assert "scope" not in record["properties"]
    assert instance["properties"]["scope"]["readOnly"] is True
    assert instance["x-tarav-completeness"] == "partial"
    assert Block.view_schemas()["record"]["properties"]["content_ships"]["type"] == "array"


def test_introspection_does_not_construct_or_read_descriptors():
    class Dangerous(TaravObject):
        @classmethod
        def class_entity(cls):
            return TaravClass(target=cls, id=TypeShip("5026543e-9315-4ec5-9a4c-f494d75ae7bc"), name="Test.Paths.Dangerous")

        def __init__(self, item: "UnknownType"):  # noqa: F821 - unresolved declarations must not be evaluated
            raise AssertionError("Never construct")

        @property
        def secret(self) -> str:
            raise AssertionError("Never read")

    schema = Dangerous.view_schemas()["instance"]
    assert schema["properties"]["secret"] == {"x-python-annotation": "str", "readOnly": True}
    assert schema["properties"]["item"] == {"x-python-annotation": "UnknownType"}


def test_project_selection_uses_defining_source_and_can_be_overridden(project):
    manager = TypesManager(SimpleNamespace(root=Path(__file__).parent,
                                          records=SimpleNamespace(types=project.records.types)))
    selected = manager.all()
    assert Subject in selected and TestProject in selected
    assert Line not in selected and Block not in selected
    assert project.types.all() == (Subject,)
    assert project.records.types is get_runtime().records


def test_pointer_paths_include_root_and_escape_literal_keys_and_array_indices():
    assert tuple(json_paths({"a/b": {"~": [1]}})) == ("", "/a~1b", "/a~1b/~0", "/a~1b/~0/0")
    with pytest.raises(ValueError, match="JSON Pointer"):
        PathEntry(Ship(uuid4()), "/bad~escape")


def test_new_project_reads_and_checks_do_not_provision(project):
    before = tuple(project.root.rglob("*"))
    assert project.paths.open().entries == []
    assert project.checks.run().complete
    assert tuple(project.root.rglob("*")) == before
    assert not project.paths.file.exists()


def test_rename_preserves_path_ship_attachments_and_line_context(project):
    entries = project.paths.enroll(Subject, "record")
    path = next(e for e in entries if e.typed.path == "/properties/old")
    registry = project.paths.open()
    block = Block(id=Ship(uuid4()))
    doc = PathDocumentation(id=Ship(uuid4()), scope=block, text="The value retained by this field.")
    block.append(doc)
    registry.attach(path.id, doc)
    Subject.schema = {"properties": {"new": {"type": "string"}}}
    current, = project.paths.views()
    findings = RegistryCheck(registry, [current]).run().pois()
    assert {type(p) for p in findings} == {SchemaChanged, PathMissing, PathUnregistered}
    for entry in registry.entries:
        if entry.typed.path and "/old" in entry.typed.path:
            registry.declare(entry.id, entry.typed.path.replace("/old", "/new"))
    registry.accept(current)
    project.paths.save(registry)
    restored = project.paths.open()
    assert restored.entry(path.id).typed.path == "/properties/new"
    assert restored.entry(path.id).typed.attachments == [doc.id]
    assert doc.scope is block
    assert tuple(RegistryCheck(restored, [current]).run().pois()) == ()
    assert get_runtime().records.from_record(restored.records.to_record()).records.to_record() == restored.records.to_record()


def test_checks_report_invalid_maps_without_repairing_them(project):
    project.paths.enroll(Subject, "record")
    registry = project.paths.open()
    view = registry.views[0]
    duplicate = registry.add(view.id, "/properties/old")
    registry.add(view.id, None)
    registry.entries.append(duplicate)
    registry.add(Ship(uuid4()), "")
    project.paths.save(registry)
    before = project.paths.file.read_bytes()
    kinds = {type(p) for p in project.checks.run().pois()}
    assert kinds == {DuplicatePath, PathUndeclared, IdentityConflict, ViewMissing}
    assert project.paths.file.read_bytes() == before


def test_retirement_keeps_identity_and_new_paths_get_explicit_ships(project):
    project.paths.enroll(Subject, "record")
    registry = project.paths.open()
    removed = next(e for e in registry.entries if e.typed.path == "/properties/old")
    registry.retire(removed.id)
    fresh = registry.add(removed.typed.view, "/properties/old")
    assert fresh.id != removed.id
    assert registry.entry(removed.id).typed.active is False
    assert registry.entry(removed.id).typed.path is None


def test_path_lookup_exposes_ambiguity_and_view_retirement_preserves_attachments(project):
    project.paths.enroll(Subject, "record")
    registry = project.paths.open()
    view = registry.views[0]
    entry, = registry.at(view.id, "/properties/old")
    block = Block(id=Ship(uuid4()))
    registry.attach(entry.id, block)
    duplicate = registry.add(view.id, "/properties/old")
    assert registry.at(view.id, "/properties/old") == (entry, duplicate)
    registry.retire_view(view.id)
    assert registry.at(view.id, "/properties/old") == ()
    assert registry.entry(entry.id).typed.attachments == [block.id]
    assert tuple(RegistryCheck(registry, []).run().pois()) == ()


def test_schema_changes_open_actions_and_explicit_acceptance_closes_them(project):
    project.paths.enroll(Subject, "record")
    assert project.status().actions["opened"] == 0
    Subject.schema = {"properties": {"old": {"type": "number"}}}
    assert project.status().actions["opened"] == 1
    actions = project.actions.list()
    assert len(actions) == 1
    before = project.paths.file.read_bytes()
    project.checks.run()
    assert project.paths.file.read_bytes() == before
    registry = project.paths.open()
    registry.accept(project.paths.views()[0])
    project.paths.save(registry)
    assert project.status().actions["gone"] == 1


def test_unavailable_computation_or_registry_does_not_close_old_actions(project, monkeypatch):
    project.paths.enroll(Subject, "record")
    Subject.schema = {"properties": {"old": {"type": "number"}}}
    project.status()
    def broken(cls):
        raise ValueError("Introspection unavailable")
    monkeypatch.setattr(Subject, "view_schemas", classmethod(broken))
    status = project.status()
    assert not status.checks.complete
    assert status.actions["gone"] == 0
    project.paths.file.unlink()
    assert project.status().actions["gone"] == 0


def test_registry_rejects_other_project_storage(project):
    PathRegistry(Ship(uuid4())).save(project.paths.file)
    with pytest.raises(ValueError, match="different Project"):
        project.paths.open()


def test_json_view_is_a_stable_computed_identity_with_an_independent_value():
    value = {"properties": {"text": {"type": "string"}}}
    first = JSONView(entity(Line).id, "record", value)
    value["properties"].clear()
    second = JSONView(entity(Line).id, "record", {})
    assert first.id == second.id
    assert first.typed.value == {"properties": {"text": {"type": "string"}}}
