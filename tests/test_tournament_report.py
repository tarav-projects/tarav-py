# $kw: ^test-tournament-report --from Agentos.Tournament --from Tournament.Verdict --note [DF] boundary tests for raw accumulation, no-contest distribution read both ways, and the absence of any ordering ^<anchor-on-landing>
from __future__ import annotations

from pathlib import Path

from agentos.tournament import (
    TournamentStore,
    VerdictOutcome,
    tournament_report,
)
from agentos.tournament.poi import tournament_poi_instances


def _store(tmp_path: Path):
    store = TournamentStore(tmp_path / "tournament")
    tournament = store.create_tournament(
        definition_path="/defs/lines.py",
        definition_digest="sha256:" + "0" * 64,
    )
    return store, tournament


def _preferred(store, tournament, match_id, players, winner) -> None:
    store.append_verdict(
        tournament_id=tournament.tournament_id,
        match_id=match_id,
        players=players,
        outcome=VerdictOutcome.PREFERRED,
        preferred=winner,
        judge={"provider": "claude-code", "model": None, "account": None},
        presented=players,
        verbatim_hash="sha256:" + "1" * 64,
    )


def _no_contest(store, tournament, match_id, players, attribution) -> None:
    store.append_verdict(
        tournament_id=tournament.tournament_id,
        match_id=match_id,
        players=players,
        outcome=VerdictOutcome.NO_CONTEST,
        no_contest_reason=f"declined: {attribution}",
        no_contest_attribution=attribution,
        judge={"provider": "claude-code", "model": None, "account": None},
        presented=players,
        verbatim_hash="sha256:" + "2" * 64,
    )


def test_report_counts_wins_losses_and_matches_per_player(tmp_path: Path) -> None:
    store, tournament = _store(tmp_path)
    _preferred(store, tournament, "m1", ("a", "b"), "a")
    _preferred(store, tournament, "m2", ("a", "b"), "a")
    _preferred(store, tournament, "m3", ("b", "c"), "c")

    report = tournament_report(
        tournament=tournament, verdicts=store.verdicts(tournament.tournament_id)
    )
    players = {row["player"]: row for row in report["players"]}

    assert players["a"] == {
        "player": "a",
        "wins": 2,
        "losses": 0,
        "matches": 2,
        "no_contests": 0,
    }
    assert players["b"]["losses"] == 3
    assert players["b"]["matches"] == 3
    assert players["c"]["wins"] == 1


def test_report_emits_no_ranking_or_ordering(tmp_path: Path) -> None:
    store, tournament = _store(tmp_path)
    # The loser is encountered first: if the report ranked, "b" would lead.
    _preferred(store, tournament, "m1", ("a", "b"), "b")

    report = tournament_report(
        tournament=tournament, verdicts=store.verdicts(tournament.tournament_id)
    )

    assert "standing" not in report
    assert "rank" not in report
    assert "score" not in report
    assert [row["player"] for row in report["players"]] == ["a", "b"]


def test_no_contest_distribution_is_reported_pool_wide_and_per_player(
    tmp_path: Path,
) -> None:
    store, tournament = _store(tmp_path)
    _preferred(store, tournament, "m1", ("a", "b"), "a")
    _no_contest(store, tournament, "m2", ("a", "c"), "player")
    _no_contest(store, tournament, "m3", ("b", "c"), "player")

    report = tournament_report(
        tournament=tournament, verdicts=store.verdicts(tournament.tournament_id)
    )
    no_contest = report["no_contest"]
    players = {row["player"]: row for row in report["players"]}

    assert no_contest["count"] == 2
    assert no_contest["rate"] == 2 / 3
    assert no_contest["attributions"] == {"player": 2}
    assert players["c"]["no_contests"] == 2


def test_every_count_is_reported_beside_its_match_count(tmp_path: Path) -> None:
    store, tournament = _store(tmp_path)
    _preferred(store, tournament, "m1", ("a", "b"), "a")

    report = tournament_report(
        tournament=tournament, verdicts=store.verdicts(tournament.tournament_id)
    )

    for row in report["players"]:
        assert "matches" in row


def test_empty_tournament_reports_zeroes_rather_than_failing(tmp_path: Path) -> None:
    store, tournament = _store(tmp_path)

    report = tournament_report(tournament=tournament, verdicts=())

    assert report["verdict_count"] == 0
    assert report["no_contest"]["count"] == 0
    assert report["no_contest"]["rate"] == 0.0
    assert all(row["matches"] == 0 for row in report["players"])


