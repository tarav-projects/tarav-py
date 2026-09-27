from __future__ import annotations

from tarav.l0.kernel import entity

import json
from pathlib import Path

import pytest

from tarav import get_runtime, set_runtime
from tarav.context import context
from tarav.context.storage import StoredDictionaryContext, SubjectContextRoot
from tarav.l0.kernel import RecordTypeMismatch, TaravObject
from tarav.context import Context, ContextEntry, ContextExplorer, ContextFolder, ContextList
from tarav.archive.records import (
    ArchiveEntry,
    ArchiveExplorer,
    ArchiveFolder,
    ArchiveRoot,
    ArchiveList,
)
from tarav.references import FileReference
from tarav.runtime import create_runtime
from tarav.test_workflow import TEST_ENTITY_SHIP
from tarav.test_workflow import TestEntity as WorkspaceEntity
from tarav.test_workflow import TestItem as WorkspaceItem
from tarav.test_workflow import TestWorkflow as WorkspaceWorkflow


@pytest.fixture
def runtime(tmp_path):
    previous = get_runtime()
    selected = create_runtime(archive_root=tmp_path / "archive")
    set_runtime(selected)
    try:
        yield selected
    finally:
        set_runtime(previous)


def test_context_composes_runtime_and_archive_entries_lazily(
    runtime, monkeypatch
) -> None:
    workflow = runtime.workflows.get("test")
    assert workflow is WorkspaceWorkflow
    root, _ = workflow.create_context_workspace(runtime.contexts)

    loaded_paths: list[Path] = []
    original_load = runtime.records.load

    def tracked_load(path, *, expected_type=None):
        loaded_paths.append(Path(path))
        return original_load(path, expected_type=expected_type)

    monkeypatch.setattr(runtime.records, "load", tracked_load)
    view = runtime.context(workflow)
    assert isinstance(view, ContextExplorer)
    assert isinstance(view.root, ContextFolder)
    assert loaded_paths == []
    assert [entry.name for entry in view.ls()] == [
        "entity",
        "runtime-example",
        "runtime-alias",
        "sample-entity",
        "examples",
        "ordered",
        "retained-example",
    ]
    assert root.root in loaded_paths
    retained_entry = next(
        entry for entry in view.ls() if entry.name == "retained-example"
    )
    assert isinstance(retained_entry.backing, ArchiveEntry)
    assert retained_entry.archive_entry() is retained_entry.backing
    retained_path = root.root / retained_entry.backing.artifact
    assert retained_path not in loaded_paths
    assert view.open("runtime-example") is view.open("runtime-alias")
    assert retained_path not in loaded_paths

    retained = view.open("retained-example")
    assert isinstance(retained, WorkspaceItem)
    assert retained.label == "retained"
    assert retained_entry.description == "Synthetic retained example."
    stored_wrapper = retained_entry.backing.open()
    assert isinstance(stored_wrapper, ContextEntry)
    assert stored_wrapper.open().label == "retained"
    assert loaded_paths[-1] == retained_path

    examples = view.open("examples")
    assert isinstance(examples, ContextFolder)
    assert isinstance(examples, TaravObject)
    folder_entry = view.get("examples")
    assert folder_entry.description == "Named synthetic examples."
    assert (folder_entry.backing.artifact_location() / "context.json").is_file()
    view.cd("examples")
    assert view.pwd() == "/examples"
    assert [entry.name for entry in view.ls()] == ["nested-example"]
    assert view.open("nested-example").label == "nested"
    view.cd("..").cd("..")
    assert view.pwd() == "/"


def test_context_read_does_not_create_archive_data(runtime) -> None:
    workflow = runtime.workflows.get("test")
    assert [entry.name for entry in runtime.context(workflow).ls()] == [
        "entity",
        "runtime-example",
        "runtime-alias",
        "sample-entity",
    ]
    assert not runtime.contexts.partition.directory.exists()


