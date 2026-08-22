from __future__ import annotations

import json
from uuid import UUID

import pytest

from tarav.bloberia import BloberiaDepot
from tarav.indexlab import (
    EvidenceNeighborhood,
    IndexLibrary,
    IndexRecord,
    IndexWorkspace,
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


def _workspace(tmp_path, name: str = "main", *, touch_adapter: str = "chatlas"):
    library = IndexLibrary.initialize(tmp_path / "library")
    return library.create_workspace(name, touch_adapter=touch_adapter)


def test_library_owns_a_registry_but_is_not_a_depot(tmp_path) -> None:
    root = tmp_path / "library"

    library = IndexLibrary.initialize(root)

    assert library.root == root.resolve()
    assert json.loads((root / "library.json").read_text("utf-8")) == {
        "schema": "tarav.index-library.v1",
        "workspaces": {},
    }
    assert not (root / "meta.json").exists()
    assert IndexLibrary.open(root) == library


def test_workspace_has_stable_identity_and_is_the_depot_and_git_root(tmp_path) -> None:
    library = IndexLibrary.initialize(tmp_path / "library")

    workspace = library.create_workspace("main", touch_adapter="chatlas")

    UUID(workspace.id)
    assert workspace.root == library.root / "workspaces" / workspace.id
    assert workspace.touch_adapter == "chatlas"
    assert (workspace.root / ".git").is_dir()
    assert json.loads((workspace.root / "workspace.json").read_text("utf-8")) == {
        "schema": "tarav.index-workspace.v1",
        "id": workspace.id,
        "touch_adapter": "chatlas",
    }
    depot_meta = json.loads((workspace.root / "meta.json").read_text("utf-8"))
    assert depot_meta["type"] == "shards"
    assert depot_meta["key"] == "id"
    assert depot_meta["git"] == "."
    assert BloberiaDepot(workspace.root).all({}) == ()
    assert library.resolve("main") == workspace
    assert library.resolve(workspace.id) == workspace
    assert IndexWorkspace.open(workspace.root) == workspace


def test_library_creates_isolated_named_workspaces(tmp_path) -> None:
    library = IndexLibrary.initialize(tmp_path / "library")
    main = library.create_workspace("main")
    scenarios = library.create_workspace("approval-scenarios", touch_adapter="mock")

    RecordStore(main).append(_record("record-main"))
    RecordStore(scenarios).append(_record("record-scenario"))

    assert [item.name for item in library.list_workspaces()] == [
        "approval-scenarios",
        "main",
    ]
    assert [record.id for record in RecordStore(main).list()] == ["record-main"]
    assert [record.id for record in RecordStore(scenarios).list()] == [
        "record-scenario"
    ]


@pytest.mark.parametrize("name", ["../escape", "/absolute", ".hidden", "two words"])
def test_library_rejects_names_that_are_not_safe_selectors(tmp_path, name) -> None:
    library = IndexLibrary.initialize(tmp_path / "library")

    with pytest.raises(WorkspaceError, match="workspace name"):
        library.create_workspace(name)


def test_library_rejects_duplicate_names_and_unknown_selectors(tmp_path) -> None:
    library = IndexLibrary.initialize(tmp_path / "library")
    library.create_workspace("main")

    with pytest.raises(WorkspaceError, match="already exists"):
        library.create_workspace("main")
    with pytest.raises(WorkspaceError, match="unknown Index.Workspace"):
        library.resolve("absent")


def test_library_and_workspace_refuse_nonempty_unowned_directories(tmp_path) -> None:
    occupied_library = tmp_path / "occupied-library"
    occupied_library.mkdir()
    (occupied_library / "unrelated.txt").write_text("keep me", "utf-8")

    with pytest.raises(WorkspaceError, match="non-empty directory"):
        IndexLibrary.initialize(occupied_library)

    occupied_workspace = tmp_path / "occupied-workspace"
    occupied_workspace.mkdir()
    (occupied_workspace / "unrelated.txt").write_text("keep me", "utf-8")
    with pytest.raises(WorkspaceError, match="non-empty directory"):
        IndexWorkspace.initialize(
            occupied_workspace,
            workspace_id="fbd0f237-d76c-4ad6-9ca5-87676274f3eb",
            touch_adapter="chatlas",
        )


def test_store_uses_workspace_root_as_bloberia_depot(tmp_path) -> None:
    workspace = _workspace(tmp_path)
    store = RecordStore(workspace)

    stored = store.append(_record("record-queryable"))

    assert store.depot_root == workspace.root
    assert BloberiaDepot(workspace.root).first(
        {"id": {"equals": stored.id}}
    ) == stored.to_dict()
    assert not (workspace.root / "records" / "meta.json").exists()


def test_store_assigns_stable_order_and_round_trips_records(tmp_path) -> None:
    workspace = _workspace(tmp_path)
    store = RecordStore(workspace)

    first = store.append(_record("record-1"))
    second = store.append(_record("record-2"))

    assert first.ordinal == 1
    assert second.ordinal == 2
    assert store.list() == (first, second)
    assert RecordStore(IndexWorkspace.open(workspace.root)).get("record-1") == first


def test_store_replacement_cannot_rewrite_record_context_or_order(tmp_path) -> None:
    store = RecordStore(_workspace(tmp_path))
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
    store = RecordStore(_workspace(tmp_path))
    record = store.append(_record())

    store.purge(record.id)

    assert store.list() == ()


def test_context_local_repair_and_purge_recompute_the_projection(tmp_path) -> None:
    store = RecordStore(_workspace(tmp_path))
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


def test_initializers_reopen_populated_owned_surfaces(tmp_path) -> None:
    library = IndexLibrary.initialize(tmp_path / "library")
    workspace = library.create_workspace("main")
    RecordStore(workspace).append(_record("record-init"))

    assert IndexLibrary.initialize(library.root) == library
    assert IndexWorkspace.initialize(
        workspace.root,
        workspace_id=workspace.id,
        touch_adapter="chatlas",
    ) == workspace
    assert len(RecordStore(workspace).list()) == 1


def test_load_reports_unloadable_cargo_instead_of_raising(tmp_path) -> None:
    """`list` still fails closed; `load` hands corruption back as a defect."""

    store = RecordStore(_workspace(tmp_path))
    store.append(_record("record-good"))
    store._depot.insert({"id": "record-broken", "schema": "tarav.indexlab-record.v1"})

    records, defects = store.load()

    assert [record.id for record in records] == ["record-good"]
    assert [defect.record_id for defect in defects] == ["record-broken"]
    assert defects[0].error

    with pytest.raises(WorkspaceError):
        store.list()
