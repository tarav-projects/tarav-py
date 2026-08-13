# $kw: ^test-tournament-reassembly --from Match.Component.Registry --from Match.Template --from Tournament.Verdict --note [DC] the verdict's recorded verbatim hash is the reassembly check: rebuilding from the registered template must reproduce it ^<anchor-on-landing>
from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path

import pytest

from agentos._core.errors import CliError
from agentos.agent.run_runtime import AgentRunResult
from agentos.tournament import JudgeSpawn, TournamentStore, load_definition, run_match
from agentos.tournament.commands import register_tournament_commands
from agentos.tournament.components import ComponentMissingError, ComponentRegistry
from agentos.tournament.template import TemplateMissingError, reassemble

DEFINITION = '''
question = "Which line is better?"
criteria = "Prefer the one that survives a hostile reading."

def match_players(ctx):
    return ("alpha", "beta")

def present_player(ctx):
    return f"the player called {ctx.player}"

def match_identity(ctx):
    return "|".join(ctx.players)
'''


class StubJudge:
    provider = "stub"

    def __init__(self, *answers) -> None:
        self._answers = list(answers)

    def run(self, command_config, run_config) -> AgentRunResult:  # noqa: ANN001
        prompt = command_config.prompt or ""
        if self._answers:
            self._submit(prompt, self._answers.pop(0))
        return AgentRunResult(exit_code=0, stdout="")

    def _submit(self, prompt: str, ranking) -> None:
        ticket = re.search(r"--ticket (\S+)", prompt).group(1)
        depot = re.search(r"--depot (\S+)", prompt).group(1)
        parser = argparse.ArgumentParser()
        register_tournament_commands(parser.add_subparsers(dest="command"))
        args = parser.parse_args(
            [
                "tournament", "submit", "--depot", depot,
                "--ticket", ticket, "--ranking", ",".join(ranking),
            ]
        )
        try:
            args.handler(args)
        except CliError:
            pass


def _run(tmp_path: Path):
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
        spawn=JudgeSpawn(agent=StubJudge(["A", "B"]), cwd=tmp_path),
    )
    return store, tournament, result


def test_a_verdict_reassembles_to_the_exact_prompt_its_judge_saw(
    tmp_path: Path,
) -> None:
    store, tournament, result = _run(tmp_path)
    verdict = store.verdicts(tournament.tournament_id)[0]

    rebuilt = reassemble(store, verdict)

    assert rebuilt == result.verbatim
    digest = "sha256:" + hashlib.sha256(rebuilt.encode("utf-8")).hexdigest()
    assert digest == verdict.envelope["verbatim_hash"]


def test_the_verdict_carries_the_template_address_not_the_text(
    tmp_path: Path,
) -> None:
    store, tournament, _result = _run(tmp_path)
    envelope = store.verdicts(tournament.tournament_id)[0].envelope

    assert str(envelope["template"]).startswith("sha256:")
    assert "verbatim" not in envelope
    assert envelope["template_bindings"]["ticket_id"] == envelope["ticket"]


def test_a_verdict_recorded_before_templates_says_so(tmp_path: Path) -> None:
    store, tournament, _result = _run(tmp_path)
    verdict = store.verdicts(tournament.tournament_id)[0]
    verdict.envelope.pop("template")

    with pytest.raises(TemplateMissingError):
        reassemble(store, verdict)


def test_a_missing_component_names_the_address_it_wanted(tmp_path: Path) -> None:
    """A partial rebuild would be worse than none, so it is not attempted."""
    store, tournament, _result = _run(tmp_path)
    verdict = store.verdicts(tournament.tournament_id)[0]
    registry = ComponentRegistry(store.root)
    presentation = registry.path_for(
        next(
            address
            for address in _component_addresses(registry, verdict)
            if b"the player called" in registry.get(address)
        )
    )
    presentation.unlink()

    with pytest.raises(ComponentMissingError):
        reassemble(store, verdict)


