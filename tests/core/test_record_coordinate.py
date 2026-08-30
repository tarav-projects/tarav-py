"""Slice 9: `commit + file + path` — derived, immutable, and absent before a commit."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tarav._core.record_depot import OpaqueRecordDepot
from tarav._core.record_depot import TYPE_SHARDS, InvalidRecordDepotInputError
from tarav._core.record_coordinate import CoordinateError, RecordCoordinate


def _repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    for args in (
        ("init", "-q"),
        ("config", "user.email", "t@example.com"),
        ("config", "user.name", "t"),
    ):
        subprocess.run(("git", "-C", str(path), *args), check=True, capture_output=True)
    return path


def _depot(tmp_path: Path, **kwargs: object) -> OpaqueRecordDepot:
    repo = _repo(tmp_path / "project")
    return OpaqueRecordDepot(repo / "depot", git="..", **kwargs)  # type: ignore[arg-type]


class TestDerivation:
    def test_a_committed_record_has_a_coordinate(self, tmp_path: Path) -> None:
        depot = _depot(tmp_path)
        depot.insert({"id": "a", "line": {"label": "^c1-1u"}})
        coordinate = depot.coordinate({"id": {"equals": "a"}})
        assert coordinate is not None
        assert len(coordinate.commit) == 40
        assert coordinate.file.startswith("depot/records/")

    def test_an_uncommitted_record_has_no_coordinate(self, tmp_path: Path) -> None:
        """Reported, never manufactured: no commit is fired to produce one."""
        depot = _depot(tmp_path, git_interval_seconds=10**9)
        depot.insert({"id": "a"})
        subprocess.run(
            ("git", "-C", str(depot.root.parent), "reset", "-q", "--hard"),
            check=True,
            capture_output=True,
        )
        depot.insert({"id": "b"})
        assert depot.coordinate({"id": {"equals": "b"}}) is None

    def test_an_untracked_depot_has_no_coordinates(self, tmp_path: Path) -> None:
        depot = OpaqueRecordDepot(tmp_path / "depot")
        depot.insert({"id": "a"})
        assert depot.coordinate({"id": {"equals": "a"}}) is None

    def test_a_query_matching_nothing_yields_no_coordinate(self, tmp_path: Path) -> None:
        depot = _depot(tmp_path)
        depot.insert({"id": "a"})
        assert depot.coordinate({"id": {"equals": "absent"}}) is None


class TestImmutability:
    def test_a_coordinate_still_resolves_after_the_record_is_rewritten(
        self, tmp_path: Path
    ) -> None:
        """The whole point of the reference system."""
        depot = _depot(tmp_path, git_interval_seconds=0)
        depot.insert({"id": "a", "v": "original"})
        coordinate = depot.coordinate({"id": {"equals": "a"}})
        assert coordinate is not None

        depot.replace({"id": {"equals": "a"}}, {"id": "a", "v": "rewritten"})
        assert depot.first({"id": {"equals": "a"}})["v"] == "rewritten"
        assert depot.at(coordinate) == {"id": "a", "v": "original"}

    def test_a_coordinate_still_resolves_after_the_record_is_deleted(
        self, tmp_path: Path
    ) -> None:
        depot = _depot(tmp_path, git_interval_seconds=0)
        depot.insert({"id": "a", "v": "original"})
        coordinate = depot.coordinate({"id": {"equals": "a"}})
        assert coordinate is not None

        depot.delete({"id": {"equals": "a"}})
        assert depot.count({}) == 0
        assert depot.at(coordinate) == {"id": "a", "v": "original"}


class TestPaths:
    def test_a_path_addresses_a_sub_value(self, tmp_path: Path) -> None:
        depot = _depot(tmp_path)
        depot.insert({"id": "a", "support": {"members": [{"session": "s1"}]}})
        coordinate = depot.coordinate(
            {"id": {"equals": "a"}}, path="support.members.0.session"
        )
        assert coordinate is not None
        assert depot.at(coordinate) == "s1"

    def test_an_empty_path_is_the_whole_record(self, tmp_path: Path) -> None:
        depot = _depot(tmp_path)
        depot.insert({"id": "a"})
        coordinate = depot.coordinate({"id": {"equals": "a"}})
        assert coordinate is not None
        assert coordinate.path == ""
        assert depot.at(coordinate) == {"id": "a"}

    def test_a_path_that_names_nothing_is_an_error_not_a_none(
        self, tmp_path: Path
    ) -> None:
        depot = _depot(tmp_path)
        depot.insert({"id": "a"})
        coordinate = depot.coordinate({"id": {"equals": "a"}}, path="absent")
        assert coordinate is not None
        with pytest.raises(CoordinateError, match="no such path"):
            depot.at(coordinate)

    def test_a_sharded_coordinate_reaches_through_the_shard_key(
        self, tmp_path: Path
    ) -> None:
        """A `shards` record is one entry in a file, so its path starts at its key."""
        repo = _repo(tmp_path / "project")
        depot = OpaqueRecordDepot(
            repo / "depot", depot_type=TYPE_SHARDS, key="id", git=".."
        )
        depot.insert({"id": "a", "v": 1})
        coordinate = depot.coordinate({"id": {"equals": "a"}}, path="v")
        assert coordinate is not None
        assert coordinate.path == "a.v"
        assert depot.at(coordinate) == 1


class TestSpelling:
    def test_a_coordinate_round_trips_through_its_text_form(self) -> None:
        coordinate = RecordCoordinate(commit="a" * 40, file="depot/records/x.json", path="a.b")
        assert RecordCoordinate.parse(str(coordinate)) == coordinate

    def test_a_pathless_coordinate_round_trips(self) -> None:
        coordinate = RecordCoordinate(commit="a" * 40, file="x.json")
        assert str(coordinate) == f"record-depot:{'a' * 40}/x.json"
        assert RecordCoordinate.parse(str(coordinate)) == coordinate

    @pytest.mark.parametrize("text", ["nonsense", "record-depot:", "record-depot:abc"])
    def test_a_malformed_coordinate_is_refused(self, text: str) -> None:
        with pytest.raises(CoordinateError):
            RecordCoordinate.parse(text)

    def test_resolving_against_an_untracked_depot_is_refused(
        self, tmp_path: Path
    ) -> None:
        depot = OpaqueRecordDepot(tmp_path / "depot")
        with pytest.raises(InvalidRecordDepotInputError, match="not git-tracked"):
            depot.at(RecordCoordinate(commit="a" * 40, file="x.json"))
