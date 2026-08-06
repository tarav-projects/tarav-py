# $kw: ^test-tournament-pairing --from Tournament.Hook --note [DF] boundary tests for the consumer-facing pairing library and the engine's independence from it ^<anchor-on-landing>
from __future__ import annotations

import random
from pathlib import Path

from agentos.tournament.pairing import (
    least_played,
    played_counts,
    random_pair,
    random_players,
    round_robin,
)

POOL = ("a", "b", "c")


def _verdict(first: str, second: str) -> dict[str, object]:
    return {"players": [first, second]}


def test_round_robin_covers_every_pair_before_repeating() -> None:
    seen = [round_robin(POOL, match_index=i) for i in range(3)]
    assert sorted(seen) == [("a", "b"), ("a", "c"), ("b", "c")]
    assert round_robin(POOL, match_index=3) == seen[0]


def test_round_robin_is_deterministic() -> None:
    assert round_robin(POOL, match_index=5) == round_robin(POOL, match_index=5)


def test_least_played_prefers_an_unplayed_pair() -> None:
    verdicts = (_verdict("a", "b"), _verdict("a", "b"), _verdict("a", "c"))
    assert least_played(POOL, verdicts=verdicts) == ("b", "c")


def test_least_played_ignores_player_order_when_counting() -> None:
    verdicts = (_verdict("b", "a"), _verdict("a", "b"))
    assert least_played(("a", "b", "c"), verdicts=verdicts) != ("a", "b")


def test_random_pair_is_reproducible_from_a_seed() -> None:
    first = random_pair(POOL, rng=random.Random(11))
    second = random_pair(POOL, rng=random.Random(11))
    assert first == second
    assert first is not None and set(first) <= set(POOL)


def test_random_pair_actually_varies_across_seeds() -> None:
    drawn = {random_pair(POOL, rng=random.Random(seed)) for seed in range(20)}
    assert len(drawn) > 1


def test_every_strategy_returns_none_when_the_pool_is_too_small() -> None:
    assert round_robin(("a",), match_index=0) is None
    assert least_played(("a",)) is None
    assert random_pair(("a",)) is None
    assert round_robin((), match_index=0) is None


def test_a_pool_with_duplicates_is_deduplicated() -> None:
    assert round_robin(("a", "a", "b"), match_index=0) == ("a", "b")


def test_played_counts_skips_malformed_envelopes() -> None:
    counts = played_counts(({"players": ["a"]}, {"nope": 1}, _verdict("a", "b")))
    assert counts == {("a", "b"): 1}


def test_the_engine_never_imports_the_pairing_library() -> None:
    """Pairing is consumer territory; packaging it here must not create a dependency."""
    engine_dir = Path(__file__).resolve().parents[1] / "src" / "agentos" / "tournament"
    importers = [
        path.name
        for path in sorted(engine_dir.glob("*.py"))
        if path.name != "pairing.py" and "pairing" in path.read_text(encoding="utf-8")
    ]
    assert importers == []


def test_random_players_draws_the_requested_arity() -> None:
    drawn = random_players(("a", "b", "c", "d", "e"), arity=4, rng=random.Random(3))
    assert drawn is not None
    assert len(drawn) == 4
    assert len(set(drawn)) == 4
    assert set(drawn) <= {"a", "b", "c", "d", "e"}


def test_random_players_is_reproducible_from_a_seed() -> None:
    first = random_players(("a", "b", "c", "d"), arity=3, rng=random.Random(5))
    second = random_players(("a", "b", "c", "d"), arity=3, rng=random.Random(5))
    assert first == second


def test_random_players_returns_none_when_the_pool_is_too_small() -> None:
    assert random_players(("a", "b"), arity=4) is None
    assert random_players(("a", "b", "c"), arity=1) is None
