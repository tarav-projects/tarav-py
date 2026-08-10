# $kw: ^tournament-commands --from Agentos.Tournament --from Tournament.Depot --from Tournament.Hook --note [DF] thin argparse handlers over the importable tournament engine; the depot defaults globally and the failure envelope is the orchestration primitive --supp ^c20260806-26u ^<anchor-on-landing>
"""`agentos tournament ...` — a thin JSON CLI over the tournament engine."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from agentos._core.errors import CliError
from agentos.tournament.contract import (
    OUTCOME_NO_CONTEST,
    ContractError,
    position_labels,
    validate_verdict_answer,
)
from agentos.tournament.hooks import load_definition, open_definition
from agentos.tournament.model import TournamentError, VerdictOutcome
from agentos.tournament.tickets import TicketStore
from agentos.tournament.report import tournament_report
from agentos.tournament.runner import JudgeSpawn, preview_match, run_pool
from agentos.tournament.store import TournamentStore
from agentos.tournament.template import reassemble


def _store(args: argparse.Namespace) -> TournamentStore:
    return TournamentStore(args.depot)


def _print_json(payload: object) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def _snapshot_dir(store: TournamentStore, tournament_id: str) -> Path:
    return store.definition_dir(tournament_id)


def _cmd_create(args: argparse.Namespace) -> int:
    store = _store(args)
    try:
        # Loaded before the tournament exists so a definition missing a required
        # hook fails without leaving an empty tournament behind.
        staging = store.root / "definitions" / "_staging"
        definition = load_definition(args.definition, snapshot_dir=staging)
        tournament = store.create_tournament(
            definition_path=str(definition.origin_path),
            definition_digest=definition.digest,
        )
        final_dir = _snapshot_dir(store, tournament.tournament_id)
        final_dir.parent.mkdir(parents=True, exist_ok=True)
        definition.snapshot_path.parent.rename(final_dir)
    except TournamentError as exc:
        raise CliError(str(exc)) from exc
    _print_json(
        {
            "status": "ok",
            "command": "tournament create",
            "depot": str(store.root),
            "tournament_id": tournament.tournament_id,
            "definition_path": tournament.definition_path,
            "definition_digest": tournament.definition_digest,
        }
    )
    return 0


def _cmd_list(args: argparse.Namespace) -> int:
    store = _store(args)
    _print_json(
        {
            "status": "ok",
            "command": "tournament list",
            "depot": str(store.root),
            "tournaments": [
                {
                    "tournament_id": item.tournament_id,
                    "definition_path": item.definition_path,
                    "created_at": item.created_at,
                }
                for item in store.tournaments()
            ],
        }
    )
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    from agentos.agent.providers import resolve_agent

    store = _store(args)
    try:
        tournament = store.tournament(args.tournament)
        definition = _reload_definition(store, tournament, _run_params(args.param))
    except TournamentError as exc:
        raise CliError(str(exc)) from exc

    agent = resolve_agent(
        provider=args.provider,
        profile=args.profile,
        start_path=Path.cwd(),
        home=args.home,
    )
    spawn = JudgeSpawn(
        agent=agent,
        cwd=Path.cwd(),
        model=args.model,
        account=args.account,
        timeout_sec=args.timeout,
        agent_argv=tuple(args.agent_arg or ()),
    )
    # Sweep before minting: cleanup is age-based, and no run depends on it
    # having happened.
    TicketStore(store.root).sweep()
    try:
        payload = run_pool(
            store=store,
            definition=definition,
            tournament=tournament,
            spawn=spawn,
            budget=args.budget,
            concurrency=args.concurrency,
            dry_run=args.dry_run,
        )
    except TournamentError as exc:
        raise CliError(str(exc)) from exc
    _print_json(payload)
    return 0 if payload["status"] == "ok" else 1


def _cmd_preview(args: argparse.Namespace) -> int:
    """Render one real match and print it, for looking at.

    Mints a genuine ticket, so what it prints is byte-identical to what a judge
    would receive and can be answered by hand with `tournament submit`. That is
    the difference from `run --dry-run`, which mints nothing and therefore shows
    a prompt missing its submit instruction — a third of what a judge reads.
    """
    store = _store(args)
    try:
        tournament = store.tournament(args.tournament)
        definition = _reload_definition(store, tournament, _run_params(args.param))
        players = definition.match_players(
            verdicts=tuple(
                v.envelope for v in store.verdicts(tournament.tournament_id)
            ),
            match_index=args.match_index,
            budget=1,
        )
    except TournamentError as exc:
        raise CliError(str(exc)) from exc
    if players is None:
        raise CliError(
            "the definition declined to supply a match at this index; try another "
            "--match-index"
        )

    result = preview_match(
        store=store,
        definition=definition,
        tournament=tournament,
        players=players,
        judge=_preview_judge(args),
        rng_seed=args.seed,
    )
    if args.json:
        _print_json(
            {
                "status": "ok",
                "command": "tournament preview",
                "tournament_id": tournament.tournament_id,
                "ticket": result.ticket_id,
                "match_id": result.match_id,
                "players": list(result.players),
                "presented": list(result.presented),
                "controls": dict(result.controls),
                "player_labels": dict(result.player_labels),
                "match_label": result.match_label,
                "template": result.template,
                "verbatim_hash": result.verbatim_hash,
                "verbatim": result.verbatim,
            }
        )
    else:
        print(result.verbatim)
    return 0


def _preview_judge(args: argparse.Namespace) -> dict[str, object]:
    return {"provider": args.provider or "preview", "model": args.model, "account": None}


def _cmd_show(args: argparse.Namespace) -> int:
    store = _store(args)
    try:
        tournament = store.tournament(args.tournament)
    except TournamentError as exc:
        raise CliError(str(exc)) from exc
    _print_json(
        tournament_report(
            tournament=tournament, verdicts=store.verdicts(tournament.tournament_id)
        )
    )
    return 0


def _cmd_verbatim(args: argparse.Namespace) -> int:
    """Rebuild and print the exact prompt one verdict's judge was handed.

    It reports whether the rebuilt text still hashes to what was recorded, and
    never repairs a mismatch: the mismatch is the finding.
    """
    store = _store(args)
    try:
        tournament = store.tournament(args.tournament)
    except TournamentError as exc:
        raise CliError(str(exc)) from exc
    for verdict in store.verdicts(tournament.tournament_id):
        if verdict.record_id == args.verdict:
            break
    else:
        raise CliError(
            f"no verdict {args.verdict} in tournament {tournament.tournament_id}"
        )

    try:
        rebuilt = reassemble(store, verdict)
    except TournamentError as exc:
        raise CliError(str(exc)) from exc

    recorded = str(verdict.envelope.get("verbatim_hash") or "")
    rebuilt_hash = "sha256:" + hashlib.sha256(rebuilt.encode("utf-8")).hexdigest()
    if args.json:
        _print_json(
            {
                "status": "ok",
                "command": "tournament verbatim",
                "tournament_id": tournament.tournament_id,
                "verdict_id": verdict.record_id,
                "match_id": verdict.match_id,
                "template": verdict.envelope.get("template"),
                "verbatim": rebuilt,
                "verbatim_hash": recorded,
                "rebuilt_hash": rebuilt_hash,
                "matches": rebuilt_hash == recorded,
            }
        )
    else:
        print(rebuilt)
        if rebuilt_hash != recorded:
            print(
                f"\n[warning] rebuilt hash {rebuilt_hash} does not match the "
                f"recorded {recorded}",
            )
    return 0


def _reload_definition(store: TournamentStore, tournament, params=None):  # noqa: ANN001
    """Open the tournament's own snapshot, never the live definition file."""
    snapshot = _snapshot_dir(store, tournament.tournament_id) / "_definition-snap.py"
    return open_definition(
        snapshot, origin_path=tournament.definition_path, params=params
    )


