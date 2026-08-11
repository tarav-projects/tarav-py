# $kw: ^agentos-cli --from Agentos.Bloberia --from Skw.Edition.History.Service --from Anchory.System --from Chatlas.Anchory --from Agentos.Hook --from Agentos.Daemon --note [DC] the umbrella CLI composes foundation command registrars with feature-owned integrations ^c20260724-31u --supp live Chatlas resolution injection authorized ^c20260725-15u --supp Anchory amendment validation authorized ^c20260730-33u --supp general hook composition authorized ^c20260811-35u --supp deferred hook dispatch authorized ^c20260811-50u
from __future__ import annotations

import argparse
import sys
from typing import Sequence

from agentos import __version__
from agentos.agent import register_agent_commands
from agentos.anchory.commands import register_anchory_commands
from agentos.bloberia.commands import register_bloberia_commands
from agentos._core.errors import CliError
from agentos.daemon import register_daemon_commands
from agentos.forum import register_forum_commands
from agentos.hooks import (
    register_hook_commands,
)
from agentos.index.commands import register_index_commands
from agentos.mdblocks.commands import register_mdblocks_commands
from agentos.mission import register_mission_commands
from agentos.poi.commands import register_poi_commands
from agentos.prefix.commands import register_prefix_commands
from agentos.project import register_project_commands
from agentos.refs import register_refs_commands
from agentos.runtime import AgentosRuntime, HookRegistrar, create_runtime
from agentos.skills import register_skills_commands
from agentos.skillware.commands import register_skillware_commands
from agentos.system import register_system_commands
from agentos.tara_tapes import register_tara_tapes_commands
from agentos.tournament.commands import register_tournament_commands
from agentos.utils import register_utils_commands
from agentos.wayfinder.commands import register_wayfinder_commands
from agentos.workspaces.commands import register_workspace_commands
from agentos.canvas import register_canvas_commands
from agentos.chatlas import register_chatlas_commands
from agentos.chatlas.anchory import (
    resolve_event_support_set_record,
    validate_chatlas_anchory_amendment,
)
from agentos.chatlas.index_checks import (
    chatlas_anchor_line_drift_check,
    chatlas_grounding_provenance_check,
    chatlas_line_approval_check,
    chatlas_line_verbatim_gate_check,
    chatlas_review_reference_resolver,
    chatlas_support_reference_resolver,
)
from agentos.chatlas.line_manifest import (
    create_chatlas_line_relationship_projector,
    materialize_index_line_manifest,
)
from agentos.chatlas.project_index_reconciliation import project_index_coverage_check


def register_stdlib_commands(subparsers: argparse._SubParsersAction) -> None:
    stdlib_parser = subparsers.add_parser(
        "stdlib",
        help="Standard-library primitives used by higher-level Agentos surfaces.",
    )
    stdlib_subparsers = stdlib_parser.add_subparsers(
        dest="stdlib_command",
        required=True,
    )
    register_mdblocks_commands(stdlib_subparsers)
    register_prefix_commands(stdlib_subparsers)
    register_refs_commands(stdlib_subparsers)
    register_utils_commands(stdlib_subparsers)


def register_future_commands(subparsers: argparse._SubParsersAction) -> None:
    future_parser = subparsers.add_parser(
        "future",
        help="Emerging Agentos surfaces that are not common-use yet.",
    )
    future_parser.add_subparsers(
        dest="future_command",
        required=True,
    )


def build_parser(
    *,
    runtime: AgentosRuntime | None = None,
    hook_registrars: Sequence[HookRegistrar] = (),
) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agentos",
        description="Core CLI primitives for agentic workflows.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    subparsers = parser.add_subparsers(dest="command")
    register_agent_commands(subparsers)
    composed = runtime or create_runtime(hook_registrars=hook_registrars)
    register_hook_commands(subparsers, registry=composed.hooks)
    register_daemon_commands(subparsers, registry=composed.hooks)
    register_anchory_commands(
        subparsers,
        amend_validator=validate_chatlas_anchory_amendment,
    )
    register_bloberia_commands(subparsers)
    register_canvas_commands(subparsers)
    register_project_commands(subparsers)
    register_system_commands(subparsers)
    register_forum_commands(subparsers)
    register_chatlas_commands(subparsers)
    register_future_commands(subparsers)
    register_tara_tapes_commands(subparsers)
    register_stdlib_commands(subparsers)
    register_skills_commands(subparsers)
    register_wayfinder_commands(subparsers)
    register_tournament_commands(subparsers)
    register_workspace_commands(subparsers)
    register_poi_commands(subparsers)
    register_skillware_commands(
        subparsers,
        edition_history_support_resolver=resolve_event_support_set_record,
    )
    register_index_commands(
        subparsers,
        extra_linter_checks=(
            chatlas_grounding_provenance_check(),
            chatlas_anchor_line_drift_check(),
            chatlas_line_approval_check(),
            chatlas_line_verbatim_gate_check(),
            project_index_coverage_check(),
        ),
        support_reference_resolver=chatlas_support_reference_resolver(),
        review_reference_resolver=chatlas_review_reference_resolver(),
        line_manifest_relationship_projector_factory=create_chatlas_line_relationship_projector,
        line_manifest_materializer=materialize_index_line_manifest,
    )
    register_mission_commands(subparsers)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    try:
        argv_list = list(argv) if argv is not None else sys.argv[1:]
        args = parser.parse_args(argv_list)
        args._agentos_argv = argv_list
        handler = getattr(args, "handler", None)
        if handler is None:
            parser.print_help()
            return 0
        return int(handler(args))
    except CliError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
