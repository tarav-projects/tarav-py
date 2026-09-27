"""Public read-only CLI for Tarav.Reading.Club."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from tarav.l0._core.errors import CliError

from .core import ReadingClub, ReadingClubError, ReadingProject


def _club(args: argparse.Namespace) -> ReadingClub:
    root = Path(args.root).expanduser().resolve() if args.root is not None else None
    return ReadingClub.open(root)


def _emit_json(command: str, club: ReadingClub, projects: tuple[ReadingProject, ...]) -> None:
    print(
        json.dumps(
            {
                "status": "ok",
                "command": command,
                "reading_club": str(club.root),
                "count": len(projects),
                "projects": [item.to_dict() for item in projects],
            },
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        )
    )


def _emit_text(projects: tuple[ReadingProject, ...]) -> None:
    for project in projects:
        print(f"{project.status}\t{project.slug}\t{project.title}")


def _run(args: argparse.Namespace, command: str) -> tuple[ReadingClub, tuple[ReadingProject, ...]]:
    try:
        club = _club(args)
        if command == "list":
            projects = club.projects(include_inactive=args.all)
        elif command == "find":
            projects = club.find(args.query, include_inactive=args.all)
        else:
            projects = (club.project(args.project),)
    except ReadingClubError as exc:
        raise CliError(str(exc)) from exc
    return club, projects


def _cmd_list(args: argparse.Namespace) -> int:
    club, projects = _run(args, "list")
    if args.json:
        _emit_json("tarav reading-club list", club, projects)
    else:
        _emit_text(projects)
    return 0


def _cmd_find(args: argparse.Namespace) -> int:
    club, projects = _run(args, "find")
    if args.json:
        _emit_json("tarav reading-club find", club, projects)
    else:
        _emit_text(projects)
    return 0


def _cmd_show(args: argparse.Namespace) -> int:
    club, projects = _run(args, "show")
    if args.json:
        _emit_json("tarav reading-club show", club, projects)
    else:
        project = projects[0]
        print(f"project: {project.slug}")
        print(f"title: {project.title}")
        print(f"status: {project.status}")
        print(f"tags: {', '.join(project.tags)}")
        print(f"transcript: {project.transcript}")
        if project.notes is not None:
            print(f"notes: {project.notes}")
        if project.source is not None:
            print(f"source: {project.source}")
    return 0


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--all", action="store_true", help="Include inactive projects.")
    parser.add_argument("--json", action="store_true", help="Print structured JSON.")


def register_reading_club_commands(subparsers: argparse._SubParsersAction) -> None:
    reading_club = subparsers.add_parser(
        "reading-club",
        help="Discover and navigate Tarav.Reading.Club projects.",
    )
    reading_club.add_argument(
        "--root",
        help="Reading Club root; defaults to ~/Documents/tarav/reading-club/.",
    )
    commands = reading_club.add_subparsers(dest="reading_club_command", required=True)

    listing = commands.add_parser("list", help="List Reading Projects.")
    _add_common(listing)
    listing.set_defaults(handler=_cmd_list)

    find = commands.add_parser("find", help="Find Reading Projects by text.")
    find.add_argument("query")
    _add_common(find)
    find.set_defaults(handler=_cmd_find)

    show = commands.add_parser("show", help="Show one exact Reading Project.")
    show.add_argument("project", help="Exact Reading Project slug.")
    show.add_argument("--json", action="store_true", help="Print structured JSON.")
    show.set_defaults(handler=_cmd_show)


__all__ = ["register_reading_club_commands"]
