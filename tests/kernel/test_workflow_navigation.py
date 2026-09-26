from __future__ import annotations

from tarav.kernel import entity

import pytest

from tarav.kernel import (
    FileRecord,
    TaravClass,
    TaravObject,
    TaravTypeDeclarationError,
    TaravWorkflow,
    TypeRegistry,
    TypeShip,
    WorkflowDeclarationError,
    WorkflowRegistry,
    WorkflowShip,
)
from tarav.kernel.space import FilesystemProvider, RecordProvider
from tarav.navigation import NavigationService


def test_external_workflow_registers_and_navigates(tmp_path):
    code = tmp_path / "plugin.py"
    code.write_text(
        """from tarav.kernel import TaravClass, TaravWorkflow, TypeShip, WorkflowShip
class Example(TaravWorkflow):
    @classmethod
    def class_entity(cls):
        return TaravClass(
            target=cls,
            id=TypeShip("2afd3288-433c-40e6-8f0d-706c15ea0eae"),
            name="Test.Workflow.External",
            workflow=WorkflowShip("f710989b-2a05-4e5c-88a0-c9cdba37d8ce"),
        )

    @classmethod
    def _workflow_id(cls):
        return WorkflowShip("f710989b-2a05-4e5c-88a0-c9cdba37d8ce")
    workflow_name = "example"
    constitution = "Provide a disposable external test workspace."
def register(registry):
    registry.register(Example)
"""
    )
    registry = WorkflowRegistry()
    registry.load(code)
    records = TypeRegistry(TaravObject, (FileRecord,))
    data = tmp_path / "data"
    data.mkdir()
    (data / "one.json").write_text(
        '{"type":"Tarav.FileRecord","content":"hello"}'
    )
    nav = NavigationService()
    nav.mount("example", FilesystemProvider(data, records))
    assert registry.get("example").workflow_name == "example"
    assert nav.list().value[0].name == "example"
    assert nav.list("/example").value[0].name == "one.json"
    assert isinstance(nav.load("/example/one.json").value, FileRecord)
    assert not nav.load("/example/../plugin.py").ok


def test_provider_failure_is_inspectable_and_does_not_block_other_provider():
    class Broken(RecordProvider):
        def list(self, address=""):
            raise RuntimeError("offline")

    nav = NavigationService()
    nav.mount("broken", Broken())
    result = nav.list("/broken")
    assert not result.ok
    assert result.findings[0].evidence["message"] == "offline"
    assert nav.list().ok


def test_failed_external_registration_does_not_leak_workflows(tmp_path):
    code = tmp_path / "broken.py"
    code.write_text(
        """from tarav.kernel import TaravClass, TaravWorkflow, TypeShip, WorkflowShip
class Example(TaravWorkflow):
    @classmethod
    def class_entity(cls):
        return TaravClass(
            target=cls,
            id=TypeShip("8de4878f-32d9-4078-b75c-fe46201eaf27"),
            name="Test.Workflow.Broken",
            workflow=WorkflowShip("43e653fb-c43e-4b9f-9dc8-2a40ec7552bf"),
        )

    @classmethod
    def _workflow_id(cls):
        return WorkflowShip("43e653fb-c43e-4b9f-9dc8-2a40ec7552bf")
    workflow_name = "example"
    constitution = "Provide a disposable broken test workspace."
def register(registry):
    registry.register(Example)
    raise ValueError("incomplete registration")
"""
    )
    registry = WorkflowRegistry()
    with pytest.raises(ValueError, match="incomplete registration"):
        registry.load(code)
    assert registry.workflows == {}


def test_invalid_provider_response_is_a_poi():
    class Invalid(RecordProvider):
        def load(self, address):
            return {"type": "uninterpreted"}

    nav = NavigationService()
    nav.mount("invalid", Invalid())
    result = nav.load("/invalid/record")
    assert not result.ok
    assert result.findings[0].evidence["error"] == "TypeError"