def _run_params(values: list[str] | None) -> dict[str, str]:
    """Consumer parameters, rejected at the boundary rather than downstream.

    The engine never reads a key, so nothing here validates meaning — only that
    each entry is a `key=value` pair. A repeated key resolves last-wins.
    """
    params: dict[str, str] = {}
    for entry in values or ():
        key, separator, value = str(entry).partition("=")
        if not separator or not key.strip():
            raise CliError(
                f"--param must be key=value (got {entry!r})"
            )
        params[key.strip()] = value
    return params


def _cmd_submit(args: argparse.Namespace) -> int:
    """Record one judge's answer, or tell the judge exactly what to fix.

    This is the boundary where a contract violation becomes actionable: the
    message goes to the agent that made it, in the context that can still
    correct it. Only contract rejections count against the cap, because those
    are the ones a retry can fix.
    """
    store = _store(args)
    tickets = TicketStore(store.root)
    try:
        ticket = tickets.load(args.ticket)
    except TournamentError as exc:
        raise CliError(str(exc)) from exc

    if ticket.redeemed:
        raise CliError(
            f"tournament ticket {ticket.ticket_id} was already redeemed by verdict "
            f"{ticket.verdict_id}; each ticket answers one match once"
        )
    if ticket.exhausted:
        raise CliError(
            f"tournament ticket {ticket.ticket_id} is out of attempts "
            f"({ticket.attempts}/{ticket.attempt_cap}); this match will be recorded "
            "as unanswered"
        )

    answer = _submitted_answer(args)
    try:
        validate_verdict_answer(answer, arity=ticket.arity)
    except ContractError as exc:
        remaining = tickets.record_attempt(ticket.ticket_id)
        raise CliError(
            f"{exc} — attempt {remaining.attempts} of {remaining.attempt_cap}. "
            "Fix the ranking and submit again."
        ) from exc

    try:
        verdict = _append_submitted(store, ticket, answer)
        tickets.redeem(ticket.ticket_id, verdict_id=verdict.record_id, exit_code=None)
    except TournamentError as exc:
        raise CliError(str(exc)) from exc

    _print_json(
        {
            "status": "ok",
            "command": "tournament submit",
            "ticket": ticket.ticket_id,
            "match_id": ticket.match_id,
            "verdict_id": verdict.record_id,
            "outcome": verdict.outcome,
        }
    )
    return 0


