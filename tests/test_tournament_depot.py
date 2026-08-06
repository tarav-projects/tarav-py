# $kw: ^test-tournament-depot --from Tournament.Depot --note [DF] boundary tests for the global depot default and its definitions/records split ^<anchor-on-landing>
from __future__ import annotations

from pathlib import Path

import pytest

from agentos.tournament import TournamentStore, resolve_depot_root


def test_depot_defaults_to_the_canonical_global_location(monkeypatch) -> None:
    monkeypatch.delenv("AGENTOS_TOURNAMENT_DEPOT", raising=False)
    assert resolve_depot_root(None) == (Path.home() / ".agentos" / "tournament")


def test_environment_overrides_the_default_root(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AGENTOS_TOURNAMENT_DEPOT", str(tmp_path / "elsewhere"))
    assert resolve_depot_root(None) == (tmp_path / "elsewhere").resolve()


def test_explicit_root_wins_over_the_environment(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AGENTOS_TOURNAMENT_DEPOT", str(tmp_path / "elsewhere"))
    assert resolve_depot_root(tmp_path / "explicit") == (tmp_path / "explicit").resolve()


def test_each_tournament_owns_a_definitions_directory(tmp_path: Path) -> None:
    store = TournamentStore(tmp_path / "depot")
    tournament = store.create_tournament(
        definition_path="/defs/lines.py", definition_digest="sha256:" + "0" * 64
    )

    assert store.definition_dir(tournament.tournament_id) == (
        store.root / "definitions" / tournament.tournament_id
    )


def test_records_are_namespaced_by_tournament(tmp_path: Path) -> None:
    store = TournamentStore(tmp_path / "depot")
    tournament = store.create_tournament(
        definition_path="/defs/lines.py", definition_digest="sha256:" + "0" * 64
    )

    assert (store.root / "records" / tournament.tournament_id).is_dir()
    assert store.depot.namespaces() == (tournament.tournament_id,)


def test_listing_tournaments_reads_namespaces_not_the_whole_depot(tmp_path: Path) -> None:
    store = TournamentStore(tmp_path / "depot")
    first = store.create_tournament(
        definition_path="/defs/a.py", definition_digest="sha256:" + "1" * 64
    )
    second = store.create_tournament(
        definition_path="/defs/b.py", definition_digest="sha256:" + "2" * 64
    )

    listed = {item.tournament_id for item in store.tournaments()}
    assert listed == {first.tournament_id, second.tournament_id}
    assert set(store.depot.namespaces()) == listed
