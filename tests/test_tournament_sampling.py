# $kw: ^test-tournament-sampling --from Tournament.Hook --from Agentos.Tournament --note [DF] boundary tests for the default pair sampler and the consumer override seam ^<anchor-on-landing>
from __future__ import annotations

from pathlib import Path

import pytest

from agentos.tournament import HookReturnError, load_definition, select_pairs


def _definition(tmp_path: Path, body: str = "question = 'q'\n"):
    path = tmp_path / "definition.py"
    path.write_text(body, encoding="utf-8")
    return load_definition(path, snapshot_dir=tmp_path / "snap")


POOL = ("a", "b", "c", "d")


def test_default_sampler_covers_every_pair_before_repeating(tmp_path: Path) -> None:
    definition = _definition(tmp_path)

    pairs = select_pairs(definition=definition, pool=POOL, budget=6, verdicts=())

    normalized = {tuple(sorted(pair)) for pair in pairs}
    assert len(pairs) == 6
    assert len(normalized) == 6


def test_default_sampler_prefers_the_least_played_pairs(tmp_path: Path) -> None:
    definition = _definition(tmp_path)
    verdicts = tuple(
        {"players": ["a", "b"]} for _ in range(3)
    )

    pairs = select_pairs(definition=definition, pool=POOL, budget=3, verdicts=verdicts)

    assert ("a", "b") not in {tuple(sorted(pair)) for pair in pairs}


def test_budget_larger_than_the_pool_wraps_into_a_second_round(tmp_path: Path) -> None:
    definition = _definition(tmp_path)

    pairs = select_pairs(definition=definition, pool=("a", "b", "c"), budget=5, verdicts=())

    assert len(pairs) == 5
    counts: dict[tuple[str, str], int] = {}
    for pair in pairs:
        key = tuple(sorted(pair))
        counts[key] = counts.get(key, 0) + 1
    assert max(counts.values()) - min(counts.values()) <= 1


def test_consumer_override_is_honored(tmp_path: Path) -> None:
    body = (
        "question = 'q'\n\n"
        "def select_pairs(ctx):\n"
        "    return [('a', 'd')] * ctx.budget\n"
    )
    definition = _definition(tmp_path, body)

    pairs = select_pairs(definition=definition, pool=POOL, budget=2, verdicts=())

    assert pairs == (("a", "d"), ("a", "d"))


def test_override_naming_an_unknown_player_is_rejected(tmp_path: Path) -> None:
    body = (
        "question = 'q'\n\n"
        "def select_pairs(ctx):\n"
        "    return [('a', 'zzz')]\n"
    )
    definition = _definition(tmp_path, body)

    with pytest.raises(HookReturnError) as excinfo:
        select_pairs(definition=definition, pool=POOL, budget=1, verdicts=())
    assert "zzz" in str(excinfo.value)


def test_override_pairing_a_player_with_itself_is_rejected(tmp_path: Path) -> None:
    body = (
        "question = 'q'\n\n"
        "def select_pairs(ctx):\n"
        "    return [('a', 'a')]\n"
    )
    definition = _definition(tmp_path, body)

    with pytest.raises(HookReturnError):
        select_pairs(definition=definition, pool=POOL, budget=1, verdicts=())


def test_a_pool_smaller_than_a_pair_yields_nothing(tmp_path: Path) -> None:
    definition = _definition(tmp_path)

    assert select_pairs(definition=definition, pool=("a",), budget=3, verdicts=()) == ()