def _submitted_answer(args: argparse.Namespace) -> dict[str, object]:
    if args.no_contest:
        if not (args.refusal_reason or "").strip():
            raise CliError("--no-contest requires --refusal-reason")
        return {
            "outcome": OUTCOME_NO_CONTEST,
            "refusal_reason": args.refusal_reason,
        }
    if not args.ranking:
        raise CliError("supply --ranking, or --no-contest with --refusal-reason")
    return {"outcome": [item.strip() for item in args.ranking.split(",") if item.strip()]}


def _append_submitted(store: TournamentStore, ticket, answer: dict[str, object]):  # noqa: ANN001
    """Turn a validated submission into a verdict.

    Everything but the outcome comes from the ticket, which is why a judge can
    never describe a match it was not given.
    """
    if answer["outcome"] == OUTCOME_NO_CONTEST:
        return store.append_verdict(
            tournament_id=ticket.tournament_id,
            match_id=ticket.match_id,
            players=ticket.players,
            outcome=VerdictOutcome.NO_CONTEST,
            refusal_reason=str(answer["refusal_reason"]),
            judge=ticket.judge,
            presented=ticket.presented,
            verbatim_hash=ticket.verbatim_hash,
            ticket=ticket.ticket_id,
            slot=ticket.slot or {},
            controls=ticket.controls,
            template=ticket.template,
            template_bindings=ticket.template_bindings,
            player_labels=ticket.player_labels,
            match_label=ticket.match_label,
        )
    labels = position_labels(ticket.arity)
    ordering = tuple(
        ticket.presented[labels.index(str(label))] for label in answer["outcome"]
    )
    return store.append_verdict(
        tournament_id=ticket.tournament_id,
        match_id=ticket.match_id,
        players=ticket.players,
        outcome=VerdictOutcome.ORDERED,
        ordering=ordering,
        judge=ticket.judge,
        presented=ticket.presented,
        verbatim_hash=ticket.verbatim_hash,
        ticket=ticket.ticket_id,
        slot=ticket.slot or {},
        controls=ticket.controls,
        template=ticket.template,
        template_bindings=ticket.template_bindings,
        player_labels=ticket.player_labels,
        match_label=ticket.match_label,
    )


def _cmd_gc(args: argparse.Namespace) -> int:
    store = _store(args)
    removed = TicketStore(store.root).sweep()
    _print_json(
        {
            "status": "ok",
            "command": "tournament gc",
            "depot": str(store.root),
            "removed": sum(removed.values()),
            # Split by kind: swept `match` tickets went unanswered by a judge,
            # swept `preview` tickets are development noise.
            "removed_by_kind": removed,
        }
    )
    return 0


def _add_depot_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--depot",
        help=(
            "Tournament depot root. Defaults to $AGENTOS_TOURNAMENT_DEPOT, "
            "then ~/.agentos/tournament."
        ),
    )


