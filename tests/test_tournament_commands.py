# $kw: ^test-tournament-commands --from Agentos.Tournament --from Tournament.Depot --note [DF] boundary tests for the concurrent fan-out envelope, its failure rows, the no-spawn dry run, and the global depot default ^<anchor-on-landing>
from __future__ import annotations

import argparse
import json
import threading
from pathlib import Path

import pytest

from agentos._core.errors import CliError
from agentos.agent.run_runtime import AgentRunDryResult, AgentRunResult
from agentos.tournament import (
    JudgeSpawn,
    TournamentStore,
    load_definition,
    run_pool,
)
from agentos.tournament.commands import register_tournament_commands

DEFINITION = '''
import itertools

question = "which is better?"
POOL = ("alpha", "beta", "gamma")
PAIRS = tuple(itertools.combinations(POOL, 2))

def match_players(ctx):
    return PAIRS[ctx.match_index % len(PAIRS)]

def match_identity(ctx):
    return "|".join(sorted(ctx.players))
'''

PAIRS = (("alpha", "beta"), ("alpha", "gamma"), ("beta", "gamma"))


class StubJudge:
    provider = "claude-code"

    def __init__(self, *, answers: dict[str, AgentRunResult] | None = None) -> None:
        self.answers = answers or {}
        self.calls: list[str] = []
        self.dry_calls = 0
        self._lock = threading.Lock()

    def run(self, command_config, run_config) -> AgentRunResult:  # noqa: ANN001
        prompt = command_config.prompt or ""
        with self._lock:
            self.calls.append(prompt)
        for marker, result in self.answers.items():
            if marker in prompt:
                return result
        return AgentRunResult(
            exit_code=0,
            stdout=json.dumps(
                {"outcome": ["A", "B"], "attribution": "none", "reason": "default"}
            ),
        )

    def run_dry(self, command_config) -> AgentRunDryResult:  # noqa: ANN001
        self.dry_calls += 1
        return AgentRunDryResult(lines=("claude", "-p", "<prompt>"))


def _setup(tmp_path: Path, body: str = DEFINITION):
    path = tmp_path / "definition.py"
    path.write_text(body, encoding="utf-8")
    store = TournamentStore(tmp_path / "tournament")
    definition = load_definition(path, snapshot_dir=tmp_path / "snap")
    tournament = store.create_tournament(
        definition_path=str(path), definition_digest=definition.digest
    )
    return store, definition, tournament


def _spawn(agent: StubJudge) -> JudgeSpawn:
    return JudgeSpawn(agent=agent, cwd=Path("."))


def test_envelope_reports_counts_and_keeps_hook_order(tmp_path: Path) -> None:
    store, definition, tournament = _setup(tmp_path)
    agent = StubJudge()

    payload = run_pool(
        store=store,
        definition=definition,
        tournament=tournament,
        spawn=_spawn(agent),
        budget=3,
        concurrency=3,
    )

    assert payload["status"] == "ok"
    assert payload["run_count"] == 3
    assert payload["failed_count"] == 0
    assert [tuple(run["players"]) for run in payload["runs"]] == list(PAIRS)


def test_a_failed_match_lands_in_failures_without_aborting_siblings(
    tmp_path: Path,
) -> None:
    store, definition, tournament = _setup(tmp_path)
    agent = StubJudge(
        answers={"gamma": AgentRunResult(exit_code=9, stdout="", stderr="boom")}
    )

    payload = run_pool(
        store=store,
        definition=definition,
        tournament=tournament,
        spawn=_spawn(agent),
        budget=3,
        concurrency=2,
    )

    assert payload["status"] == "error"
    assert payload["run_count"] == 3
    assert payload["failed_count"] == 2
    assert len(store.verdicts(tournament.tournament_id)) == 1


def test_serial_and_concurrent_runs_agree_on_the_envelope_shape(
    tmp_path: Path,
) -> None:
    store, definition, tournament = _setup(tmp_path)
    serial = run_pool(
        store=store,
        definition=definition,
        tournament=tournament,
        spawn=_spawn(StubJudge()),
        budget=3,
        concurrency=1,
    )
    concurrent = run_pool(
        store=store,
        definition=definition,
        tournament=tournament,
        spawn=_spawn(StubJudge()),
        budget=3,
        concurrency=4,
    )

    assert sorted(serial) == sorted(concurrent)
    assert serial["run_count"] == concurrent["run_count"] == 3


def test_dry_run_returns_prompt_and_argv_without_spawning(tmp_path: Path) -> None:
    store, definition, tournament = _setup(tmp_path)
    agent = StubJudge()

    payload = run_pool(
        store=store,
        definition=definition,
        tournament=tournament,
        spawn=_spawn(agent),
        budget=3,
        dry_run=True,
    )

    assert agent.calls == []
    assert payload["dry_run"] is True
    first = payload["runs"][0]
    assert "alpha" in first["verbatim"]
    assert first["agent_command"] == ["claude", "-p", "<prompt>"]
    assert store.verdicts(tournament.tournament_id) == ()


def test_repeat_runs_are_not_skipped_on_prior_success(tmp_path: Path) -> None:
    store, definition, tournament = _setup(tmp_path)
    for _ in range(2):
        run_pool(
            store=store,
            definition=definition,
            tournament=tournament,
            spawn=_spawn(StubJudge()),
            budget=1,
            concurrency=1,
        )

    assert len(store.verdicts(tournament.tournament_id)) == 2


def test_a_hook_error_becomes_a_failure_row_rather_than_an_abort(
    tmp_path: Path,
) -> None:
    body = DEFINITION.replace(
        'return "|".join(sorted(ctx.players))',
        'return 7 if ctx.players[1] == "gamma" else "|".join(sorted(ctx.players))',
    )
    store, definition, tournament = _setup(tmp_path, body)

    payload = run_pool(
        store=store,
        definition=definition,
        tournament=tournament,
        spawn=_spawn(StubJudge()),
        budget=3,
    )

    assert payload["failed_count"] == 2
    assert payload["run_count"] == 3


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")
    register_tournament_commands(subparsers)
    return parser


def test_create_needs_only_a_definition(tmp_path: Path) -> None:
    args = _parser().parse_args(["tournament", "create", "--definition", "/defs/x.py"])
    assert args.definition == "/defs/x.py"
    assert args.depot is None
    assert not hasattr(args, "player")
    assert not hasattr(args, "players_file")


def test_depot_is_optional_on_every_subcommand() -> None:
    parser = _parser()
    for argv in (
        ["tournament", "list"],
        ["tournament", "create", "--definition", "/defs/x.py"],
        ["tournament", "run", "--tournament", "t-1"],
        ["tournament", "show", "--tournament", "t-1"],
    ):
        assert parser.parse_args(argv).depot is None


def test_create_without_a_depot_uses_the_global_default(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("AGENTOS_TOURNAMENT_DEPOT", str(tmp_path / "global"))
    path = tmp_path / "definition.py"
    path.write_text(DEFINITION, encoding="utf-8")

    args = _parser().parse_args(["tournament", "create", "--definition", str(path)])
    assert args.handler(args) == 0
    assert (tmp_path / "global" / "records").is_dir()


def test_creating_from_a_definition_missing_a_required_hook_fails(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("AGENTOS_TOURNAMENT_DEPOT", str(tmp_path / "global"))
    path = tmp_path / "definition.py"
    path.write_text("question = 'x'\n", encoding="utf-8")

    args = _parser().parse_args(["tournament", "create", "--definition", str(path)])
    with pytest.raises(CliError) as excinfo:
        args.handler(args)
    assert "match_players" in str(excinfo.value)
