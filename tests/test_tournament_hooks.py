# $kw: ^test-tournament-hooks --from Tournament.Hook --from Tournament.Definition --note [DF] boundary tests for the required hooks, the defaulted ones, snapshot execution, and purity ^<anchor-on-landing>
from __future__ import annotations

from pathlib import Path

import pytest

from agentos.tournament import (
    HookLoadError,
    HookPurityError,
    HookReturnError,
    load_definition,
    open_definition,
)

MINIMAL = '''
question = "Which is better?"

def match_players(ctx):
    return ("a", "b")

def match_identity(ctx):
    return "|".join(ctx.players)
'''


def _write(tmp_path: Path, body: str, name: str = "definition.py") -> Path:
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path


def _load(tmp_path: Path, body: str):
    return load_definition(_write(tmp_path, body), snapshot_dir=tmp_path / "snap")


def test_a_definition_missing_match_players_fails_at_load(tmp_path: Path) -> None:
    body = 'def match_identity(ctx):\n    return "x"\n'
    with pytest.raises(HookLoadError) as excinfo:
        _load(tmp_path, body)
    assert "match_players" in str(excinfo.value)


def test_a_definition_missing_match_identity_fails_at_load(tmp_path: Path) -> None:
    body = 'def match_players(ctx):\n    return ("a", "b")\n'
    with pytest.raises(HookLoadError) as excinfo:
        _load(tmp_path, body)
    assert "match_identity" in str(excinfo.value)


def test_a_definition_missing_both_required_hooks_names_both(tmp_path: Path) -> None:
    with pytest.raises(HookLoadError) as excinfo:
        _load(tmp_path, "question = 'x'\n")
    message = str(excinfo.value)
    assert "match_players" in message and "match_identity" in message


def test_present_player_defaults_to_the_payload_itself(tmp_path: Path) -> None:
    definition = _load(tmp_path, MINIMAL)
    assert definition.present_player("- [CT] a line") == "- [CT] a line"


def test_present_player_hook_overrides_the_default(tmp_path: Path) -> None:
    body = MINIMAL + '\ndef present_player(ctx):\n    return f"<<{ctx.player}>>"\n'
    definition = _load(tmp_path, body)
    assert definition.present_player("x") == "<<x>>"


def test_match_players_returning_none_signals_exhaustion(tmp_path: Path) -> None:
    body = MINIMAL.replace('return ("a", "b")', "return None")
    definition = _load(tmp_path, body)
    assert definition.match_players(verdicts=(), match_index=0, budget=1) is None


def test_match_players_rejects_malformed_player_sets(tmp_path: Path) -> None:
    bad_returns = [
        '("a", "a")',            # the same player twice
        '("a", "")',             # an empty payload
        '("a",)',                # below the minimum arity
        '"ab"',                  # a bare string, not a set
        'tuple(str(i) for i in range(27))',  # past label exhaustion
    ]
    for bad in bad_returns:
        body = MINIMAL.replace('return ("a", "b")', f"return {bad}")
        definition = _load(tmp_path, body)
        with pytest.raises(HookReturnError):
            definition.match_players(verdicts=(), match_index=0, budget=1)


def test_match_players_accepts_any_arity_the_definition_chooses(
    tmp_path: Path,
) -> None:
    body = MINIMAL.replace('return ("a", "b")', 'return ("a", "b", "c", "d")')
    definition = _load(tmp_path, body)
    assert definition.match_players(verdicts=(), match_index=0, budget=1) == (
        "a",
        "b",
        "c",
        "d",
    )


def test_arity_may_differ_between_successive_calls(tmp_path: Path) -> None:
    """Arity is a per-match choice, not a tournament-level setting."""
    body = MINIMAL.replace(
        'return ("a", "b")',
        'return ("a", "b") if ctx.match_index % 2 else ("a", "b", "c", "d", "e", "f")',
    )
    definition = _load(tmp_path, body)
    first = definition.match_players(verdicts=(), match_index=0, budget=2)
    second = definition.match_players(verdicts=(), match_index=1, budget=2)
    assert len(first) == 6 and len(second) == 2


def test_match_identity_never_sees_the_presented_order(tmp_path: Path) -> None:
    """Identity must not vary with the shuffle, so the context cannot carry it."""
    body = MINIMAL.replace(
        'return "|".join(ctx.players)',
        'return "|".join(ctx.players) + str(getattr(ctx, "presented", None))',
    )
    definition = _load(tmp_path, body)
    identity = definition.match_identity(
        players=("a", "b"), presentations=("A", "B")
    )
    assert identity == "a|bNone"


def test_verdict_slot_defaults_to_empty_and_must_be_an_object(tmp_path: Path) -> None:
    definition = _load(tmp_path, MINIMAL)
    assert definition.verdict_slot(players=("a", "b"), presentations=("a", "b")) == {}

    body = MINIMAL + "\ndef verdict_slot(ctx):\n    return 7\n"
    definition = _load(tmp_path, body)
    with pytest.raises(HookReturnError):
        definition.verdict_slot(players=("a", "b"), presentations=("a", "b"))


