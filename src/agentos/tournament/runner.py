# $kw: ^tournament-runner --from Tournament.Match --from Tournament.Judge --note [DC] one judge run serves one match and carries no state from any other; a failed run produces no match record ^<anchor-on-landing>
"""One match: render, randomize, spawn, validate, record.

The engine performs every effect here. Hooks supplied the rendering and the
identity; this module shuffles the pair, hands the rendered text to one judge in
a fresh context, validates the answer at the boundary, and appends the verdict.
A run that fails to produce a valid answer appends nothing.
"""

from __future__ import annotations

import hashlib
import random
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from agentos._core.errors import CliError
from agentos.agent.run_runtime import (
    AgentCommandConfig,
    AgentRunConfig,
    AgentRunResult,
)
from agentos.tournament.contract import (
    OUTCOME_NO_CONTEST,
    ContractError,
    parse_judge_answer,
    validate_verdict_answer,
)
from agentos.tournament.hooks import TournamentDefinition
from agentos.tournament.model import Tournament, Verdict, VerdictOutcome
from agentos.tournament.store import TournamentStore

# The judge decides one pair in one fresh context; presentation order is the
# engine's randomization, so the answer names a position, not a player.
_POSITIONS = ("A", "B")


@dataclass(frozen=True)
class JudgeSpawn:
    """Everything needed to run one judge, resolved once per tournament run."""

    agent: object
    cwd: Path
    model: str | None = None
    account: str | None = None
    timeout_sec: int | None = None

    def identity(self) -> dict[str, object]:
        return {
            "provider": getattr(self.agent, "provider", None),
            "model": self.model,
            "account": self.account,
        }


@dataclass(frozen=True)
class MatchResult:
    match_id: str
    players: tuple[str, str]
    presented: tuple[str, str]
    verbatim: str
    verbatim_hash: str
    verdict: Verdict | None = None
    error: str | None = None

    @property
    def failed(self) -> bool:
        return self.verdict is None


def run_match(
    *,
    store: TournamentStore,
    definition: TournamentDefinition,
    tournament: Tournament,
    players: tuple[str, str],
    spawn: JudgeSpawn,
    rng_seed: int | None = None,
    dry_run: bool = False,
) -> MatchResult:
    presented = _presented_order(players, rng_seed)
    verbatim = definition.render_match(players=players, presented=presented)
    verbatim_hash = "sha256:" + hashlib.sha256(verbatim.encode("utf-8")).hexdigest()
    match_id = definition.match_identity(
        players=players, presented=presented, rendering=verbatim
    )

    if dry_run:
        return MatchResult(
            match_id=match_id,
            players=players,
            presented=presented,
            verbatim=verbatim,
            verbatim_hash=verbatim_hash,
        )

    started = time.monotonic()
    try:
        run_result = _spawn_judge(spawn, verbatim)
    except (CliError, OSError) as error:
        return _failure(match_id, players, presented, verbatim, verbatim_hash, str(error))
    duration_ms = int((time.monotonic() - started) * 1000)

    if run_result.exit_code != 0:
        return _failure(
            match_id,
            players,
            presented,
            verbatim,
            verbatim_hash,
            f"judge exit {run_result.exit_code}",
        )

    try:
        answer = parse_judge_answer(run_result.stdout)
        validate_verdict_answer(answer)
    except ContractError as error:
        return _failure(match_id, players, presented, verbatim, verbatim_hash, str(error))

    slot = definition.verdict_slot(
        players=players, presented=presented, rendering=verbatim
    )
    verdict = _append(
        store=store,
        tournament=tournament,
        match_id=match_id,
        players=players,
        presented=presented,
        answer=answer,
        judge=spawn.identity(),
        verbatim_hash=verbatim_hash,
        duration_ms=duration_ms,
        slot=slot,
    )
    return MatchResult(
        match_id=match_id,
        players=players,
        presented=presented,
        verbatim=verbatim,
        verbatim_hash=verbatim_hash,
        verdict=verdict,
    )


