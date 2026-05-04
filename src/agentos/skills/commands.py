from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from agentos._core.errors import CliError
from agentos._core.project import require_explicit_agentos_project
from agentos._core.project_command_log import command_payload_from_args, record_project_command
from agentos.skills.routing import (
    SKILLS_IMPORT_MODE_DEPOT_LINKING,
    SKILLS_IMPORT_MODES,
    import_selected_skills,
    list_selected_skills,
    resolve_selected_skill,
    resolve_skills_selection,
    selected_skills_status,
)

NO_IMPORTED_SKILLS_MESSAGE = "No skills are selected for import into this project target."
NO_SKILLS_DEPOTS_MESSAGE = "no skills depots are configured for this project target"


def _format_selected_skill_list(skills: list) -> str:
    return "\n".join(f"{skill.name} ({skill.source})" for skill in skills)


def _serialize_status_entry(entry) -> dict[str, str | None]:
    return {
        "name": entry.name,
        "path": str(entry.path),
        "source": entry.source,
        "expected_source_path": (
            str(entry.expected_source_path) if entry.expected_source_path is not None else None
        ),
        "actual_entry_kind": entry.actual_entry_kind,
        "actual_link_target": entry.actual_link_target,
        "actual_resolved_target": (
            str(entry.actual_resolved_target) if entry.actual_resolved_target is not None else None
        ),
    }


def _serialize_skill_record(skill) -> dict[str, object]:
    return {
        "name": skill.name,
        "description": skill.description,
        "source": skill.source,
        "paths": [str(path) for path in skill.paths],
    }


def _format_status_entries(title: str, lines: list[str]) -> str:
    if not lines:
        return ""
    return "\n".join([title, *lines])


def _format_depot_status(depot_status) -> str:
    issue_count = (
        len(depot_status.missing)
        + len(depot_status.broken)
        + len(depot_status.unsynced)
        + len(depot_status.conflicts)
        + len(depot_status.extra)
    )
    overall_state = "clean" if issue_count == 0 else "issues found"

    lines = [
        f"Depot: {depot_status.depot_root}",
        f"- state: {overall_state}",
        f"- matching: {len(depot_status.matching)}",
        f"- missing: {len(depot_status.missing)}",
        f"- broken: {len(depot_status.broken)}",
        f"- unsynced: {len(depot_status.unsynced)}",
        f"- conflicts: {len(depot_status.conflicts)}",
        f"- extra: {len(depot_status.extra)}",
    ]

    sections = [
        _format_status_entries(
            "Depot symlinks:",
            [
                f"- {entry.name} ({entry.source}) -> {entry.actual_resolved_target}"
                for entry in depot_status.matching
            ],
        ),
        _format_status_entries(
            "Missing symlinks:",
            [
                f"- {entry.name} ({entry.source}) expected {entry.expected_source_path}"
                for entry in depot_status.missing
            ],
        ),
        _format_status_entries(
            "Broken symlinks:",
            [
                f"- {entry.name} -> {entry.actual_link_target}"
                for entry in depot_status.broken
            ],
        ),
        _format_status_entries(
            "Unsynced symlinks:",
            [
                (
                    f"- {entry.name} expected {entry.expected_source_path} "
                    f"actual {entry.actual_resolved_target}"
                )
                for entry in depot_status.unsynced
            ],
        ),
        _format_status_entries(
            "Conflicting entries:",
            [
                f"- {entry.name} at {entry.path} is a {entry.actual_entry_kind}"
                for entry in depot_status.conflicts
            ],
        ),
        _format_status_entries(
            "Extra entries:",
            [
                (
                    f"- {entry.name} ({entry.actual_entry_kind})"
                    if entry.actual_entry_kind != "symlink"
                    else f"- {entry.name} -> {entry.actual_resolved_target}"
                )
                for entry in depot_status.extra
            ],
        ),
    ]

    return "\n\n".join([lines[0], "\n".join(lines[1:]), *[section for section in sections if section]])