def test_the_snapshot_executes_rather_than_the_edited_origin(tmp_path: Path) -> None:
    origin = _write(tmp_path, MINIMAL)
    definition = load_definition(origin, snapshot_dir=tmp_path / "snap")
    origin.write_text(MINIMAL.replace('("a", "b")', '("x", "y")'), encoding="utf-8")

    assert definition.match_players(verdicts=(), match_index=0, budget=1) == ("a", "b")


def test_a_hook_that_writes_raises_a_purity_error(tmp_path: Path) -> None:
    guarded = tmp_path / "guarded.txt"
    guarded.write_text("original", encoding="utf-8")
    body = MINIMAL + (
        "\nimport pathlib\n"
        "def present_player(ctx):\n"
        f"    pathlib.Path({str(guarded)!r}).write_text('tampered')\n"
        "    return ctx.player\n"
    )
    definition = load_definition(
        _write(tmp_path, body),
        snapshot_dir=tmp_path / "snap",
        guarded_paths=(guarded,),
    )
    with pytest.raises(HookPurityError):
        definition.present_player("a")


def test_a_hook_may_randomize_which_players_meet(tmp_path: Path) -> None:
    """Only presentation-order randomization is engine-side."""
    body = (
        "import random\n"
        "question = 'q'\n"
        "def match_players(ctx):\n"
        "    return tuple(random.Random(ctx.match_index).sample(['a','b','c'], 2))\n"
        "def match_identity(ctx):\n"
        "    return '|'.join(sorted(ctx.players))\n"
    )
    definition = _load(tmp_path, body)
    seen = {
        definition.match_players(verdicts=(), match_index=i, budget=5)
        for i in range(5)
    }
    assert len(seen) > 1


def test_a_definition_without_controls_declares_none_and_substitutes_nothing(
    tmp_path: Path,
) -> None:
    definition = _load(tmp_path, MINIMAL)
    assert definition.controls(verdicts=(), match_index=0, budget=1) == {}
    assert definition.control_rate == 0.0


def test_controls_returns_the_pool_with_each_declared_band(tmp_path: Path) -> None:
    body = MINIMAL + (
        "\ncontrol_rate = 0.25\n"
        "def controls(ctx):\n"
        "    return {'ringer': 'high', 'dud': 'low'}\n"
    )
    definition = _load(tmp_path, body)
    assert definition.controls(verdicts=(), match_index=0, budget=1) == {
        "ringer": "high",
        "dud": "low",
    }
    assert definition.control_rate == 0.25


def test_a_band_outside_high_and_low_is_a_return_error(tmp_path: Path) -> None:
    """Mid-pack is where noise lives, so a middle expectation is not falsifiable."""
    body = MINIMAL + "\ndef controls(ctx):\n    return {'x': 'middle'}\n"
    definition = _load(tmp_path, body)
    with pytest.raises(HookReturnError) as excinfo:
        definition.controls(verdicts=(), match_index=0, budget=1)
    assert "middle" in str(excinfo.value)


def test_controls_rejects_malformed_pools(tmp_path: Path) -> None:
    bad_returns = [
        "['a', 'b']",       # a sequence, not a declaration of expectation
        "{'': 'high'}",     # an empty player
        "{'a': None}",      # a player with no declared band
        "7",
    ]
    for bad in bad_returns:
        body = MINIMAL + f"\ndef controls(ctx):\n    return {bad}\n"
        definition = _load(tmp_path, body)
        with pytest.raises(HookReturnError):
            definition.controls(verdicts=(), match_index=0, budget=1)


def test_controls_returning_none_is_an_empty_pool(tmp_path: Path) -> None:
    body = MINIMAL + "\ndef controls(ctx):\n    return None\n"
    definition = _load(tmp_path, body)
    assert definition.controls(verdicts=(), match_index=0, budget=1) == {}


def test_a_control_rate_outside_zero_to_one_is_a_return_error(tmp_path: Path) -> None:
    for bad in ("1.5", "-0.1", "'often'"):
        definition = _load(tmp_path, MINIMAL + f"\ncontrol_rate = {bad}\n")
        with pytest.raises(HookReturnError):
            definition.control_rate


def test_reopening_verifies_the_snapshot_instead_of_re_recording_it(
    tmp_path: Path,
) -> None:
    definition = load_definition(_write(tmp_path, MINIMAL), snapshot_dir=tmp_path / "s")
    reopened = open_definition(
        definition.snapshot_path, origin_path=definition.origin_path
    )
    assert reopened.digest == definition.digest


def test_a_tampered_snapshot_is_caught_on_reopen(tmp_path: Path) -> None:
    definition = load_definition(_write(tmp_path, MINIMAL), snapshot_dir=tmp_path / "s")
    definition.snapshot_path.write_text(MINIMAL + "\n# tampered\n", encoding="utf-8")

    with pytest.raises(HookPurityError):
        open_definition(definition.snapshot_path, origin_path=definition.origin_path)


def test_a_missing_definition_file_is_a_load_error(tmp_path: Path) -> None:
    with pytest.raises(HookLoadError):
        load_definition(tmp_path / "nope.py", snapshot_dir=tmp_path / "snap")