def test_running_the_same_match_twice_registers_each_component_once(
    tmp_path: Path,
) -> None:
    path = tmp_path / "definition.py"
    path.write_text(DEFINITION, encoding="utf-8")
    store = TournamentStore(tmp_path / "tournament")
    definition = load_definition(path, snapshot_dir=tmp_path / "snap")
    tournament = store.create_tournament(
        definition_path=str(path), definition_digest=definition.digest
    )
    registry = ComponentRegistry(store.root)

    for _ in range(3):
        run_match(
            store=store,
            definition=definition,
            tournament=tournament,
            players=("alpha", "beta"),
            spawn=JudgeSpawn(agent=StubJudge(["A", "B"]), cwd=tmp_path),
        )

    files = [path for path in registry.root.rglob("*") if path.is_file()]
    # brief + two presentations + footnote template, plus one template per run:
    # the presented order is randomized, so a template repeats only by chance.
    assert 5 <= len(files) <= 7


def _component_addresses(registry: ComponentRegistry, verdict) -> tuple[str, ...]:  # noqa: ANN001
    import json

    template = json.loads(registry.get(str(verdict.envelope["template"])))
    found: list[str] = []
    for section in template["sections"]:
        if section.get("component"):
            found.append(section["component"])
        found.extend(section.get("presentations") or ())
    return tuple(found)


FRAMED_DEFINITION = '''
from agentos.tournament import Cite, Frame, Players, Section, Shuffle, Table, Text

VOCABULARY = {
    "DF": "names a thing",
    "DC": "pins a choice",
    "CT": "bounds one",
    "RJ": "rejects one",
}

def match_players(ctx):
    return ("alpha@DC", "beta@CT")

def present_player(ctx):
    anchor, _, code = ctx.player.rpartition("@")
    return Section(
        "candidate",
        [Text(f"line: the line called {anchor}"), Cite("Line types", code)],
    )

def match_identity(ctx):
    return "|".join(ctx.players)

def match_frame(ctx):
    return Frame(
        question="Which line is most accurately typed?",
        nodes=(
            Text("Rank by how well each line does what its own type says."),
            Shuffle(Table("Line types", VOCABULARY)),
            Players(),
        ),
    )
'''


def _run_framed(tmp_path: Path):
    path = tmp_path / "definition.py"
    path.write_text(FRAMED_DEFINITION, encoding="utf-8")
    store = TournamentStore(tmp_path / "tournament")
    definition = load_definition(path, snapshot_dir=tmp_path / "snap")
    tournament = store.create_tournament(
        definition_path=str(path), definition_digest=definition.digest
    )
    result = run_match(
        store=store,
        definition=definition,
        tournament=tournament,
        players=("alpha@DC", "beta@CT"),
        spawn=JudgeSpawn(agent=StubJudge(["A", "B"]), cwd=tmp_path),
        rng_seed=11,
    )
    return store, tournament, result


def test_a_framed_verdict_reassembles_including_its_shuffled_order(
    tmp_path: Path,
) -> None:
    """The permutation lives in the bindings, so the rebuild must recover it."""
    store, tournament, result = _run_framed(tmp_path)
    verdict = store.verdicts(tournament.tournament_id)[0]

    rebuilt = reassemble(store, verdict)

    assert rebuilt == result.verbatim
    digest = "sha256:" + hashlib.sha256(rebuilt.encode("utf-8")).hexdigest()
    assert digest == verdict.envelope["verbatim_hash"]


def test_a_framed_match_renders_its_shared_material_once(tmp_path: Path) -> None:
    _store, _tournament, result = _run_framed(tmp_path)
    assert result.verbatim.count("pins a choice") == 1
    assert result.verbatim.count("bounds one") == 1


def test_a_framed_verdict_records_its_permutation(tmp_path: Path) -> None:
    store, tournament, _result = _run_framed(tmp_path)
    verdict = store.verdicts(tournament.tournament_id)[0]
    operations = verdict.envelope["template_bindings"]["frame_operations"]
    assert sorted(operations["0"]) == [0, 1, 2, 3]


def test_the_shared_table_dedups_across_matches(tmp_path: Path) -> None:
    """The whole point of addressing the frame: one copy in the depot, not one per match."""
    store, tournament, first = _run_framed(tmp_path)
    path = tmp_path / "definition.py"
    definition = load_definition(path, snapshot_dir=tmp_path / "snap2")
    second = run_match(
        store=store,
        definition=definition,
        tournament=tournament,
        players=("alpha@DC", "beta@CT"),
        spawn=JudgeSpawn(agent=StubJudge(["B", "A"]), cwd=tmp_path),
        rng_seed=99,
    )
    assert first.template == second.template
