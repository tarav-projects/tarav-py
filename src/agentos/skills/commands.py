from __future__ import annotations

import argparse
import json
from pathlib import Path

from agentos._core.errors import CliError
from agentos.skills.routing import list_routed_skills, resolve_routed_skill

NO_ROUTED_SKILLS_MESSAGE = (
    "No routed skills are available for this caller context.\n"
    "AGENTS: Treat this result as authoritative. Do not search for skills outside `agentos skills`."
)


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


def _cmd_skills_path(args: argparse.Namespace) -> int:
    _, skill = resolve_routed_skill(args.name, Path.cwd(), project=args.project)
    if skill is not None:
        print(skill.path)
        return 0
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
        "--project",
        type=Path,
        default=None,
        help="Optional caller project root override for routing.",
    )
    skills_list_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit routed skills as structured JSON records.",
    )
    skills_list_parser.set_defaults(handler=_cmd_skills_list)

    skills_path_parser = skills_subparsers.add_parser(
        "path",
        help="Resolve one routed skill to its loadable path.",
    )
    skills_path_parser.add_argument(
        "name",
        help="Canonical routed skill name.",
    )
    skills_path_parser.add_argument(
        "--project",
        type=Path,
        default=None,
        help="Optional caller project root override for routing.",
    )
    skills_path_parser.set_defaults(handler=_cmd_skills_path)
