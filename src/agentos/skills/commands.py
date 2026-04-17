from __future__ import annotations

import argparse
import json
from pathlib import Path

from agentos._core.errors import CliError
from agentos.skills.routing import (
    import_routed_skills,
    list_routed_skills,
    resolve_routed_skill,
    resolve_routed_skills_selection,
)

NO_ROUTED_SKILLS_MESSAGE = (
    "No routed skills are available for this caller context."
)
NO_ROUTED_PROFILE_MESSAGE = "no local routed skills context is available for this caller context"


def _format_routed_skill_cards(skills: list) -> str:
    return "\n\n".join(
        "\n".join(
            [
                skill.name,
                f"- source: {skill.source}",
                f"- path: {skill.path}",
                f"- description: {skill.description}",
            ]
        )
        for skill in skills
    )


def _add_project_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--project",
        nargs="?",
        type=Path,
        const=Path("."),
        default=None,
        help="Optional caller project root override for routing. When passed without a path, use current `pwd`.",
    )


def _cmd_skills_list(args: argparse.Namespace) -> int:
    _, skills = list_routed_skills(Path.cwd(), project=args.project)

    if args.json:
        print(
            json.dumps(
                [
                    {
                        "name": skill.name,
                        "description": skill.description,
                        "source": skill.source,
                        "path": str(skill.path),
                    }
                    for skill in skills
                ]
            )
        )
        return 0

    if not skills:
        print(NO_ROUTED_SKILLS_MESSAGE)
        return 0

    print(_format_routed_skill_cards(skills))
    return 0


def _cmd_skills_import(args: argparse.Namespace) -> int:
    result = import_routed_skills(Path.cwd(), project=args.project)

    if result.selection.profile_name is None or result.selection.depot_root is None:
        print(NO_ROUTED_SKILLS_MESSAGE)
        return 0

    print(
        "\n".join(
            [
                "Routed skills import complete",
                f"- depot: {result.selection.depot_root}",
                f"- catalog: {len(result.skills)}",
                f"- created: {len(result.sync_result.created_links)}",
                f"- updated: {len(result.sync_result.updated_links)}",
                f"- removed: {len(result.sync_result.removed_links)}",
                f"- matching: {len(result.sync_result.matching_links)}",
            ]
        )
    )
    return 0


def _cmd_skills_path(args: argparse.Namespace) -> int:
    if args.depot:
        selection = resolve_routed_skills_selection(Path.cwd(), project=args.project)
        if selection.depot_root is None:
            raise CliError(NO_ROUTED_PROFILE_MESSAGE)
        print(selection.depot_root)
        return 0

    if args.name is None:
        args._parser.print_help()
        return 0

    selection, skill = resolve_routed_skill(args.name, Path.cwd(), project=args.project)
    if skill is not None:
        print(skill.path)
        return 0
    if selection.profile_name is None:
        raise CliError(NO_ROUTED_PROFILE_MESSAGE)
    raise CliError(f"skill not found in routed skills: {args.name}")


def register_skills_commands(subparsers: argparse._SubParsersAction) -> None:
    skills_parser = subparsers.add_parser(
        "skills",
        help="Inspect the public routed skills catalog.",
    )
    skills_subparsers = skills_parser.add_subparsers(dest="skills_command")

    skills_list_parser = skills_subparsers.add_parser(
        "list",
        help="List routed skills visible to the current caller context.",
    )
    skills_list_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit routed skills as structured JSON records.",
    )
    _add_project_argument(skills_list_parser)
    skills_list_parser.set_defaults(handler=_cmd_skills_list)

    skills_import_parser = skills_subparsers.add_parser(
        "import",
        help="Materialize the routed skills catalog into the resolved local skill depot.",
    )
    _add_project_argument(skills_import_parser)
    skills_import_parser.set_defaults(handler=_cmd_skills_import)

    skills_path_parser = skills_subparsers.add_parser(
        "path",
        help="Resolve one routed skill to its local loadable path, or print the routed local depot path.",
    )
    skills_path_parser.add_argument(
        "name",
        nargs="?",
        help="Canonical routed skill name.",
    )
    skills_path_parser.add_argument(
        "--depot",
        action="store_true",
        help="Print the routed local skills depot path for the current caller context.",
    )
    _add_project_argument(skills_path_parser)
    skills_path_parser.set_defaults(handler=_cmd_skills_path)
    skills_path_parser.set_defaults(_parser=skills_path_parser)
