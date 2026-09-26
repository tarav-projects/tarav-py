import pytest

from tarav.kernel import TaravObject, TaravWorkflow, entity
from tarav.runtime import create_runtime


def test_all_registered_workflows_are_non_instantiable_classes():
    runtime = create_runtime()
    for workflow in runtime.workflows.workflows.values():
        assert issubclass(workflow, TaravWorkflow)
        assert not issubclass(workflow, TaravObject)
        assert entity(workflow).target is workflow
        assert runtime.workflows.get(workflow.id) is workflow
        with pytest.raises(TypeError, match="do not instantiate"):
            workflow()
        assert workflow not in runtime.records.record_types


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
