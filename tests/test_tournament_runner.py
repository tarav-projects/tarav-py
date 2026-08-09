# $kw: ^test-tournament-runner --from Tournament.Match --from Tournament.Judge --note [DF] boundary tests for engine-composed verbatims, position decoding, shuffle-independent identity, and failed runs recording nothing ^<anchor-on-landing>
from __future__ import annotations

import argparse
import re
from pathlib import Path

import pytest

from agentos._core.errors import CliError
from agentos.agent.run_runtime import AgentRunResult
from agentos.tournament.commands import register_tournament_commands
from agentos.tournament import (
    JudgeSpawn,
    TournamentStore,
    load_definition,
    run_match,
    run_pool,
)

DEFINITION = '''
question = "Which line is better?"

def match_players(ctx):
    return ("alpha", "beta")

def match_identity(ctx):
    return "|".join(ctx.players)
'''


class StubJudge:
    """A RunCapable stand-in that answers the way a real judge now does.

    It reads its ticket out of the prompt and submits through the actual CLI
    handler, so these tests exercise the real boundary rather than a shortcut.
    """

    provider = "stub"

    def __init__(self, *answers, exit_code: int = 0) -> None:
        self._answers = list(answers)
        self.prompts: list[str] = []
        self.exit_code = exit_code
        self.rejections: list[str] = []

    def run(self, command_config, run_config) -> AgentRunResult:  # noqa: ANN001
        prompt = command_config.prompt or ""
        self.prompts.append(prompt)
        if not self._answers:
            return AgentRunResult(exit_code=self.exit_code, stdout="")
        for answer in self._answers.pop(0):
            self._submit(prompt, answer)
        return AgentRunResult(exit_code=self.exit_code, stdout="")

    def _submit(self, prompt: str, answer) -> None:
        ticket = re.search(r"--ticket (\S+)", prompt).group(1)
        depot = re.search(r"--depot (\S+)", prompt).group(1)
        argv = ["tournament", "submit", "--depot", depot, "--ticket", ticket]
        if answer == "no_contest":
            argv += ["--no-contest", "--refusal-reason", "not comparable"]
        elif isinstance(answer, tuple):
            argv += ["--no-contest", "--refusal-reason", answer[1]]
        else:
            argv += ["--ranking", ",".join(answer)]
        parser = argparse.ArgumentParser()
        register_tournament_commands(parser.add_subparsers(dest="command"))
        args = parser.parse_args(argv)
        try:
            args.handler(args)
        except CliError as error:
            self.rejections.append(str(error))


def _answer(outcome, reason: str = "because"):
    """One spawn's worth of submissions."""
    if outcome == "no_contest":
        return [("no_contest", reason)]
    return [outcome]


def _setup(tmp_path: Path, body: str = DEFINITION):
    path = tmp_path / "definition.py"
    path.write_text(body, encoding="utf-8")
    store = TournamentStore(tmp_path / "tournament")
    definition = load_definition(path, snapshot_dir=tmp_path / "snap")
    tournament = store.create_tournament(
        definition_path=str(path), definition_digest=definition.digest
    )
    return store, definition, tournament


def _spawn(tmp_path: Path, *results: AgentRunResult) -> JudgeSpawn:
    return JudgeSpawn(agent=StubJudge(*results), cwd=tmp_path)


def test_the_engine_composes_the_verbatim_from_presentations_and_its_own_frame(
    tmp_path: Path,
) -> None:
    store, definition, tournament = _setup(tmp_path)
    spawn = _spawn(tmp_path, _answer(["A", "B"]))

    result = run_match(
        store=store,
        definition=definition,
        tournament=tournament,
        players=("alpha", "beta"),
        spawn=spawn,
    )

    verbatim = result.verbatim
    assert "Which line is better?" in verbatim
    assert "A:" in verbatim and "B:" in verbatim
    assert "alpha" in verbatim and "beta" in verbatim
    assert "Rank all 2 candidates" in verbatim


def test_criteria_reach_the_verbatim_when_the_definition_declares_them(
    tmp_path: Path,
) -> None:
    body = DEFINITION + '\ncriteria = "Prefer the line that binds action."\n'
    store, definition, tournament = _setup(tmp_path, body)

    result = run_match(
        store=store,
        definition=definition,
        tournament=tournament,
        players=("alpha", "beta"),
        spawn=_spawn(tmp_path, _answer(["A", "B"])),
    )
    assert "Prefer the line that binds action." in result.verbatim


def test_a_judge_answering_b_records_the_player_presented_second(
    tmp_path: Path,
) -> None:
    store, definition, tournament = _setup(tmp_path)

    result = run_match(
        store=store,
        definition=definition,
        tournament=tournament,
        players=("alpha", "beta"),
        spawn=_spawn(tmp_path, _answer(["B", "A"])),
        rng_seed=7,
    )

    assert result.verdict is not None
    assert result.verdict.ordering == (result.presented[1], result.presented[0])


