from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


def resolve_project_root() -> Path:
    """Resolve project root with env override for non-standard layouts."""
    env_root = os.getenv("AGENTOS_PROJECT_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve()
    return Path(__file__).resolve().parents[3]


def skills_dir() -> Path:
    return resolve_project_root() / "skills"


def list_skill_names() -> list[str]:
    root = skills_dir()
    if not root.exists():
        return []
    names: list[str] = []
    for child in root.iterdir():
        if child.is_dir() and not child.name.startswith("."):
            names.append(child.name)
    return sorted(names)


def _cmd_skills_list(args: argparse.Namespace) -> int:
    names = list_skill_names()
    if args.json:
        print(json.dumps(names))
        return 0

    if not names:
        print("No skills found.")
        return 0

    for name in names:
        print(name)
    return 0


def _cmd_skills_path(args: argparse.Namespace) -> int:
    root = skills_dir()
    if args.name:
        print(root / args.name)
    else:
        print(root)
    return 0


def register_skills_commands(subparsers: argparse._SubParsersAction) -> None:
    skills_parser = subparsers.add_parser(
        "skills",
        help="Inspect the local bundled skills directory.",
    )
    skills_subparsers = skills_parser.add_subparsers(dest="skills_command")

    skills_list_parser = skills_subparsers.add_parser(
        "list",
        help="List skills from the local skills directory.",
    )
    skills_list_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit list as a JSON array.",
    )
    skills_list_parser.set_defaults(handler=_cmd_skills_list)

    skills_path_parser = skills_subparsers.add_parser(
        "path",
        help="Print full path to skills root or a specific skill.",
    )
    skills_path_parser.add_argument(
        "name",
        nargs="?",
        help="Optional skill name.",
    )
    skills_path_parser.set_defaults(handler=_cmd_skills_path)
