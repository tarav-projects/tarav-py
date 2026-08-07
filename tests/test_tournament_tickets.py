# $kw: ^test-tournament-tickets --from Tournament.Ticket --note [DF] boundary tests for the mutable staging that authorizes one submission per match run ^<anchor-on-landing>
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from agentos.tournament.tickets import (
    DEFAULT_ATTEMPT_CAP,
    KIND_MATCH,
    KIND_PREVIEW,
    SWEEP_HORIZON_SECONDS,
    Ticket,
    TicketError,
    TicketStore,
)


def _store(tmp_path: Path) -> TicketStore:
    return TicketStore(tmp_path / "depot")


def _mint(store: TicketStore, **overrides) -> Ticket:
    payload = {
        "tournament_id": "t-1",
        "match_id": "alpha VS beta",
        "players": ("alpha", "beta"),
        "presented": ("beta", "alpha"),
        "verbatim_hash": "sha256:" + "1" * 64,
        "judge": {"provider": "claude-code", "model": None, "account": None},
    }
    payload.update(overrides)
    return store.mint(**payload)


def test_a_minted_ticket_round_trips_its_match_context(tmp_path: Path) -> None:
    store = _store(tmp_path)
    ticket = _mint(store)

    loaded = store.load(ticket.ticket_id)
    assert loaded.tournament_id == "t-1"
    assert loaded.match_id == "alpha VS beta"
    assert loaded.players == ("alpha", "beta")
    assert loaded.presented == ("beta", "alpha")
    assert loaded.verbatim_hash == "sha256:" + "1" * 64
    assert loaded.attempts == 0
    assert loaded.attempt_cap == DEFAULT_ATTEMPT_CAP
    assert loaded.redeemed_at is None


def test_the_ticket_file_lives_outside_the_record_store(tmp_path: Path) -> None:
    """Mutable staging beside immutable records, never inside them."""
    store = _store(tmp_path)
    ticket = _mint(store)

    assert (store.root / f"{ticket.ticket_id}.json").is_file()
    assert store.root.name == "tickets"
    assert not (store.root.parent / "records").exists()


def test_arity_comes_from_the_ticket_not_the_submission(tmp_path: Path) -> None:
    store = _store(tmp_path)
    ticket = _mint(store, players=("a", "b", "c", "d"), presented=("d", "c", "b", "a"))

    assert store.load(ticket.ticket_id).arity == 4


def test_recording_an_attempt_increments_and_persists(tmp_path: Path) -> None:
    store = _store(tmp_path)
    ticket = _mint(store)

    store.record_attempt(ticket.ticket_id)
    store.record_attempt(ticket.ticket_id)

    assert store.load(ticket.ticket_id).attempts == 2


def test_the_cap_is_enforced_after_its_last_attempt(tmp_path: Path) -> None:
    store = _store(tmp_path)
    ticket = _mint(store, attempt_cap=2)

    store.record_attempt(ticket.ticket_id)
    assert store.load(ticket.ticket_id).exhausted is False
    store.record_attempt(ticket.ticket_id)
    assert store.load(ticket.ticket_id).exhausted is True


def test_redemption_marks_rather_than_deletes(tmp_path: Path) -> None:
    """The design sweeps by age, not on completion, so the file survives."""
    store = _store(tmp_path)
    ticket = _mint(store)

    store.redeem(ticket.ticket_id, verdict_id="v-1", exit_code=0)

    reloaded = store.load(ticket.ticket_id)
    assert (store.root / f"{ticket.ticket_id}.json").is_file()
    assert reloaded.redeemed_at is not None
    assert reloaded.verdict_id == "v-1"


def test_a_redeemed_ticket_refuses_a_second_redemption(tmp_path: Path) -> None:
    store = _store(tmp_path)
    ticket = _mint(store)
    store.redeem(ticket.ticket_id, verdict_id="v-1", exit_code=0)

    with pytest.raises(TicketError) as excinfo:
        store.redeem(ticket.ticket_id, verdict_id="v-2", exit_code=0)
    assert "already" in str(excinfo.value)


def test_an_unknown_ticket_is_an_error_naming_it(tmp_path: Path) -> None:
    store = _store(tmp_path)
    with pytest.raises(TicketError) as excinfo:
        store.load("no-such-ticket")
    assert "no-such-ticket" in str(excinfo.value)


