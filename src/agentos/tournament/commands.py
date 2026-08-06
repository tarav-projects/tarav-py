# $kw: ^tournament-commands --from Agentos.Tournament --from Tournament.Depot --note [DF] thin argparse handlers over the importable tournament engine; the depot defaults globally and the failure envelope is the orchestration primitive --supp ^c20260806-26u ^<anchor-on-landing>
"""`agentos tournament ...` — a thin JSON CLI over the tournament engine."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from agentos._core.errors import CliError
from agentos.tournament.hooks import load_definition, open_definition
from agentos.tournament.model import TournamentError
from agentos.tournament.report import tournament_report
from agentos.tournament.runner import JudgeSpawn, run_pool
from agentos.tournament.store import TournamentStore


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
        definition = _reload_definition(store, tournament)
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
    )
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


def _reload_definition(store: TournamentStore, tournament):  # noqa: ANN001
    """Open the tournament's own snapshot, never the live definition file."""
    snapshot = _snapshot_dir(store, tournament.tournament_id) / "_definition-snap.py"
    return open_definition(snapshot, origin_path=tournament.definition_path)


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
        "--dry-run",
        action="store_true",
        help="Render prompts and resolve the agent command without spawning.",
    )
    run_parser.set_defaults(handler=_cmd_run)

    show_parser = commands.add_parser(
        "show", help="Report raw accumulation for a tournament."
    )
    _add_depot_argument(show_parser)
    show_parser.add_argument("--tournament", required=True, help="Tournament identity.")
    show_parser.set_defaults(handler=_cmd_show)
