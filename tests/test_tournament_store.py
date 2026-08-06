# $kw: ^test-tournament-store --from Agentos.Tournament --from Tournament.Verdict --from Tournament.Depot --note [DF] boundary tests for the verdict record split and the append-only, namespace-scoped store ^<anchor-on-landing>
from __future__ import annotations

from pathlib import Path

import pytest

from agentos.tournament import (
    EnvelopeShadowedError,
    MatchIdentityRequiredError,
    TournamentStore,
    VerdictOutcome,
)


def _store(tmp_path: Path) -> TournamentStore:
    return TournamentStore(tmp_path / "tournament")


def _tournament(store: TournamentStore) -> str:
    return store.create_tournament(
        definition_path="/defs/lines.py",
        definition_digest="sha256:" + "0" * 64,
    ).tournament_id


def _judge() -> dict[str, object]:
    return {"provider": "claude-code", "model": None, "account": None}


def test_verdict_round_trips_envelope_and_consumer_slot(tmp_path: Path) -> None:
    store = _store(tmp_path)
    tournament_id = _tournament(store)

    store.append_verdict(
        tournament_id=tournament_id,
        match_id="m-1",
        players=("a", "b"),
        outcome=VerdictOutcome.ORDERED,
        ordering=("a", "b"),
        judge={"provider": "claude-code", "model": "opus", "account": "work"},
        presented=("b", "a"),
        verbatim_hash="sha256:" + "1" * 64,
        slot={"note": "consumer analysis material"},
    )

    (verdict,) = store.verdicts(tournament_id)
    assert verdict.envelope["match_id"] == "m-1"
    assert verdict.envelope["presented"] == ["b", "a"]
    assert verdict.ordering == ("a", "b")
    assert verdict.slot == {"note": "consumer analysis material"}


def test_append_only_store_exposes_no_mutation(tmp_path: Path) -> None:
    store = _store(tmp_path)
    tournament_id = _tournament(store)
    for index in range(3):
        store.append_verdict(
            tournament_id=tournament_id,
            match_id=f"m-{index}",
            players=("a", "b"),
            outcome=VerdictOutcome.ORDERED,
            ordering=("a", "b"),
            judge=_judge(),
            presented=("a", "b"),
            verbatim_hash="sha256:" + "2" * 64,
        )

    assert len(store.verdicts(tournament_id)) == 3
    assert not hasattr(store, "edit_verdict")
    assert not hasattr(store, "update_verdict")


def test_repeated_match_id_accumulates_rather_than_replacing(tmp_path: Path) -> None:
    store = _store(tmp_path)
    tournament_id = _tournament(store)
    for ordering in (("a", "b"), ("b", "a")):
        store.append_verdict(
            tournament_id=tournament_id,
            match_id="same-match",
            players=("a", "b"),
            outcome=VerdictOutcome.ORDERED,
            ordering=ordering,
            judge=_judge(),
            presented=("a", "b"),
            verbatim_hash="sha256:" + "3" * 64,
        )

    verdicts = store.verdicts(tournament_id, match_id="same-match")
    assert [v.ordering for v in verdicts] == [("a", "b"), ("b", "a")]


def test_missing_match_id_is_rejected_rather_than_generated(tmp_path: Path) -> None:
    store = _store(tmp_path)
    tournament_id = _tournament(store)

    with pytest.raises(MatchIdentityRequiredError):
        store.append_verdict(
            tournament_id=tournament_id,
            match_id="",
            players=("a", "b"),
            outcome=VerdictOutcome.ORDERED,
            ordering=("a", "b"),
            judge=_judge(),
            presented=("a", "b"),
            verbatim_hash="sha256:" + "4" * 64,
        )


def test_consumer_slot_may_not_shadow_an_envelope_field(tmp_path: Path) -> None:
    store = _store(tmp_path)
    tournament_id = _tournament(store)

    with pytest.raises(EnvelopeShadowedError):
        store.append_verdict(
            tournament_id=tournament_id,
            match_id="m-1",
            players=("a", "b"),
            outcome=VerdictOutcome.ORDERED,
            ordering=("a", "b"),
            judge=_judge(),
            presented=("a", "b"),
            verbatim_hash="sha256:" + "5" * 64,
            slot={"ordering": ["b", "a"]},
        )


def test_no_contest_verdict_requires_and_keeps_its_reason(tmp_path: Path) -> None:
    store = _store(tmp_path)
    tournament_id = _tournament(store)

    store.append_verdict(
        tournament_id=tournament_id,
        match_id="m-nc",
        players=("a", "b"),
        outcome=VerdictOutcome.NO_CONTEST,
        refusal_reason="the two lines are not comparable",
        judge=_judge(),
        presented=("a", "b"),
        verbatim_hash="sha256:" + "6" * 64,
    )

    (verdict,) = store.verdicts(tournament_id)
    assert verdict.envelope["outcome"] == "no_contest"
    assert verdict.envelope["refusal_reason"] == "the two lines are not comparable"
    assert verdict.ordering is None


def test_verdicts_never_read_another_tournaments_namespace(tmp_path: Path) -> None:
    store = _store(tmp_path)
    first = _tournament(store)
    second = _tournament(store)
    store.append_verdict(
        tournament_id=first,
        match_id="m-1",
        players=("a", "b"),
        outcome=VerdictOutcome.ORDERED,
        ordering=("a", "b"),
        judge=_judge(),
        presented=("a", "b"),
        verbatim_hash="sha256:" + "7" * 64,
    )

    assert len(store.verdicts(first)) == 1
    assert store.verdicts(second) == ()
    assert (store.root / "records" / first).is_dir()
    assert (store.root / "records" / second).is_dir()


def test_a_four_player_ordering_round_trips(tmp_path: Path) -> None:
    store = _store(tmp_path)
    tournament_id = _tournament(store)
    players = ("a", "b", "c", "d")

    store.append_verdict(
        tournament_id=tournament_id,
        match_id="m-4",
        players=players,
        outcome=VerdictOutcome.ORDERED,
        ordering=("c", "a", "d", "b"),
        judge=_judge(),
        presented=("d", "a", "b", "c"),
        verbatim_hash="sha256:" + "8" * 64,
    )

    (verdict,) = store.verdicts(tournament_id)
    assert verdict.ordering == ("c", "a", "d", "b")
    assert verdict.envelope["players"] == list(players)


def test_an_ordering_that_is_not_a_permutation_is_rejected(tmp_path: Path) -> None:
    from agentos.tournament import TournamentError

    store = _store(tmp_path)
    tournament_id = _tournament(store)
    for bad in [("a", "b", "c"), ("a", "a"), ("a", "z"), ("a",), "ab"]:
        with pytest.raises(TournamentError):
            store.append_verdict(
                tournament_id=tournament_id,
                match_id="m-bad",
                players=("a", "b"),
                outcome=VerdictOutcome.ORDERED,
                ordering=bad,
                judge=_judge(),
                presented=("a", "b"),
                verbatim_hash="sha256:" + "9" * 64,
            )
