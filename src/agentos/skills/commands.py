from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from agentos.utils.skills import (
    flatten_skills_root,
    list_skill_names,
    prune_broken_skill_symlinks,
    skills_dir,
)


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


def _cmd_skills_flatten(args: argparse.Namespace) -> int:
    root = args.root.expanduser().resolve() if args.root is not None else Path.cwd().resolve()
    created_links, overwritten_links, matching_skips, conflict_skips = flatten_skills_root(
        root,
        dry_run=args.dry_run,
        overwrite=args.overwrite,
    )

    if created_links or overwritten_links:
        for link_path in created_links:
            if args.dry_run:
                print(f"DRY-RUN would create: {link_path}")
            else:
                print(link_path)
        for link_path in overwritten_links:
            if args.dry_run:
                print(f"DRY-RUN would replace: {link_path}")
            else:
                print(link_path)
    else:
        if args.dry_run:
            print("No symlinks would be created.")
        else:
            print("No new symlinks created.")

    for link_path, source_path in matching_skips:
        print(
            f"info: skipping nested skill source {source_path} because destination already links to it: {link_path}"
        )

    for link_path, source_path in conflict_skips:
        print(
            f"warn: skipping nested skill source {source_path} because destination already exists and does not link to it: {link_path}",
            file=sys.stderr,
        )

    if matching_skips:
        print(f"Skipped {len(matching_skips)} existing matching symlink(s).")

    if overwritten_links:
        if args.dry_run:
            print(f"Would replace {len(overwritten_links)} conflicting symlink(s).")
        else:
            print(f"Replaced {len(overwritten_links)} conflicting symlink(s).")

    if conflict_skips:
        print(f"Skipped {len(conflict_skips)} conflicting existing path(s).")

    if args.dry_run and (created_links or overwritten_links):
        print("Dry run: no symlinks were created or replaced.")

    return 0


def _cmd_skills_prune(args: argparse.Namespace) -> int:
    root = args.root.expanduser().resolve() if args.root is not None else Path.cwd().resolve()
    pruned_links = prune_broken_skill_symlinks(root, dry_run=args.dry_run)

    if pruned_links:
        for link_path in pruned_links:
            if args.dry_run:
                print(f"DRY-RUN would remove: {link_path}")
            else:
                print(link_path)
    else:
        if args.dry_run:
            print("No broken symlinks would be removed.")
        else:
            print("No broken symlinks removed.")

    if args.dry_run and pruned_links:
        print("Dry run: no symlinks were removed.")

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

    skills_flatten_parser = skills_subparsers.add_parser(
        "flatten",
        help="Flatten nested skills into the skills root via symlinks.",
    )
    skills_flatten_parser.add_argument(
        "root",
        nargs="?",
        type=Path,
        default=None,
        help="Skills root to flatten (default: current working directory).",
    )
    skills_flatten_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show symlinks that would be created or replaced without writing changes.",
    )
    skills_flatten_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace conflicting destination symlinks instead of skipping them.",
    )
    skills_flatten_parser.set_defaults(handler=_cmd_skills_flatten)

    skills_prune_parser = skills_subparsers.add_parser(
        "prune",
        help="Delete broken symlinks under a skills root.",
    )
    skills_prune_parser.add_argument(
        "root",
        nargs="?",
        type=Path,
        default=None,
        help="Skills root to prune (default: current working directory).",
    )
    skills_prune_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show broken symlinks that would be removed without writing changes.",
    )
    skills_prune_parser.set_defaults(handler=_cmd_skills_prune)
