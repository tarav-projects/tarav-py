# Tournament-owned storage for tournaments and verdicts.
"""Tournament and verdict storage over the shared internal record depot.

Append-only is enforced here: ``OpaqueRecordDepot.replace`` overwrites in
place, so this store exposes creation and reading and never reaches for it.

The store mints its own ``record_id``. The depot stores cargo verbatim and hands back no
identity, so a verdict that must be addressable carries its id in its own schema.
"""

from __future__ import annotations

from pathlib import Path

from datetime import datetime, timezone

from tarav._core.clock import iso_z, utc_now_iso
from tarav._core.ids import generate_uuid4_string
from tarav._core.record_depot import OpaqueRecordDepot
from tarav.tournament.depot import DEFINITIONS_DIRNAME, resolve_depot_root
from tarav.tournament.model import (
    ENVELOPE_KEY,
    RECORD_ID_KEY,
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
    """One `Tournament.Depot`: frozen definitions beside namespaced records."""

    def __init__(self, root: Path | str | None = None) -> None:
        self.root = resolve_depot_root(root)
        self.depot = OpaqueRecordDepot(self.root)

    def definition_dir(self, tournament_id: str) -> Path:
        return self.root / DEFINITIONS_DIRNAME / tournament_id

    def create_tournament(
        self,
        *,
        definition_path: str,
        definition_digest: str,
    ) -> Tournament:



        tournament_id = generate_uuid4_string()
        self.depot.insert(
            {
                KIND_KEY: RECORD_KIND_TOURNAMENT,
                "tournament_id": tournament_id,
                "definition_path": definition_path,
                "definition_digest": definition_digest,
                "created_at": utc_now_iso(),
            },
            namespace=tournament_id,
        )
        return self.tournament(tournament_id)

    def tournament(self, tournament_id: str) -> Tournament:
        cargo = self.depot.first(
            {KIND_KEY: {"equals": RECORD_KIND_TOURNAMENT}}, namespace=tournament_id
        )
        if cargo is None:
            raise TournamentNotFoundError(f"tournament does not exist: {tournament_id}")
        return _tournament_from_cargo(cargo)

    def tournaments(self) -> tuple[Tournament, ...]:
        """List by namespace directory rather than by scanning every record."""
        found: list[Tournament] = []
        for namespace in self.depot.namespaces():
            if "/" in namespace:
                continue
            try:
                found.append(self.tournament(namespace))
            except TournamentNotFoundError:
                continue
        return tuple(sorted(found, key=lambda item: item.created_at))

    def append_verdict(
        self,
        *,
        tournament_id: str,
        match_id: str,
        players: tuple[str, ...],
        outcome: VerdictOutcome,
        judge: dict[str, object],
        presented: tuple[str, ...],
        verbatim_hash: str,
        ordering: tuple[str, ...] | list[str] | None = None,
        refusal_reason: str | None = None,
        ticket: str | None = None,
        duration_ms: int | None = None,
        slot: dict[str, object] | None = None,
        controls: dict[str, str] | None = None,
        template: str | None = None,
        template_bindings: dict[str, object] | None = None,
        player_labels: dict[str, str] | None = None,
        match_label: str | None = None,
    ) -> Verdict:
        match_id = require_match_id(match_id)
        slot_value = require_unshadowed_slot(slot)
        if outcome is VerdictOutcome.ORDERED:
            ordering = _require_ordering(ordering, players)
            refusal_reason = None
        else:
            if not refusal_reason:
                raise TournamentError("a no-contest verdict requires a stated reason")
            ordering = None

        envelope: dict[str, object] = {
            "tournament_id": tournament_id,
            "match_id": match_id,
            "players": list(players),
            "presented": list(presented),
            "outcome": outcome.value,
            "ordering": list(ordering) if ordering is not None else None,



            "controls": dict(controls or {}),



            "template": template,
            "template_bindings": dict(template_bindings or {}),



            "player_labels": dict(player_labels or {}),
            "match_label": match_label,
            "refusal_reason": refusal_reason,
            "ticket": ticket,
            "judge": dict(judge),
            "verbatim_hash": verbatim_hash,


            "recorded_at": iso_z(datetime.now(timezone.utc), drop_micros=False),
            "duration_ms": duration_ms,
        }
        cargo = {
            KIND_KEY: RECORD_KIND_VERDICT,
            RECORD_ID_KEY: generate_uuid4_string(),
            ENVELOPE_KEY: envelope,
            SLOT_KEY: slot_value,
        }
        self.depot.insert(cargo, namespace=tournament_id)
        return _verdict_from_cargo(cargo)

    def verdicts(
        self, tournament_id: str, *, match_id: str | None = None
    ) -> tuple[Verdict, ...]:
        query: dict[str, dict[str, object]] = {
            KIND_KEY: {"equals": RECORD_KIND_VERDICT},
            f"{ENVELOPE_KEY}.tournament_id": {"equals": tournament_id},
        }
        if match_id is not None:
            query[f"{ENVELOPE_KEY}.match_id"] = {"equals": match_id}
        cargos = self.depot.all(query, namespace=tournament_id)
        return tuple(
            sorted(
                (_verdict_from_cargo(cargo) for cargo in cargos),
                key=lambda item: (item.envelope["recorded_at"], item.record_id),
            )
        )


def _require_ordering(
    ordering: object, players: tuple[str, ...]
) -> tuple[str, ...]:
    """An ordered outcome must rank exactly the match's players, once each."""
    if not isinstance(ordering, (list, tuple)):
        raise TournamentError("an ordered outcome must supply the ranked players")
    ranked = tuple(str(item) for item in ordering)
    if sorted(ranked) != sorted(players):
        raise TournamentError(
            "an ordered outcome must rank exactly the match's players once each: "
            f"expected {sorted(players)}, got {sorted(ranked)}"
        )
    return ranked


def _tournament_from_cargo(value: object) -> Tournament:
    if not isinstance(value, dict):
        raise TournamentError(f"corrupt tournament record: {value!r}")
    return Tournament(
        tournament_id=str(value["tournament_id"]),
        definition_path=str(value["definition_path"]),
        definition_digest=str(value["definition_digest"]),
        created_at=str(value["created_at"]),
    )


def _verdict_from_cargo(value: object) -> Verdict:
    if not isinstance(value, dict):
        raise TournamentError(f"corrupt verdict record: {value!r}")
    record_id = value.get(RECORD_ID_KEY)
    envelope = value.get(ENVELOPE_KEY)
    slot = value.get(SLOT_KEY)
    if not isinstance(record_id, str) or not isinstance(envelope, dict) or not isinstance(slot, dict):
        raise TournamentError(f"corrupt verdict record: {record_id!r}")
    return Verdict(record_id=record_id, envelope=dict(envelope), slot=dict(slot))
