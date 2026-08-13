# $kw: --from Deep.Modules --from Agentos.Hook --from Agentos.Daemon --note [DC] the shared runtime composes one hook registry used for CLI submission and daemon-owned callback execution --supp ^c20260811-5u ^c20260813-26u ^c20260813-27u
from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import partial
from typing import TYPE_CHECKING

from agentos.chatlas.hook_consumers import register_chatlas_hook_callbacks
from agentos.agent.providers.claude_code.usage_hooks import (
    register_claude_usage_hook_callbacks,
)
from agentos.agent.providers.codex.usage_hooks import (
    register_codex_usage_hook_callbacks,
)
from agentos.hooks import HookRegistry, register_hook_sampling_callbacks

if TYPE_CHECKING:
    import argparse


HookRegistrar = Callable[[HookRegistry], None]


@dataclass(frozen=True, slots=True)
class AgentosRuntime:
    """One composed in-process Agentos runtime."""

    hooks: HookRegistry

    def register_commands(
        self,
        subparsers: argparse._SubParsersAction,
    ) -> None:
        """Compose the complete CLI command surface lazily.

        Keeping these imports inside the command adapter lets daemon-only
        processes construct the shared runtime without importing argparse or
        every feature command module.
        """
        from agentos.agent import register_agent_commands
        from agentos.anchory.commands import register_anchory_commands
        from agentos.bloberia.commands import register_bloberia_commands
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
        from agentos.chatlas.project_index_reconciliation import (
            project_index_coverage_check,
        )
        from agentos.daemon import register_daemon_commands
        from agentos.daemon.client import submit_hook_invocation
        from agentos.daemon.log import report_hook_delivery_failure
        from agentos.forum import register_forum_commands
        from agentos.hooks import register_hook_commands
        from agentos.index.commands import register_index_commands
        from agentos.index.poi_catalog import discover_poi_catalog
        from agentos.index.wayfinder import create_index_wayfinder
        from agentos.stdlib.mdblocks.commands import register_mdblocks_commands
        from agentos.mission import register_mission_commands
        from agentos.poi.commands import register_poi_commands
        from agentos.poi.adapters.bloberia import build_bloberia_linter_report
        from agentos.poi.adapters.mdblocks import build_mdblocks_linter_report
        from agentos.poi.adapters.wayfinder import (
            build_wayfinder_registry_linter_report,
        )
        from agentos.stdlib.prefix.commands import register_prefix_commands
        from agentos.project import register_project_commands
        from agentos.stdlib.refs import register_refs_commands
        from agentos.surfaces.commands import register_surface_commands
        from agentos.skills import register_skills_commands
        from agentos.skillware.commands import register_skillware_commands
        from agentos.system import register_system_commands
        from agentos.tournament.commands import register_tournament_commands
        from agentos.stdlib.utils import register_utils_commands
        from agentos.wayfinder.commands import register_wayfinder_commands
        from agentos.workspaces.commands import register_workspace_commands

        wayfinder = create_index_wayfinder()
        poi_catalog = discover_poi_catalog()

        register_agent_commands(subparsers)
        register_hook_commands(
            subparsers,
            submitter=submit_hook_invocation,
            delivery_failure_reporter=report_hook_delivery_failure,
        )
        register_daemon_commands(subparsers, registry=self.hooks)
        register_anchory_commands(
            subparsers,
            amend_validator=validate_chatlas_anchory_amendment,
        )
        register_bloberia_commands(
            subparsers,
            check_report_builder=lambda result, depot: build_bloberia_linter_report(
                result,
                depot=depot,
                wayfinder=wayfinder,
            ),
        )
        register_canvas_commands(subparsers)
        register_project_commands(subparsers)
        register_system_commands(subparsers)
        register_forum_commands(subparsers)
        register_chatlas_commands(subparsers)
        register_surface_commands(subparsers)
        _register_future_commands(subparsers)
        _register_stdlib_commands(
            subparsers,
            registrars=(
                partial(
                    register_mdblocks_commands,
                    lint_report_builder=lambda payload: build_mdblocks_linter_report(
                        payload,
                        wayfinder=wayfinder,
                    ),
                ),
                register_prefix_commands,
                register_refs_commands,
                register_utils_commands,
            ),
        )
        register_skills_commands(subparsers)
        register_wayfinder_commands(
            subparsers,
            wayfinder=wayfinder,
            check_report_builder=lambda result, registry_path: (
                build_wayfinder_registry_linter_report(
                    result,
                    registry_path=registry_path,
                    wayfinder=wayfinder,
                )
            ),
        )
        register_tournament_commands(subparsers)
        register_workspace_commands(subparsers)
        register_poi_commands(
            subparsers,
            catalog=poi_catalog,
            wayfinder=wayfinder,
        )
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
            line_manifest_relationship_projector_factory=(
                create_chatlas_line_relationship_projector
            ),
            line_manifest_materializer=materialize_index_line_manifest,
            poi_catalog=poi_catalog,
        )
        register_mission_commands(subparsers)


CommandRegistrar = Callable[["argparse._SubParsersAction"], None]


def _register_stdlib_commands(
    subparsers: argparse._SubParsersAction,
    *,
    registrars: Sequence[CommandRegistrar],
) -> None:
    stdlib_parser = subparsers.add_parser(
        "stdlib",
        help="Standard-library primitives used by higher-level Agentos surfaces.",
    )
    stdlib_subparsers = stdlib_parser.add_subparsers(
        dest="stdlib_command",
        required=True,
    )
    for registrar in registrars:
        registrar(stdlib_subparsers)


def _register_future_commands(subparsers: argparse._SubParsersAction) -> None:
    future_parser = subparsers.add_parser(
        "future",
        help="Emerging Agentos surfaces that are not common-use yet.",
    )
    future_parser.add_subparsers(
        dest="future_command",
        required=True,
    )


def create_runtime(
    *,
    hook_registrars: Sequence[HookRegistrar] = (),
) -> AgentosRuntime:
    registry = HookRegistry()
    register_hook_sampling_callbacks(registry)
    register_claude_usage_hook_callbacks(registry)
    register_codex_usage_hook_callbacks(registry)
    register_chatlas_hook_callbacks(registry)
    for registrar in hook_registrars:
        registrar(registry)
    return AgentosRuntime(hooks=registry)


__all__ = ["AgentosRuntime", "HookRegistrar", "create_runtime"]
