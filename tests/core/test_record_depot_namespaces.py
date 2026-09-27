"""Constraints carried forward from the retired `test_record depot*` modules.

Those suites guarded two things the reshaping did not touch: namespaces are placement,
and a write either lands whole or leaves the previous state alone. What they also guarded
— a store-minted id, an envelope with owned metadata, a revision counter, recursive
subset queries — described a store that models its cargo, and went with it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tarav.l0._core.record_depot import OpaqueRecordDepot
from tarav.l0._core.record_depot import InvalidRecordDepotInputError


def _depot(tmp_path: Path) -> OpaqueRecordDepot:
    return OpaqueRecordDepot(tmp_path / "depot")


class TestNamespaceIsPlacement:
    def test_a_namespaced_record_round_trips(self, tmp_path: Path) -> None:
        depot = _depot(tmp_path)
        depot.insert({"k": 1}, namespace="alpha")
        assert depot.first({"k": {"equals": 1}}, namespace="alpha") == {"k": 1}

    def test_a_namespace_of_arbitrary_depth_is_addressed_by_prefix(
        self, tmp_path: Path
    ) -> None:
        depot = _depot(tmp_path)
        depot.insert({"k": 1}, namespace="a/b/c")
        assert depot.count({"k": {"equals": 1}}, namespace="a") == 1
        assert depot.count({"k": {"equals": 1}}, namespace="a/b/c") == 1

    def test_a_read_without_a_namespace_walks_every_namespace(
        self, tmp_path: Path
    ) -> None:
        depot = _depot(tmp_path)
        depot.insert({"k": 1}, namespace="alpha")
        depot.insert({"k": 1}, namespace="beta")
        depot.insert({"k": 1})
        assert depot.count({"k": {"equals": 1}}) == 3

    def test_a_namespace_scoped_read_excludes_siblings(self, tmp_path: Path) -> None:
        depot = _depot(tmp_path)
        depot.insert({"k": "alpha"}, namespace="alpha")
        depot.insert({"k": "beta"}, namespace="beta")
        assert depot.all({}, namespace="alpha") == ({"k": "alpha"},)

    def test_a_flat_depot_stays_readable_after_namespaces_appear(
        self, tmp_path: Path
    ) -> None:
        """Namespaces are a subdirectory, not a re-rooting, so old placement still reads."""
        depot = _depot(tmp_path)
        depot.insert({"k": "flat"})
        depot.insert({"k": "nested"}, namespace="alpha")
        assert depot.count({}) == 2

    def test_namespaces_lists_prefixes(self, tmp_path: Path) -> None:
        depot = _depot(tmp_path)
        depot.insert({"k": 1}, namespace="alpha")
        depot.insert({"k": 1}, namespace="beta")
        assert depot.namespaces() == ("alpha", "beta")

    @pytest.mark.parametrize("namespace", ["../escape", ".hidden", ""])
    def test_an_unsafe_namespace_is_rejected_rather_than_silently_rerooted(
        self, tmp_path: Path, namespace: str
    ) -> None:
        depot = _depot(tmp_path)
        with pytest.raises(InvalidRecordDepotInputError):
            depot.insert({"k": 1}, namespace=namespace)


class TestDurability:
    def test_a_returned_cargo_is_detached_from_stored_state(
        self, tmp_path: Path
    ) -> None:
        """Mutating what a read handed back must not reach the depot."""
        depot = _depot(tmp_path)
        depot.insert({"nested": {"k": 1}})
        cargo = depot.first({})
        cargo["nested"]["k"] = 999
        assert depot.first({}) == {"nested": {"k": 1}}

    def test_non_json_cargo_is_refused_before_anything_is_written(
        self, tmp_path: Path
    ) -> None:
        depot = _depot(tmp_path)
        with pytest.raises(InvalidRecordDepotInputError):
            depot.insert({"k": object()})
        assert depot.count({}) == 0

    def test_a_failed_replace_leaves_the_previous_record_intact(
        self, tmp_path: Path
    ) -> None:
        depot = _depot(tmp_path)
        depot.insert({"k": "before"})
        with pytest.raises(InvalidRecordDepotInputError):
            depot.replace({"k": {"equals": "before"}}, {"k": object()})
        assert depot.first({}) == {"k": "before"}

    def test_a_query_that_is_not_a_mapping_is_refused(self, tmp_path: Path) -> None:
        depot = _depot(tmp_path)
        with pytest.raises(InvalidRecordDepotInputError):
            depot.count(["not", "a", "mapping"])  # type: ignore[arg-type]


class TestCheck:
    def test_an_absent_depot_and_a_valid_depot_both_pass(self, tmp_path: Path) -> None:
        assert _depot(tmp_path).check().ok
        depot = _depot(tmp_path)
        depot.insert({"k": 1}, namespace="alpha")
        assert depot.check().ok

    def test_check_walks_into_namespaces_and_reports_without_mutating(
        self, tmp_path: Path
    ) -> None:
        depot = _depot(tmp_path)
        depot.insert({"k": 1}, namespace="alpha")
        broken = depot.root / "records" / "alpha" / "broken.json"
        broken.write_text("{not json", encoding="utf-8")

        result = depot.check()
        assert [f.code for f in result.findings] == ["invalid-json"]
        assert not result.ok
        assert broken.read_text(encoding="utf-8") == "{not json"

    def test_check_reports_only_json_validity(self, tmp_path: Path) -> None:
        """A filename record depot did not mint is not a finding.

        Nothing resolves by filename any more, so a name the store would not have
        chosen has no consequence to report — unlike a record that will not parse.
        """
        depot = _depot(tmp_path)
        depot.insert({"k": 1})
        odd = depot.root / "records" / "not-a-uuid.json"
        odd.write_text(json.dumps({"k": 2}), encoding="utf-8")
        assert depot.check().ok
        assert depot.count({"k": {"equals": 2}}) == 1
