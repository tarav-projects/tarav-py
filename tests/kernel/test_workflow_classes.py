import pytest

from tarav.kernel import TaravObject, TaravWorkflow, entity
from tarav.runtime import create_runtime


def test_workflow_containment_returns_objects_and_terminates_at_root(tmp_path):
    from tarav.archive.workflow import ArchiveWorkflow
    from tarav.archive.records import ArchiveFolder, ArchivePartition, RecordArchiveWorkflow
    from tarav.kernel import TaravClass

    root = TaravWorkflow()
    assert root is TaravWorkflow()
    assert root.workflow is None
    assert entity(TaravWorkflow).workflow is root
    assert entity(ArchiveWorkflow).workflow is ArchiveWorkflow()
    assert ArchiveWorkflow().workflow is root
    assert RecordArchiveWorkflow().workflow is ArchiveWorkflow()
    assert entity(ArchiveFolder).workflow is RecordArchiveWorkflow()
    partition = ArchivePartition(tmp_path, ArchiveWorkflow().id)
    assert partition.workflow is ArchiveWorkflow()
    assert partition.to_record()["workflow"] == str(ArchiveWorkflow().id)
    projection = entity(ArchiveFolder)
    assert projection.to_record()["workflow"] == str(RecordArchiveWorkflow().id)
    assert TaravClass.from_record(projection.to_record()).workflow is RecordArchiveWorkflow()
    for cls in create_runtime().workflows.workflows.values():
        current = cls()
        seen = set()
        while current is not None:
            assert current.id not in seen
            seen.add(current.id)
            current = current.workflow
        assert root.id in seen


def test_workflow_identity_is_independent_of_class_ownership():
    from concurrent.futures import ThreadPoolExecutor
    from tarav.kernel import TaravClass, TypeShip, WorkflowShip, WorkflowRegistry
    from tarav.kernel.workflows import KernelWorkflow

    class Example(TaravWorkflow):
        workflow_name = "singleton-example"
        constitution = "Exercise independent workflow identity."

        @classmethod
        def class_entity(cls):
            return TaravClass(
                target=cls,
                id=TypeShip("a67586aa-e6f3-45ec-92d0-2ad704d1ef4d"),
                name="Test.Singleton.Example",
                workflow=KernelWorkflow().id,
            )

        @classmethod
        def _workflow_id(cls):
            return WorkflowShip("d80243f1-af78-45f3-821c-40685380f84b")

    with ThreadPoolExecutor(max_workers=8) as pool:
        instances = tuple(pool.map(lambda _: Example(), range(32)))
    first = instances[0]
    assert all(item is first for item in instances)
    assert first.id != entity(Example).workflow_ship
    assert first.id != entity(Example).id
    first.configuration = {"enabled": True}
    assert Example().configuration == {"enabled": True}
    registry = WorkflowRegistry()
    registry.register(Example)
    assert registry.get(first.id) is Example
    with pytest.raises(KeyError):
        registry.get(entity(Example).workflow_ship)
    with pytest.raises(AttributeError):
        first.id = KernelWorkflow().id


def test_all_registered_workflows_have_separate_singleton_entities():
    runtime = create_runtime()
    instances = [workflow() for workflow in runtime.workflows.workflows.values()]
    assert len({id(instance) for instance in instances}) == len(instances)
    for workflow in runtime.workflows.workflows.values():
        assert issubclass(workflow, TaravWorkflow)
        assert issubclass(workflow, TaravObject)
        assert entity(workflow).target is workflow
        instance = workflow()
        assert workflow() is instance
        assert runtime.workflows.get(instance.id) is workflow
        assert instance.id != entity(workflow).id
        assert isinstance(workflow.id, property)
        assert workflow.from_record(instance.to_record()) is instance
        with pytest.raises(ValueError, match="does not identify"):
            workflow.from_record({"id": str(entity(workflow).id)})
        assert workflow not in runtime.records.record_types


def test_workflow_subclasses_must_declare_their_own_identity():
    from tarav.kernel import TaravClass, TypeShip, WorkflowDeclarationError
    from tarav.kernel.workflows import KernelWorkflow

    with pytest.raises(WorkflowDeclarationError, match="class-local _workflow_id"):
        class MissingIdentity(KernelWorkflow):
            workflow_name = "missing-identity"
            constitution = "Do not inherit another workflow's identity."

            @classmethod
            def class_entity(cls):
                return TaravClass(
                    target=cls,
                    id=TypeShip("a82e389b-9f6e-41c7-b124-a4d0a174b3d3"),
                    name="Test.MissingWorkflowIdentity",
                    workflow=KernelWorkflow().id,
                )


def test_runtime_services_are_isolated(tmp_path):
    first = create_runtime(archive_root=tmp_path / "first")
    second = create_runtime(archive_root=tmp_path / "second")
    assert first.contexts is not second.contexts
    assert first.contexts.archive_root != second.contexts.archive_root
    assert first.references is not second.references
    assert first.references.records is first.records
    assert second.references.records is second.records
    assert first.breadcrumbs is not second.breadcrumbs
    assert first.navigation.providers is not second.navigation.providers
    assert first.workflows.get("context") is second.workflows.get("context")