def test_identity_is_stable_across_runs_with_different_presented_order(
    tmp_path: Path,
) -> None:
    """The shuffle must not reach identity, or repeat matches never accumulate."""
    store, definition, tournament = _setup(tmp_path)

    first = run_match(
        store=store,
        definition=definition,
        tournament=tournament,
        players=("alpha", "beta"),
        spawn=_spawn(tmp_path, _answer(["A", "B"])),
        rng_seed=1,
    )
    second = run_match(
        store=store,
        definition=definition,
        tournament=tournament,
        players=("alpha", "beta"),
        spawn=_spawn(tmp_path, _answer(["A", "B"])),
        rng_seed=4,
    )

    assert first.match_id == second.match_id
    assert len(store.verdicts(tournament.tournament_id, match_id=first.match_id)) == 2


def test_the_presented_order_actually_run_is_recorded(tmp_path: Path) -> None:
    store, definition, tournament = _setup(tmp_path)
    result = run_match(
        store=store,
        definition=definition,
        tournament=tournament,
        players=("alpha", "beta"),
        spawn=_spawn(tmp_path, _answer(["A", "B"])),
    )
    assert result.verdict is not None
    assert list(result.verdict.envelope["presented"]) == list(result.presented)
    assert sorted(result.presented) == ["alpha", "beta"]


def test_a_judge_that_exits_without_submitting_appends_no_record(tmp_path: Path) -> None:
    store, definition, tournament = _setup(tmp_path)
    result = run_match(
        store=store,
        definition=definition,
        tournament=tournament,
        players=("alpha", "beta"),
        spawn=JudgeSpawn(agent=StubJudge(exit_code=1), cwd=tmp_path),
    )

    assert result.failed
    assert store.verdicts(tournament.tournament_id) == ()


def test_a_judge_that_prints_instead_of_submitting_appends_no_record(tmp_path: Path) -> None:
    store, definition, tournament = _setup(tmp_path)
    result = run_match(
        store=store,
        definition=definition,
        tournament=tournament,
        players=("alpha", "beta"),
        spawn=JudgeSpawn(agent=StubJudge(), cwd=tmp_path),
    )

    assert result.failed
    assert store.verdicts(tournament.tournament_id) == ()


def test_a_declining_judge_records_a_no_contest_with_its_reason(
    tmp_path: Path,
) -> None:
    store, definition, tournament = _setup(tmp_path)
    run_match(
        store=store,
        definition=definition,
        tournament=tournament,
        players=("alpha", "beta"),
        spawn=_spawn(tmp_path, _answer("no_contest", "not comparable")),
    )

    (verdict,) = store.verdicts(tournament.tournament_id)
    assert verdict.outcome == "no_contest"
    assert verdict.envelope["refusal_reason"] == "not comparable"
    assert verdict.ordering is None


def test_the_verbatim_hash_records_exactly_what_the_judge_saw(tmp_path: Path) -> None:
    store, definition, tournament = _setup(tmp_path)
    spawn = _spawn(tmp_path, _answer(["A", "B"]))
    result = run_match(
        store=store,
        definition=definition,
        tournament=tournament,
        players=("alpha", "beta"),
        spawn=spawn,
    )

    assert spawn.agent.prompts == [result.verbatim]
    assert result.verdict is not None
    assert result.verdict.envelope["verbatim_hash"] == result.verbatim_hash


def test_dry_run_renders_without_spawning(tmp_path: Path) -> None:
    store, definition, tournament = _setup(tmp_path)
    spawn = _spawn(tmp_path)
    result = run_match(
        store=store,
        definition=definition,
        tournament=tournament,
        players=("alpha", "beta"),
        spawn=spawn,
        dry_run=True,
    )

    assert spawn.agent.prompts == []
    assert result.verdict is None
    assert "alpha" in result.verbatim


def test_run_pool_drives_matches_from_the_hook_until_budget(tmp_path: Path) -> None:
    store, definition, tournament = _setup(tmp_path)
    spawn = _spawn(tmp_path, _answer(["A", "B"]), _answer(["A", "B"]), _answer(["A", "B"]))

    payload = run_pool(
        store=store,
        definition=definition,
        tournament=tournament,
        spawn=spawn,
        budget=3,
    )

    assert payload["status"] == "ok"
    assert payload["run_count"] == 3
    assert len(store.verdicts(tournament.tournament_id)) == 3