def test_registry_resolves_workflow_entities_by_name_and_ship():
    class Example(TaravWorkflow):
        @classmethod
        def class_entity(cls) -> TaravClass:
            return TaravClass(
                target=cls,
                id=TypeShip("6d6bb303-9363-4c62-8608-c9b03427407a"),
                name="Test.Workflow.Example",
                workflow=WorkflowShip("0e21310e-8fa1-44ce-bf12-ebc285747b9f"),
            )

        @classmethod
        def _workflow_id(cls):
            return WorkflowShip("0e21310e-8fa1-44ce-bf12-ebc285747b9f")

        workflow_name = "example"
        constitution = "Provide a disposable test workspace."

    workflow = Example
    registry = WorkflowRegistry()
    registry.register(workflow)

    assert registry.get("example") is workflow
    assert registry.get(entity(Example).workflow_ship) is workflow
    assert workflow().id == entity(Example).workflow_ship
    assert Example.constitution == "Provide a disposable test workspace."
    assert entity(workflow).target is workflow
    assert issubclass(workflow, TaravObject)
    assert workflow() is workflow()


def test_registry_rejects_duplicate_workflow_identities():
    class First(TaravWorkflow):
        @classmethod
        def class_entity(cls) -> TaravClass:
            return TaravClass(
                target=cls,
                id=TypeShip("11e8fb3a-38ad-452a-a31a-1175248a70a6"),
                name="Test.Workflow.First",
                workflow=WorkflowShip("2edb4f91-874d-4cd9-9427-bda3a37de1b8"),
            )

        @classmethod
        def _workflow_id(cls):
            return WorkflowShip("2edb4f91-874d-4cd9-9427-bda3a37de1b8")

        workflow_name = "shared"
        constitution = "Provide the first test workspace."

    class SameName(TaravWorkflow):
        @classmethod
        def class_entity(cls) -> TaravClass:
            return TaravClass(
                target=cls,
                id=TypeShip("eef4134e-846b-4bad-a6d1-dc34c651cd0b"),
                name="Test.Workflow.SameName",
                workflow=WorkflowShip("4c175dca-e2fd-45a8-a0d0-cc03fe2bd1ea"),
            )

        @classmethod
        def _workflow_id(cls):
            return WorkflowShip("4c175dca-e2fd-45a8-a0d0-cc03fe2bd1ea")

        workflow_name = "shared"
        constitution = "Provide another test workspace with the same name."

    class SameShip(TaravWorkflow):
        @classmethod
        def class_entity(cls) -> TaravClass:
            return TaravClass(
                target=cls,
                id=TypeShip("d9080bbe-c9c5-4de1-b03e-fe3a7ac4fa81"),
                name="Test.Workflow.SameShip",
                workflow=entity(First).workflow_ship,
            )

        @classmethod
        def _workflow_id(cls):
            return entity(First).workflow_ship

        workflow_name = "other"
        constitution = "Provide another test workspace with the same Ship."

    registry = WorkflowRegistry()
    registry.register(First)

    with pytest.raises(ValueError, match="Duplicate Workflow name"):
        registry.register(SameName)
    with pytest.raises(ValueError, match="Duplicate Workflow Ship"):
        registry.register(SameShip)


def test_workflow_classes_declare_name_constitution_and_class_entity():
    with pytest.raises(WorkflowDeclarationError, match="workflow_name"):

        class MissingName(TaravWorkflow):
            @classmethod
            def class_entity(cls) -> TaravClass:
                return TaravClass(
                    target=cls,
                    id=TypeShip("04faad22-8537-40f5-b30d-a271f7bde817"),
                    name="Test.Workflow.MissingName",
                )

    with pytest.raises(TaravTypeDeclarationError, match="class-local class_entity"):

        class MissingClassEntity(TaravWorkflow):
            workflow_name = "missing-class-entity"

    with pytest.raises(WorkflowDeclarationError, match="constitution"):

        class MissingConstitution(TaravWorkflow):
            @classmethod
            def class_entity(cls) -> TaravClass:
                return TaravClass(
                    target=cls,
                    id=TypeShip("b99bcfe0-b466-4ca9-89f8-71ee54603a1c"),
                    name="Test.Workflow.MissingConstitution",
                )

            workflow_name = "missing-constitution"

    with pytest.raises(WorkflowDeclarationError, match="constitution"):

        class EmptyConstitution(TaravWorkflow):
            @classmethod
            def class_entity(cls) -> TaravClass:
                return TaravClass(
                    target=cls,
                    id=TypeShip("8946b07e-8d5a-4983-b3d9-c17121660db1"),
                    name="Test.Workflow.EmptyConstitution",
                )

            workflow_name = "empty-constitution"
            constitution = "  "
