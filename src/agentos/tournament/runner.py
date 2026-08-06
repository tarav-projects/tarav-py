# $kw: ^tournament-runner --from Tournament.Match --from Tournament.Judge --note [DC] the engine composes the Match.Verbatim from the consumer's player presentations and its own frame --supp ^c20260806-7u ^<anchor-on-landing>
"""One match: present, identify, shuffle, compose, spawn, validate, record.

The engine performs every effect here. The definition supplied the two players
and each one's presentation; this module frames them — question, criteria,
position labels, answer contract — hands the result to one judge in a fresh
context, validates the answer at the boundary, and appends the verdict.

Two orderings matter and are deliberately separated. Identity is derived from the
players in *canonical* order, before any shuffle, so repeat runs of one match
accumulate against one identity. The verbatim hash is taken *after* the shuffle,
because it is evidence of what the judge actually saw. A run that fails to
produce a valid answer appends nothing.

The consumer never sees a position label, so it cannot disagree with the decode
that turns the judge's answer back into a player. That hazard is unreachable
rather than guarded.
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
    ATTRIBUTIONS,
    OUTCOME_NO_CONTEST,
    ContractError,
    parse_judge_answer,
    validate_verdict_answer,
)
from agentos.tournament.hooks import HookError, TournamentDefinition
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


def compose_verbatim(
    *,
    question: str,
    criteria: str | None,
    presented_presentations: tuple[str, str],
) -> str:
    """Frame two presentations as one match prompt. Engine-owned, start to end."""
    first, second = presented_presentations
    parts = [question.strip()]
    if criteria and criteria.strip():
        parts.append(criteria.strip())
    parts.append(f"{_POSITIONS[0]}:\n{first}")
    parts.append(f"{_POSITIONS[1]}:\n{second}")
    parts.append(
        'Answer with exactly one JSON object: {"outcome": "A" | "B" | "no_contest", '
        f'"attribution": {" | ".join(repr(item) for item in ATTRIBUTIONS)}, '
        '"reason": "..."}\n'
        'Use "no_contest" when the comparison cannot honestly be made, and attribute '
        'it to the question, to one player, or to this prompt. Use "none" only when '
        "you decided."
    )
    return "\n\n".join(parts)


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
    presentations = tuple(definition.present_player(player) for player in players)
    # Identity before the shuffle: it must not vary with presentation order.
    match_id = definition.match_identity(players=players, presentations=presentations)

    order = _presented_order(players, presentations, rng_seed)
    presented, presented_presentations = order
    verbatim = compose_verbatim(
        question=definition.question,
        criteria=definition.criteria,
        presented_presentations=presented_presentations,
    )
    verbatim_hash = "sha256:" + hashlib.sha256(verbatim.encode("utf-8")).hexdigest()

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

    slot = definition.verdict_slot(players=players, presentations=presentations)
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
    spawn: JudgeSpawn,
    budget: int = 1,
    concurrency: int = 1,
    dry_run: bool = False,
) -> dict[str, object]:
    """Ask the definition for matches until it declines or the budget runs out.

    Failures are rows, not exceptions: one bad match never aborts its siblings,
    and the returned envelope is the orchestration primitive a caller re-invokes
    for the failed subset. Repeat runs of a match are the feature, so nothing is
    skipped on prior success.
    """
    if concurrency < 1:
        raise CliError("tournament run concurrency must be at least 1")
    if budget < 0:
        raise CliError("tournament run budget must not be negative")

    pairs, exhausted = _collect_pairs(
        store=store, definition=definition, tournament=tournament, budget=budget
    )

    def run_one(indexed: tuple[int, tuple[str, str]]) -> dict[str, object]:
        _index, pair = indexed
        try:
            result = run_match(
                store=store,
                definition=definition,
                tournament=tournament,
                players=pair,
                spawn=spawn,
                dry_run=dry_run,
            )
        except (CliError, HookError) as error:
            return {"players": list(pair), "error": str(error)}
        return _run_row(result, spawn=spawn, dry_run=dry_run)

    indexed_pairs = list(enumerate(pairs))
    if concurrency == 1 or len(indexed_pairs) <= 1:
        runs = [run_one(item) for item in indexed_pairs]
    else:
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            runs = list(pool.map(run_one, indexed_pairs))

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
        "budget": budget,
        "exhausted": exhausted,
        "run_count": len(runs),
        "failed_count": len(failures),
        "failures": failures,
        "runs": runs,
    }


def _collect_pairs(
    *,
    store: TournamentStore,
    definition: TournamentDefinition,
    tournament: Tournament,
    budget: int,
) -> tuple[tuple[tuple[str, str], ...], bool]:
    """Call the match-players hook up to ``budget`` times.

    The hook sees the durable verdicts but not the matches already collected in
    this run — in-flight matches have produced no verdict yet. A hook that wants
    variety uses randomness; a deterministic one repeats a pair, which is extra
    samples rather than corruption.
    """
    verdicts = tuple(
        verdict.envelope for verdict in store.verdicts(tournament.tournament_id)
    )
    pairs: list[tuple[str, str]] = []
    for index in range(budget):
        pair = definition.match_players(
            verdicts=verdicts, match_index=index, budget=budget
        )
        if pair is None:
            return tuple(pairs), True
        pairs.append(pair)
    return tuple(pairs), False


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


def _presented_order(
    players: tuple[str, str],
    presentations: tuple[str, ...],
    rng_seed: int | None,
) -> tuple[tuple[str, str], tuple[str, str]]:
    """Shuffle the pair, carrying each player's presentation with it."""
    paired = list(zip(players, presentations))
    random.Random(rng_seed).shuffle(paired)
    ordered_players = (paired[0][0], paired[1][0])
    ordered_presentations = (paired[0][1], paired[1][1])
    return ordered_players, ordered_presentations


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
    # The judge named a position; the engine turns it back into a player through
    # the order it ran. Nothing the consumer wrote can disagree with this.
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
