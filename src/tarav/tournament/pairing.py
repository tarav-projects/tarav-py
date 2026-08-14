# $kw: ^tournament-pairing --from Tournament.Hook --note [DC] pairing strategies live in an importable library a definition may call, never in the engine --supp ^c20260806-15u ^<anchor-on-landing>
"""Pairing strategies a tournament definition may import and call.

This module exists **for definitions, not for the engine**. The engine holds no
pool and enumerates no pairs; a consumer that wants round-robin or least-played
coverage calls one of these from its own ``match_players`` hook. Nothing in
``tarav.tournament`` imports this module, and a test asserts that.

Every strategy returns one player set — the shape ``match_players`` returns — or
``None`` when the pool cannot produce one. Returning ``None`` from the hook ends
a run before its budget.
"""

from __future__ import annotations

import random
from itertools import combinations


def _unique_pool(pool: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    seen: list[str] = []
    for item in pool:
        text = str(item)
        if text not in seen:
            seen.append(text)
    return tuple(seen)


def _all_pairs(pool: tuple[str, ...]) -> tuple[tuple[str, str], ...]:
    return tuple(combinations(pool, 2))


def round_robin(
    pool: tuple[str, ...] | list[str], *, match_index: int
) -> tuple[str, str] | None:
    """Walk every pair in a stable order, cycling once the pool is covered."""
    pairs = _all_pairs(_unique_pool(pool))
    if not pairs:
        return None
    return pairs[match_index % len(pairs)]


def least_played(
    pool: tuple[str, ...] | list[str],
    *,
    verdicts: tuple[dict[str, object], ...] = (),
) -> tuple[str, str] | None:
    """Pick a pair with the fewest recorded verdicts, ties broken stably.

    It reads only durable verdicts, so matches already dispatched in the current
    run are invisible. Under concurrency that yields extra samples of one pair
    rather than corruption; a consumer that wants spread adds randomness.
    """
    pairs = _all_pairs(_unique_pool(pool))
    if not pairs:
        return None
    played = played_counts(verdicts)
    return min(pairs, key=lambda pair: (played.get(tuple(sorted(pair)), 0), pair))


def random_pair(
    pool: tuple[str, ...] | list[str], *, rng: random.Random | None = None
) -> tuple[str, str] | None:
    """Draw a pair uniformly. Seed the rng for a reproducible run."""
    unique = _unique_pool(pool)
    if len(unique) < 2:
        return None
    chooser = rng or random.Random()
    first, second = chooser.sample(list(unique), 2)
    return (first, second)


def played_counts(
    verdicts: tuple[dict[str, object], ...],
) -> dict[tuple[str, ...], int]:
    """How many verdicts each unordered pair already carries."""
    counts: dict[tuple[str, ...], int] = {}
    for envelope in verdicts:
        players = envelope.get("players")
        if not isinstance(players, (list, tuple)) or len(players) != 2:
            continue
        key = tuple(sorted(str(player) for player in players))
        counts[key] = counts.get(key, 0) + 1
    return counts


def random_players(
    pool: tuple[str, ...] | list[str],
    *,
    arity: int,
    rng: random.Random | None = None,
) -> tuple[str, ...] | None:
    """Draw ``arity`` distinct players uniformly.

    The N-ary generalization of ``random_pair``. A larger arity buys more
    comparisons per judge run; where that stops paying against a judge's
    discrimination is empirical, so the caller picks the number.
    """
    unique = _unique_pool(pool)
    if arity < 2 or len(unique) < arity:
        return None
    chooser = rng or random.Random()
    return tuple(chooser.sample(list(unique), arity))
