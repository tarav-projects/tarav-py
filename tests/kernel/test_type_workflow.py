import pytest

from tarav.l0.kernel import TaravClass, TaravObject, TypeWorkflow, entity
from tarav.l1.context import explore as context
from tarav.l1.archive.records import ArchiveFolder
from tarav.l3.runtime import create_runtime


def test_type_workflow_ownership_and_registration():
    runtime = create_runtime()
    owner = runtime.workflows.get("type")
    assert owner is TypeWorkflow
    assert entity(TaravClass).workflow_ship == owner().id
    assert entity(ArchiveFolder).workflow_ship != owner().id
    assert entity(TaravClass).id == TaravClass.class_entity().id


def test_bases_follow_python_and_remain_discoverable():
    subject = entity(ArchiveFolder)
    expected = tuple(
        base for base in ArchiveFolder.__bases__ if issubclass(base, TaravObject)
    )
    assert tuple(base.target for base in subject.bases()) == expected
    explorer = context(subject).cd("bases")
    assert tuple(entry.open().target for entry in explorer.ls()) == expected
    parent = explorer.open(0)
    assert context(parent).get("bases") is not None
    assert context(parent).cd("target").open("entity").id == parent.id


def test_class_record_roundtrip_does_not_invent_live_inheritance():
    original = entity(ArchiveFolder)
    restored = TaravClass.from_record(original.to_record())
    assert restored.to_record() == original.to_record()
    assert restored.workflow == original.workflow
    with pytest.raises(RuntimeError, match="live Python class"):
        restored.bases()
