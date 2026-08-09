# $kw: ^tournament-tickets --from Tournament.Ticket --from Tournament.Depot --note [DC] tickets are mutable staging outside the record store, so the append-only rule over verdicts stays untouched --supp ^c20260806-68u ^<anchor-on-landing>
"""One ticket authorizes one submission for one run of one match.

A ticket is a plain JSON file under ``<depot>/tickets/``. Deliberately **not** a
Bloberia record: it is mutable — attempts accumulate on it, redemption marks it —
and keeping mutation out of the record store is exactly what leaves verdicts
append-only.

It is minted before the judge spawns and carries everything the verdict needs
except the outcome. That is the security property: a submission names only its
ticket and its ranking, so a confused judge cannot describe a match it was never
given. Arity comes from the ticket too, which is why validation needs nothing
from the command line.

Redemption marks rather than deletes, and collection is by age. Nothing in a run
depends on cleanup having happened, and the attempt history stays readable until
the sweep takes it.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from agentos._core.clock import iso_z
from agentos._core.ids import generate_uuid4_string
from agentos.tournament.model import TournamentError

TICKETS_DIRNAME = "tickets"

# Where a ticket came from. A preview mints one that will never be redeemed, and
# without this an unredeemed preview is indistinguishable from a match a judge
# was given and failed to answer — so an afternoon of tuning would erase the one
# place that records judge failure.
KIND_MATCH = "match"
KIND_PREVIEW = "preview"
TICKET_KINDS = (KIND_MATCH, KIND_PREVIEW)
DEFAULT_ATTEMPT_CAP = 3
# A week. The horizon only has to be far longer than any match can run; at this
# distance no live submission can be racing the sweep, so a ticket needs no
# deadline of its own.
SWEEP_HORIZON_SECONDS = 7 * 24 * 60 * 60


class TicketError(TournamentError):
    """A ticket could not be resolved, or would not accept what was asked."""


@dataclass(frozen=True)
class Ticket:
    ticket_id: str
    tournament_id: str
    match_id: str
    players: tuple[str, ...]
    presented: tuple[str, ...]
    verbatim_hash: str
    judge: dict[str, object]
    created_at: str
    attempts: int = 0
    attempt_cap: int = DEFAULT_ATTEMPT_CAP
    redeemed_at: str | None = None
    verdict_id: str | None = None
    exit_code: int | None = None
    slot: dict[str, object] | None = None
    kind: str = KIND_MATCH
    # Which of this match's players are controls, and the band each declared.
    # Carried on the ticket because `submit` builds the verdict from the ticket
    # alone and never loads the definition the bands were declared in.
    controls: dict[str, str] = field(default_factory=dict)
    # The registered `Match.Template` this run rendered from, and the per-run
    # values bound into it. Both ride the ticket for the same reason `controls`
    # does: `submit` writes the verdict from the ticket alone.
    template: str | None = None
    template_bindings: dict[str, object] = field(default_factory=dict)

    @property
    def is_preview(self) -> bool:
        return self.kind == KIND_PREVIEW

    @property
    def arity(self) -> int:
        return len(self.players)

    @property
    def redeemed(self) -> bool:
        return self.redeemed_at is not None

    @property
    def exhausted(self) -> bool:
        return self.attempts >= self.attempt_cap

    def as_dict(self) -> dict[str, object]:
        return {
            "ticket_id": self.ticket_id,
            "tournament_id": self.tournament_id,
            "match_id": self.match_id,
            "players": list(self.players),
            "presented": list(self.presented),
            "verbatim_hash": self.verbatim_hash,
            "judge": dict(self.judge),
            "created_at": self.created_at,
            "attempts": self.attempts,
            "attempt_cap": self.attempt_cap,
            "redeemed_at": self.redeemed_at,
            "verdict_id": self.verdict_id,
            "exit_code": self.exit_code,
            "slot": dict(self.slot) if self.slot is not None else None,
            "kind": self.kind,
            "controls": dict(self.controls),
            "template": self.template,
            "template_bindings": dict(self.template_bindings),
        }


class TicketStore:
    """The ``tickets/`` staging area of one `Tournament.Depot`."""

    def __init__(self, depot_root: Path | str) -> None:
        self.root = Path(depot_root).expanduser().resolve() / TICKETS_DIRNAME

    def mint(
        self,
        *,
        tournament_id: str,
        match_id: str,
        players: tuple[str, ...] | list[str],
        presented: tuple[str, ...] | list[str],
        verbatim_hash: str,
        judge: dict[str, object],
        attempt_cap: int = DEFAULT_ATTEMPT_CAP,
        kind: str = KIND_MATCH,
        controls: dict[str, str] | None = None,
    ) -> Ticket:
        if kind not in TICKET_KINDS:
            raise TicketError(
                f"unknown ticket kind {kind!r}; expected one of {list(TICKET_KINDS)}"
            )
        ticket = Ticket(
            ticket_id=generate_uuid4_string(),
            tournament_id=tournament_id,
            match_id=match_id,
            players=tuple(str(item) for item in players),
            presented=tuple(str(item) for item in presented),
            verbatim_hash=verbatim_hash,
            judge=dict(judge),
            created_at=iso_z(datetime.now(timezone.utc), drop_micros=False),
            attempt_cap=attempt_cap,
            kind=kind,
            controls=dict(controls or {}),
        )
        self._write(ticket)
        return ticket

    def load(self, ticket_id: str) -> Ticket:
        path = self._path(ticket_id)
        if not path.is_file():
            raise TicketError(f"no such tournament ticket: {ticket_id}")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise TicketError(f"unreadable tournament ticket {ticket_id}: {error}") from error
        return _ticket_from_payload(payload, ticket_id)

    def set_verbatim_hash(self, ticket_id: str, verbatim_hash: str) -> Ticket:
        """Record the hash of what the judge was actually shown.

        Written after minting because the prompt embeds the ticket id, so the
        hash cannot exist before the ticket does.
        """
        updated = _replace(self.load(ticket_id), verbatim_hash=verbatim_hash)
        self._write(updated)
        return updated

    def set_template(
        self,
        ticket_id: str,
        template: str | None,
        bindings: dict[str, object],
    ) -> Ticket:
        """Record which template rendered this run, and what was bound into it.

        Written after minting for the same reason the hash is: the frame embeds
        the ticket id, so neither can exist before the ticket does.
        """
        updated = _replace(
            self.load(ticket_id), template=template, template_bindings=dict(bindings)
        )
        self._write(updated)
        return updated

    def set_slot(self, ticket_id: str, slot: dict[str, object]) -> Ticket:
        """Carry the consumer slot forward so `submit` never loads a definition."""
        updated = _replace(self.load(ticket_id), slot=dict(slot))
        self._write(updated)
        return updated

    def record_attempt(self, ticket_id: str) -> Ticket:
        """Count one rejected submission against the cap.

        Only contract rejections reach here. A submission against a redeemed or
        exhausted ticket is refused without incrementing, so a confused judge
        cannot burn down a counter that no longer protects anything.
        """
        current = self.load(ticket_id)
        updated = _replace(current, attempts=current.attempts + 1)
        self._write(updated)
        return updated

    def redeem(self, ticket_id: str, *, verdict_id: str, exit_code: int | None) -> Ticket:
        current = self.load(ticket_id)
        if current.redeemed:
            raise TicketError(
                f"tournament ticket {ticket_id} was already redeemed by verdict "
                f"{current.verdict_id}"
            )
        updated = _replace(
            current,
            redeemed_at=iso_z(datetime.now(timezone.utc), drop_micros=False),
            verdict_id=verdict_id,
            exit_code=exit_code,
        )
        self._write(updated)
        return updated

    def sweep(
        self, *, horizon_seconds: int = SWEEP_HORIZON_SECONDS
    ) -> dict[str, int]:
        """Remove tickets older than the horizon, counted by kind.

        Split by kind because the two mean different things once gone: an
        unredeemed `match` ticket is a judge that failed to answer, while an
        unredeemed `preview` is somebody tuning a question.
        """
        removed: dict[str, int] = {}
        if not self.root.is_dir():
            return removed
        cutoff = time.time() - horizon_seconds
        for path in sorted(self.root.glob("*.json")):
            try:
                if path.stat().st_mtime >= cutoff:
                    continue
                kind = self.load(path.stem).kind
                path.unlink()
            except (OSError, TicketError):
                continue
            removed[kind] = removed.get(kind, 0) + 1
        return removed

    def _path(self, ticket_id: str) -> Path:
        return self.root / f"{ticket_id}.json"

    def _write(self, ticket: Ticket) -> None:
        # One file per ticket means one writer per file, so the pending side needs
        # no depot-wide lock; Bloberia still takes one at submit.
        self.root.mkdir(parents=True, exist_ok=True)
        path = self._path(ticket.ticket_id)
        temp = path.with_suffix(".json.tmp")
        temp.write_text(json.dumps(ticket.as_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temp, path)


def _replace(ticket: Ticket, **changes: object) -> Ticket:
    payload = {
        field: getattr(ticket, field)
        for field in (
            "ticket_id",
            "tournament_id",
            "match_id",
            "players",
            "presented",
            "verbatim_hash",
            "judge",
            "created_at",
            "attempts",
            "attempt_cap",
            "redeemed_at",
            "verdict_id",
            "exit_code",
            "slot",
            "kind",
            "controls",
            "template",
            "template_bindings",
        )
    }
    payload.update(changes)
    return Ticket(**payload)  # type: ignore[arg-type]


def _ticket_from_payload(payload: object, ticket_id: str) -> Ticket:
    if not isinstance(payload, dict):
        raise TicketError(f"corrupt tournament ticket: {ticket_id}")
    try:
        return Ticket(
            ticket_id=str(payload["ticket_id"]),
            tournament_id=str(payload["tournament_id"]),
            match_id=str(payload["match_id"]),
            players=tuple(str(item) for item in payload["players"]),
            presented=tuple(str(item) for item in payload["presented"]),
            verbatim_hash=str(payload["verbatim_hash"]),
            judge=dict(payload["judge"]),  # type: ignore[arg-type]
            created_at=str(payload["created_at"]),
            attempts=int(payload.get("attempts", 0)),
            attempt_cap=int(payload.get("attempt_cap", DEFAULT_ATTEMPT_CAP)),
            redeemed_at=payload.get("redeemed_at") and str(payload["redeemed_at"]),
            verdict_id=payload.get("verdict_id") and str(payload["verdict_id"]),
            exit_code=payload.get("exit_code"),  # type: ignore[arg-type]
            slot=payload.get("slot"),  # type: ignore[arg-type]
            # Defaulted, not required: a ticket written before this field is a
            # match ticket, not a broken one.
            kind=str(payload.get("kind", KIND_MATCH)),
            controls={
                str(name): str(band)
                for name, band in (payload.get("controls") or {}).items()
            },
            template=payload.get("template") and str(payload["template"]),
            template_bindings=dict(payload.get("template_bindings") or {}),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise TicketError(f"corrupt tournament ticket {ticket_id}: {error}") from error
