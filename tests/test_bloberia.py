# $kw: ^test-bloberia --from Agentos.Bloberia --note [DF] boundary tests for the reviewed Bloberia record and depot contract ^c20260724-31u
from __future__ import annotations

import json
import multiprocessing
from pathlib import Path
from uuid import UUID

import pytest

from agentos.bloberia import (
    BloberiaDepot,
    InvalidBloberiaInputError,
    RecordExistsError,
    RecordNotFoundError,
)


def _edit_after_signal(
    root: str, record_id: str, value: int, start: object
) -> None:
    start.wait()  # type: ignore[attr-defined]
    BloberiaDepot(root).edit(record_id, {"value": value})


@pytest.mark.parametrize(
    "value",
    [
        {"kind": "example", "nested": {"enabled": True}},
        [1, "two", None],
        "scalar",
        42,
        False,
        None,
    ],
)
def test_create_get_round_trip_for_arbitrary_json_values(
    tmp_path: Path, value: object
) -> None:
    depot = BloberiaDepot(tmp_path / "bloberia")

    created = depot.create(value)
    loaded = BloberiaDepot(depot.root).get(created.id)

    assert loaded == created
    assert loaded.value == value
    assert UUID(loaded.id).version == 4
    assert loaded.created_at == loaded.updated_at
    assert loaded.revision == 1
    assert loaded.as_dict() == {
        "_bloberia": {
            "id": loaded.id,
            "created_at": loaded.created_at,
            "updated_at": loaded.updated_at,
            "revision": 1,
        },
        "value": value,
    }


def test_public_records_are_detached_from_persisted_state(tmp_path: Path) -> None:
    depot = BloberiaDepot(tmp_path / "bloberia")
    created = depot.create({"nested": {"items": [1]}})

    created.value["nested"]["items"].append(2)  # type: ignore[index,union-attr]

    assert depot.get(created.id).value == {"nested": {"items": [1]}}


def test_get_missing_record_is_distinct(tmp_path: Path) -> None:
    depot = BloberiaDepot(tmp_path / "bloberia")

    with pytest.raises(RecordNotFoundError, match="record does not exist"):
        depot.get("a8dcf050-086a-4fb6-8bd4-a24167c94584")


def test_create_rejects_non_json_value(tmp_path: Path) -> None:
    depot = BloberiaDepot(tmp_path / "bloberia")

    with pytest.raises(InvalidBloberiaInputError, match="JSON serializable"):
        depot.create({1, 2, 3})