def test_entity_and_class_ships_address_their_own_context_roots(runtime) -> None:
    workflow = runtime.workflows.get("test")
    workflow_root, _ = workflow.create_context_workspace(runtime.contexts)

    archive_view = ArchiveExplorer(ArchiveRoot(runtime.contexts.archive_root)).cd(
        f"{runtime.workflows.get("context")().id}/{entity(workflow).id}"
    )
    assert archive_view.current.container.directory == workflow_root.root
    assert archive_view.get("retained-example").open().open().label == "retained"

    subject = runtime.context(workflow).open("sample-entity")
    assert isinstance(subject, WorkspaceEntity)
    assert subject.id == TEST_ENTITY_SHIP
    loaded = runtime.records.from_record(subject.to_record())
    view = runtime.context(loaded)
    assert [entry.name for entry in view.ls()] == ["class", "entity-note"]
    assert view.open("entity-note").label == "about sample"
    entity_root = runtime.contexts.directory(loaded)
    assert (entity_root / "main.json").is_file()
    assert (entity_root / ".git").is_dir()
    assert not (runtime.contexts.partition.directory / ".git").exists()

    runtime.contexts.create_subject_archive(
        WorkspaceItem, constitution="Disposable Type Context."
    )
    runtime.contexts.put(WorkspaceItem, "type-note", WorkspaceItem("about the Type"))
    class_view = runtime.context(WorkspaceItem)
    assert [entry.name for entry in class_view.ls()] == ["entity", "type-note"]
    assert class_view.open("type-note").label == "about the Type"


def test_subject_archive_requires_its_subject_ship_and_exact_type(runtime) -> None:
    workflow = runtime.workflows.get("test")
    root, _ = workflow.create_context_workspace(runtime.contexts)
    assert isinstance(runtime.contexts.subject_archive(workflow), ArchiveFolder)
    assert isinstance(
        runtime.load_object(root.root / "context.json"), SubjectContextRoot
    )
    with pytest.raises(RecordTypeMismatch):
        runtime.load_object(root.root, expected_type=WorkspaceItem)

    binding = json.loads((root.root / "context.json").read_text())
    binding["subject"] = "f1541079-b6ca-4e65-9d9c-4dd524597494"
    (root.root / "context.json").write_text(json.dumps(binding))
    with pytest.raises(ValueError, match="does not match its placement"):
        runtime.context(workflow).ls()


def test_vector_context_uses_positions_without_making_them_identities(runtime) -> None:
    workflow = runtime.workflows.get("test")
    root, _ = workflow.create_context_workspace(runtime.contexts)
    ordered = runtime.context(workflow).open("ordered")
    assert isinstance(ordered, ContextList)
    assert [entry.placement for entry in ordered.ls()] == [0, 1]
    first = ordered.ls()[0]
    assert first.name == "0"
    assert first.open().label == "first"
    assert ordered.open(1).label == "second"

    archive = root.get("ordered").open()
    assert isinstance(archive, ArchiveList)
    runtime.contexts.write(archive, 0, WorkspaceItem("inserted"))
    assert first.open().label == "first"
    fresh = runtime.context(workflow).open("ordered")
    assert isinstance(fresh, ContextList)
    assert [fresh.open(position).label for position in range(3)] == [
        "inserted",
        "first",
        "second",
    ]


def test_only_identified_subjects_can_get_retained_context(runtime) -> None:
    anonymous = WorkspaceItem("runtime only")
    assert runtime.contexts.subject_archive(anonymous) is None
    with pytest.raises(TypeError, match="Only identified subjects"):
        runtime.contexts.create_subject_archive(
            anonymous, constitution="Should not be retained."
        )
    assert [entry.name for entry in runtime.context(anonymous).ls()] == ["class"]


def test_context_writer_retains_wrapper_and_keeps_reference_as_cargo(
    runtime, tmp_path
) -> None:
    workflow = runtime.workflows.get("test")
    root = runtime.contexts.create_subject_archive(
        workflow, constitution="Reference cargo test."
    )
    source = tmp_path / "source.txt"
    source.write_text("source", encoding="utf-8")
    written = runtime.contexts.put(
        workflow,
        "source",
        FileReference(source),
        description="Evidence for this workflow.",
    )

    assert isinstance(written.archive_entry(), ArchiveEntry)
    stored = root.get("source").open()
    assert isinstance(stored, ContextEntry)
    assert stored.to_record()["cargo"]["type"] == "Tarav.Reference.File"
    reference = stored.open()
    assert isinstance(reference, FileReference)
    assert reference.resolve().status == "resolved"

    explorer = runtime.context(workflow)
    discovered = explorer.get("source")
    assert discovered.name == "source"
    assert discovered.description == "Evidence for this workflow."
    assert isinstance(discovered.open(), FileReference)
    assert discovered.open().resolve().target == source
    assert context(discovered) is explorer
    assert isinstance(explorer.subject, FileReference)
    assert explorer.back().subject is workflow


