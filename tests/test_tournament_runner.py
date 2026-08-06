# $kw: ^test-tournament-runner --from Tournament.Match --from Tournament.Judge --note [DF] boundary tests for one stateless match: randomized order recorded, verbatim hashed, failed runs recording nothing ^<anchor-on-landing>
from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentos.agent.run_runtime import AgentRunResult
from agentos.tournament import (
    JudgeSpawn,
    TournamentStore,
    load_definition,
    run_match,
)


class StubJudge:
    """A RunCapable stand-in: the agent boundary, stubbed."""

    def __init__(self, *results: AgentRunResult) -> None:
        self._results = list(results)
        self.prompts: list[str] = []

    def run(self, command_config, run_config) -> AgentRunResult:  # noqa: ANN001
        self.prompts.append(command_config.prompt or "")
        return self._results.pop(0)


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


def _setup(tmp_path: Path, body: str = "question = 'which is better?'\n"):
    path = tmp_path / "definition.py"
    path.write_text(body, encoding="utf-8")
    store = TournamentStore(tmp_path / "tournament")
    definition = load_definition(path, snapshot_dir=tmp_path / "snap")
    tournament = store.create_tournament(
        definition_path=str(path),
        definition_digest=definition.digest,
        players=("alpha", "beta"),
    )
    return store, definition, tournament


def _spawn(agent: StubJudge) -> JudgeSpawn:
    return JudgeSpawn(agent=agent, cwd=Path("."), model="opus", account="work", timeout_sec=60)


def test_completed_run_appends_one_verdict_with_order_and_hash(tmp_path: Path) -> None:
    store, definition, tournament = _setup(tmp_path)
    agent = StubJudge(_answer("A"))

    result = run_match(
        store=store,
        definition=definition,
        tournament=tournament,
        players=("alpha", "beta"),
        spawn=_spawn(agent),
        rng_seed=1,
    )

    verdicts = store.verdicts(tournament.tournament_id)
    assert len(verdicts) == 1
    envelope = verdicts[0].envelope
    assert envelope["outcome"] == "preferred"
    assert envelope["preferred"] == envelope["presented"][0]
    assert set(envelope["presented"]) == {"alpha", "beta"}
    assert envelope["verbatim_hash"].startswith("sha256:")
    assert result.verdict is not None


def test_presented_order_is_randomized_and_recorded(tmp_path: Path) -> None:
    store, definition, tournament = _setup(tmp_path)
    seen = set()
    for seed in range(24):
        agent = StubJudge(_answer("A"))
        run_match(
            store=store,
            definition=definition,
            tournament=tournament,
            players=("alpha", "beta"),
            spawn=_spawn(agent),
            rng_seed=seed,
        )
    for verdict in store.verdicts(tournament.tournament_id):
        seen.add(tuple(verdict.envelope["presented"]))

    assert seen == {("alpha", "beta"), ("beta", "alpha")}


def test_verbatim_hash_tracks_the_prompt_actually_sent(tmp_path: Path) -> None:
    import hashlib

    store, definition, tournament = _setup(tmp_path)
    agent = StubJudge(_answer("B"))
    run_match(
        store=store,
        definition=definition,
        tournament=tournament,
        players=("alpha", "beta"),
        spawn=_spawn(agent),
        rng_seed=3,
    )

    (verdict,) = store.verdicts(tournament.tournament_id)
    expected = "sha256:" + hashlib.sha256(agent.prompts[0].encode("utf-8")).hexdigest()
    assert verdict.envelope["verbatim_hash"] == expected


def test_declining_judge_appends_a_no_contest_with_its_reason(tmp_path: Path) -> None:
    store, definition, tournament = _setup(tmp_path)
    agent = StubJudge(_answer("no_contest", "the two lines are not comparable"))

    run_match(
        store=store,
        definition=definition,
        tournament=tournament,
        players=("alpha", "beta"),
        spawn=_spawn(agent),
        rng_seed=0,
    )

    (verdict,) = store.verdicts(tournament.tournament_id)
    assert verdict.envelope["outcome"] == "no_contest"
    assert verdict.envelope["no_contest_reason"] == "the two lines are not comparable"
    assert verdict.envelope["preferred"] is None


def test_nonzero_exit_records_no_verdict(tmp_path: Path) -> None:
    store, definition, tournament = _setup(tmp_path)
    agent = StubJudge(AgentRunResult(exit_code=1, stdout="", stderr="boom"))

    result = run_match(
        store=store,
        definition=definition,
        tournament=tournament,
        players=("alpha", "beta"),
        spawn=_spawn(agent),
        rng_seed=0,
    )

    assert store.verdicts(tournament.tournament_id) == ()
    assert result.verdict is None
    assert result.failed is True
    assert "exit" in (result.error or "")


def test_unparseable_answer_records_no_verdict_and_reports_actionably(
    tmp_path: Path,
) -> None:
    store, definition, tournament = _setup(tmp_path)
    agent = StubJudge(AgentRunResult(exit_code=0, stdout="I liked the first one"))

    result = run_match(
        store=store,
        definition=definition,
        tournament=tournament,
        players=("alpha", "beta"),
        spawn=_spawn(agent),
        rng_seed=0,
    )

    assert store.verdicts(tournament.tournament_id) == ()
    assert result.failed is True
    assert "JSON object" in (result.error or "")


def test_contract_violation_records_no_verdict(tmp_path: Path) -> None:
    store, definition, tournament = _setup(tmp_path)
    agent = StubJudge(
        AgentRunResult(exit_code=0, stdout=json.dumps({"outcome": "maybe", "attribution": "none", "reason": "x"}))
    )

    result = run_match(
        store=store,
        definition=definition,
        tournament=tournament,
        players=("alpha", "beta"),
        spawn=_spawn(agent),
        rng_seed=0,
    )

    assert store.verdicts(tournament.tournament_id) == ()
    assert result.failed is True


def test_consumer_slot_hook_lands_on_the_verdict(tmp_path: Path) -> None:
    body = (
        "question = 'q'\n\n"
        "def verdict_slot(ctx):\n"
        "    return {'pair': list(ctx.players)}\n"
    )
    store, definition, tournament = _setup(tmp_path, body)
    agent = StubJudge(_answer("A"))

    run_match(
        store=store,
        definition=definition,
        tournament=tournament,
        players=("alpha", "beta"),
        spawn=_spawn(agent),
        rng_seed=0,
    )

    (verdict,) = store.verdicts(tournament.tournament_id)
    assert verdict.slot == {"pair": ["alpha", "beta"]}


def test_match_identity_comes_from_the_definition(tmp_path: Path) -> None:
    body = (
        "question = 'q'\n\n"
        "def match_identity(ctx):\n"
        "    return 'pair::' + '::'.join(sorted(ctx.players))\n"
    )
    store, definition, tournament = _setup(tmp_path, body)
    agent = StubJudge(_answer("A"))

    run_match(
        store=store,
        definition=definition,
        tournament=tournament,
        players=("alpha", "beta"),
        spawn=_spawn(agent),
        rng_seed=0,
    )

    (verdict,) = store.verdicts(tournament.tournament_id)
    assert verdict.envelope["match_id"] == "pair::alpha::beta"
