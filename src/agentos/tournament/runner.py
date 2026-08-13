# $kw: ^tournament-runner --from Tournament.Match --from Tournament.Judge --from Tournament.Label --from Judge.Blinding --note [DC] the engine composes the Match.Verbatim from the consumer's player presentations and its own frame --supp ^c20260806-7u ^<anchor-on-landing>
"""One match: substitute, present, identify, shuffle, compose, spawn, record.

The engine performs every effect here. The definition supplied the match's
players and each one's presentation; this module frames them — question,
criteria, position labels, answer contract — hands the result to one judge in a
fresh context, validates the returned ordering at the boundary, and appends the
verdict.

Positions, not players: the judge ranks labels and the engine decodes each back
through the order it ran, so nothing a consumer wrote can invert a verdict.

Control substitution happens first, before anything else observes the roster:
a match carrying a control is a different match from the one without, so it must
reach identity as a different roster rather than be merged under one id.

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
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from agentos._core.errors import CliError
from agentos.agent.run_runtime import (
    AgentCommandConfig,
    AgentRunConfig,
    AgentRunResult,
)
from agentos.tournament.components import ComponentRegistry
from agentos.tournament.frame import Frame, plan_operations, validate_cards
from agentos.tournament.hooks import HookError, TournamentDefinition
from agentos.tournament.model import Tournament, Verdict
from agentos.tournament.store import TournamentStore
from agentos.tournament.template import (
    build_template,
    register_template,
    render_template,
)
from agentos.tournament.tickets import KIND_PREVIEW, TicketStore




@dataclass(frozen=True)
class JudgeSpawn:
    """Everything needed to run one judge, resolved once per tournament run."""

    agent: object
    cwd: Path
    model: str | None = None
    account: str | None = None
    timeout_sec: int | None = None




    agent_argv: tuple[str, ...] = ()

    def identity(self) -> dict[str, object]:
        return {
            "provider": getattr(self.agent, "provider", None),
            "model": self.model,
            "account": self.account,
        }


@dataclass(frozen=True)
class MatchResult:
    match_id: str
    players: tuple[str, ...]
    presented: tuple[str, ...]
    verbatim: str
    verbatim_hash: str


    controls: dict[str, str] = field(default_factory=dict)


    template: str | None = None
    template_bindings: dict[str, object] = field(default_factory=dict)


    player_labels: dict[str, str] = field(default_factory=dict)
    match_label: str | None = None
    ticket_id: str | None = None
    verdict: Verdict | None = None
    error: str | None = None

    @property
    def failed(self) -> bool:
        return self.verdict is None


def compose_verbatim(
    *,
    question: str,
    criteria: str | None,
    presented_presentations: tuple[str, ...],
    ticket_id: str | None = None,
    depot_root: Path | str | None = None,
) -> str:
    """Frame N presentations as one match prompt. Engine-owned, start to end.

    The frame is described as a `Match.Template` and rendered from it rather than
    concatenated here, so the same bytes are reachable later from the record alone.
    The submit instruction is engine-owned for the same reason the position labels
    are: an invocation a consumer could get wrong is one the frame can simply
    prevent.
    """
    return _composed(
        question=question,
        criteria=criteria,
        presented_presentations=presented_presentations,
        ticket_id=ticket_id,
        depot_root=depot_root,
    )[0]


def _composed(
    *,
    question: str,
    criteria: str | None,
    presented_presentations: tuple[str, ...],
    ticket_id: str | None = None,
    depot_root: Path | str | None = None,
    registry: ComponentRegistry | None = None,
    frame: Frame | None = None,
    rng: random.Random | None = None,
) -> tuple[str, str | None, dict[str, object]]:
    """Render the frame and, given a registry, leave its parts behind.

    Returns the verbatim, the template's address when one was registered, and the
    bindings that produced it.

    Every declared shuffle is drawn here, from the match's own rng, exactly as
    presentation order already is. Drawing it inside the definition would produce
    a permutation the engine could neither reproduce nor record.
    """
    operations = (
        plan_operations(frame, rng or random.Random())
        if frame is not None
        else None
    )
    template, components, bindings = build_template(
        question=question,
        criteria=criteria,
        presented_presentations=presented_presentations,
        ticket_id=ticket_id,
        depot_root=depot_root,
        frame=frame,
        frame_operations=operations,
    )
    verbatim = render_template(template, components, bindings)
    address = (
        None if registry is None else register_template(registry, template, components)
    )
    return verbatim, address, bindings


def _prepared(
    definition: TournamentDefinition, players: tuple[str, ...]
) -> tuple[tuple[str, ...], Frame | None]:
    """Build the cards and the frame, and check them against each other.

    The two hooks are called separately but compose into one prompt, so this is
    the only place a card's cite can be resolved against the frame's tables. It
    runs before any ticket is minted: an unresolvable reference is a definition
    bug and must not cost a spawn to discover.
    """
    cards = tuple(definition.present_card(player) for player in players)
    presentations = tuple(text for text, _node in cards)
    frame = definition.match_frame(players=players, presentations=presentations)
    if frame is not None:
        validate_cards(frame, [node for _text, node in cards if node is not None])
    return presentations, frame


def run_match(
    *,
    store: TournamentStore,
    definition: TournamentDefinition,
    tournament: Tournament,
    players: tuple[str, ...],
    spawn: JudgeSpawn,
    rng_seed: int | None = None,
    dry_run: bool = False,
) -> MatchResult:
    rng = random.Random(rng_seed)



    players, controls = _substituted(
        definition=definition,
        tournament=tournament,
        store=store,
        players=players,
        rng=rng,
    )
    presentations, frame = _prepared(definition, players)

    match_id = definition.match_identity(players=players, presentations=presentations)
    player_labels, match_label = _labels(definition, players, presentations)

    presented, presented_presentations = _presented_order(players, presentations, rng)

    if dry_run:

        verbatim, _address, _bindings = _composed(
            question=definition.question,
            criteria=definition.criteria,
            presented_presentations=presented_presentations,
            frame=frame,
            rng=rng,
        )
        return MatchResult(
            match_id=match_id,
            players=players,
            presented=presented,
            verbatim=verbatim,
            verbatim_hash="sha256:"
            + hashlib.sha256(verbatim.encode("utf-8")).hexdigest(),
            controls=controls,
            player_labels=player_labels,
            match_label=match_label,
        )

    tickets = TicketStore(store.root)
    ticket = tickets.mint(
        tournament_id=tournament.tournament_id,
        match_id=match_id,
        players=players,
        presented=presented,
        verbatim_hash="",
        judge=spawn.identity(),
        controls=controls,
        player_labels=player_labels,
        match_label=match_label,
    )
    verbatim, template, bindings = _composed(
        question=definition.question,
        criteria=definition.criteria,
        presented_presentations=presented_presentations,
        ticket_id=ticket.ticket_id,
        depot_root=store.root,
        registry=ComponentRegistry(store.root),
        frame=frame,
        rng=rng,
    )
    verbatim_hash = "sha256:" + hashlib.sha256(verbatim.encode("utf-8")).hexdigest()
    tickets.set_verbatim_hash(ticket.ticket_id, verbatim_hash)
    tickets.set_template(ticket.ticket_id, template, bindings)



    tickets.set_slot(
        ticket.ticket_id,
        definition.verdict_slot(players=players, presentations=presentations),
    )

    try:
        run_result = _spawn_judge(spawn, verbatim)
        exit_code = run_result.exit_code
    except (CliError, OSError) as error:
        return _failure(
            ticket.ticket_id, match_id, players, presented, verbatim, verbatim_hash,
            controls, template, bindings, str(error),
            player_labels=player_labels, match_label=match_label,
        )



    verdict = _verdict_for_ticket(store, tournament, ticket.ticket_id)
    if verdict is None:
        redeemed = tickets.load(ticket.ticket_id)
        detail = (
            f"judge made {redeemed.attempts} rejected submission(s)"
            if redeemed.attempts
            else "judge submitted nothing"
        )
        return _failure(
            ticket.ticket_id, match_id, players, presented, verbatim, verbatim_hash,
            controls, template, bindings, f"{detail} (judge exit {exit_code})",
            player_labels=player_labels, match_label=match_label,
        )
    return MatchResult(
        ticket_id=ticket.ticket_id,
        match_id=match_id,
        players=players,
        presented=presented,
        verbatim=verbatim,
        verbatim_hash=verbatim_hash,
        controls=controls,
        template=template,
        template_bindings=bindings,
        player_labels=player_labels,
        match_label=match_label,
        verdict=verdict,
    )


def preview_match(
    *,
    store: TournamentStore,
    definition: TournamentDefinition,
    tournament: Tournament,
    players: tuple[str, ...],
    judge: dict[str, object],
    rng_seed: int | None = None,
) -> MatchResult:
    """Compose one real match without spawning anything.

    It mints a genuine ticket, so the rendered text is exactly what a judge would
    be handed and can be answered by hand. Everything after the frame — the
    spawn, the wait, the resolution — is what this skips.
    """
    rng = random.Random(rng_seed)


    players, controls = _substituted(
        definition=definition,
        tournament=tournament,
        store=store,
        players=players,
        rng=rng,
    )
    presentations, frame = _prepared(definition, players)
    match_id = definition.match_identity(players=players, presentations=presentations)
    player_labels, match_label = _labels(definition, players, presentations)
    presented, presented_presentations = _presented_order(players, presentations, rng)

    tickets = TicketStore(store.root)
    ticket = tickets.mint(
        tournament_id=tournament.tournament_id,
        match_id=match_id,
        players=players,
        presented=presented,
        verbatim_hash="",
        judge=judge,
        kind=KIND_PREVIEW,
        controls=controls,
        player_labels=player_labels,
        match_label=match_label,
    )
    verbatim, template, bindings = _composed(
        question=definition.question,
        criteria=definition.criteria,
        presented_presentations=presented_presentations,
        ticket_id=ticket.ticket_id,
        depot_root=store.root,
        registry=ComponentRegistry(store.root),
        frame=frame,
        rng=rng,
    )
    verbatim_hash = "sha256:" + hashlib.sha256(verbatim.encode("utf-8")).hexdigest()
    tickets.set_verbatim_hash(ticket.ticket_id, verbatim_hash)
    tickets.set_template(ticket.ticket_id, template, bindings)
    tickets.set_slot(
        ticket.ticket_id,
        definition.verdict_slot(players=players, presentations=presentations),
    )
    return MatchResult(
        match_id=match_id,
        players=players,
        presented=presented,
        verbatim=verbatim,
        verbatim_hash=verbatim_hash,
        controls=controls,
        template=template,
        template_bindings=bindings,
        player_labels=player_labels,
        match_label=match_label,
        ticket_id=ticket.ticket_id,
    )


def _verdict_for_ticket(
    store: TournamentStore, tournament: Tournament, ticket_id: str
) -> Verdict | None:
    """Find the verdict this spawn produced.

    Keyed on the ticket, not the match id: repeat runs of one match share an id
    deliberately, so only the ticket says which run answered.
    """
    for verdict in store.verdicts(tournament.tournament_id):
        if verdict.envelope.get("ticket") == ticket_id:
            return verdict
    return None


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

    def run_one(indexed: tuple[int, tuple[str, ...]]) -> dict[str, object]:
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
) -> tuple[tuple[tuple[str, ...], ...], bool]:
    """Call the match-players hook up to ``budget`` times.

    The hook sees the durable verdicts but not the matches already collected in
    this run — in-flight matches have produced no verdict yet. A hook that wants
    variety uses randomness; a deterministic one repeats a pair, which is extra
    samples rather than corruption.
    """
    verdicts = tuple(
        verdict.envelope for verdict in store.verdicts(tournament.tournament_id)
    )
    pairs: list[tuple[str, ...]] = []
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
        "ticket": result.ticket_id,
        "players": list(result.players),
        "presented": list(result.presented),
        "controls": dict(result.controls),
        "template": result.template,
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
    ordering = result.verdict.ordering
    row["ordering"] = list(ordering) if ordering is not None else None
    row["verdict_id"] = result.verdict.record_id
    return row


def _dry_command(spawn: JudgeSpawn, verbatim: str) -> tuple[str, ...]:
    run_dry = getattr(spawn.agent, "run_dry", None)
    if run_dry is None:
        return ()
    dry = run_dry(
        AgentCommandConfig(
            prompt=verbatim,
            argv=tuple(spawn.agent_argv),
            model=spawn.model,
            account=spawn.account,
            interaction_mode="non_interactive",
        )
    )
    return tuple(dry.lines)


def _presented_order(
    players: tuple[str, ...],
    presentations: tuple[str, ...],
    rng: random.Random,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Shuffle the match, carrying each player's presentation with it."""
    paired = list(zip(players, presentations))
    rng.shuffle(paired)
    return tuple(item[0] for item in paired), tuple(item[1] for item in paired)