def test_context_entry_cargo_dispatch_uses_the_loading_registry(runtime) -> None:
    record = ContextEntry(cargo=WorkspaceItem("embedded")).to_record()
    loaded = runtime.records.from_record(record)
    assert isinstance(loaded, ContextEntry)
    assert loaded.open().label == "embedded"


def test_context_archive_rejects_unwrapped_leaf(runtime) -> None:
    workflow = runtime.workflows.get("test")
    root = runtime.contexts.create_subject_archive(
        workflow, constitution="Malformed Context fixture."
    )
    root.put("raw", WorkspaceItem("missing wrapper"))

    with pytest.raises(TypeError, match="must contain a ContextEntry"):
        runtime.context(workflow).open("raw")


def test_context_folder_has_an_attachment_at_its_archive_path(runtime) -> None:
    workflow = runtime.workflows.get("test")
    runtime.contexts.create_subject_archive(
        workflow, constitution="Folder attachment test."
    )
    written = runtime.contexts.put_folder(
        workflow,
        "group",
        ArchiveFolder,
        constitution="Grouped Context entries.",
        description="Why this folder exists.",
    )
    backing = written.archive_entry()
    assert isinstance(backing, ArchiveEntry)
    assert isinstance(backing.open(), ArchiveFolder)
    attachment = runtime.load_object(
        backing.artifact_location() / "context.json",
        expected_type=ContextEntry,
    )
    assert attachment.description == "Why this folder exists."
    assert "kind" not in attachment.to_record()
    assert attachment.to_record()["cargo"]["type"] == ("Tarav.Context.StoredDictionary")

    folder = written.open()
    assert isinstance(folder, Context)
    assert isinstance(folder, TaravObject)
    runtime.contexts.write(backing.open(), "item", WorkspaceItem("inside"))
    directly_opened = attachment.open()
    assert isinstance(directly_opened, StoredDictionaryContext)
    assert directly_opened.open("item").label == "inside"
    explorer = runtime.context(workflow)
    assert explorer.get("group").description == "Why this folder exists."
    assert explorer.cd("group").open("item").label == "inside"
    assert explorer.back().pwd() == "/"

    (backing.artifact_location() / "context.json").unlink()
    with pytest.raises(FileNotFoundError):
        runtime.context(workflow).ls()


def test_context_folder_can_be_a_vector_element(runtime) -> None:
    workflow = runtime.workflows.get("test")
    root = runtime.contexts.create_subject_archive(
        workflow, constitution="Vector folder test."
    )
    ordered_entry = runtime.contexts.create_folder(
        root,
        "ordered",
        ArchiveList,
        constitution="Ordered entries.",
    )
    ordered_backing = ordered_entry.archive_entry()
    assert isinstance(ordered_backing, ArchiveEntry)
    ordered = ordered_backing.open()
    assert isinstance(ordered, ArchiveList)
    nested = runtime.contexts.create_folder(
        ordered,
        None,
        ArchiveFolder,
        constitution="Nested entries.",
    )
    nested_backing = nested.archive_entry()
    assert isinstance(nested_backing, ArchiveEntry)
    runtime.contexts.write(nested_backing.open(), "item", WorkspaceItem("deep"))

    explorer = runtime.context(workflow)
    assert explorer.cd("ordered").cd(0).open("item").label == "deep"


def test_context_entry_jump_keeps_explorer_history_across_entity_roots(runtime) -> None:
    workflow = runtime.workflows.get("test")
    workflow.create_context_workspace(runtime.contexts)
    explorer = context(workflow)
    sample_entry = explorer.get("sample-entity")
    assert sample_entry.archive_entry() is None
    assert explorer.subject is workflow

    assert context(sample_entry) is explorer
    assert isinstance(explorer.subject, WorkspaceEntity)
    assert explorer.open("entity-note").label == "about sample"
    assert explorer.back() is explorer
    assert explorer.subject is workflow

    sample = sample_entry.open()
    independent = context(sample)
    assert independent is not explorer
    assert isinstance(independent.subject, WorkspaceEntity)
    assert explorer.subject is workflow
