# $kw: ^tournament-report --from Agentos.Tournament --from Tournament.Verdict::No.Contest --note [CT] raw accumulation only; the fold enumerates its players from the verdicts because the engine holds no declared pool --supp ^c20260806-43u ^<anchor-on-landing>
"""Raw accumulation over a tournament's verdicts.

Counts, not standings. Every count is reported beside its match count so a
consumer can filter by confidence instead of reading an under-played player as a
finding, and the no-contest distribution is reported both pool-wide and per
player because those two readings indict different things.

The player set comes from the verdicts, not from a declared pool: the engine
holds none, and a player whose payload was edited out of the definition keeps the
history it accumulated instead of vanishing from the read.
"""

from __future__ import annotations

from agentos.tournament.model import Tournament, Verdict


def tournament_report(
    *,
    tournament: Tournament,
    verdicts: tuple[Verdict, ...] | list[Verdict],
) -> dict[str, object]:
    verdicts = tuple(verdicts)
    rows: dict[str, dict[str, object]] = {}

    def row_for(player: str) -> dict[str, object]:
        if player not in rows:
            rows[player] = {
                "player": player,
                "wins": 0,
                "losses": 0,
                "matches": 0,
                "no_contests": 0,
            }
        return rows[player]

    for verdict in verdicts:
        for player in verdict.envelope.get("players", ()):
            row_for(str(player))

    no_contest_count = 0
    # Counted on the attribution axis, not on free text: a refusal's prose is one
    # sample, while "which of the three things is at fault" is the readable signal.
    attributions: dict[str, int] = {}
    reason_samples: dict[str, str] = {}

    for verdict in verdicts:
        players = [str(item) for item in verdict.envelope.get("players", ())]
        for player in players:
            rows[player]["matches"] += 1
        if verdict.outcome == "no_contest":
            no_contest_count += 1
            attribution = str(
                verdict.envelope.get("no_contest_attribution") or "unattributed"
            )
            attributions[attribution] = attributions.get(attribution, 0) + 1
            reason_samples.setdefault(
                attribution, str(verdict.envelope.get("no_contest_reason") or "")
            )
            for player in players:
                rows[player]["no_contests"] += 1
            continue
        # Pairwise comparisons are extracted here, never stored: for ranks i < j
        # the earlier player beat the later one. One 4-way match yields six.
        ordering = verdict.ordering or ()
        for rank, winner in enumerate(ordering):
            for loser in ordering[rank + 1 :]:
                rows[winner]["wins"] += 1
                rows[loser]["losses"] += 1

    return {
        "status": "ok",
        "command": "tournament show",
        "tournament_id": tournament.tournament_id,
        "definition_path": tournament.definition_path,
        "verdict_count": len(verdicts),
        "players": list(rows.values()),
        "no_contest": {
            "count": no_contest_count,
            "rate": (no_contest_count / len(verdicts)) if verdicts else 0.0,
            "attributions": attributions,
            "reason_samples": reason_samples,
        },
    }