def _substituted(
    *,
    definition: TournamentDefinition,
    tournament: Tournament,
    store: TournamentStore,
    players: tuple[str, ...],
    rng: random.Random,
) -> tuple[tuple[str, ...], dict[str, str]]:
    """Swap one control in for one pool player, at the definition's rate.

    One control at most, and never one already in the match — drawing a duplicate
    is a roster the arity check would refuse, and skipping is the honest outcome.
    Retrying the draw instead would make the effective rate depend on how much
    the pool and the control set overlap, which is not what a rate says.

    Both draws are the engine's: the consumer declares who the controls are and
    how often they appear, never which one lands in which match.
    """
    rate = definition.control_rate
    if rate <= 0.0:
        return players, {}
    pool = definition.controls(
        verdicts=tuple(
            verdict.envelope for verdict in store.verdicts(tournament.tournament_id)
        ),
        match_index=0,
        budget=1,
    )
    available = sorted(name for name in pool if name not in players)
    if not available or rng.random() >= rate:
        return players, {}
    control = rng.choice(available)
    index = rng.randrange(len(players))
    roster = players[:index] + (control,) + players[index + 1 :]
    return roster, {control: pool[control]}


def _spawn_judge(spawn: JudgeSpawn, verbatim: str) -> AgentRunResult:
    return spawn.agent.run(
        AgentCommandConfig(
            prompt=verbatim,
            argv=tuple(spawn.agent_argv),
            model=spawn.model,
            account=spawn.account,
            interaction_mode="non_interactive",
        ),


        AgentRunConfig(
            cwd=spawn.cwd, process_mode="capture", timeout_sec=spawn.timeout_sec
        ),
    )


