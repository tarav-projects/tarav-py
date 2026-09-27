from __future__ import annotations

import json
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from typing import Literal

import pytest

from tarav import ARCHIVE, get_runtime, set_runtime
from tarav.l0.kernel import (
    Ship,
    TaravClass,
    TaravEnvironment,
    TypeShip,
    UnknownRecordType,
)
from tarav.archive.records import (
    ArchiveEntry,
    ArchiveExplorer,
    ArchiveFolder,
    ArchivePartition,
    ArchiveRoot,
    ArchiveList,
)
from tarav.runtime import create_runtime
from tarav.test_workflow import TestItem as WorkspaceItem
from tarav.test_workflow import TestEntity as WorkspaceEntity
from tarav.test_workflow import TestWorkflow as WorkspaceWorkflow
from tarav.test_workflow import TEST_WORKFLOW_SHIP


class ExternalWorkspaceItem(WorkspaceItem):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("0827c57e-1cf9-4b75-9c9d-c1332ddca986"),
            name="Tarav.Test.ExternalItem",
            workflow=TEST_WORKFLOW_SHIP,
        )

    class RecordInterface(WorkspaceItem.RecordInterface):
        type: Literal["Tarav.Test.ExternalItem"]


def test_test_workflow_stores_and_reopens_both_archive_structures(tmp_path) -> None:
    runtime = get_runtime()
    workflow = runtime.workflows.get("test")
    assert workflow is WorkspaceWorkflow
    archive = ArchiveRoot(tmp_path / "archive")
    partition = archive.for_workflow(workflow)
    run_name = "first-run"
    root = partition.directory / run_name

    named, ordered = workflow.create_record_archives(partition, run_name)

    assert [entry.name for entry in named.ls()] == ["greeting"]
    named_main = json.loads((root / "named" / "main.json").read_text())
    ordered_main = json.loads((root / "ordered" / "main.json").read_text())
    assert set(named_main) == {"type", "id", "constitution"}
    assert set(ordered_main) == {"type", "id", "constitution"}
    named_entries = json.loads((root / "named" / "entries.json").read_text())
    ordered_entries = json.loads((root / "ordered" / "entries.json").read_text())
    assert set(named_entries) == {"greeting"}
    assert named_entries["greeting"].startswith("records/")
    assert len(ordered_entries) == 2
    assert all(path.startswith("records/") for path in ordered_entries)
    greeting = named.get("greeting")
    assert isinstance(greeting, ArchiveEntry)
    assert greeting.placement == "greeting"
    assert greeting.archive == named.id
    assert greeting.record_path == named_entries["greeting"]
    assert greeting.artifact.startswith("artifacts/")
    assert json.loads((named.root / greeting.record_path).read_text()) == {
        "type": "Tarav.RecordArchive.Entry",
        "archive": str(named.id),
        "artifact": greeting.artifact,
    }
    greeting_object = greeting.open()
    assert isinstance(greeting_object, WorkspaceEntity)
    assert greeting_object.label == "hello tarav"
    assert [entry.placement for entry in ordered.ls()] == [0, 1]
    assert [entry.open().label for entry in ordered.ls()] == ["first", "second"]
    assert (root / ".git").is_dir()
    assert not (partition.directory / ".git").exists()
    assert not (root / "named" / ".git").exists()
    assert not (root / "ordered" / ".git").exists()
    for child in ("named", "ordered"):
        assert subprocess.run(
            ["git", "-C", str(root / child), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip() == str(root)
    assert subprocess.run(
        ["git", "-C", str(root / "named"), "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout

    reopened_named = ArchiveFolder.from_path(root / "named")
    reopened_ordered = ArchiveList.from_path(root / "ordered")
    assert reopened_named.entries == named.entries
    assert reopened_ordered.entries == ordered.entries
    assert reopened_named.id == named.id
    assert reopened_named.constitution == named.constitution
    assert isinstance(reopened_named.get("greeting").open(), WorkspaceEntity)
    assert reopened_named.get("greeting").open().id == greeting_object.id
    assert [entry.open().label for entry in reopened_ordered.ls()] == [
        "first",
        "second",
    ]

    old_second = reopened_ordered.get(1)
    reopened_ordered.insert(1, WorkspaceItem("inserted"))
    assert [entry.open().label for entry in reopened_ordered.ls()] == [
        "first",
        "inserted",
        "second",
    ]
    assert old_second.record_path == reopened_ordered.get(2).record_path
    assert old_second.artifact == reopened_ordered.get(2).artifact
    assert old_second.placement == 1  # a placement snapshot, not object identity
    assert "placement" not in old_second.to_record()
    assert len(json.loads((root / "ordered" / "entries.json").read_text())) == 3

    archive_context = runtime.context(reopened_named)
    entries_context = archive_context.open("entries")
    assert [entry.name for entry in entries_context.ls()] == ["greeting"]
    placed = entries_context.open("greeting")
    assert isinstance(placed, ArchiveEntry)
    assert runtime.context(placed).open("object").label == "hello tarav"


def test_archive_entries_can_open_and_navigate_nested_typed_archives(tmp_path) -> None:
    workflow = get_runtime().workflows.get("test")
    archive = ArchiveRoot(tmp_path / "archive")
    run = archive.for_workflow(workflow).create_directory("nested-run")
    named = run.create_dictionary("named", constitution="Named examples")
    greeting = named.put(
        "greeting",
        WorkspaceEntity(Ship("b1ee352e-1b19-42a7-88ee-0082290fcb20"), "hello"),
    )
    queue_entry = named.put_archive("queue", ArchiveList, constitution="Queue")
    queue = queue_entry.open()
    assert isinstance(queue, ArchiveList)
    assert queue_entry.directory
    assert queue.root == named.root / queue_entry.artifact
    assert not (queue.root / ".git").exists()
    assert greeting.open().label == "hello"
    queue.append(WorkspaceItem("first"))
    notes_entry = queue.append_archive(ArchiveFolder, constitution="Notes")
    notes = notes_entry.open()
    assert isinstance(notes, ArchiveFolder)
    notes.put("note", WorkspaceItem("nested"))

    cursor = ArchiveExplorer(archive).cd(f"{workflow().id}/nested-run/named/queue/1")
    assert cursor.pwd() == f"/{workflow().id}/nested-run/named/queue/1"
    assert cursor.current.container.root == notes.root
    assert cursor.get("note").open().label == "nested"
    assert cursor.cd("..").get(0).open().label == "first"
    with pytest.raises(NotADirectoryError):
        ArchiveExplorer(archive).cd(f"{workflow().id}/nested-run/named/greeting")


def test_archive_handles_reload_indexes_before_writing(tmp_path) -> None:
    named = ArchiveFolder.create(tmp_path / "named", constitution="Shared")
    named_other = ArchiveFolder.from_path(named.root)
    ordered = ArchiveList.create(tmp_path / "ordered", constitution="Shared")
    ordered_other = ArchiveList.from_path(ordered.root)

    assert named_other.ls() == ()
    assert ordered_other.ls() == ()
    named.put("first", WorkspaceItem("one"))
    named_other.put("second", WorkspaceItem("two"))
    ordered.append(WorkspaceItem("one"))
    ordered_other.append(WorkspaceItem("two"))

    assert (
        [entry.name for entry in named.ls()]
        == [entry.name for entry in named_other.ls()]
        == ["first", "second"]
    )
    assert [entry.open().label for entry in ordered.ls()] == ["one", "two"]
    assert [entry.open().label for entry in ordered_other.ls()] == [
        "one",
        "two",
    ]


def test_archive_lock_preserves_concurrent_dictionary_and_vector_writes(
    tmp_path,
) -> None:
    named = ArchiveFolder.create(tmp_path / "named", constitution="Shared")
    ordered = ArchiveList.create(tmp_path / "ordered", constitution="Shared")

    def write(position: int) -> None:
        ArchiveFolder.from_path(named.root).put(
            f"entry-{position}", WorkspaceItem(str(position))
        )
        ArchiveList.from_path(ordered.root).append(WorkspaceItem(str(position)))

    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(write, range(12)))

    reopened = ArchiveFolder.from_path(named.root)
    assert {entry.name for entry in reopened.ls()} == {
        f"entry-{position}" for position in range(12)
    }
    assert {entry.open().label for entry in reopened.ls()} == {
        str(position) for position in range(12)
    }
    reopened_ordered = ArchiveList.from_path(ordered.root)
    assert len(reopened_ordered.ls()) == 12
    assert {entry.open().label for entry in reopened_ordered.ls()} == {
        str(position) for position in range(12)
    }


def test_archive_creation_is_explicit_and_never_overwrites_a_root(tmp_path) -> None:
    root = tmp_path / "already-here"
    root.mkdir()
    (root / "important.txt").write_text("keep")

    with pytest.raises(FileExistsError):
        ArchiveFolder.create(root, constitution="Test")
    assert (root / "important.txt").read_text() == "keep"


def test_git_config_can_create_a_new_repository_at_a_child(tmp_path) -> None:
    workflow = get_runtime().workflows.get("test")
    partition = ArchiveRoot(tmp_path / "archive").for_workflow(workflow)
    run = partition.create_directory("run")
    config = run.git_config_path
    config.write_text('{"children": "new"}\n', encoding="utf-8")
    run.gitignore_path.write_text("*.tmp\n", encoding="utf-8")

    settings = run.git_settings()
    assert settings["children"] == "new"
    assert settings["source"] == config
    assert settings["repository"] == run.directory
    assert settings["gitignore_path"] == run.gitignore_path
    assert settings["gitignore_exists"] is True

    child = run.create_dictionary("named", constitution="Nested history")
    assert (child.root / ".git").is_dir()
    assert child.git_config_path == child.root / "git-config.json"
    assert child.gitignore_path == child.root / ".gitignore"
    assert child.gitignore_exists is False
    assert run.git_settings()["repository"] == run.directory


def test_git_policy_stops_at_workflow_boundary_and_rejects_invalid_config(
    tmp_path,
) -> None:
    workflow = get_runtime().workflows.get("test")
    archive = ArchiveRoot(tmp_path / "archive")
    partition = archive.for_workflow(workflow)
    partition.directory.mkdir(parents=True)
    config = partition.git_config_path
    config.write_text('{"children": "inherit"}\n', encoding="utf-8")
    assert partition.git_settings()["source"] == config
    with pytest.raises(ValueError, match="requires a parent repository"):
        partition.create_directory("run")
    assert not (partition.directory / "run").exists()

    config.write_text('{"children": "new"}\n', encoding="utf-8")
    run = partition.create_directory("run")
    assert (run.directory / ".git").is_dir()
    assert run.git_settings()["children"] == "auto"
    assert run.git_settings()["source"] is None

    config.write_text('{"children": "unsupported"}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid Archive Git children policy"):
        partition.create_directory("another")
    assert not (partition.directory / "another").exists()

    config.unlink()
    (partition.directory / ".git").mkdir()
    with pytest.raises(ValueError, match="Workflow partition must not"):
        run.create_vector("ordered", constitution="Forbidden parent")


def test_archive_root_git_is_not_inherited_and_existing_nested_repos_still_open(
    tmp_path,
) -> None:
    root = tmp_path / "archive"
    root.mkdir()
    subprocess.run(["git", "init", "--quiet", str(root)], check=True)
    workflow = get_runtime().workflows.get("test")
    partition = ArchiveRoot(root).for_workflow(workflow)
    run = partition.create_directory("run")
    assert (run.directory / ".git").is_dir()
    assert not (partition.directory / ".git").exists()

    # Older Archive runs may already have a repository in each typed child.
    nested = ArchiveFolder.create(run.directory / "old-named", constitution="Old")
    nested.put("item", WorkspaceItem("retained"))
    assert (nested.root / ".git").is_dir()
    assert (
        ArchiveExplorer(ArchiveRoot(root))
        .cd(f"{workflow().id}/run/old-named")
        .get("item")
        .open()
        .label
        == "retained"
    )


def test_archive_requires_its_entry_registry(tmp_path) -> None:
    archive = ArchiveFolder.create(tmp_path / "records", constitution="Test")
    (archive.root / "entries.json").unlink()
    reopened = ArchiveFolder.from_path(archive.root)
    with pytest.raises(FileNotFoundError):
        reopened.ls()


def test_archive_root_requires_canonical_workflow_ship_partitions(tmp_path) -> None:
    root = tmp_path / "archive"
    (root / "test").mkdir(parents=True)
    with pytest.raises(ValueError, match="Workflow Ship"):
        ArchiveRoot(root).ls()


def test_archive_tree_navigates_placements_without_changing_workflow_objects(
    tmp_path,
) -> None:
    runtime = get_runtime()
    workflow = runtime.workflows.get("test")
    root = tmp_path / "archive"
    run = "12345678123456781234567812345678"
    archive = ArchiveRoot(root)
    partition = archive.for_workflow(workflow)
    assert archive.for_workflow(WorkspaceWorkflow).directory == partition.directory
    assert partition.directory == root / str(workflow().id)
    assert not partition.directory.exists()
    restored_partition = runtime.records.from_record(partition.to_record())
    assert restored_partition.directory == partition.directory
    named, ordered = workflow.create_record_archives(partition, run)

    assert ARCHIVE is not archive
    assert (str(workflow().id),) == tuple(entry.name for entry in archive.ls())
    workflow_entry = archive.get(str(workflow().id))
    assert isinstance(workflow_entry, ArchiveEntry)
    assert isinstance(workflow_entry.open(), ArchivePartition)
    assert workflow_entry.open().owning_workflow() is workflow
    assert not hasattr(workflow, "cd")

    test_cursor = ArchiveExplorer(archive).cd(str(workflow().id))
    run_entry = test_cursor.get(run)
    assert isinstance(run_entry.open(), ArchivePartition)
    run_cursor = ArchiveExplorer(archive).cd(f"{workflow().id}/{run}")
    assert {entry.name for entry in run_cursor.ls()} == {"named", "ordered"}
    assert run_cursor.get("named").open().id == named.id
    assert run_cursor.get("ordered").open().id == ordered.id
    assert run_cursor.cd("named").get("greeting").open().label == "hello tarav"
    assert [
        entry.open().label
        for entry in ArchiveExplorer(archive).cd(f"{workflow().id}/{run}/ordered").ls()
    ] == [
        "first",
        "second",
    ]
    assert ArchiveExplorer(archive).pwd() == "/"
    assert test_cursor.pwd() == f"/{workflow().id}"
    with pytest.raises(NotADirectoryError):
        ArchiveExplorer(archive).cd(f"{workflow().id}/{run}/named/greeting")
    stored = named.get("greeting")
    (named.root / stored.artifact).write_text('{"type":"Unregistered.Test"}\n')
    assert [
        entry.name
        for entry in ArchiveExplorer(archive).cd(f"{workflow().id}/{run}/named").ls()
    ] == ["greeting"]
    with pytest.raises(UnknownRecordType):
        ArchiveExplorer(archive).cd(f"{workflow().id}/{run}/named").get("greeting").open()


def test_dictionary_name_is_not_a_ship_and_unknown_types_remain_inspectable(
    tmp_path,
) -> None:
    archive = ArchiveFolder.create(tmp_path / "records", constitution="Test")
    entry = archive.put("ordinary-name", WorkspaceItem("known"))
    assert not isinstance(entry.placement, Ship)
    assert archive.get("ordinary-name").to_record()["archive"] == str(archive.id)
    with pytest.raises(FileExistsError):
        archive.put("ordinary-name", WorkspaceItem("replacement"))
    with pytest.raises(ValueError, match="ordinary path segment"):
        archive.put("../escape", WorkspaceItem("bad"))

    entry_path = archive.root / entry.artifact
    entry_path.write_text('{"type":"Unregistered.Test"}\n')
    assert [entry.name for entry in archive.ls()] == ["ordinary-name"]
    assert archive.get("ordinary-name").artifact == entry.artifact
    with pytest.raises(UnknownRecordType, match="not registered"):
        archive.get("ordinary-name").open()


def test_archive_entry_record_cannot_escape_its_records_directory(tmp_path) -> None:
    archive = ArchiveFolder.create(tmp_path / "records", constitution="Test")
    entry = archive.put("item", WorkspaceItem("kept"))
    outside = tmp_path / "outside.json"
    outside.write_text((archive.root / entry.record_path).read_text())
    record = archive.root / entry.record_path
    record.unlink()
    record.symlink_to(outside)

    with pytest.raises(ValueError, match="escapes its records directory"):
        archive.get("item")


@pytest.mark.parametrize(
    ("damage", "error", "message"),
    [
        ("missing_record", FileNotFoundError, "No such file"),
        ("wrong_parent", ValueError, "does not belong"),
        ("invalid_entry", ValueError, "artifacts/"),
        ("missing_artifact", FileNotFoundError, "artifact is missing"),
    ],
)
def test_archive_get_fails_on_broken_indexed_entries(
    tmp_path, damage, error, message
) -> None:
    archive = ArchiveFolder.create(tmp_path / "records", constitution="Test")
    entry = archive.put("item", WorkspaceItem("kept"))
    record_path = archive.root / entry.record_path
    artifact_path = archive.root / entry.artifact

    if damage == "missing_record":
        record_path.unlink()
    elif damage in {"wrong_parent", "invalid_entry"}:
        record = json.loads(record_path.read_text())
        if damage == "wrong_parent":
            record["archive"] = "ec885738-bd64-4ba8-a223-5a92f0f25843"
        else:
            record["artifact"] = "elsewhere/item.json"
        record_path.write_text(json.dumps(record))
    else:
        artifact_path.unlink()

    assert [entry.name for entry in archive.ls()] == ["item"]
    with pytest.raises(error, match=message):
        archive.get("item")


def test_archive_get_fails_when_nested_archive_loses_main_record(tmp_path) -> None:
    archive = ArchiveFolder.create(tmp_path / "records", constitution="Test")
    entry = archive.put_archive("nested", ArchiveList, constitution="Nested")
    (archive.root / entry.artifact / "main.json").unlink()

    with pytest.raises(FileNotFoundError, match="has no main.json"):
        archive.get("nested")


def test_archive_cannot_write_through_a_redirected_artifacts_directory(
    tmp_path,
) -> None:
    archive = ArchiveFolder.create(tmp_path / "records", constitution="Test")
    outside = tmp_path / "outside"
    outside.mkdir()
    shutil.rmtree(archive.root / "artifacts")
    (archive.root / "artifacts").symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="artifacts/ directory is redirected"):
        archive.put("item", WorkspaceItem("kept"))
    assert archive.ls() == ()
    assert list(outside.iterdir()) == []


def test_archive_uses_the_selected_global_runtime_for_external_types(tmp_path) -> None:
    previous = get_runtime()
    environment = TaravEnvironment()
    environment.bind_type("Tarav.Test.ExternalItem", ExternalWorkspaceItem)
    selected = create_runtime(environment=environment)
    try:
        set_runtime(selected)
        assert get_runtime() is selected
        archive = ArchiveFolder.create(tmp_path / "external", constitution="Test")
        archive.put("external", ExternalWorkspaceItem("outside tarav"))
        reopened = ArchiveFolder.from_path(archive.root)
        loaded = reopened.get("external").open()
        assert type(loaded) is ExternalWorkspaceItem
        assert loaded.label == "outside tarav"
    finally:
        set_runtime(previous)
