from __future__ import annotations

import argparse
import json
from pathlib import Path

from agentos.utils.skills import (
    list_target_skill_names,
    prune_skills_target,
    require_skills_project_root,
    resolve_project_skills_dir,
    sync_skills_target,
)


def _resolve_project_and_target(args: argparse.Namespace) -> tuple[Path, Path]:
    project_root = require_skills_project_root(Path.cwd())
    target_dir = resolve_project_skills_dir(project_root, skills_folder=args.skills_folder)
    return (project_root, target_dir)


def _cmd_skills_list(args: argparse.Namespace) -> int:
    _, target_dir = _resolve_project_and_target(args)
    names = list_target_skill_names(target_dir)
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
    _, target_dir = _resolve_project_and_target(args)
    if args.name:
        print(target_dir / args.name)
    else:
        print(target_dir)
    return 0


def _cmd_skills_sync(args: argparse.Namespace) -> int:
    project_root, target_dir = _resolve_project_and_target(args)
    result = sync_skills_target(project_root, target_dir, dry_run=args.dry_run)

    if result.created_links or result.updated_links or result.removed_links:
        for link_path in result.created_links:
            if args.dry_run:
                print(f"DRY-RUN would create: {link_path}")
            else:
                print(f"created: {link_path}")
        for link_path in result.updated_links:
            if args.dry_run:
                print(f"DRY-RUN would update: {link_path}")
            else:
                print(f"updated: {link_path}")
        for link_path in result.removed_links:
            if args.dry_run:
                print(f"DRY-RUN would remove stale link: {link_path}")
            else:
                print(f"removed stale link: {link_path}")
    else:
        if args.dry_run:
            print("No changes would be made.")
        else:
            print("No changes.")

    if result.matching_links:
        print(f"Unchanged {len(result.matching_links)} existing matching symlink(s).")

    return 0


def _cmd_skills_prune(args: argparse.Namespace) -> int:
    project_root, target_dir = _resolve_project_and_target(args)
    pruned_links = prune_skills_target(project_root, target_dir, dry_run=args.dry_run)

    if pruned_links:
        for link_path in pruned_links:
            if args.dry_run:
                print(f"DRY-RUN would remove: {link_path}")
            else:
                print(f"removed: {link_path}")
    else:
        if args.dry_run:
            print("No broken managed symlinks would be removed.")
        else:
            print("No broken managed symlinks removed.")

    return 0


def register_skills_commands(subparsers: argparse._SubParsersAction) -> None:
    skills_parser = subparsers.add_parser(
        "skills",
        help="Manage project-local skill imports and sync targets.",
    )
    skills_subparsers = skills_parser.add_subparsers(dest="skills_command")

    skills_list_parser = skills_subparsers.add_parser(
        "list",
        help="List skills from the effective project skills folder.",
    )
    skills_list_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit list as a JSON array.",
    )
    skills_list_parser.add_argument(
        "--skills-folder",
        type=Path,
        default=None,
        help="Project-relative skills target folder override (default: skills).",
    )
    skills_list_parser.set_defaults(handler=_cmd_skills_list)

    skills_path_parser = skills_subparsers.add_parser(
        "path",
        help="Print full path to the effective project skills folder or one skill path.",
    )
    skills_path_parser.add_argument(
        "name",
        nargs="?",
        help="Optional skill name.",
    )
    skills_path_parser.add_argument(
        "--skills-folder",
        type=Path,
        default=None,
        help="Project-relative skills target folder override (default: skills).",
    )
    skills_path_parser.set_defaults(handler=_cmd_skills_path)

    skills_sync_parser = skills_subparsers.add_parser(
        "sync",
        help="Sync configured skills.imports into the effective project skills folder via symlinks.",
    )
    skills_sync_parser.add_argument(
        "--skills-folder",
        type=Path,
        default=None,
        help="Project-relative skills target folder override (default: skills).",
    )
    skills_sync_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show planned symlink changes without writing filesystem changes.",
    )
    skills_sync_parser.set_defaults(handler=_cmd_skills_sync)

    skills_prune_parser = skills_subparsers.add_parser(
        "prune",
        help="Delete broken managed symlinks from the effective project skills folder.",
    )
    skills_prune_parser.add_argument(
        "--skills-folder",
        type=Path,
        default=None,
        help="Project-relative skills target folder override (default: skills).",
    )
    skills_prune_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show broken managed symlinks that would be removed without writing changes.",
    )
    skills_prune_parser.set_defaults(handler=_cmd_skills_prune)
