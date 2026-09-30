"""CLI composition for Git and commit-message Breadcrumb evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from tarav.l0._core.errors import CliError
from tarav.l1.breadcrumbs import BreadcrumbError, BreadcrumbStore
from tarav.l1.git import GitError
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
    commit.set_defaults(handler=_cmd_commit)


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
