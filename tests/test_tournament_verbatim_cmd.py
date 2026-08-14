# $kw: ^test-tournament-verbatim-cmd --from Match.Verbatim --from Match.Component.Registry --note [DC] auditing what a judge actually saw is a shell command, not a library call ^<anchor-on-landing>
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import pytest

from tarav._core.errors import CliError
from tarav.agent.run_runtime import AgentRunResult
from tarav.tournament import JudgeSpawn, TournamentStore, load_definition, run_match
from tarav.tournament.commands import register_tournament_commands

DEFINITION = '''
question = "Which line is better?"

def match_players(ctx):
    return ("alpha", "beta")

def match_identity(ctx):
    return "|".join(ctx.players)
'''


class StubJudge:
    provider = "stub"

    def run(self, command_config, run_config) -> AgentRunResult:  # noqa: ANN001
        prompt = command_config.prompt or ""
        ticket = re.search(r"--ticket (\S+)", prompt).group(1)
        depot = re.search(r"--depot (\S+)", prompt).group(1)
        _invoke(
            ["tournament", "submit", "--depot", depot, "--ticket", ticket,
             "--ranking", "A,B"]
        )
        return AgentRunResult(exit_code=0, stdout="")


def _invoke(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    register_tournament_commands(parser.add_subparsers(dest="command"))
    args = parser.parse_args(argv)
    return args.handler(args)


def _recorded(tmp_path: Path):
    path = tmp_path / "definition.py"
    path.write_text(DEFINITION, encoding="utf-8")
    store = TournamentStore(tmp_path / "tournament")
    definition = load_definition(path, snapshot_dir=tmp_path / "snap")
    tournament = store.create_tournament(
        definition_path=str(path), definition_digest=definition.digest
    )
    result = run_match(
        store=store,
        definition=definition,
        tournament=tournament,
        players=("alpha", "beta"),
        spawn=JudgeSpawn(agent=StubJudge(), cwd=tmp_path),
    )
    verdict = store.verdicts(tournament.tournament_id)[0]
    return store, tournament, verdict, result


def test_the_command_prints_the_prompt_the_judge_received(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store, tournament, verdict, result = _recorded(tmp_path)
    capsys.readouterr()  # the judge's own submit already printed

    _invoke(
        ["tournament", "verbatim", "--depot", str(store.root),
         "--tournament", tournament.tournament_id, "--verdict", verdict.record_id]
    )

    assert capsys.readouterr().out.strip() == result.verbatim.strip()


def test_json_reports_the_rebuilt_hash_beside_the_recorded_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store, tournament, verdict, _result = _recorded(tmp_path)
    capsys.readouterr()  # the judge's own submit already printed

    _invoke(
        ["tournament", "verbatim", "--depot", str(store.root),
         "--tournament", tournament.tournament_id, "--verdict", verdict.record_id,
         "--json"]
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["matches"] is True
    assert payload["rebuilt_hash"] == payload["verbatim_hash"]
    assert payload["verbatim"]


def test_an_unknown_verdict_is_a_cli_error(tmp_path: Path) -> None:
    store, tournament, _verdict, _result = _recorded(tmp_path)

    with pytest.raises(CliError) as excinfo:
        _invoke(
            ["tournament", "verbatim", "--depot", str(store.root),
             "--tournament", tournament.tournament_id, "--verdict", "nope"]
        )
    assert "nope" in str(excinfo.value)


def test_a_verdict_without_a_template_fails_with_a_message_not_a_traceback(
    tmp_path: Path,
) -> None:
    store, tournament, verdict, _result = _recorded(tmp_path)
    record = store.depot.get(verdict.record_id, namespace=tournament.tournament_id)
    record.value["envelope"].pop("template")
    store.depot.edit(
        verdict.record_id, record.value, namespace=tournament.tournament_id
    )

    with pytest.raises(CliError) as excinfo:
        _invoke(
            ["tournament", "verbatim", "--depot", str(store.root),
             "--tournament", tournament.tournament_id, "--verdict", verdict.record_id]
        )
    assert "template" in str(excinfo.value)
