# $kw: ^tournament-sampling --from Tournament.Hook --note [DC] pair selection is a declared hook with a working engine default ^<anchor-on-landing>
"""Default pair selection, and the seam a consumer overrides.

The default spreads matches evenly: it fills the least-played pairs first, so a
pool is covered before any pair repeats. Uncertainty-driven sampling — the thing
that makes a large pool affordable — is deliberately not here; this establishes
the seam it will land on.
"""

from __future__ import annotations

from itertools import combinations

from agentos.tournament.hooks import TournamentDefinition


def select_pairs(
    *,
    definition: TournamentDefinition,
    pool: tuple[str, ...],
    budget: int,
    verdicts: tuple[dict[str, object], ...] = (),
) -> tuple[tuple[str, str], ...]:
    """Resolve the pairs for one run: consumer hook first, engine default otherwise."""
    override = definition.select_pairs(pool=pool, budget=budget, verdicts=verdicts)
    if override is not None:
        return override
    return _least_played_first(pool=pool, budget=budget, verdicts=verdicts)


def _least_played_first(
    *,
    pool: tuple[str, ...],
    budget: int,
    verdicts: tuple[dict[str, object], ...],
) -> tuple[tuple[str, str], ...]:
    candidates = [tuple(sorted(pair)) for pair in combinations(sorted(set(pool)), 2)]
    if not candidates or budget <= 0:
        return ()

    played = _played_counts(verdicts)
    counts = {pair: played.get(pair, 0) for pair in candidates}

    chosen: list[tuple[str, str]] = []
    for _ in range(budget):
        pair = min(candidates, key=lambda item: (counts[item], item))
        chosen.append(pair)
        counts[pair] += 1
    return tuple(chosen)


def _played_counts(
    verdicts: tuple[dict[str, object], ...]
) -> dict[tuple[str, str], int]:
    counts: dict[tuple[str, str], int] = {}
    for envelope in verdicts:
        players = envelope.get("players")
        if not isinstance(players, (list, tuple)) or len(players) != 2:
            continue
        key = tuple(sorted(str(player) for player in players))
        counts[key] = counts.get(key, 0) + 1
    return counts
