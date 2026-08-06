# $kw: ^tournament-report --from Agentos.Tournament --from Tournament.Verdict::No.Contest --note [CT] raw accumulation only; any ranking over a pool is a read-side fold and is not computed here ^<anchor-on-landing>
"""Raw accumulation over a tournament's verdicts.

Counts, not standings. Every count is reported beside its match count so a
consumer can filter by confidence instead of reading an under-played player as a
finding, and the no-contest distribution is reported both pool-wide and per
player because those two readings indict different things.
"""

from __future__ import annotations

from agentos.tournament.model import Tournament, Verdict


def tournament_report(
    *,
    tournament: Tournament,
    verdicts: tuple[Verdict, ...] | list[Verdict],
) -> dict[str, object]:
    verdicts = tuple(verdicts)
    rows = {
        player: {
            "player": player,
            "wins": 0,
            "losses": 0,
            "matches": 0,
            "no_contests": 0,
        }
        for player in tournament.players
    }

    no_contest_count = 0
    # Counted on the attribution axis, not on free text: a refusal's prose is one
    # sample, while "which of the three things is at fault" is the readable signal.
    attributions: dict[str, int] = {}
    reason_samples: dict[str, str] = {}

    for verdict in verdicts:
        players = [str(item) for item in verdict.envelope.get("players", ())]
        for player in players:
            if player in rows:
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
                if player in rows:
                    rows[player]["no_contests"] += 1
            continue
        preferred = verdict.preferred
        for player in players:
            if player not in rows:
                continue
            if player == preferred:
                rows[player]["wins"] += 1
            else:
                rows[player]["losses"] += 1

    return {
        "status": "ok",
        "command": "tournament show",
        "tournament_id": tournament.tournament_id,
        "definition_path": tournament.definition_path,
        "verdict_count": len(verdicts),
        "players": [rows[player] for player in tournament.players],
        "no_contest": {
            "count": no_contest_count,
            "rate": (no_contest_count / len(verdicts)) if verdicts else 0.0,
            "attributions": attributions,
            "reason_samples": reason_samples,
        },
    }