def test_run_pool_stops_early_when_the_hook_declines_another_match(
    tmp_path: Path,
) -> None:
    body = DEFINITION.replace(
        'return ("alpha", "beta")',
        'return ("alpha", "beta") if ctx.match_index < 2 else None',
    )
    store, definition, tournament = _setup(tmp_path, body)
    spawn = _spawn(tmp_path, _answer(["A", "B"]), _answer(["A", "B"]))

    payload = run_pool(
        store=store,
        definition=definition,
        tournament=tournament,
        spawn=spawn,
        budget=10,
    )

    assert payload["run_count"] == 2
    assert payload["exhausted"] is True


def test_a_failed_match_is_a_row_and_never_aborts_its_siblings(
    tmp_path: Path,
) -> None:
    store, definition, tournament = _setup(tmp_path)
    spawn = _spawn(tmp_path, _answer(["A", "B"]), [], _answer(["B", "A"]))

    payload = run_pool(
        store=store,
        definition=definition,
        tournament=tournament,
        spawn=spawn,
        budget=3,
    )

    assert payload["status"] == "error"
    assert payload["run_count"] == 3
    assert payload["failed_count"] == 1
    assert len(store.verdicts(tournament.tournament_id)) == 2


def test_concurrency_below_one_is_rejected(tmp_path: Path) -> None:
    store, definition, tournament = _setup(tmp_path)
    with pytest.raises(CliError):
        run_pool(
            store=store,
            definition=definition,
            tournament=tournament,
            spawn=_spawn(tmp_path),
            budget=1,
            concurrency=0,
        )


def test_a_four_way_match_labels_a_through_d_and_records_its_ordering(
    tmp_path: Path,
) -> None:
    body = DEFINITION.replace(
        'return ("alpha", "beta")', 'return ("alpha", "beta", "gamma", "delta")'
    )
    store, definition, tournament = _setup(tmp_path, body)
    spawn = _spawn(tmp_path, _answer(["C", "A", "D", "B"]))

    result = run_match(
        store=store,
        definition=definition,
        tournament=tournament,
        players=("alpha", "beta", "gamma", "delta"),
        spawn=spawn,
        rng_seed=3,
    )

    verbatim = result.verbatim
    for label in ("A:", "B:", "C:", "D:"):
        assert label in verbatim
    assert "Rank all 4 candidates" in verbatim

    assert result.verdict is not None
    presented = result.presented
    # The judge ranked positions C, A, D, B; the engine decodes each through the
    # order it actually ran.
    assert result.verdict.ordering == (
        presented[2],
        presented[0],
        presented[3],
        presented[1],
    )
    assert sorted(result.verdict.ordering) == sorted(
        ["alpha", "beta", "gamma", "delta"]
    )


def test_identity_ignores_presentation_order_at_higher_arity(tmp_path: Path) -> None:
    body = DEFINITION.replace(
        'return ("alpha", "beta")', 'return ("alpha", "beta", "gamma", "delta")'
    )
    store, definition, tournament = _setup(tmp_path, body)
    players = ("alpha", "beta", "gamma", "delta")

    first = run_match(
        store=store, definition=definition, tournament=tournament,
        players=players, spawn=_spawn(tmp_path, _answer(["A", "B", "C", "D"])),
        rng_seed=1,
    )
    second = run_match(
        store=store, definition=definition, tournament=tournament,
        players=players, spawn=_spawn(tmp_path, _answer(["D", "C", "B", "A"])),
        rng_seed=9,
    )

    assert first.presented != second.presented
    assert first.match_id == second.match_id


def test_a_judge_ordering_that_omits_a_label_records_nothing(tmp_path: Path) -> None:
    body = DEFINITION.replace(
        'return ("alpha", "beta")', 'return ("alpha", "beta", "gamma")'
    )
    store, definition, tournament = _setup(tmp_path, body)

    result = run_match(
        store=store,
        definition=definition,
        tournament=tournament,
        players=("alpha", "beta", "gamma"),
        spawn=_spawn(tmp_path, _answer(["A", "B"])),
    )

    assert result.failed
    assert store.verdicts(tournament.tournament_id) == ()


def test_provider_argv_passes_through_to_the_spawn(tmp_path: Path) -> None:
    """A judge answers by running a command, so it needs its provider's tool grant."""

    class RecordingJudge(StubJudge):
        def __init__(self) -> None:
            super().__init__()
            self.argv: tuple[str, ...] = ()

        def run(self, command_config, run_config):  # noqa: ANN001
            self.argv = tuple(command_config.argv)
            return super().run(command_config, run_config)

    store, definition, tournament = _setup(tmp_path)
    agent = RecordingJudge()
    spawn = JudgeSpawn(
        agent=agent, cwd=tmp_path, agent_argv=("--allowedTools", "Bash")
    )

    run_match(
        store=store,
        definition=definition,
        tournament=tournament,
        players=("alpha", "beta"),
        spawn=spawn,
    )

    assert agent.argv == ("--allowedTools", "Bash")


