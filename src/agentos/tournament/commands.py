# $kw: ^tournament-commands --from Agentos.Tournament --from Tournament.Definition --note [DF] thin argparse handlers over the importable tournament engine; the failure envelope is the orchestration primitive ^<anchor-on-landing>
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
from agentos.tournament.sampling import select_pairs
from agentos.tournament.store import TournamentStore


def _store(args: argparse.Namespace) -> TournamentStore:
    return TournamentStore(Path(args.depot))


def _print_json(payload: object) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def _snapshot_dir(store: TournamentStore, tournament_id: str) -> Path:
    return store.depot.root / "definitions" / tournament_id


def _cmd_create(args: argparse.Namespace) -> int:
    store = _store(args)
    players = _players_arg(args)
    try:
        definition = load_definition(
            args.definition, snapshot_dir=store.depot.root / "definitions" / "_staging"
        )
        tournament = store.create_tournament(
            definition_path=str(definition.origin_path),
            definition_digest=definition.digest,
            players=players,
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
            "tournament_id": tournament.tournament_id,
            "definition_path": tournament.definition_path,
            "definition_digest": tournament.definition_digest,
            "players": list(tournament.players),
        }
    )
    return 0


def _cmd_list(args: argparse.Namespace) -> int:
    store = _store(args)
    _print_json(
        {
            "status": "ok",
            "command": "tournament list",
            "tournaments": [
                {
                    "tournament_id": item.tournament_id,
                    "definition_path": item.definition_path,
                    "players": list(item.players),
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
        pairs = select_pairs(
            definition=definition,
            pool=tournament.players,
            budget=args.budget,
            verdicts=tuple(v.envelope for v in store.verdicts(tournament.tournament_id)),
        )
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
    payload = run_pool(
        store=store,
        definition=definition,
        tournament=tournament,
        pairs=pairs,
        spawn=spawn,
        concurrency=args.concurrency,
        dry_run=args.dry_run,
    )
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


def _players_arg(args: argparse.Namespace) -> tuple[str, ...]:
    if args.players_file:
        raw = Path(args.players_file).read_text(encoding="utf-8")
        try:
            value = json.loads(raw)
        except ValueError as exc:
            raise CliError(f"players file is not valid JSON: {exc}") from exc
        if not isinstance(value, list):
            raise CliError("players file must contain a JSON array of player payloads")
        return tuple(str(item) for item in value)
    if not args.player:
        raise CliError("a tournament needs players: pass --player or --players-file")
    return tuple(args.player)


def _add_depot_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--depot", required=True, help="Tournament depot root.")


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
    create_parser.add_argument(
        "--player", action="append", help="A player payload; repeatable."
    )
    create_parser.add_argument(
        "--players-file", help="Path to a JSON array of player payloads."
    )
    create_parser.set_defaults(handler=_cmd_create)

    list_parser = commands.add_parser("list", help="List tournaments in a depot.")
    _add_depot_argument(list_parser)
    list_parser.set_defaults(handler=_cmd_list)

    run_parser = commands.add_parser("run", help="Run matches and record verdicts.")
    _add_depot_argument(run_parser)
    run_parser.add_argument("--tournament", required=True, help="Tournament identity.")
    run_parser.add_argument(
        "--budget", type=int, default=1, help="How many matches to run."
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
