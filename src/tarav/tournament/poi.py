# $kw: ^tournament-poi --from Agentos.Tournament --from POI.System --note [RJ] the engine emits POIs about tournament dynamics only; consumers read the records and mint their own domain POIs ^<anchor-on-landing>
"""Engine-owned POI classes.

These describe tournament dynamics, never domain semantics. The engine never
learns what a player represents, so it cannot say a line is weakly typed — only
that a player loses consistently, that no judge could evaluate it, or that the
definition's refusals are scattered enough to indict the question itself.
"""

from __future__ import annotations

from tarav.poi import POIInstance, POILocation, tarav_poi_class_reference

PLAYER_LOW_STANDING = "Tournament.Linter/Player.LowStanding"
PLAYER_UNJUDGEABLE = "Tournament.Linter/Player.Unjudgeable"
DEFINITION_INCOHERENT = "Tournament.Linter/Definition.Incoherent"

TOURNAMENT_POI_CLASSES = (
    PLAYER_LOW_STANDING,
    PLAYER_UNJUDGEABLE,
    DEFINITION_INCOHERENT,
)



MIN_MATCHES_FOR_STANDING = 6


MIN_MATCHES_FOR_UNJUDGEABLE = 3
LOW_STANDING_WIN_RATE = 0.25
UNJUDGEABLE_NO_CONTEST_RATE = 0.5
INCOHERENT_POOL_NO_CONTEST_RATE = 0.5


def tournament_poi_instances(report: dict[str, object]) -> tuple[POIInstance, ...]:
    """Derive engine-owned POIs from one raw accumulation report."""
    tournament_id = str(report.get("tournament_id", "unknown"))
    target = POILocation(path=f"tournament:{tournament_id}")
    instances: list[POIInstance] = []

    players = report.get("players")
    rows = players if isinstance(players, list) else []

    for row in rows:
        matches = int(row.get("matches", 0))
        if matches < MIN_MATCHES_FOR_UNJUDGEABLE:
            continue
        no_contests = int(row.get("no_contests", 0))
        if no_contests / matches >= UNJUDGEABLE_NO_CONTEST_RATE:
            instances.append(
                _player_unjudgeable(
                    target,
                    f"no judge could evaluate {row['player']!r} in "
                    f"{no_contests} of {matches} matches",
                    {"player": row["player"], "no_contests": no_contests, "matches": matches},
                )
            )
            continue
        if matches < MIN_MATCHES_FOR_STANDING:
            continue
        decided = matches - no_contests
        if decided and int(row.get("wins", 0)) / decided <= LOW_STANDING_WIN_RATE:
            instances.append(
                _player_low_standing(
                    target,
                    f"{row['player']!r} lost {row['losses']} of {decided} decided matches",
                    {"player": row["player"], "wins": row["wins"], "matches": matches},
                )
            )

    no_contest = report.get("no_contest")
    if isinstance(no_contest, dict):
        rate = float(no_contest.get("rate", 0.0))
        count = int(no_contest.get("count", 0))
        if count and rate >= INCOHERENT_POOL_NO_CONTEST_RATE:
            instances.append(
                _definition_incoherent(
                    target,
                    f"judges declined {count} of {report.get('verdict_count')} matches "
                    "across the pool",
                    {"no_contest_rate": rate, "reasons": no_contest.get("reasons", {})},
                )
            )
    return tuple(instances)


def _instance(
    class_name: str,
    target: POILocation,
    situation: str,
    evidence: dict[str, object],
) -> POIInstance:
    return POIInstance.create(
        class_reference=tarav_poi_class_reference(class_name),
        target=target,
        severity="warning",
        situation=situation,
        evidence=evidence,
    )


# $kw: Tournament.Linter/Player.LowStanding
# --note [DF] a player has been decided against in at least three quarters of its decided matches
# --note [CT] it reports standing within the pool, never that the player is wrong
# --note [CT] the instance preserves the player, its wins, and its match count
# --note [RJ] class-level repair guidance is not yet established
def _player_low_standing(
    target: POILocation, situation: str, evidence: dict[str, object]
) -> POIInstance:
    return _instance(PLAYER_LOW_STANDING, target, situation, evidence)


# $kw: Tournament.Linter/Player.Unjudgeable
# --note [DF] at least half of a player's matches ended with no judge able to decide them
# --note [CT] it indicts the player's evaluability, not its quality — an unjudgeable player has no standing to be low
# --note [CT] the instance preserves the player, its no-contest count, and its match count
# --note [RJ] class-level repair guidance is not yet established
def _player_unjudgeable(
    target: POILocation, situation: str, evidence: dict[str, object]
) -> POIInstance:
    return _instance(PLAYER_UNJUDGEABLE, target, situation, evidence)


# $kw: Tournament.Linter/Definition.Incoherent
# --note [DF] at least half of the whole pool's matches ended in no contest, which indicts the question rather than any player
# --note [CT] the instance preserves the pool no-contest rate and the judges' stated reasons
# --note [RJ] class-level repair guidance is not yet established
def _definition_incoherent(
    target: POILocation, situation: str, evidence: dict[str, object]
) -> POIInstance:
    return _instance(DEFINITION_INCOHERENT, target, situation, evidence)