def _format_selected_skills_status(status) -> str:
    lines = [
        "Skills status",
        f"- profile: {status.selection.profile_name}",
        f"- expected: {len(status.skills)}",
        f"- depots: {len(status.depot_statuses)}",
    ]
    depot_sections = [_format_depot_status(depot_status) for depot_status in status.depot_statuses]
    return "\n\n".join([lines[0], "\n".join(lines[1:]), *depot_sections])


def _format_selected_skills_import(result, *, force: bool) -> str:
    lines = [
        "Skills import complete",
        f"- mode: {result.mode}",
        f"- sync: {'force' if force else 'sync'}",
        f"- profile: {result.selection.profile_name}",
        f"- catalog: {len(result.skills)}",
        f"- depots: {len(result.depot_results)}",
    ]
    if result.global_depot_root is not None:
        lines.append(f"- global depot: {result.global_depot_root}")
    depot_sections = [
        "\n".join(
            [
                f"Depot: {depot_result.depot_root}",
                f"- created: {len(depot_result.sync_result.created_links)}",
                f"- updated: {len(depot_result.sync_result.updated_links)}",
                f"- removed: {len(depot_result.sync_result.removed_links)}",
                f"- matching: {len(depot_result.sync_result.matching_links)}",
            ]
        )
        for depot_result in result.depot_results
    ]
    return "\n\n".join([lines[0], "\n".join(lines[1:]), *depot_sections])


def _add_project_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--project",
        nargs="?",
        type=Path,
        const=Path("."),
        default=None,
        help="Required project target. Bare --project targets current pwd. Skills commands require an existing project.",
    )
    parser.add_argument(
        "--project-name",
        default=None,
        help="Assert the resolved project name after resolving --project.",
    )


def _emit_selection_warnings(selection) -> None:
    for warning in selection.warnings:
        print(f"warning: {warning}", file=sys.stderr)


def _record_skills_project_command(args: argparse.Namespace) -> None:
    project = require_explicit_agentos_project(
        project=args.project,
        project_name=args.project_name,
        command_name="agentos skills",
    )
    record_project_command(
        project=project,
        agentos_command=command_payload_from_args(args),
    )


def _cmd_skills_list(args: argparse.Namespace) -> int:
    _record_skills_project_command(args)
    selection, skills = list_selected_skills(Path.cwd(), project=args.project)
    _emit_selection_warnings(selection)

    if args.json:
        print(
            json.dumps(
                [_serialize_skill_record(skill) for skill in skills]
            )
        )
        return 0

    if not skills:
        print(NO_IMPORTED_SKILLS_MESSAGE)
        return 0

    print(_format_selected_skill_list(skills))
    return 0


def _cmd_skills_import(args: argparse.Namespace) -> int:
    _record_skills_project_command(args)
    result = import_selected_skills(
        Path.cwd(),
        project=args.project,
        force=args.force,
        mode=args.mode,
    )
    _emit_selection_warnings(result.selection)

    if result.selection.profile_name is None or not result.selection.depot_roots:
        print(NO_IMPORTED_SKILLS_MESSAGE)
        return 0

    print(_format_selected_skills_import(result, force=args.force))
    return 0


def _cmd_skills_status(args: argparse.Namespace) -> int:
    _record_skills_project_command(args)
    status = selected_skills_status(Path.cwd(), project=args.project)
    _emit_selection_warnings(status.selection)

    if args.json:
        print(
            json.dumps(
                {
                    "profile": status.selection.profile_name,
                    "expected": len(status.skills),
                    "depots": [
                        {
                            "depot": str(depot_status.depot_root),
                            "matching": [_serialize_status_entry(entry) for entry in depot_status.matching],
                            "missing": [_serialize_status_entry(entry) for entry in depot_status.missing],
                            "broken": [_serialize_status_entry(entry) for entry in depot_status.broken],
                            "unsynced": [_serialize_status_entry(entry) for entry in depot_status.unsynced],
                            "conflicts": [_serialize_status_entry(entry) for entry in depot_status.conflicts],
                            "extra": [_serialize_status_entry(entry) for entry in depot_status.extra],
                        }
                        for depot_status in status.depot_statuses
                    ],
                }
            )
        )
        return 0

    if not status.selection.depot_roots:
        print(NO_IMPORTED_SKILLS_MESSAGE)
        return 0

    print(_format_selected_skills_status(status))
    return 0


