"""CLI composition for Git and commit-message Breadcrumb evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from tarav.l0._core.errors import CliError
from tarav.l1.breadcrumbs import BreadcrumbError, BreadcrumbStore
from tarav.l1.git import GitError
from tarav.l1.git.change import find
from tarav.l1.git.hooks import install, run_hook
from tarav.l0.project import require_agentos_project
from tarav.l1.usage import describe_file
from tarav.l2.breadcrumb_workflows.chatlas_context import (
    ChatlasContextBreadcrumbWorkflow,
    ChatlasContextRequest,
)
from tarav.l2.git.breadcrumbs import (
    CommitManifest,
    CommitObservationError,
    commit_from_manifest,
    register_commit,
)


def _cmd_commit(args: argparse.Namespace) -> int:
    try:
        manifest = CommitManifest.load(args.manifest)
        result = commit_from_manifest(
            manifest,
            store=BreadcrumbStore(args.breadcrumbs_root),
            workflow=ChatlasContextBreadcrumbWorkflow(),
            request=ChatlasContextRequest(
                chatlas_root=(
                    Path(args.chatlas_root).expanduser()
                    if args.chatlas_root
                    else None
                )
            ),
        )
    except CommitObservationError as exc:
        raise CliError(str(exc)) from exc
    except (BreadcrumbError, GitError, OSError, TypeError, ValueError) as exc:
        raise CliError(str(exc)) from exc
    return _print_result(args, result.to_json())


def _cmd_register_commit(args: argparse.Namespace) -> int:
    try:
        result = register_commit(
            args.repo,
            args.commit,
            store=BreadcrumbStore(args.breadcrumbs_root),
        )
    except (BreadcrumbError, GitError, OSError, TypeError, ValueError) as exc:
        raise CliError(str(exc)) from exc
    return _print_result(args, result.to_json())


def _cmd_hook(args: argparse.Namespace) -> int:
    return run_hook(args.name, args.arg)


def _cmd_hooks_install(args: argparse.Namespace) -> int:
    root = require_agentos_project(args.project.expanduser().resolve()).root.resolve()
    config = install(root, add=args.handlers)
    if args.json:
        print(json.dumps({"project": str(root), **config.model_dump(mode="json")}, indent=2))
    else:
        print(f"project: {root}")
        print(f"handlers: {', '.join(config.handlers) or 'none'}")
    return 0


def _cmd_change_find(args: argparse.Namespace) -> int:
    try:
        commits = find(Path(args.repo).expanduser().resolve(), args.id)
    except (GitError, ValueError) as exc:
        raise CliError(str(exc)) from exc
    if args.json:
        print(json.dumps({"change": args.id, "commits": list(commits)}, indent=2))
    else:
        print("\n".join(commits) if commits else f"No commit carries {args.id}")
    return 0 if commits else 1


def _print_result(args: argparse.Namespace, payload: dict[str, object]) -> int:
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"commit: {payload['commit']}")
        print(f"repository: {payload['repository']}")
        print(f"breadcrumbs: {len(payload['breadcrumbs'])}")
    return 0


def register_commands(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "git",
        help="Operate on explicitly selected Git repositories.",
    )
    commands = parser.add_subparsers(dest="git_command", required=True)
    commit = commands.add_parser(
        "commit",
        help="Create one manifest-scoped commit and register its evidence.",
    )
    commit.add_argument("--manifest", required=True)
    commit.add_argument("--breadcrumbs-root")
    commit.add_argument("--chatlas-root")
    commit.add_argument("--json", action="store_true")
    # tarav.breadcrumb 9d973eb5b27555e0e72c43dde98eb9b43fb05668dec701dac6a9f54d4f162f22
    commit.set_defaults(
        handler=_cmd_commit,
        usage_descriptor=lambda args: {"manifest": describe_file(args.manifest)},
    )


    hook = commands.add_parser(
        "hook",
        help="Run the Project's Tarav handlers for one Git hook; the installed scripts call it.",
    )
    hook.add_argument("--name", required=True, help="The Git hook, such as commit-msg.")
    hook.add_argument("--arg", action="append", default=[],
                      help="One argument Git gave the hook, in order; repeat for each.")
    hook.set_defaults(handler=_cmd_hook)
    hooks = commands.add_parser("hooks", help="Manage the Git hooks of a Project.")
    hooks_commands = hooks.add_subparsers(dest="git_hooks_command", required=True)
    hooks_install = hooks_commands.add_parser(
        "install",
        help="Make the Project's repository run the hooks its config selects.",
    )
    hooks_install.add_argument(
        "--project", type=Path, nargs="?", const=Path("."), required=True,
        help="Search this directory and parents for a Project; optionally start at PATH.",
    )
    hooks_install.add_argument("--handler", dest="handlers", action="append", default=[],
                               help="Add this handler to the Project's config first; repeatable.")
    hooks_install.add_argument("--json", action="store_true")
    hooks_install.set_defaults(handler=_cmd_hooks_install)
    change = commands.add_parser("change", help="Find commits by their tarav-change.")
    change_commands = change.add_subparsers(dest="git_change_command", required=True)
    change_find = change_commands.add_parser(
        "find", help="The commits on any branch that gained this tarav-change, oldest first.")
    change_find.add_argument("--id", required=True, help="The tarav-change, a lowercase UUID.")
    change_find.add_argument("--repo", default=".", help="A folder in the repository.")
    change_find.add_argument("--json", action="store_true")
    change_find.set_defaults(handler=_cmd_change_find)


def register_breadcrumb_git_commands(
    subparsers: argparse._SubParsersAction,
) -> None:
    parser = subparsers.add_parser(
        "register-commit",
        help="Recover Breadcrumb evidence registration from one Git commit.",
    )
    parser.add_argument("--repo", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--breadcrumbs-root")
    parser.add_argument("--json", action="store_true")
    parser.set_defaults(handler=_cmd_register_commit)


__all__ = ["register_breadcrumb_git_commands", "register_commands"]