CONTROLLED = DEFINITION + (
    "\ncontrol_rate = 1.0\n"
    "def controls(ctx):\n"
    "    return {'ringer': 'high'}\n"
)


def test_a_control_replaces_exactly_one_pool_player(tmp_path: Path) -> None:
    store, definition, tournament = _setup(tmp_path, CONTROLLED)

    result = run_match(
        store=store,
        definition=definition,
        tournament=tournament,
        players=("alpha", "beta"),
        spawn=_spawn(tmp_path, _answer(["A", "B"])),
        rng_seed=5,
    )

    assert result.controls == {"ringer": "high"}
    assert "ringer" in result.players
    assert len(result.players) == 2
    assert len(set(result.players)) == 2


def test_a_zero_rate_substitutes_nothing(tmp_path: Path) -> None:
    body = CONTROLLED.replace("control_rate = 1.0", "control_rate = 0.0")
    store, definition, tournament = _setup(tmp_path, body)

    result = run_match(
        store=store,
        definition=definition,
        tournament=tournament,
        players=("alpha", "beta"),
        spawn=_spawn(tmp_path, _answer(["A", "B"])),
        rng_seed=5,
    )

    assert result.controls == {}
    assert result.players == ("alpha", "beta")


def test_a_control_already_in_the_match_is_not_substituted_in(tmp_path: Path) -> None:
    """Drawing it would duplicate a player, which the arity check already refuses."""
    body = CONTROLLED.replace("{'ringer': 'high'}", "{'alpha': 'low'}")
    store, definition, tournament = _setup(tmp_path, body)

    result = run_match(
        store=store,
        definition=definition,
        tournament=tournament,
        players=("alpha", "beta"),
        spawn=_spawn(tmp_path, _answer(["A", "B"])),
        rng_seed=5,
    )

    assert result.controls == {}
    assert result.players == ("alpha", "beta")


def test_substitution_precedes_identity(tmp_path: Path) -> None:
    """A match carrying a control is a different match from the one without."""
    store, controlled, tournament = _setup(tmp_path, CONTROLLED)
    (tmp_path / "plain").mkdir()
    plain_store, plain, plain_tournament = _setup(tmp_path / "plain")

    with_control = run_match(
        store=store, definition=controlled, tournament=tournament,
        players=("alpha", "beta"),
        spawn=_spawn(tmp_path, _answer(["A", "B"])), rng_seed=5,
    )
    without = run_match(
        store=plain_store, definition=plain, tournament=plain_tournament,
        players=("alpha", "beta"),
        spawn=_spawn(tmp_path, _answer(["A", "B"])), rng_seed=5,
    )

    assert with_control.match_id != without.match_id
    assert "ringer" in with_control.match_id


def test_the_same_seed_reproduces_the_same_substitution(tmp_path: Path) -> None:
    body = CONTROLLED.replace("control_rate = 1.0", "control_rate = 0.5")
    store, definition, tournament = _setup(tmp_path, body)

    runs = [
        run_match(
            store=store, definition=definition, tournament=tournament,
            players=("alpha", "beta"),
            spawn=_spawn(tmp_path, _answer(["A", "B"])), rng_seed=11,
        )
        for _ in range(2)
    ]

    assert runs[0].players == runs[1].players
    assert runs[0].controls == runs[1].controls
    assert runs[0].presented == runs[1].presented


def test_a_previewed_match_carries_controls_like_a_run_one(tmp_path: Path) -> None:
    """Preview renders a *valid* match, and a valid match may carry a control."""
    from agentos.tournament.runner import preview_match

    store, definition, tournament = _setup(tmp_path, CONTROLLED)
    result = preview_match(
        store=store,
        definition=definition,
        tournament=tournament,
        players=("alpha", "beta"),
        judge={"provider": "preview", "model": None, "account": None},
        rng_seed=5,
    )

    assert result.controls == {"ringer": "high"}
    assert "ringer" in result.verbatim


def test_the_example_ranking_is_never_the_presentation_order(tmp_path: Path) -> None:
    """Copying the template must be distinguishable from choosing that order."""
    from agentos.tournament.runner import compose_verbatim

    for arity in (2, 3, 4, 7):
        labels = tuple("ABCDEFG"[:arity])
        verbatim = compose_verbatim(
            question="q",
            criteria=None,
            presented_presentations=tuple(f"p{i}" for i in range(arity)),
            ticket_id="t-1",
            depot_root="/depot",
        )
        assert f"--ranking {','.join(labels)}" not in verbatim
        assert f"--ranking {','.join(labels[1:] + labels[:1])}" in verbatim
