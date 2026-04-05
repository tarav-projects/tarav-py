from __future__ import annotations

import argparse
import json
from pathlib import Path

from agentos._core.errors import CliError
from agentos.utils.skills import (
    global_public_skills_depot,
    prune_global_skills_depot,
    prune_skills_target,
    resolve_skill,
    resolve_skills_command_project_root,
    resolve_project_skills_depot,
    resolve_skills_path,
    list_resolved_skills,
    sync_global_skills_depot,
    sync_skills_target,
)


def _resolve_project_and_target(args: argparse.Namespace) -> tuple[Path, Path]:
    if getattr(args, "global_depot", False) and args.skills_depot is not None:
        raise CliError("--global-depot cannot be combined with --skills-depot")
    if getattr(args, "global_depot", False):
        return (Path(), global_public_skills_depot())
    project_root = resolve_skills_command_project_root(Path.cwd())
    target_dir = resolve_project_skills_depot(project_root, skills_depot=args.skills_depot)
    return (project_root, target_dir)


def _format_skills_list_rows(skills: list) -> list[str]:
    source_labels = [f"{skill.source_kind}[{skill.resolved_from_index}]" for skill in skills]
    name_width = max(len(skill.name) for skill in skills)
    source_width = max(len(label) for label in source_labels)
    return [
        f"{skill.name.ljust(name_width)}  {source_label.ljust(source_width)}  {skill.path}"
        for skill, source_label in zip(skills, source_labels)
    ]


def _cmd_skills_list(args: argparse.Namespace) -> int:
    skills = list_resolved_skills(Path.cwd(), skills_depot=args.skills_depot)
    if args.json:
        print(
            json.dumps(
                [
                    {
                        "name": skill.name,
                        "resolved_from_index": skill.resolved_from_index,
                        "source_kind": skill.source_kind,
                        "root": str(skill.root),
                        "path": str(skill.path),
                    }
                    for skill in skills
                ]
            )
        )
        return 0

    if not skills:
        print("No skills found.")
        return 0

    for row in _format_skills_list_rows(skills):
        print(row)
    return 0


def _cmd_skills_path(args: argparse.Namespace) -> int:
    if args.name:
        skill = resolve_skill(args.name, Path.cwd(), skills_depot=args.skills_depot)
        if skill is None:
            raise CliError(f"skill not found in effective skills path: {args.name}")
        print(skill.name)
        print(f"resolved_from: PATH[{skill.resolved_from_index}]")
        print(f"source_kind: {skill.source_kind}")
        print(f"path: {skill.path}")
    else:
        for entry in resolve_skills_path(Path.cwd(), skills_depot=args.skills_depot):
            print(f"PATH[{entry.resolved_from_index}] {entry.source_kind} {entry.root}")
    return 0


def _cmd_skills_sync(args: argparse.Namespace) -> int:
    project_root, target_dir = _resolve_project_and_target(args)
    if args.global_depot:
        result = sync_global_skills_depot(target_dir, dry_run=args.dry_run)
    else:
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
    if args.global_depot:
        pruned_links = prune_global_skills_depot(target_dir, dry_run=args.dry_run)
    else:
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
        help="List effective skills from the ordered skills path with source provenance.",
    )
    skills_list_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit resolved skills as structured JSON records.",
    )
    skills_list_parser.add_argument(
        "--skills-depot",
        type=Path,
        default=None,
        help="Project-relative project skills depot override for the first PATH entry (default: project config or skills).",
    )
    skills_list_parser.set_defaults(handler=_cmd_skills_list)

    skills_path_parser = skills_subparsers.add_parser(
        "path",
        help="Print the ordered skills path, or resolve one skill through it.",
    )
    skills_path_parser.add_argument(
        "name",
        nargs="?",
        help="Optional skill name.",
    )
    skills_path_parser.add_argument(
        "--skills-depot",
        type=Path,
        default=None,
        help="Project-relative project skills depot override for the first PATH entry (default: project config or skills).",
    )
    skills_path_parser.set_defaults(handler=_cmd_skills_path)

    skills_sync_parser = skills_subparsers.add_parser(
        "sync",
        help="Sync configured skills.imports into the effective project skills depot via symlinks, falling back to the current folder when no project marker exists.",
    )
    skills_sync_parser.add_argument(
        "--skills-depot",
        type=Path,
        default=None,
        help="Project-relative project skills depot override (default: project config or current-folder skills).",
    )
    skills_sync_parser.add_argument(
        "--global-depot",
        action="store_true",
        help="Operate on the global public skills depot instead of a project depot.",
    )
    skills_sync_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show planned symlink changes without writing filesystem changes.",
    )
    skills_sync_parser.set_defaults(handler=_cmd_skills_sync)

    skills_prune_parser = skills_subparsers.add_parser(
        "prune",
        help="Delete broken managed symlinks from the effective project skills depot, falling back to the current folder when no project marker exists.",
    )
    skills_prune_parser.add_argument(
        "--skills-depot",
        type=Path,
        default=None,
        help="Project-relative project skills depot override (default: project config or current-folder skills).",
    )
    skills_prune_parser.add_argument(
        "--global-depot",
        action="store_true",
        help="Operate on the global public skills depot instead of a project depot.",
    )
    skills_prune_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show broken managed symlinks that would be removed without writing changes.",
    )
    skills_prune_parser.set_defaults(handler=_cmd_skills_prune)