def _cmd_skills_path(args: argparse.Namespace) -> int:
    if args.depot:
        _record_skills_project_command(args)
        selection = resolve_skills_selection(Path.cwd(), project=args.project)
        _emit_selection_warnings(selection)
        if not selection.depot_roots:
            raise CliError(NO_SKILLS_DEPOTS_MESSAGE)
        print("\n".join(str(depot_root) for depot_root in selection.depot_roots))
        return 0

    if args.name is None:
        args._parser.print_help()
        return 0

    _record_skills_project_command(args)
    selection, skill = resolve_selected_skill(args.name, Path.cwd(), project=args.project)
    _emit_selection_warnings(selection)
    if skill is not None:
        print("\n".join(str(path) for path in skill.paths))
        return 0
    if selection.profile_name is None:
        raise CliError(NO_SKILLS_DEPOTS_MESSAGE)
    raise CliError(f"skill not found in imported skills: {args.name}")


def register_skills_commands(subparsers: argparse._SubParsersAction) -> None:
    skills_parser = subparsers.add_parser(
        "skills",
        help="Manage project-local imported skills for an existing Agentos project.",
        description=(
            "Preview the selected skills catalog for the current project, import it "
            "into local depots, and inspect depot state."
        ),
    )
    skills_subparsers = skills_parser.add_subparsers(dest="skills_command")

    skills_list_parser = skills_subparsers.add_parser(
        "list",
        help="List skills selected for import into the resolved project target.",
        description=(
            "Preview the skills selected for import into the resolved project target. "
            "This command is config-derived and does not sync depots."
        ),
    )
    skills_list_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit name, description, source, and projected local paths as JSON.",
    )
    _add_project_argument(skills_list_parser)
    skills_list_parser.set_defaults(handler=_cmd_skills_list)

    skills_import_parser = skills_subparsers.add_parser(
        "import",
        help="Sync the selected skills into the depots configured for the resolved existing project.",
        description=(
            "Import the selected skills into every configured depot for the resolved "
            "existing project."
        ),
    )
    skills_import_parser.add_argument(
        "--force",
        action="store_true",
        help=(
            "Delete existing symlinks in every resolved depot, then recreate the "
            "imported symlink set. Conflicting non-symlink entries still error."
        ),
    )
    skills_import_parser.add_argument(
        "--mode",
        choices=SKILLS_IMPORT_MODES,
        default=SKILLS_IMPORT_MODE_DEPOT_LINKING,
        help=(
            "Import materialization mode. depot-linking links project depots to a "
            "shared global depot; flat-linking writes per-skill links directly in "
            f"each project depot. Default: {SKILLS_IMPORT_MODE_DEPOT_LINKING}."
        ),
    )
    _add_project_argument(skills_import_parser)
    skills_import_parser.set_defaults(handler=_cmd_skills_import)

    skills_status_parser = skills_subparsers.add_parser(
        "status",
        help="Analyze the imported skills depots for the resolved existing project.",
        description=(
            "Compare every configured depot against the selected skills catalog "
            "without syncing it."
        ),
    )
    skills_status_parser.add_argument(
        "--json",
        action="store_true",
        help=(
            "Emit per-depot matching, missing, broken, unsynced, conflicting, "
            "and extra entries as JSON."
        ),
    )
    _add_project_argument(skills_status_parser)
    skills_status_parser.set_defaults(handler=_cmd_skills_status)

    skills_path_parser = skills_subparsers.add_parser(
        "path",
        help="Resolve one imported skill to its loadable project-local paths, or print the configured depot paths.",
        description=(
            "Print the local load paths for one selected skill, or print the "
            "configured depot roots with --depot. Paths are predictive until "
            "import syncs the depots."
        ),
    )
    skills_path_parser.add_argument(
        "name",
        nargs="?",
        help="Canonical selected skill name.",
    )
    skills_path_parser.add_argument(
        "--depot",
        action="store_true",
        help="Print the configured local depot roots instead of a skill path.",
    )
    _add_project_argument(skills_path_parser)
    skills_path_parser.set_defaults(handler=_cmd_skills_path)
    skills_path_parser.set_defaults(_parser=skills_path_parser)
