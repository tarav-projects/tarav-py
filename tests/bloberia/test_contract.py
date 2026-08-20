"""The Bloberia contract: opaque cargo, path queries, arity at the call site."""

from __future__ import annotations

from pathlib import Path

import pytest

from tarav.bloberia import BloberiaDepot


def _depot(tmp_path: Path) -> BloberiaDepot:
    return BloberiaDepot(tmp_path / "depot")


class TestOpaqueCargo:
    def test_a_record_is_the_cargo_verbatim(self, tmp_path: Path) -> None:
        """No envelope. What the consumer stored is what it reads back.

        The moment bloberia adds a field, it owns a schema, and every consumer
        inherits its migrations.
        """
        cargo = {"id": "ln_abc", "line": {"label": "^c20260819-1u"}, "links": None}
        depot = _depot(tmp_path)
        depot.insert(cargo)
        assert depot.all({}) == (cargo,)

    def test_cargo_bloberia_has_never_seen_round_trips(self, tmp_path: Path) -> None:
        cargo = {"whatever": [1, {"deep": {"deeper": True}}], "unicode": "café — ok"}
        depot = _depot(tmp_path)
        depot.insert(cargo)
        assert depot.first({}) == cargo

    def test_two_identical_cargos_are_two_records(self, tmp_path: Path) -> None:
        """Uniqueness is the consumer's business; bloberia does not care."""
        depot = _depot(tmp_path)
        depot.insert({"a": 1})
        depot.insert({"a": 1})
        assert depot.count({}) == 2


class TestArityAtTheCallSite:
    def test_first_returns_one_and_all_returns_every_match(self, tmp_path: Path) -> None:
        depot = _depot(tmp_path)
        depot.insert({"kind": "x", "n": 1})
        depot.insert({"kind": "x", "n": 2})
        depot.insert({"kind": "y", "n": 3})
        assert depot.first({"kind": {"equals": "y"}}) == {"kind": "y", "n": 3}
        assert len(depot.all({"kind": {"equals": "x"}})) == 2

    def test_first_returns_none_when_nothing_matches(self, tmp_path: Path) -> None:
        assert _depot(tmp_path).first({"kind": {"equals": "absent"}}) is None


class TestPathQueries:
    def test_equals_addresses_a_nested_path(self, tmp_path: Path) -> None:
        depot = _depot(tmp_path)
        depot.insert({"line": {"label": "^c20260819-1u", "type": "DF"}})
        assert depot.first({"line.label": {"equals": "^c20260819-1u"}}) is not None
        assert depot.first({"line.label": {"equals": "^c20260819-9u"}}) is None

    def test_contains_matches_a_substring(self, tmp_path: Path) -> None:
        depot = _depot(tmp_path)
        depot.insert({"line": {"body": "a state is a value plus an error"}})
        assert depot.first({"line.body": {"contains": "value plus"}}) is not None

    def test_exists_distinguishes_absent_from_null(self, tmp_path: Path) -> None:
        depot = _depot(tmp_path)
        depot.insert({"links": {"landing": None}})
        depot.insert({"links": {}})
        assert depot.count({"links.landing": {"exists": True}}) == 1
        assert depot.count({"links.landing": {"exists": False}}) == 1

    def test_a_list_index_is_a_path_segment(self, tmp_path: Path) -> None:
        depot = _depot(tmp_path)
        depot.insert({"members": [{"session": "s1"}, {"session": "s2"}]})
        assert depot.first({"members.1.session": {"equals": "s2"}}) is not None

    def test_regex_is_not_a_predicate_yet(self, tmp_path: Path) -> None:
        """The one operator no index or prescan can serve. Refused, not silently ignored."""
        depot = _depot(tmp_path)
        depot.insert({"a": "b"})
        with pytest.raises(Exception, match="regex"):
            depot.first({"a": {"regex": "b.*"}})


class TestMutation:
    def test_replace_rewrites_every_match(self, tmp_path: Path) -> None:
        depot = _depot(tmp_path)
        depot.insert({"id": "a", "v": 1})
        depot.insert({"id": "b", "v": 1})
        assert depot.replace({"id": {"equals": "a"}}, {"id": "a", "v": 2}) == 1
        assert depot.first({"id": {"equals": "a"}}) == {"id": "a", "v": 2}
        assert depot.first({"id": {"equals": "b"}}) == {"id": "b", "v": 1}

    def test_delete_removes_every_match(self, tmp_path: Path) -> None:
        depot = _depot(tmp_path)
        depot.insert({"k": 1})
        depot.insert({"k": 2})
        assert depot.delete({"k": {"equals": 1}}) == 1
        assert depot.count({}) == 1


class TestLayoutIsPrivate:
    def test_the_api_never_reveals_a_storage_path(self, tmp_path: Path) -> None:
        """A leaked layout is a layout that can never change.

        Anchory's 2-hex sharding leaked, and two migration scripts in this project
        reimplemented it — which is what makes a storage change impossible later.
        """
        depot = _depot(tmp_path)
        depot.insert({"a": 1})
        for value in (depot.first({}), depot.all({})[0]):
            assert "path" not in repr(value)
            assert str(tmp_path) not in repr(value)