def test_a_player_no_judge_can_evaluate_becomes_an_unjudgeable_poi(
    tmp_path: Path,
) -> None:
    store, tournament = _store(tmp_path)
    for index in range(4):
        _no_contest(store, tournament, f"m{index}", ("a", "b"), "player")
    _preferred(store, tournament, "m9", ("b", "c"), "b")

    report = tournament_report(
        tournament=tournament, verdicts=store.verdicts(tournament.tournament_id)
    )
    instances = tournament_poi_instances(report)
    classes = {instance.class_reference for instance in instances}

    assert any("Player.Unjudgeable" in str(reference) for reference in classes)


def test_a_pool_wide_refusal_rate_indicts_the_definition(tmp_path: Path) -> None:
    store, tournament = _store(tmp_path)
    _no_contest(store, tournament, "m1", ("a", "b"), "question")
    _no_contest(store, tournament, "m2", ("b", "c"), "question")
    _no_contest(store, tournament, "m3", ("a", "c"), "question")

    report = tournament_report(
        tournament=tournament, verdicts=store.verdicts(tournament.tournament_id)
    )
    instances = tournament_poi_instances(report)

    assert any(
        "Definition.Incoherent" in str(instance.class_reference)
        for instance in instances
    )


def test_a_low_scoring_player_with_enough_matches_becomes_a_poi(
    tmp_path: Path,
) -> None:
    store, tournament = _store(tmp_path)
    for index in range(8):
        _preferred(store, tournament, f"m{index}", ("a", "b"), "a")

    report = tournament_report(
        tournament=tournament, verdicts=store.verdicts(tournament.tournament_id)
    )
    instances = tournament_poi_instances(report)

    assert any(
        "Player.LowStanding" in str(instance.class_reference) for instance in instances
    )


def test_an_under_played_low_scorer_is_not_reported(tmp_path: Path) -> None:
    store, tournament = _store(tmp_path)
    _preferred(store, tournament, "m1", ("a", "b"), "a")

    report = tournament_report(
        tournament=tournament, verdicts=store.verdicts(tournament.tournament_id)
    )
    instances = tournament_poi_instances(report)

    assert not any(
        "Player.LowStanding" in str(instance.class_reference) for instance in instances
    )


def test_no_contest_attributions_are_counted_on_their_axis(tmp_path: Path) -> None:
    store, tournament = _store(tmp_path)
    _no_contest(store, tournament, "m1", ("a", "b"), "question")
    _no_contest(store, tournament, "m2", ("a", "c"), "question")
    _no_contest(store, tournament, "m3", ("b", "c"), "player")

    report = tournament_report(
        tournament=tournament, verdicts=store.verdicts(tournament.tournament_id)
    )

    assert report["no_contest"]["attributions"] == {"question": 2, "player": 1}
    assert set(report["no_contest"]["reason_samples"]) == {"question", "player"}


def test_an_unattributed_no_contest_cannot_be_recorded(tmp_path: Path) -> None:
    import pytest

    from agentos.tournament import TournamentError

    store, tournament = _store(tmp_path)
    with pytest.raises(TournamentError):
        store.append_verdict(
            tournament_id=tournament.tournament_id,
            match_id="m1",
            players=("a", "b"),
            outcome=VerdictOutcome.NO_CONTEST,
            no_contest_reason="declined",
            judge={"provider": "claude-code", "model": None, "account": None},
            presented=("a", "b"),
            verbatim_hash="sha256:" + "9" * 64,
        )


def test_a_player_absent_from_every_verdict_is_not_reported(tmp_path: Path) -> None:
    store, tournament = _store(tmp_path)
    _preferred(store, tournament, "m1", ("a", "b"), "a")

    report = tournament_report(
        tournament=tournament, verdicts=store.verdicts(tournament.tournament_id)
    )
    assert {row["player"] for row in report["players"]} == {"a", "b"}


def test_a_player_that_left_the_pool_keeps_its_accumulated_history(tmp_path: Path) -> None:
    """No declared pool means no list for a departed player to fall off of.

    An index line edited mid-tournament retires its player; folding from a
    declared pool would silently drop everything that player accumulated.
    """
    store, tournament = _store(tmp_path)
    _preferred(store, tournament, "m1", ("stale-line", "b"), "b")
    _preferred(store, tournament, "m2", ("edited-line", "b"), "edited-line")

    report = tournament_report(
        tournament=tournament, verdicts=store.verdicts(tournament.tournament_id)
    )
    rows = {row["player"]: row for row in report["players"]}
    assert rows["stale-line"]["losses"] == 1
    assert rows["edited-line"]["wins"] == 1
