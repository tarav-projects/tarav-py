# $kw: ^tournament-store --from Agentos.Tournament --from Tournament.Verdict --from Agentos.Bloberia --note [CT] append-only is a Tournament-layer rule; BloberiaDepot.edit exists and this store never calls it ^<anchor-on-landing>
"""Bloberia-backed tournament and verdict storage.

Append-only is enforced here, not by Bloberia: ``BloberiaDepot.edit`` mutates in
place, so this store exposes creation and reading and never reaches for it.
"""

from __future__ import annotations

from pathlib import Path

from datetime import datetime, timezone

from agentos._core.clock import iso_z, utc_now_iso
from agentos.bloberia import BloberiaDepot, BloberiaRecord
from agentos.tournament.model import (
    ENVELOPE_KEY,
    KIND_KEY,
    RECORD_KIND_TOURNAMENT,
    RECORD_KIND_VERDICT,
    SLOT_KEY,
    Tournament,
    TournamentError,
    Verdict,
    VerdictOutcome,
    require_match_id,
    require_unshadowed_slot,
)


class TournamentNotFoundError(TournamentError):
    pass


class TournamentStore:
    """One tournament depot rooted at an explicit directory."""

    def __init__(self, root: Path | str) -> None:
        self.depot = BloberiaDepot(root)

    def create_tournament(
        self,
        *,
        definition_path: str,
        definition_digest: str,
        players: tuple[str, ...] | list[str],
    ) -> Tournament:
        players = tuple(str(player) for player in players)
        if len(set(players)) != len(players):
            raise TournamentError("player identities must be unique within a pool")
        if len(players) < 2:
            raise TournamentError("a tournament pool needs at least two players")
        record = self.depot.create(
            {
                KIND_KEY: RECORD_KIND_TOURNAMENT,
                "definition_path": definition_path,
                "definition_digest": definition_digest,
                "players": list(players),
                "created_at": utc_now_iso(),
            }
        )
        return _tournament_from_record(record)

    def tournament(self, tournament_id: str) -> Tournament:
        matches = self.depot.query(
            {"value": {KIND_KEY: RECORD_KIND_TOURNAMENT}}
        )
        for record in matches:
            if record.id == tournament_id:
                return _tournament_from_record(record)
        raise TournamentNotFoundError(f"tournament does not exist: {tournament_id}")

    def tournaments(self) -> tuple[Tournament, ...]:
        records = self.depot.query({"value": {KIND_KEY: RECORD_KIND_TOURNAMENT}})
        return tuple(
            sorted(
                (_tournament_from_record(record) for record in records),
                key=lambda item: item.created_at,
            )
        )

    def append_verdict(
        self,
        *,
        tournament_id: str,
        match_id: str,
        players: tuple[str, str],
        outcome: VerdictOutcome,
        judge: dict[str, object],
        presented: tuple[str, str],
        verbatim_hash: str,
        preferred: str | None = None,
        no_contest_reason: str | None = None,
        no_contest_attribution: str | None = None,
        duration_ms: int | None = None,
        slot: dict[str, object] | None = None,
    ) -> Verdict:
        match_id = require_match_id(match_id)
        slot_value = require_unshadowed_slot(slot)
        if outcome is VerdictOutcome.PREFERRED:
            if preferred not in players:
                raise TournamentError(
                    "a preferred outcome must name one of the match's players"
                )
            no_contest_reason = None
            no_contest_attribution = None
        else:
            if not no_contest_reason:
                raise TournamentError("a no-contest verdict requires a stated reason")
            if not no_contest_attribution:
                raise TournamentError(
                    "a no-contest verdict must attribute the refusal to the "
                    "question, a player, or the prompt"
                )
            preferred = None

        envelope: dict[str, object] = {
            "tournament_id": tournament_id,
            "match_id": match_id,
            "players": list(players),
            "presented": list(presented),
            "outcome": outcome.value,
            "preferred": preferred,
            "no_contest_reason": no_contest_reason,
            "no_contest_attribution": no_contest_attribution,
            "judge": dict(judge),
            "verbatim_hash": verbatim_hash,
            # Microsecond precision: repeated runs of one match are expected, and
            # second-resolution timestamps would make their recorded order arbitrary.
            "recorded_at": iso_z(datetime.now(timezone.utc), drop_micros=False),
            "duration_ms": duration_ms,
        }
        record = self.depot.create(
            {
                KIND_KEY: RECORD_KIND_VERDICT,
                ENVELOPE_KEY: envelope,
                SLOT_KEY: slot_value,
            }
        )
        return _verdict_from_record(record)

    def verdicts(
        self, tournament_id: str, *, match_id: str | None = None
    ) -> tuple[Verdict, ...]:
        query: dict[str, object] = {
            KIND_KEY: RECORD_KIND_VERDICT,
            ENVELOPE_KEY: {"tournament_id": tournament_id},
        }
        if match_id is not None:
            query[ENVELOPE_KEY] = {
                "tournament_id": tournament_id,
                "match_id": match_id,
            }
        records = self.depot.query({"value": query})
        return tuple(
            sorted(
                (_verdict_from_record(record) for record in records),
                key=lambda item: (item.envelope["recorded_at"], item.record_id),
            )
        )


def _tournament_from_record(record: BloberiaRecord) -> Tournament:
    value = record.value
    if not isinstance(value, dict):
        raise TournamentError(f"corrupt tournament record: {record.id}")
    return Tournament(
        tournament_id=record.id,
        definition_path=str(value["definition_path"]),
        definition_digest=str(value["definition_digest"]),
        players=tuple(str(player) for player in value["players"]),
        created_at=str(value["created_at"]),
    )


def _verdict_from_record(record: BloberiaRecord) -> Verdict:
    value = record.value
    if not isinstance(value, dict):
        raise TournamentError(f"corrupt verdict record: {record.id}")
    envelope = value.get(ENVELOPE_KEY)
    slot = value.get(SLOT_KEY)
    if not isinstance(envelope, dict) or not isinstance(slot, dict):
        raise TournamentError(f"corrupt verdict record: {record.id}")
    return Verdict(record_id=record.id, envelope=dict(envelope), slot=dict(slot))