def test_sweep_removes_stale_tickets_and_keeps_fresh_ones(tmp_path: Path) -> None:
    store = _store(tmp_path)
    fresh = _mint(store)
    stale = _mint(store)
    stale_path = store.root / f"{stale.ticket_id}.json"
    old = time.time() - SWEEP_HORIZON_SECONDS - 60
    os.utime(stale_path, (old, old))

    removed = store.sweep()

    assert removed == {KIND_MATCH: 1}
    assert not stale_path.exists()
    assert (store.root / f"{fresh.ticket_id}.json").is_file()


def test_sweep_keeps_a_redeemed_ticket_until_it_ages_out(tmp_path: Path) -> None:
    store = _store(tmp_path)
    ticket = _mint(store)
    store.redeem(ticket.ticket_id, verdict_id="v-1", exit_code=0)

    assert store.sweep() == {}
    assert (store.root / f"{ticket.ticket_id}.json").is_file()


def test_sweep_on_an_absent_directory_is_a_no_op(tmp_path: Path) -> None:
    assert TicketStore(tmp_path / "nothing").sweep() == {}


def test_sweep_ignores_files_it_did_not_write(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _mint(store)
    litter = store.root / "notes.txt"
    litter.write_text("not a ticket", encoding="utf-8")
    old = time.time() - SWEEP_HORIZON_SECONDS - 60
    os.utime(litter, (old, old))

    assert store.sweep() == {}
    assert litter.is_file()


# --- kind ---------------------------------------------------------------------


def test_a_ticket_defaults_to_the_match_kind(tmp_path: Path) -> None:
    store = _store(tmp_path)
    ticket = _mint(store)

    assert ticket.kind == KIND_MATCH
    assert store.load(ticket.ticket_id).kind == KIND_MATCH


def test_a_preview_kind_round_trips(tmp_path: Path) -> None:
    store = _store(tmp_path)
    ticket = _mint(store, kind=KIND_PREVIEW)

    assert store.load(ticket.ticket_id).kind == KIND_PREVIEW
    assert store.load(ticket.ticket_id).is_preview is True


def test_a_ticket_written_before_the_field_still_loads(tmp_path: Path) -> None:
    """An existing file predates `kind`; it is a match ticket, not a broken one."""
    store = _store(tmp_path)
    ticket = _mint(store)
    path = store.root / f"{ticket.ticket_id}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    del payload["kind"]
    path.write_text(json.dumps(payload), encoding="utf-8")

    assert store.load(ticket.ticket_id).kind == KIND_MATCH


def test_kind_changes_nothing_about_redemption_or_the_cap(tmp_path: Path) -> None:
    """A preview ticket is a real ticket: answering it records a real verdict."""
    store = _store(tmp_path)
    preview = _mint(store, kind=KIND_PREVIEW)

    store.record_attempt(preview.ticket_id)
    assert store.load(preview.ticket_id).attempts == 1

    store.redeem(preview.ticket_id, verdict_id="v-1", exit_code=None)
    assert store.load(preview.ticket_id).redeemed is True

    with pytest.raises(TicketError):
        store.redeem(preview.ticket_id, verdict_id="v-2", exit_code=None)


def test_an_unknown_kind_is_rejected(tmp_path: Path) -> None:
    store = _store(tmp_path)
    with pytest.raises(TicketError):
        _mint(store, kind="whatever")


def test_sweep_reports_what_it_removed_by_kind(tmp_path: Path) -> None:
    """Unredeemed match tickets are judge failures; unredeemed previews are tuning."""
    store = _store(tmp_path)
    old = time.time() - SWEEP_HORIZON_SECONDS - 60
    for kind, count in ((KIND_MATCH, 1), (KIND_PREVIEW, 2)):
        for _ in range(count):
            ticket = _mint(store, kind=kind)
            path = store.root / f"{ticket.ticket_id}.json"
            os.utime(path, (old, old))
    _mint(store)  # fresh, survives

    removed = store.sweep()

    assert removed == {KIND_MATCH: 1, KIND_PREVIEW: 2}
    assert sum(removed.values()) == 3
