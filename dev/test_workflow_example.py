"""Full Test Workflow example: one Entity in Archive and Context.

Run from tarav-py:

    uv run python dev/test_workflow_example.py

Each run creates fresh, inspectable fixtures under ~/Documents/tarav/archive/.
The Test Workflow's constitution marks these as synthetic test data. The
example does not delete earlier runs or make Git commits.
"""

from __future__ import annotations

__test__ = False

import sys
from pathlib import Path
from uuid import uuid4

from tarav import ARCHIVE, get_runtime
from tarav.l2.context import context
from tarav.l1.context import ContextEntry
from tarav.l1.archive.records import (
    ArchiveEntry,
    ArchiveExplorer,
    ArchiveFolder,
    ArchiveList,
    ArchiveRoot,
)
from tarav.runtime import TaravRuntime
from tarav.test_workflow import TestEntity, TestItem, TestWorkflow


def _show_tree(root: Path) -> None:
    """Show retained data without dumping Git's implementation files."""

    print(root)
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if ".git" not in relative.parts:
            suffix = "/" if path.is_dir() else ""
            print(f"  {relative}{suffix}")


def run_example(archive: ArchiveRoot, runtime: TaravRuntime) -> tuple[Path, Path]:
    """Build and inspect one isolated Test run and one Entity Context root."""

    test = runtime.workflows.get("test")
    assert test is TestWorkflow
    run_name = uuid4().hex

    # The Test Workflow owns this partition. The Archive owns placement and
    # storage; TestEntity and TestItem keep their own Type and Record semantics.
    partition = archive.for_workflow(test)
    named, ordered = test.create_record_archives(partition, run_name)
    run_root = partition.directory / run_name
    assert isinstance(named, ArchiveFolder)
    assert isinstance(ordered, ArchiveList)

    # ls() reads the placement index. get() validates one ArchiveEntry Record;
    # entry.open() dispatches its artifact to the trusted TestEntity Type.
    explorer = ArchiveExplorer(archive).cd(f"{test().id}/{run_name}/named")
    print("Archive route:", explorer.pwd())
    print("Archive entries:", [entry.name for entry in explorer.ls()])
    greeting_entry = explorer.get("greeting")
    greeting = greeting_entry.open()
    assert isinstance(greeting, TestEntity)
    assert explorer.pwd() == f"/{test().id}/{run_name}/named"  # open does not cd
    print("Archived Entity:", greeting.id, greeting.label)
    print("Entry Record:", named.root / greeting_entry.record_path)
    print("Entity Record:", greeting_entry.artifact_location())
    print("Ordered values:", [entry.open().label for entry in ordered.ls()])

    explorer.cd("..")
    assert explorer.back().pwd() == f"/{test().id}/{run_name}/named"
    assert explorer.forward().pwd() == f"/{test().id}/{run_name}"

    # The Entity Ship gives Context a durable attachment point. This root
    # lives in Context's Archive partition, independently of the Test run.
    context_root = runtime.contexts.create_subject_archive(
        greeting, constitution="Disposable Context for a Test Entity."
    )
    runtime.contexts.put(
        greeting,
        "note",
        TestItem("hello from Context"),
        description="A retained note about the archived greeting Entity.",
    )
    details_entry = runtime.contexts.put_folder(
        greeting,
        "details",
        ArchiveFolder,
        constitution="Named Test Entity context details.",
        description="Named details about this synthetic Entity.",
    )
    details_backing = details_entry.archive_entry()
    assert isinstance(details_backing, ArchiveEntry)
    details = details_backing.open()
    assert isinstance(details, ArchiveFolder)
    runtime.contexts.write(details, "source", TestItem("Test Workflow fixture"))

    history_entry = runtime.contexts.put_folder(
        greeting,
        "history",
        ArchiveList,
        constitution="Ordered Test Entity context history.",
    )
    history_backing = history_entry.archive_entry()
    assert isinstance(history_backing, ArchiveEntry)
    history = history_backing.open()
    assert isinstance(history, ArchiveList)
    runtime.contexts.write(history, None, TestItem("created"))
    runtime.contexts.write(history, None, TestItem("inspected"))

    # Reopen from the retained Archive Record. Context is found by Entity
    # identity, so the newly loaded Python object sees the same attachments.
    reopened = ArchiveFolder.from_path(named.root).get("greeting").open()
    assert isinstance(reopened, TestEntity)
    assert reopened is not greeting and reopened.id == greeting.id
    view = runtime.context(reopened)
    print("Context root:", view.pwd())
    print("Context entries:", [entry.name for entry in view.ls()])
    assert view.open("note").label == "hello from Context"
    assert view.get("note").description.startswith("A retained note")
    assert view.cd("details").open("source").label == "Test Workflow fixture"
    print("Context details route:", view.pwd())
    assert view.back().pwd() == "/"
    assert view.forward().pwd() == "/details"
    assert view.cd("..").cd("history").open(1).label == "inspected"
    print("Context history:", [entry.open().label for entry in view.ls()])

    # Following a ContextEntry into its cargo's Context keeps this explorer's
    # history. A direct context(reopened) call would start a new explorer.
    view.cd("/")
    note_entry = view.get("note")
    assert isinstance(note_entry, ContextEntry)
    followed = context(note_entry)
    assert followed is view
    note_class_context = followed.open("class")
    print("Followed note Type:", note_class_context.open("entity").name)
    assert followed.back().pwd() == "/"

    # Archive can also reach the physical Context backing. It opens the
    # wrapper Record first; ContextEntry.open() then opens its TestItem cargo.
    retained = ArchiveExplorer(archive).cd(f"{runtime.workflows.get("context")().id}/{greeting.id}")
    stored_wrapper = retained.get("note").open()
    assert isinstance(stored_wrapper, ContextEntry)
    assert stored_wrapper.open().label == "hello from Context"
    print("Context Archive route:", retained.pwd())

    print("\nTest Workflow run on disk:")
    _show_tree(run_root)
    print("\nEntity Context on disk:")
    _show_tree(context_root.root)
    return run_root, context_root.root


def main() -> None:
    if len(sys.argv) != 1:
        raise SystemExit("This example takes no arguments.")
    run_example(ARCHIVE, get_runtime())


if __name__ == "__main__":
    main()