def _labels(
    definition: TournamentDefinition,
    players: tuple[str, ...],
    presentations: tuple[str, ...],
) -> tuple[dict[str, str], str | None]:
    """The match's grouping tags, resolved once before the shuffle.

    Unlabeled players are omitted rather than stored as null, so the mapping is
    the labeled set. Labels never reach the judge: they are not passed to the
    template, and nothing here returns into the render path.
    """
    labels = {
        player: label
        for player in players
        if (label := definition.player_label(player)) is not None
    }
    return labels, definition.match_label(
        players=players, presentations=presentations
    )


def _failure(
    ticket_id: str | None,
    match_id: str,
    players: tuple[str, ...],
    presented: tuple[str, ...],
    verbatim: str,
    verbatim_hash: str,
    controls: dict[str, str],
    template: str | None,
    template_bindings: dict[str, object],
    error: str,
    *,
    player_labels: dict[str, str] | None = None,
    match_label: str | None = None,
) -> MatchResult:
    return MatchResult(
        match_id=match_id,
        players=players,
        presented=presented,
        verbatim=verbatim,
        verbatim_hash=verbatim_hash,
        controls=controls,
        template=template,
        template_bindings=template_bindings,
        player_labels=dict(player_labels or {}),
        match_label=match_label,
        ticket_id=ticket_id,
        error=error,
    )
