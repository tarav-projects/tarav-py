# $kw: ^test-tournament-runner --from Tournament.Match --from Tournament.Judge --note [DF] boundary tests for engine-composed verbatims, position decoding, shuffle-independent identity, and failed runs recording nothing ^<anchor-on-landing>
from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentos._core.errors import CliError
from agentos.agent.run_runtime import AgentRunResult
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
    """A RunCapable stand-in: the agent boundary, stubbed."""

    provider = "stub"

    def __init__(self, *results: AgentRunResult) -> None:
        self._results = list(results)
        self.prompts: list[str] = []

    def run(self, command_config, run_config) -> AgentRunResult:  # noqa: ANN001
        self.prompts.append(command_config.prompt or "")
        return self._results.pop(0) if self._results else self._results_exhausted()

    @staticmethod
    def _results_exhausted() -> AgentRunResult:
        raise AssertionError("the stub judge ran more matches than it was given")


def _answer(
    outcome: str, reason: str = "because", attribution: str = "none"
) -> AgentRunResult:
    if outcome == "no_contest" and attribution == "none":
        attribution = "question"
    return AgentRunResult(
        exit_code=0,
        stdout=json.dumps(
            {"outcome": outcome, "attribution": attribution, "reason": reason}
        ),
    )


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
    spawn = _spawn(tmp_path, _answer("A"))

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
    assert "no_contest" in verbatim and "attribution" in verbatim


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
        spawn=_spawn(tmp_path, _answer("A")),
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
        spawn=_spawn(tmp_path, _answer("B")),
        rng_seed=7,
    )

    assert result.verdict is not None
    assert result.verdict.preferred == result.presented[1]


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
        spawn=_spawn(tmp_path, _answer("A")),
        rng_seed=1,
    )
    second = run_match(
        store=store,
        definition=definition,
        tournament=tournament,
        players=("alpha", "beta"),
        spawn=_spawn(tmp_path, _answer("A")),
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
        spawn=_spawn(tmp_path, _answer("A")),
    )
    assert result.verdict is not None
    assert list(result.verdict.envelope["presented"]) == list(result.presented)
    assert sorted(result.presented) == ["alpha", "beta"]


def test_a_nonzero_judge_exit_appends_no_record(tmp_path: Path) -> None:
    store, definition, tournament = _setup(tmp_path)
    result = run_match(
        store=store,
        definition=definition,
        tournament=tournament,
        players=("alpha", "beta"),
        spawn=_spawn(tmp_path, AgentRunResult(exit_code=1, stdout="")),
    )

    assert result.failed
    assert store.verdicts(tournament.tournament_id) == ()


def test_an_unparseable_answer_appends_no_record(tmp_path: Path) -> None:
    store, definition, tournament = _setup(tmp_path)
    result = run_match(
        store=store,
        definition=definition,
        tournament=tournament,
        players=("alpha", "beta"),
        spawn=_spawn(tmp_path, AgentRunResult(exit_code=0, stdout="I prefer alpha.")),
    )

    assert result.failed
    assert store.verdicts(tournament.tournament_id) == ()


def test_a_declining_judge_records_a_no_contest_with_its_attribution(
    tmp_path: Path,
) -> None:
    store, definition, tournament = _setup(tmp_path)
    run_match(
        store=store,
        definition=definition,
        tournament=tournament,
        players=("alpha", "beta"),
        spawn=_spawn(
            tmp_path, _answer("no_contest", "not comparable", attribution="question")
        ),
    )

    (verdict,) = store.verdicts(tournament.tournament_id)
    assert verdict.outcome == "no_contest"
    assert verdict.envelope["no_contest_attribution"] == "question"
    assert verdict.envelope["preferred"] is None


def test_the_verbatim_hash_records_exactly_what_the_judge_saw(tmp_path: Path) -> None:
    store, definition, tournament = _setup(tmp_path)
    spawn = _spawn(tmp_path, _answer("A"))
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
    spawn = _spawn(tmp_path, _answer("A"), _answer("A"), _answer("A"))

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
    spawn = _spawn(tmp_path, _answer("A"), _answer("A"))

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
    spawn = _spawn(
        tmp_path, _answer("A"), AgentRunResult(exit_code=1, stdout=""), _answer("B")
    )

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
