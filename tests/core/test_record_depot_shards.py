"""Slice 6: the `shards` type is a topology, not a different contract.

The controlling constraint is that every query returns the same answer under both types.
A depot type may add terms — `shards` demands a declared key and makes it unique — but it
may not change what a query means, or the two paths diverge and one of them is wrong.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tarav._core.record_depot import OpaqueRecordDepot
from tarav._core.record_depot import (
    TYPE_FILES,
    TYPE_SHARDS,
    InvalidRecordDepotInputError,
)

CARGOS = [
    {"id": "c20260510-1u", "line": {"label": "^c20260510-1u", "type": "DF"}, "links": None},
    {"id": "c20260510-2u", "line": {"label": "^c20260510-2u", "type": "CT"}, "links": {"landing": None}},
    {"id": "c20260819-9u", "line": {"label": "^c20260819-9u", "type": "DF"}, "links": {"landing": "x"}},
]

QUERIES = [
    {},
    {"id": {"equals": "c20260510-2u"}},
    {"line.type": {"equals": "DF"}},
    {"line.label": {"contains": "20260510"}},
    {"links.landing": {"exists": True}},
    {"id": {"equals": "absent"}},
]


def _filled(root: Path, depot_type: str) -> OpaqueRecordDepot:
    depot = OpaqueRecordDepot(root, depot_type=depot_type, key="id")
    for cargo in CARGOS:
        depot.insert(cargo)
    return depot


@pytest.mark.parametrize("query", QUERIES)
def test_every_query_answers_identically_under_both_types(
    tmp_path: Path, query: dict
) -> None:
    files = _filled(tmp_path / "files", TYPE_FILES)
    shards = _filled(tmp_path / "shards", TYPE_SHARDS)
    assert sorted(files.all(query), key=repr) == sorted(shards.all(query), key=repr)
    assert files.count(query) == shards.count(query)


def test_a_shard_lookup_reads_one_file_rather_than_the_depot(tmp_path: Path) -> None:
    """The reason the type exists. Proven by counting opens, not by trusting the code."""
    depot = _filled(tmp_path / "shards", TYPE_SHARDS)
    opened: list[Path] = []
    original = OpaqueRecordDepot._read_shard

    def counting(self: OpaqueRecordDepot, path: Path) -> dict:
        opened.append(path)
        return original(self, path)

    OpaqueRecordDepot._read_shard = counting  # type: ignore[method-assign]
    try:
        assert depot.first({"id": {"equals": "c20260819-9u"}})["id"] == "c20260819-9u"
        pinned = len(opened)
        opened.clear()
        depot.all({"line.type": {"equals": "DF"}})
        scanned = len(opened)
    finally:
        OpaqueRecordDepot._read_shard = original  # type: ignore[method-assign]

    assert pinned == 1
    assert scanned > pinned


def test_cargo_without_the_declared_key_fails_loudly_on_insert(tmp_path: Path) -> None:
    """Not silently placed: a record in an uncomputable shard is written and never found."""
    depot = OpaqueRecordDepot(tmp_path / "shards", depot_type=TYPE_SHARDS, key="id")
    with pytest.raises(InvalidRecordDepotInputError, match="carries no 'id'"):
        depot.insert({"line": {"label": "^c1-1u"}})
    assert depot.count({}) == 0


def test_a_non_string_key_is_refused(tmp_path: Path) -> None:
    depot = OpaqueRecordDepot(tmp_path / "shards", depot_type=TYPE_SHARDS, key="id")
    with pytest.raises(InvalidRecordDepotInputError, match="non-empty string"):
        depot.insert({"id": 17})


def test_a_shards_depot_must_declare_its_key(tmp_path: Path) -> None:
    depot = OpaqueRecordDepot(tmp_path / "shards", depot_type=TYPE_SHARDS)
    with pytest.raises(InvalidRecordDepotInputError, match="must declare the cargo path"):
        depot.insert({"id": "a"})


def test_a_duplicate_key_is_refused_rather_than_overwritten(tmp_path: Path) -> None:
    """Uniqueness is a term of this type, not of record depot.

    A dict keyed by value enforces it whether or not anyone says so, so the only choice
    is between saying it and losing a record silently.
    """
    depot = OpaqueRecordDepot(tmp_path / "shards", depot_type=TYPE_SHARDS, key="id")
    depot.insert({"id": "a", "v": 1})
    with pytest.raises(InvalidRecordDepotInputError, match="already exists"):
        depot.insert({"id": "a", "v": 2})
    assert depot.first({"id": {"equals": "a"}}) == {"id": "a", "v": 1}


def test_replace_and_delete_reach_inside_a_shard(tmp_path: Path) -> None:
    depot = _filled(tmp_path / "shards", TYPE_SHARDS)
    assert depot.replace({"id": {"equals": "c20260510-1u"}}, {"id": "c20260510-1u", "v": 9}) == 1
    assert depot.first({"id": {"equals": "c20260510-1u"}}) == {"id": "c20260510-1u", "v": 9}
    assert depot.delete({"id": {"equals": "c20260510-1u"}}) == 1
    assert depot.count({}) == 2


def test_the_type_is_recorded_and_a_contradicting_argument_is_refused(
    tmp_path: Path,
) -> None:
    """Reading a depot through a layout it was not written in must not be possible."""
    root = tmp_path / "shards"
    _filled(root, TYPE_SHARDS)
    assert OpaqueRecordDepot(root).count({}) == 3
    with pytest.raises(InvalidRecordDepotInputError, match="is type 'shards'"):
        OpaqueRecordDepot(root, depot_type=TYPE_FILES)
    with pytest.raises(InvalidRecordDepotInputError, match="unknown depot type"):
        OpaqueRecordDepot(tmp_path / "new", depot_type="mystery")


def test_the_declared_key_survives_reopening(tmp_path: Path) -> None:
    root = tmp_path / "shards"
    _filled(root, TYPE_SHARDS)
    assert OpaqueRecordDepot(root).shard_key == "id"


def test_an_empty_depot_can_materialize_its_declared_contract(tmp_path: Path) -> None:
    root = tmp_path / "shards"

    initialized = OpaqueRecordDepot(
        root,
        depot_type=TYPE_SHARDS,
        key="id",
        git=".",
        git_interval_seconds=60,
    ).initialize()

    assert initialized.root == root.resolve()
    assert initialized.count({}) == 0
    assert json.loads((root / "meta.json").read_text("utf-8")) == {
        "schema": "tarav.opaque-record-depot.v1",
        "type": "shards",
        "key": "id",
        "git": ".",
        "git_interval_seconds": 60,
    }
    reopened = OpaqueRecordDepot(root)
    assert reopened.shard_key == "id"
    assert reopened.git is not None
    assert reopened.git.repo == root.resolve()
    assert not (root / ".git").exists()
