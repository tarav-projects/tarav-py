# $kw: ^test-tournament-submit --from Tournament.Ticket --from Tournament.Judge --note [DF] boundary tests for the validating submit command: the judge names only its ticket and its ranking ^<anchor-on-landing>
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from agentos._core.errors import CliError
from agentos.tournament import TournamentStore
from agentos.tournament.commands import register_tournament_commands
from agentos.tournament.tickets import TicketStore


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    register_tournament_commands(parser.add_subparsers(dest="command"))
    return parser


def _setup(tmp_path: Path, players=("alpha", "beta")):
    store = TournamentStore(tmp_path / "depot")
    tournament = store.create_tournament(
        definition_path="/defs/x.py", definition_digest="sha256:" + "0" * 64
    )
    ticket = TicketStore(store.root).mint(
        tournament_id=tournament.tournament_id,
        match_id="m-1",
        players=players,
        presented=tuple(reversed(players)),
        verbatim_hash="sha256:" + "1" * 64,
        judge={"provider": "claude-code", "model": None, "account": None},
    )
    return store, tournament, ticket


def _submit(store, ticket_id, *extra):
    args = _parser().parse_args(
        ["tournament", "submit", "--depot", str(store.root), "--ticket", ticket_id, *extra]
    )
    return args.handler(args)


def test_a_valid_ranking_appends_one_verdict_carrying_its_ticket(tmp_path: Path) -> None:
    store, tournament, ticket = _setup(tmp_path)

    assert _submit(store, ticket.ticket_id, "--ranking", "A,B") == 0

    (verdict,) = store.verdicts(tournament.tournament_id)
    assert verdict.envelope["ticket"] == ticket.ticket_id
    # "A" is the first presented player, which is the reversed pair's head.
    assert verdict.ordering == ("beta", "alpha")


def test_the_submission_never_names_players(tmp_path: Path) -> None:
    """Everything but the outcome resolves from the ticket."""
    parser = _parser()
    argv = [a for a in parser.parse_args(
        ["tournament", "submit", "--ticket", "t", "--ranking", "A,B"]
    ).__dict__]
    assert "players" not in argv and "match_id" not in argv


def test_an_invalid_ranking_appends_nothing_and_counts_an_attempt(
    tmp_path: Path,
) -> None:
    store, tournament, ticket = _setup(tmp_path)

    with pytest.raises(CliError) as excinfo:
        _submit(store, ticket.ticket_id, "--ranking", "A,A")
    message = str(excinfo.value)
    assert "once" in message
    assert "attempt 1 of 3" in message

    assert store.verdicts(tournament.tournament_id) == ()
    assert TicketStore(store.root).load(ticket.ticket_id).attempts == 1


def test_the_cap_refuses_without_validating(tmp_path: Path) -> None:
    store, tournament, ticket = _setup(tmp_path)
    tickets = TicketStore(store.root)
    for _ in range(3):
        tickets.record_attempt(ticket.ticket_id)

    with pytest.raises(CliError) as excinfo:
        _submit(store, ticket.ticket_id, "--ranking", "A,B")
    assert "out of attempts" in str(excinfo.value)
    # Refused without incrementing: the counter no longer protects anything.
    assert tickets.load(ticket.ticket_id).attempts == 3


def test_a_redeemed_ticket_refuses_a_second_submission(tmp_path: Path) -> None:
    store, tournament, ticket = _setup(tmp_path)
    _submit(store, ticket.ticket_id, "--ranking", "A,B")

    with pytest.raises(CliError) as excinfo:
        _submit(store, ticket.ticket_id, "--ranking", "B,A")
    assert "already redeemed" in str(excinfo.value)
    assert len(store.verdicts(tournament.tournament_id)) == 1
    assert TicketStore(store.root).load(ticket.ticket_id).attempts == 0


def test_a_no_contest_submission_requires_a_reason(tmp_path: Path) -> None:
    store, tournament, ticket = _setup(tmp_path)

    with pytest.raises(CliError):
        _submit(store, ticket.ticket_id, "--no-contest")

    assert _submit(
        store, ticket.ticket_id, "--no-contest", "--refusal-reason", "not comparable"
    ) == 0
    (verdict,) = store.verdicts(tournament.tournament_id)
    assert verdict.outcome == "no_contest"
    assert verdict.envelope["refusal_reason"] == "not comparable"
    assert verdict.ordering is None


def test_submitting_neither_ranking_nor_refusal_is_rejected(tmp_path: Path) -> None:
    store, _tournament, ticket = _setup(tmp_path)
    with pytest.raises(CliError):
        _submit(store, ticket.ticket_id)


def test_an_unknown_ticket_is_refused_by_name(tmp_path: Path) -> None:
    store, _tournament, _ticket = _setup(tmp_path)
    with pytest.raises(CliError) as excinfo:
        _submit(store, "not-a-ticket", "--ranking", "A,B")
    assert "not-a-ticket" in str(excinfo.value)


def test_a_four_way_submission_resolves_arity_from_its_ticket(tmp_path: Path) -> None:
    store, tournament, ticket = _setup(tmp_path, players=("a", "b", "c", "d"))

    with pytest.raises(CliError) as excinfo:
        _submit(store, ticket.ticket_id, "--ranking", "A,B")
    assert "4" in str(excinfo.value)

    assert _submit(store, ticket.ticket_id, "--ranking", "C,A,D,B") == 0
    (verdict,) = store.verdicts(tournament.tournament_id)
    assert sorted(verdict.ordering) == ["a", "b", "c", "d"]


def test_redemption_records_the_verdict_on_the_ticket(tmp_path: Path) -> None:
    store, tournament, ticket = _setup(tmp_path)
    _submit(store, ticket.ticket_id, "--ranking", "A,B")

    (verdict,) = store.verdicts(tournament.tournament_id)
    redeemed = TicketStore(store.root).load(ticket.ticket_id)
    assert redeemed.redeemed is True
    assert redeemed.verdict_id == verdict.record_id


def test_gc_reports_what_it_removed(tmp_path: Path, capsys) -> None:
    store, _tournament, _ticket = _setup(tmp_path)
    args = _parser().parse_args(["tournament", "gc", "--depot", str(store.root)])

    assert args.handler(args) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["command"] == "tournament gc"
    assert payload["removed"] == 0
