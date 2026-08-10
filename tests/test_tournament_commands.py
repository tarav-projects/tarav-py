# $kw: ^test-tournament-commands --from Agentos.Tournament --from Tournament.Depot --note [DF] boundary tests for the concurrent fan-out envelope, its failure rows, the no-spawn dry run, and the global depot default ^<anchor-on-landing>
from __future__ import annotations

import argparse
import json
import re
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
    """Submits through the real CLI, and stays silent for matched markers."""

    provider = "claude-code"

    def __init__(self, *, silent_markers: tuple[str, ...] = ()) -> None:
        self.silent_markers = silent_markers
        self.calls: list[str] = []
        self.dry_calls = 0
        self._lock = threading.Lock()

    def run(self, command_config, run_config) -> AgentRunResult:  # noqa: ANN001
        prompt = command_config.prompt or ""
        with self._lock:
            self.calls.append(prompt)
        if any(marker in prompt for marker in self.silent_markers):
            return AgentRunResult(exit_code=9, stdout="", stderr="boom")
        ticket = re.search(r"--ticket (\S+)", prompt).group(1)
        depot = re.search(r"--depot (\S+)", prompt).group(1)
        parser = argparse.ArgumentParser()
        register_tournament_commands(parser.add_subparsers(dest="command"))
        args = parser.parse_args(
            ["tournament", "submit", "--depot", depot, "--ticket", ticket,
             "--ranking", "A,B"]
        )
        try:
            args.handler(args)
        except CliError:
            pass
        return AgentRunResult(exit_code=0, stdout="")

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
    agent = StubJudge(silent_markers=("gamma",))

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


# $kw: ^test-run-parameters-cli --from Tournament.Hook --note [PR] a misspelled key reads as a silent default, so the boundary rejects malformed parameters rather than the engine reading them --supp ^c20260809-182u ^<anchor-on-landing>

PARAMETERIZED = '''
question = "which is better?"

def match_players(ctx):
    return ("alpha", "beta") if ctx.params.get("shape") == "pair" else ("alpha", "beta", "gamma")

def match_identity(ctx):
    return "|".join(sorted(ctx.players))

def match_label(ctx):
    return ctx.params.get("shape", "unset")
'''


def test_run_and_preview_accept_repeatable_parameters() -> None:
    parser = _parser()
    for command in ("run", "preview"):
        args = parser.parse_args(
            ["tournament", command, "--tournament", "t-1",
             "--param", "shape=pair", "--param", "phase=calibrate"]
        )
        assert args.param == ["shape=pair", "phase=calibrate"]


def test_a_run_without_parameters_supplies_none() -> None:
    args = _parser().parse_args(["tournament", "run", "--tournament", "t-1"])
    assert args.param is None


def test_parameters_reach_the_definition_hooks(tmp_path: Path) -> None:
    store, tournament = _created(tmp_path, PARAMETERIZED)
    args = _parser().parse_args(
        ["tournament", "preview", "--depot", str(store.root),
         "--tournament", tournament.tournament_id, "--param", "shape=pair", "--json"]
    )
    payload = _handled(args)

    assert payload["players"] == ["alpha", "beta"]
    assert payload["match_label"] == "pair"


@pytest.mark.parametrize("bad", ["shape", "=pair", ""])
def test_a_malformed_parameter_is_rejected_at_the_boundary(
    tmp_path: Path, bad: str
) -> None:
    store, tournament = _created(tmp_path, PARAMETERIZED)
    args = _parser().parse_args(
        ["tournament", "preview", "--depot", str(store.root),
         "--tournament", tournament.tournament_id, "--param", bad, "--json"]
    )
    with pytest.raises(CliError, match="--param"):
        args.handler(args)


def test_a_repeated_parameter_key_resolves_last_wins(tmp_path: Path) -> None:
    store, tournament = _created(tmp_path, PARAMETERIZED)
    args = _parser().parse_args(
        ["tournament", "preview", "--depot", str(store.root),
         "--tournament", tournament.tournament_id,
         "--param", "shape=trio", "--param", "shape=pair", "--json"]
    )
    assert _handled(args)["match_label"] == "pair"


def _created(tmp_path: Path, body: str):
    """Create through the real handler so the snapshot is authorized on record."""
    path = tmp_path / "definition.py"
    path.write_text(body, encoding="utf-8")
    depot = tmp_path / "depot"
    args = _parser().parse_args(
        ["tournament", "create", "--depot", str(depot), "--definition", str(path)]
    )
    created = _handled(args)
    store = TournamentStore(depot)
    return store, store.tournament(created["tournament_id"])


def _handled(args, capsys=None):
    import contextlib
    import io

    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        args.handler(args)
    return json.loads(buffer.getvalue())