def register_tournament_commands(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "tournament",
        help="Domain-blind comparative evaluation by pairwise agent-judged matches.",
    )
    commands = parser.add_subparsers(dest="tournament_command", required=True)

    create_parser = commands.add_parser(
        "create", help="Snapshot a definition and create a tournament."
    )
    _add_depot_argument(create_parser)
    create_parser.add_argument(
        "--definition", required=True, help="Path to the consumer definition file."
    )
    create_parser.set_defaults(handler=_cmd_create)

    list_parser = commands.add_parser("list", help="List tournaments in a depot.")
    _add_depot_argument(list_parser)
    list_parser.set_defaults(handler=_cmd_list)

    run_parser = commands.add_parser("run", help="Run matches and record verdicts.")
    _add_depot_argument(run_parser)
    run_parser.add_argument("--tournament", required=True, help="Tournament identity.")
    run_parser.add_argument(
        "--budget",
        type=int,
        default=1,
        help=(
            "Upper bound on matches to run. The definition's match_players hook "
            "may end the run earlier by returning None."
        ),
    )
    run_parser.add_argument(
        "--concurrency", type=int, default=1, help="Parallel judge runs."
    )
    run_parser.add_argument("--provider", help="Judge provider.")
    run_parser.add_argument("--profile", help="Judge agent profile.")
    run_parser.add_argument(
        "--home", help="Provider home, required when running without --profile."
    )
    run_parser.add_argument("--model", help="Judge model.")
    run_parser.add_argument("--account", help="Judge account.")
    run_parser.add_argument("--timeout", type=int, help="Per-match timeout in seconds.")
    run_parser.add_argument(
        "--agent-arg",
        action="append",
        help=(
            "Extra argument passed through to the judge's provider; repeatable. "
            "A judge answers by running a command, so it needs tool permission — "
            "for claude-code that is --agent-arg --allowedTools --agent-arg Bash."
        ),
    )
    run_parser.add_argument(
        "--param",
        action="append",
        help=(
            "Consumer parameter as key=value; repeatable. Reaches every definition hook through its context. The engine carries these and never branches on them."
        ),
    )
    run_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Render prompts and resolve the agent command without spawning.",
    )
    run_parser.set_defaults(handler=_cmd_run)

    submit_parser = commands.add_parser(
        "submit", help="Submit one judge's answer against its ticket."
    )
    _add_depot_argument(submit_parser)
    submit_parser.add_argument("--ticket", required=True, help="Ticket identity.")
    submit_parser.add_argument(
        "--ranking", help="Position labels best first, comma separated (e.g. C,A,D,B)."
    )
    submit_parser.add_argument(
        "--no-contest",
        action="store_true",
        help="Decline the match instead of ranking it.",
    )
    submit_parser.add_argument(
        "--refusal-reason", help="Why the comparison cannot honestly be made."
    )
    submit_parser.set_defaults(handler=_cmd_submit)

    preview_parser = commands.add_parser(
        "preview",
        help="Render one real match and print it, without spawning a judge.",
    )
    _add_depot_argument(preview_parser)
    preview_parser.add_argument("--tournament", required=True, help="Tournament identity.")
    preview_parser.add_argument(
        "--match-index",
        type=int,
        default=0,
        help="Which match the definition should supply (default 0).",
    )
    preview_parser.add_argument(
        "--seed", type=int, help="Seed the presentation shuffle for a stable render."
    )
    preview_parser.add_argument("--provider", help="Judge provider to record on the ticket.")
    preview_parser.add_argument("--model", help="Judge model to record on the ticket.")
    preview_parser.add_argument(
        "--param",
        action="append",
        help=(
            "Consumer parameter as key=value; repeatable. Reaches every definition hook through its context. The engine carries these and never branches on them."
        ),
    )
    preview_parser.add_argument(
        "--json", action="store_true", help="Emit the full record instead of the prompt."
    )
    preview_parser.set_defaults(handler=_cmd_preview)

    gc_parser = commands.add_parser(
        "gc", help="Sweep tournament tickets past the collection horizon."
    )
    _add_depot_argument(gc_parser)
    gc_parser.set_defaults(handler=_cmd_gc)

    show_parser = commands.add_parser(
        "show", help="Report raw accumulation for a tournament."
    )
    _add_depot_argument(show_parser)
    show_parser.add_argument("--tournament", required=True, help="Tournament identity.")
    show_parser.set_defaults(handler=_cmd_show)

    verbatim_parser = commands.add_parser(
        "verbatim",
        help="Rebuild and print the exact prompt one verdict's judge was handed.",
    )
    _add_depot_argument(verbatim_parser)
    verbatim_parser.add_argument(
        "--tournament", required=True, help="Tournament identity."
    )
    verbatim_parser.add_argument(
        "--verdict", required=True, help="Verdict record identity."
    )
    verbatim_parser.add_argument(
        "--json", action="store_true", help="Emit the rebuilt prompt as JSON."
    )
    verbatim_parser.set_defaults(handler=_cmd_verbatim)