def test_generated_identity_collision_never_overwrites(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    depot = BloberiaDepot(tmp_path / "bloberia")
    record_id = "a8dcf050-086a-4fb6-8bd4-a24167c94584"
    monkeypatch.setattr(
        "agentos.bloberia.core.generate_uuid4_string", lambda: record_id
    )
    depot.create({"version": 1})

    with pytest.raises(RecordExistsError, match="record already exists"):
        depot.create({"version": 2})

    assert depot.get(record_id).value == {"version": 1}


def test_failed_atomic_create_cleans_temp_and_leaves_no_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    depot = BloberiaDepot(tmp_path / "bloberia")

    def fail_replace(_source: object, _target: object) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr("agentos.bloberia.core.os.replace", fail_replace)

    with pytest.raises(OSError, match="replace failed"):
        depot.create({"value": 1})

    assert list((depot.root / "records").glob("*.json")) == []
    assert list((depot.root / "records").glob("*.tmp")) == []


def test_edit_replaces_value_and_advances_owned_metadata(tmp_path: Path) -> None:
    depot = BloberiaDepot(tmp_path / "bloberia")
    created = depot.create({"version": 1})

    edited = depot.edit(created.id, {"version": 2})

    assert edited.id == created.id
    assert edited.created_at == created.created_at
    assert edited.updated_at > created.updated_at
    assert edited.revision == 2
    assert edited.value == {"version": 2}
    assert created.value == {"version": 1}
    assert depot.get(created.id) == edited


def test_failed_atomic_edit_preserves_previous_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    depot = BloberiaDepot(tmp_path / "bloberia")
    created = depot.create({"version": 1})

    def fail_replace(_source: object, _target: object) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr("agentos.bloberia.core.os.replace", fail_replace)

    with pytest.raises(OSError, match="replace failed"):
        depot.edit(created.id, {"version": 2})

    assert depot.get(created.id) == created
    assert list((depot.root / "records").glob("*.tmp")) == []


def test_query_uses_recursive_object_subset_and_deterministic_order(
    tmp_path: Path,
) -> None:
    depot = BloberiaDepot(tmp_path / "bloberia")
    first = depot.create(
        {"kind": "edition", "meta": {"active": True, "labels": ["a", "b"]}}
    )
    second = depot.create(
        {"kind": "edition", "meta": {"active": False, "labels": ["a"]}}
    )
    third = depot.create({"kind": "other"})

    matches = depot.query(
        {"value": {"kind": "edition", "meta": {"active": True}}}
    )

    assert matches == tuple(sorted((first,), key=lambda record: record.id))
    assert depot.query({"value": {"meta": {"labels": ["a"]}}}) == (second,)
    assert depot.query({"value": {"meta": {"labels": ["a", "b"]}}}) == (first,)
    assert depot.query({"value": {"kind": "missing"}}) == ()
    assert [record.id for record in depot.query({})] == sorted(
        (first.id, second.id, third.id)
    )


def test_query_can_select_reserved_envelope_and_scalar_value(tmp_path: Path) -> None:
    depot = BloberiaDepot(tmp_path / "bloberia")
    scalar = depot.create("exact")
    depot.create("other")

    assert depot.query({"_bloberia": {"id": scalar.id, "revision": 1}}) == (
        scalar,
    )
    assert depot.query({"value": "exact"}) == (scalar,)


def test_query_requires_a_json_object(tmp_path: Path) -> None:
    depot = BloberiaDepot(tmp_path / "bloberia")

    with pytest.raises(InvalidBloberiaInputError, match="query must be a JSON object"):
        depot.query(["not", "an", "object"])  # type: ignore[arg-type]


def test_concurrent_edits_serialize_revision_updates(tmp_path: Path) -> None:
    depot = BloberiaDepot(tmp_path / "bloberia")
    created = depot.create({"value": 0})
    context = multiprocessing.get_context("spawn")
    start = context.Event()
    processes = [
        context.Process(
            target=_edit_after_signal,
            args=(str(depot.root), created.id, value, start),
        )
        for value in (1, 2)
    ]
    for process in processes:
        process.start()
    start.set()
    for process in processes:
        process.join(timeout=10)

    assert [process.exitcode for process in processes] == [0, 0]
    final = depot.get(created.id)
    assert final.revision == 3
    assert final.value in ({"value": 1}, {"value": 2})


def test_check_accepts_absent_and_valid_depots(tmp_path: Path) -> None:
    depot = BloberiaDepot(tmp_path / "bloberia")

    assert depot.check().ok is True
    depot.create({"valid": True})
    assert depot.check().ok is True


def test_check_reports_corruption_deterministically_without_mutation(
    tmp_path: Path,
) -> None:
    depot = BloberiaDepot(tmp_path / "bloberia")
    records = depot.root / "records"
    records.mkdir(parents=True)
    malformed_id = "a8dcf050-086a-4fb6-8bd4-a24167c94584"
    invalid_shape_id = "4c848026-aebe-4d45-bbbc-19fb639ffc31"
    filename_id = "e161d5d4-a55c-4d8c-a945-b2c841b56280"
    payload_id = "90af5e9c-1af1-47b0-b3d2-438149232e14"
    (records / f"{malformed_id}.json").write_text("{", encoding="utf-8")
    (records / f"{invalid_shape_id}.json").write_text(
        '{"value":{"missing":"envelope"}}\n', encoding="utf-8"
    )
    valid_payload = {
        "_bloberia": {
            "id": payload_id,
            "created_at": "2026-07-25T00:00:00Z",
            "updated_at": "2026-07-25T00:00:00Z",
            "revision": 1,
        },
        "value": {"valid": True},
    }
    (records / "not-a-uuid.json").write_text(
        json.dumps(valid_payload), encoding="utf-8"
    )
    (records / f"{filename_id}.json").write_text(
        json.dumps(valid_payload), encoding="utf-8"
    )
    before = {
        path.relative_to(depot.root): path.read_bytes()
        for path in sorted(depot.root.rglob("*"))
        if path.is_file()
    }

    result = depot.check()

    assert result.ok is False
    assert [finding.code for finding in result.findings] == [
        "invalid-record",
        "invalid-json",
        "identity-mismatch",
        "invalid-record-filename",
    ]
    assert {
        path.relative_to(depot.root): path.read_bytes()
        for path in sorted(depot.root.rglob("*"))
        if path.is_file()
    } == before
