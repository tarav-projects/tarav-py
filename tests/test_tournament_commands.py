# $kw: ^test-tournament-commands --from Agentos.Tournament --from Tournament.Match --note [DF] boundary tests for the concurrent fan-out envelope, its failure rows, and the no-spawn dry run ^<anchor-on-landing>
from __future__ import annotations

import json
import threading
from pathlib import Path

from agentos.agent.run_runtime import AgentRunDryResult, AgentRunResult
from agentos.tournament import (
    JudgeSpawn,
    TournamentStore,
    load_definition,
    run_pool,
)


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
            exit_code=0, stdout=json.dumps({"outcome": "A", "attribution": "none", "reason": "default"})
        )

    def run_dry(self, command_config) -> AgentRunDryResult:  # noqa: ANN001
        self.dry_calls += 1
        return AgentRunDryResult(lines=("claude", "-p", "<prompt>"))


def _setup(tmp_path: Path, players=("alpha", "beta", "gamma")):
    path = tmp_path / "definition.py"
    path.write_text("question = 'which is better?'\n", encoding="utf-8")
    store = TournamentStore(tmp_path / "tournament")
    definition = load_definition(path, snapshot_dir=tmp_path / "snap")
    tournament = store.create_tournament(
        definition_path=str(path),
        definition_digest=definition.digest,
        players=players,
    )
    return store, definition, tournament


def _spawn(agent: StubJudge) -> JudgeSpawn:
    return JudgeSpawn(agent=agent, cwd=Path("."))


PAIRS = (("alpha", "beta"), ("beta", "gamma"), ("alpha", "gamma"))


def test_envelope_reports_counts_and_keeps_input_order(tmp_path: Path) -> None:
    store, definition, tournament = _setup(tmp_path)
    agent = StubJudge()

    payload = run_pool(
        store=store,
        definition=definition,
        tournament=tournament,
        pairs=PAIRS,
        spawn=_spawn(agent),
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
        pairs=PAIRS,
        spawn=_spawn(agent),
        concurrency=2,
    )

    assert payload["status"] == "error"
    assert payload["run_count"] == 3
    assert payload["failed_count"] == 2
    assert len(payload["failures"]) == 2
    assert len(store.verdicts(tournament.tournament_id)) == 1


def test_serial_and_concurrent_runs_agree_on_the_envelope_shape(
    tmp_path: Path,
) -> None:
    store, definition, tournament = _setup(tmp_path)
    serial = run_pool(
        store=store,
        definition=definition,
        tournament=tournament,
        pairs=PAIRS,
        spawn=_spawn(StubJudge()),
        concurrency=1,
    )
    concurrent = run_pool(
        store=store,
        definition=definition,
        tournament=tournament,
        pairs=PAIRS,
        spawn=_spawn(StubJudge()),
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
        pairs=PAIRS,
        spawn=_spawn(agent),
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
            pairs=(PAIRS[0],),
            spawn=_spawn(StubJudge()),
            concurrency=1,
        )

    assert len(store.verdicts(tournament.tournament_id)) == 2


def test_cli_registers_a_tournament_command() -> None:
    import argparse

    from agentos.tournament.commands import register_tournament_commands

    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")
    register_tournament_commands(subparsers)

    args = parser.parse_args(
        ["tournament", "list", "--depot", "/tmp/depot"]
    )
    assert args.command == "tournament"
    assert callable(args.handler)
