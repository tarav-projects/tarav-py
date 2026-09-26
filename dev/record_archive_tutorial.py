"""Walk through the first typed Record Archive slice.

Run from tarav-py:

    uv run python dev/record_archive_tutorial.py

Each run creates a fresh Test Workflow Archive under
~/Documents/tarav/archive/<test-workflow-ship>/. Its JSON Records and Git repository remain
available for inspection; existing Tarav data is left alone.
"""

from __future__ import annotations

import sys
from uuid import uuid4

from tarav.archive.records import ArchiveExplorer, ArchiveFolder, ArchiveList
from tarav import ARCHIVE, get_runtime
from tarav.test_workflow import TestEntity, TestItem, TestWorkflow


def main() -> None:
    if len(sys.argv) != 1:
        raise SystemExit("This tutorial takes no arguments.")
    # The runtime registers trusted Record Types and Workflow entities.
    runtime = get_runtime()
    test = runtime.workflows.get("test")
    assert isinstance(test, TestWorkflow)
    partition = ARCHIVE.for_workflow(test)
    run_name = uuid4().hex

    # Archive supplies the workflow's stable Ship path. The Test Workflow
    # chooses only its run name; for_workflow() does not create any data.
    named, ordered = test.create_record_archives(partition, run_name)
    root = partition.directory / run_name
    assert isinstance(named, ArchiveFolder)
    assert isinstance(ordered, ArchiveList)
    print(f"Archive root: {root}")
    print(f"Named Archive: {named.root} (Ship {named.id})")
    print(f"Ordered Archive: {ordered.root} (Ship {ordered.id})")
    print(f"Run Git repository: {root / '.git'}")
    print(
        "Run Git policy:",
        ArchiveExplorer(ARCHIVE)
        .cd(f"{test().id}/{run_name}")
        .current.container.git_settings(),
    )

    # Archive owns the path. Its entries wrap the workflow and stored objects;
    # neither object needs an Archive navigation API.
    print("\nArchive tree")
    print("root entries:", [entry.name for entry in ARCHIVE.ls()])
    print("test entry opens:", type(ARCHIVE.get(str(test().id)).open()).__name__)
    run_cursor = ArchiveExplorer(ARCHIVE).cd(f"{test().id}/{run_name}")
    print("run path:", run_cursor.pwd())
    print("run entries:", [entry.name for entry in run_cursor.ls()])
    print("named entry opens:", type(run_cursor.get("named").open()).__name__)

    # The index names an ArchiveEntry Record. That Record points to an artifact;
    # open() dispatches the artifact to its own registered Type.
    print("\n1. Dictionary Archive")
    print("names:", [entry.name for entry in named.ls()])
    greeting_entry = named.get("greeting")
    greeting = greeting_entry.open()
    assert isinstance(greeting, TestEntity)
    print("placement:", greeting_entry.placement)
    print("entry Record:", named.root / greeting_entry.record_path)
    print("artifact:", named.root / greeting_entry.artifact)
    print("loaded Type:", type(greeting).__name__)
    print("entity Ship:", greeting.id)
    print("entity label:", greeting.label)

    # Reopening reads main.json; listing reads entries.json. Opening one entry
    # reads its small Record, then its artifact only on entry.open().
    reopened_named = ArchiveFolder.from_path(named.root)
    again = reopened_named.get("greeting").open()
    assert isinstance(again, TestEntity)
    assert again.id == greeting.id
    print("reopened with same Ship:", again.id == greeting.id)

    # Vector positions are useful for ordering but do not identify objects.
    print("\n2. Vector Archive")
    reopened_ordered = ArchiveList.from_path(ordered.root)
    before = reopened_ordered.get(1)
    print("before:", [entry.open().label for entry in reopened_ordered.ls()])
    reopened_ordered.insert(1, TestItem("inserted"))
    print("after: ", [entry.open().label for entry in reopened_ordered.ls()])
    print(
        "old second entry moved to position 2:",
        before.record_path == reopened_ordered.get(2).record_path,
    )

    # An artifact can itself be an Archive, with its own entries and artifacts.
    print("\n3. Nested Archives")
    queue_entry = named.put_archive("queue", ArchiveList, constitution="Nested queue")
    queue = queue_entry.open()
    queue.append(TestItem("queued"))
    notes_entry = queue.append_archive(
        ArchiveFolder, constitution="Notes inside the queue"
    )
    notes = notes_entry.open()
    notes.put("note", TestItem("nested note"))
    cursor = ArchiveExplorer(ARCHIVE).cd(f"{test().id}/{run_name}/named/queue/1")
    print("nested path:", cursor.pwd())
    print("nested note:", cursor.get("note").open().label)

    # Context is another view over the same objects: Archive -> Entry -> object.
    print("\n4. Context navigation")
    entries_context = runtime.context(named).open("entries")
    print("entry names:", [entry.name for entry in entries_context.ls()])
    placed = entries_context.open("greeting")
    discovered = runtime.context(placed).open("object")
    print("opened object:", type(discovered).__name__, discovered.label)
    class_entity = runtime.context(type(discovered)).open("entity")
    print(
        "Type's owning Workflow:",
        runtime.workflows.get(class_entity.workflow_ship).workflow_name,
    )

    print("\nInspect these retained files:")
    print(" ", reopened_named.root / "main.json")
    print(" ", reopened_named.root / "entries.json")
    print(" ", reopened_ordered.root / "main.json")
    print(" ", reopened_ordered.root / "entries.json")
    print(" ", reopened_named.root / greeting_entry.record_path)
    print(" ", reopened_named.root / greeting_entry.artifact)
    print(" ", queue.root / "main.json")
    print(" ", notes.root / "main.json")
    print(
        "The run contains one .git directory; named and ordered inherit it. "
        "This script makes no commits."
    )


if __name__ == "__main__":
    main()
