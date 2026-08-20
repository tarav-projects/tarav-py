# $kw: ^test-bloberia-namespace --from Bloberia.Record.Namespace --note [DF] boundary tests for placement-only record namespaces under a depot's records/ ^<anchor-on-landing>
from __future__ import annotations

from pathlib import Path

import pytest

from tarav.bloberia.depot_v1 import BloberiaDepot, InvalidBloberiaInputError


def _depot(tmp_path: Path) -> BloberiaDepot:
    return BloberiaDepot(tmp_path / "depot")


def test_namespaced_record_round_trips(tmp_path: Path) -> None:
    depot = _depot(tmp_path)
    record = depot.create({"kind": "verdict"}, namespace="t-1")

    assert depot.get(record.id, namespace="t-1").value == {"kind": "verdict"}
    assert (depot.root / "records" / "t-1" / f"{record.id}.json").is_file()


def test_namespace_of_arbitrary_depth_is_addressed_by_prefix(tmp_path: Path) -> None:
    depot = _depot(tmp_path)
    deep = depot.create({"n": 1}, namespace="a/b/c")

    assert [r.id for r in depot.query({}, namespace="a")] == [deep.id]
    assert [r.id for r in depot.query({}, namespace="a/b/c")] == [deep.id]
    assert depot.query({}, namespace="a/b/d") == ()


def test_query_without_a_namespace_walks_every_namespace(tmp_path: Path) -> None:
    depot = _depot(tmp_path)
    flat = depot.create({"n": 0})
    first = depot.create({"n": 1}, namespace="t-1")
    second = depot.create({"n": 2}, namespace="t-2/deep")

    found = {record.id for record in depot.query({})}
    assert found == {flat.id, first.id, second.id}


def test_namespace_scoped_query_excludes_siblings(tmp_path: Path) -> None:
    depot = _depot(tmp_path)
    mine = depot.create({"kind": "verdict"}, namespace="t-1")
    depot.create({"kind": "verdict"}, namespace="t-2")

    assert [r.id for r in depot.query({"value": {"kind": "verdict"}}, namespace="t-1")] == [
        mine.id
    ]


def test_get_without_a_namespace_searches_every_namespace(tmp_path: Path) -> None:
    depot = _depot(tmp_path)
    record = depot.create({"n": 1}, namespace="deep/nested")

    assert depot.get(record.id).value == {"n": 1}


def test_edit_reaches_a_namespaced_record(tmp_path: Path) -> None:
    depot = _depot(tmp_path)
    record = depot.create({"n": 1}, namespace="t-1")

    edited = depot.edit(record.id, {"n": 2}, namespace="t-1")
    assert edited.revision == 2
    assert depot.get(record.id).value == {"n": 2}


def test_an_existing_flat_depot_stays_readable(tmp_path: Path) -> None:
    depot = _depot(tmp_path)
    record = depot.create({"n": 1})

    assert [r.id for r in depot.query({})] == [record.id]
    assert depot.get(record.id).value == {"n": 1}
    assert depot.check().ok


def test_check_walks_into_namespaces(tmp_path: Path) -> None:
    depot = _depot(tmp_path)
    depot.create({"n": 1}, namespace="t-1")
    corrupt = depot.root / "records" / "t-1" / "not-a-uuid.json"
    corrupt.write_text("{}", encoding="utf-8")

    codes = {finding.code for finding in depot.check().findings}
    assert "invalid-record-filename" in codes


def test_namespaces_lists_prefixes_without_reading_records(tmp_path: Path) -> None:
    depot = _depot(tmp_path)
    depot.create({"n": 1}, namespace="t-1")
    depot.create({"n": 2}, namespace="t-2/deep")

    assert depot.namespaces() == ("t-1", "t-2", "t-2/deep")


@pytest.mark.parametrize("namespace", ["/abs", "../escape", "a/../b", "a//b", "", "  "])
def test_unsafe_namespace_is_rejected_rather_than_silently_rerooted(
    tmp_path: Path, namespace: str
) -> None:
    depot = _depot(tmp_path)
    with pytest.raises(InvalidBloberiaInputError):
        depot.create({"n": 1}, namespace=namespace)