def run_pool(
    *,
    store: TournamentStore,
    definition: TournamentDefinition,
    tournament: Tournament,
    pairs: tuple[tuple[str, str], ...] | list[tuple[str, str]],
    spawn: JudgeSpawn,
    concurrency: int = 1,
    dry_run: bool = False,
) -> dict[str, object]:
    """Run many matches and report every outcome as data.

    Failures are rows, not exceptions: one bad match never aborts its siblings,
    and the returned envelope is the orchestration primitive a caller re-invokes
    with the failed subset. Repeat runs of a match are the feature, so nothing is
    skipped on prior success.
    """
    if concurrency < 1:
        raise CliError("tournament run concurrency must be at least 1")
    pairs = tuple(tuple(pair) for pair in pairs)  # type: ignore[misc]

    def run_one(pair: tuple[str, str]) -> dict[str, object]:
        try:
            result = run_match(
                store=store,
                definition=definition,
                tournament=tournament,
                players=pair,
                spawn=spawn,
                dry_run=dry_run,
            )
        except CliError as error:
            return {"players": list(pair), "error": str(error)}
        return _run_row(result, spawn=spawn, dry_run=dry_run)

    if concurrency == 1 or len(pairs) <= 1:
        runs = [run_one(pair) for pair in pairs]
    else:
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            runs = list(pool.map(run_one, pairs))

    failures = [
        {"match_id": row.get("match_id"), "players": row["players"], "error": row["error"]}
        for row in runs
        if row.get("error")
    ]
    return {
        "status": "ok" if not failures else "error",
        "command": "tournament run",
        "tournament_id": tournament.tournament_id,
        "dry_run": dry_run,
        "concurrency": concurrency,
        "run_count": len(runs),
        "failed_count": len(failures),
        "failures": failures,
        "runs": runs,
    }


def _run_row(
    result: MatchResult, *, spawn: JudgeSpawn, dry_run: bool
) -> dict[str, object]:
    row: dict[str, object] = {
        "match_id": result.match_id,
        "players": list(result.players),
        "presented": list(result.presented),
        "verbatim_hash": result.verbatim_hash,
    }
    if dry_run:
        row["verbatim"] = result.verbatim
        row["agent_command"] = list(_dry_command(spawn, result.verbatim))
        return row
    if result.verdict is None:
        row["error"] = result.error
        return row
    row["outcome"] = result.verdict.outcome
    row["preferred"] = result.verdict.preferred
    row["verdict_id"] = result.verdict.record_id
    return row


def _dry_command(spawn: JudgeSpawn, verbatim: str) -> tuple[str, ...]:
    run_dry = getattr(spawn.agent, "run_dry", None)
    if run_dry is None:
        return ()
    dry = run_dry(
        AgentCommandConfig(
            prompt=verbatim,
            model=spawn.model,
            account=spawn.account,
            interaction_mode="non_interactive",
        )
    )
    return tuple(dry.lines)


def _presented_order(players: tuple[str, str], rng_seed: int | None) -> tuple[str, str]:
    order = list(players)
    random.Random(rng_seed).shuffle(order)
    return (order[0], order[1])


def _spawn_judge(spawn: JudgeSpawn, verbatim: str) -> AgentRunResult:
    return spawn.agent.run(
        AgentCommandConfig(
            prompt=verbatim,
            model=spawn.model,
            account=spawn.account,
            interaction_mode="non_interactive",
        ),
        # "capture" and not "terminal": _run_terminal discards stdout, and the
        # judge's answer is the whole product of the run.
        AgentRunConfig(
            cwd=spawn.cwd, process_mode="capture", timeout_sec=spawn.timeout_sec
        ),
    )


def _append(
    *,
    store: TournamentStore,
    tournament: Tournament,
    match_id: str,
    players: tuple[str, str],
    presented: tuple[str, str],
    answer: dict[str, object],
    judge: dict[str, object],
    verbatim_hash: str,
    duration_ms: int,
    slot: dict[str, object],
) -> Verdict:
    outcome = str(answer["outcome"])
    reason = str(answer["reason"])
    attribution = str(answer["attribution"])
    if outcome == OUTCOME_NO_CONTEST:
        return store.append_verdict(
            tournament_id=tournament.tournament_id,
            match_id=match_id,
            players=players,
            outcome=VerdictOutcome.NO_CONTEST,
            no_contest_reason=reason,
            no_contest_attribution=attribution,
            judge=judge,
            presented=presented,
            verbatim_hash=verbatim_hash,
            duration_ms=duration_ms,
            slot=slot,
        )
    preferred = presented[_POSITIONS.index(outcome)]
    return store.append_verdict(
        tournament_id=tournament.tournament_id,
        match_id=match_id,
        players=players,
        outcome=VerdictOutcome.PREFERRED,
        preferred=preferred,
        judge=judge,
        presented=presented,
        verbatim_hash=verbatim_hash,
        duration_ms=duration_ms,
        slot=slot,
    )


def _failure(
    match_id: str,
    players: tuple[str, str],
    presented: tuple[str, str],
    verbatim: str,
    verbatim_hash: str,
    error: str,
) -> MatchResult:
    return MatchResult(
        match_id=match_id,
        players=players,
        presented=presented,
        verbatim=verbatim,
        verbatim_hash=verbatim_hash,
        error=error,
    )
