"""Shared constants and argparse helpers for agent commands."""

from __future__ import annotations

import argparse
from pathlib import Path

from agentos._core.project import normalize_project_target
from agentos.providers import canonical_provider_families

_AGENT_PROVIDER_CHOICES = tuple(
    provider.family for provider in canonical_provider_families()
)
_AGENT_ACCOUNT_MANAGEMENT_PROVIDER_CHOICES = ("codex", "claude-code", "copilot-cli")


def _config_start_path(args: argparse.Namespace) -> Path:
    if args.project is not None:
        return normalize_project_target(args.project)
    return Path.cwd().resolve()


def _add_project_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--project",
        nargs="?",
        type=Path,
        const=Path("."),
        default=None,
        help=(
            "Config start path for project-local config discovery. Bare --project "
            "uses current pwd. Agent commands do not require an existing project."
        ),
    )


def _add_agent_run_target_args(
    parser: argparse.ArgumentParser,
    *,
    provider_help: str,
) -> None:
    parser.add_argument(
        "--provider",
        default=None,
        choices=_AGENT_PROVIDER_CHOICES,
        help=provider_help,
    )
    parser.add_argument(
        "--profile",
        default=None,
        help="Configured agent profile id.",
    )
    parser.add_argument(
        "--home",
        default=None,
        help="Provider home override for this run.",
    )
    parser.add_argument(
        "-a",
        "--account",
        default=None,
        help="Provider account/auth identity for this run.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Model override.",
    )
    _add_project_argument(parser)
    parser.add_argument(
        "--cwd",
        default=None,
        help="Working directory override for the launched agent process (default: current directory).",
    )
