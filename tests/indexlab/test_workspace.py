from __future__ import annotations

import json

import pytest

from tarav.indexlab import (
    EvidenceNeighborhood,
    IndexLabWorkspace,
    IndexRecord,
    MessageRef,
    Operation,
    RecordContext,
    RecordStore,
    SupportSet,
    TurnRef,
    WorkspaceError,
    project_records,
)


def _record(record_id: str = "record-1") -> IndexRecord:
    return IndexRecord(
        id=record_id,
        ordinal=0,
        context=RecordContext(
            session="chat-a",
            horizon=TurnRef(address="turn-2", hash="hash-turn-2"),
        ),
        operation=Operation(
            type="block.create",
            parameters={
                "block_id": "block-1",
                "isoblock_id": "isoblock-1",
                "name": "Touched.Index",
            },
        ),
        support=SupportSet(
            neighborhoods=(
                EvidenceNeighborhood(
                    session="chat-a",
                    grounding=(MessageRef(address="message-1", hash="hash-1"),),
                ),
            ),
        ),
        assertions=({"type": "index.block.semantic-unit"},),
    )


def test_workspace_must_be_initialized_explicitly(tmp_path) -> None:
    root = tmp_path / "lab"

    with pytest.raises(WorkspaceError, match="not an initialized IndexLab workspace"):
        IndexLabWorkspace.open(root)

    workspace = IndexLabWorkspace.initialize(root)

    assert workspace.root == root.resolve()
    assert IndexLabWorkspace.open(root) == workspace
    assert json.loads((root / ".indexlab-workspace.json").read_text())["schema"] == (
        "tarav.indexlab-workspace.v1"
    )


def test_workspace_refuses_nonempty_unowned_directory(tmp_path) -> None:
    root = tmp_path / "existing"
    root.mkdir()
    (root / "production-record.json").write_text("{}")

    with pytest.raises(WorkspaceError, match="non-empty directory"):
        IndexLabWorkspace.initialize(root)


def test_store_assigns_stable_order_and_round_trips_records(tmp_path) -> None:
    workspace = IndexLabWorkspace.initialize(tmp_path / "lab")
    store = RecordStore(workspace)

    first = store.append(_record("record-1"))
    second = store.append(_record("record-2"))

    assert first.ordinal == 1
    assert second.ordinal == 2
    assert store.list() == (first, second)
    assert RecordStore(IndexLabWorkspace.open(workspace.root)).get("record-1") == first


def test_store_replacement_cannot_rewrite_record_context_or_order(tmp_path) -> None:
    store = RecordStore(IndexLabWorkspace.initialize(tmp_path / "lab"))
    original = store.append(_record())
    amended = IndexRecord.from_dict(
        {
            **original.to_dict(),
            "assertions": [{"type": "index.record.reviewed"}],
        }
    )

    store.replace(amended)
    assert store.get(original.id) == amended

    moved = IndexRecord.from_dict(
        {
            **amended.to_dict(),
            "context": {
                "session": "chat-b",
                "horizon": {"address": "turn-9", "hash": "hash-turn-9"},
            },
        }
    )
    with pytest.raises(WorkspaceError, match="original Record.Context"):
        store.replace(moved)


def test_store_purge_removes_bad_indexing_record(tmp_path) -> None:
    store = RecordStore(IndexLabWorkspace.initialize(tmp_path / "lab"))
    record = store.append(_record())

    store.purge(record.id)

    assert store.list() == ()


def test_context_local_repair_and_purge_recompute_the_projection(tmp_path) -> None:
    store = RecordStore(IndexLabWorkspace.initialize(tmp_path / "lab"))
    block = store.append(_record("record-block"))
    line_draft = IndexRecord(
        id="record-line",
        ordinal=0,
        context=block.context,
        operation=Operation(
            type="line.capture",
            parameters={
                "line_id": "line-1",
                "isoline_id": "isoline-1",
                "block_id": "block-1",
                "label": "^semantic-tape",
                "text": "A semantic tap.",
            },
        ),
        support=block.support,
    )
    line = store.append(line_draft)
    repaired = IndexRecord.from_dict(
        {
            **line.to_dict(),
            "operation": {
                **line.operation.to_dict(),
                "parameters": {
                    **line.operation.parameters,
                    "text": "A semantic tape.",
                },
            },
        }
    )

    store.replace(repaired)
    assert project_records(store.list()).line("line-1").text == "A semantic tape."

    store.purge(repaired.id)
    assert project_records(store.list()).block("block-1").line_ids == ()


def test_initialize_reopens_a_populated_workspace(tmp_path) -> None:
    """A valid marker is sufficient to reopen; records must not lock init out."""

    root = tmp_path / "lab"
    first = IndexLabWorkspace.initialize(root)
    store = RecordStore(first)
    store.append(_record("record-init"))

    again = IndexLabWorkspace.initialize(root)

    assert again.root == first.root
    assert len(RecordStore(again).list()) == 1


def test_initialize_still_refuses_an_unmarked_non_empty_directory(tmp_path) -> None:
    root = tmp_path / "occupied"
    root.mkdir()
    (root / "unrelated.txt").write_text("keep me", "utf-8")

    with pytest.raises(WorkspaceError):
        IndexLabWorkspace.initialize(root)


def test_load_reports_unloadable_cargo_instead_of_raising(tmp_path) -> None:
    """`list` still fails closed; `load` hands corruption back as a defect."""

    store = RecordStore(IndexLabWorkspace.initialize(tmp_path / "lab"))
    store.append(_record("record-good"))
    store._depot.insert({"id": "record-broken", "schema": "tarav.indexlab-record.v1"})

    records, defects = store.load()

    assert [record.id for record in records] == ["record-good"]
    assert [defect.record_id for defect in defects] == ["record-broken"]
    assert defects[0].error

    with pytest.raises(WorkspaceError):
        store.list()
