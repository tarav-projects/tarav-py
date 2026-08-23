# $kw: --from Deep.Modules --from Agentos.Hook --from Agentos.Daemon --note [DC] the shared runtime composes one hook registry used for CLI submission and daemon-owned callback execution --supp ^c20260811-5u ^c20260813-26u ^c20260813-27u
from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING

from tarav.chatlas.hook_consumers import register_chatlas_hook_callbacks
from tarav.agent.providers.claude_code.usage_hooks import (
    register_claude_usage_hook_callbacks,
)
from tarav.agent.providers.codex.usage_hooks import (
    register_codex_usage_hook_callbacks,
)
from tarav.hooks import HookRegistry, register_hook_sampling_callbacks

if TYPE_CHECKING:
    import argparse


HookRegistrar = Callable[[HookRegistry], None]


@dataclass(frozen=True, slots=True)
class TaravRuntime:
    """One composed in-process Tarav runtime."""

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
        from tarav.agent import register_agent_commands
        from tarav.anchory.commands import register_anchory_commands
        from tarav.bloberia.commands import register_bloberia_commands
        from tarav.canvas import register_canvas_commands
        from tarav.chatlas import register_chatlas_commands
        from tarav.chatlas.anchory import (
            resolve_event_support_set_record,
            validate_chatlas_anchory_amendment,
        )
        from tarav.daemon import register_daemon_commands
        from tarav.daemon.client import submit_hook_invocation
        from tarav.daemon.log import report_hook_delivery_failure
        from tarav.forum import register_forum_commands
        from tarav.hooks import register_hook_commands
        from tarav.indexlab.commands import register_indexlab_commands
        from tarav.skillware._build_core import find_project_root
        from tarav.skillware.managed_blocks import create_tarav_wayfinder
        from tarav.skillware.related_surfaces import RelatedSurfaceResolver
        from tarav.stdlib.mdblocks.commands import register_mdblocks_commands
        from tarav.mission import register_mission_commands
        from tarav.poi.commands import register_poi_commands
        from tarav.poi.adapters.bloberia import build_bloberia_linter_report
        from tarav.poi.adapters.mdblocks import build_mdblocks_linter_report
        from tarav.poi.adapters.wayfinder import (
            build_wayfinder_registry_linter_report,
        )
        from tarav.stdlib.prefix.commands import register_prefix_commands
        from tarav.project import register_project_commands
        from tarav.stdlib.refs import register_refs_commands
        from tarav.surfaces.commands import register_surface_commands
        from tarav.skills import register_skills_commands
        from tarav.skillware.commands import register_skillware_commands
        from tarav.system import register_system_commands
        from tarav.tournament.commands import register_tournament_commands
        from tarav.stdlib.utils import register_utils_commands
        from tarav.wayfinder.commands import register_wayfinder_commands
        from tarav.workspaces.commands import register_workspace_commands

        project_root = find_project_root(Path(__file__))
        wayfinder = create_tarav_wayfinder(project_root=project_root)

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
            wayfinder=wayfinder,
            related_resolver=RelatedSurfaceResolver(wayfinder),
        )
        register_skillware_commands(
            subparsers,
            edition_history_support_resolver=resolve_event_support_set_record,
        )
        register_indexlab_commands(subparsers)
        register_mission_commands(subparsers)


CommandRegistrar = Callable[["argparse._SubParsersAction"], None]


def _register_stdlib_commands(
    subparsers: argparse._SubParsersAction,
    *,
    registrars: Sequence[CommandRegistrar],
) -> None:
    stdlib_parser = subparsers.add_parser(
        "stdlib",
        help="Standard-library primitives used by higher-level Tarav surfaces.",
    )
    stdlib_subparsers = stdlib_parser.add_subparsers(
        dest="stdlib_command",
        required=True,
    )
    for registrar in registrars:
        registrar(stdlib_subparsers)


def create_runtime(
    *,
    hook_registrars: Sequence[HookRegistrar] = (),
) -> TaravRuntime:
    registry = HookRegistry()
    register_hook_sampling_callbacks(registry)
    register_claude_usage_hook_callbacks(registry)
    register_codex_usage_hook_callbacks(registry)
    register_chatlas_hook_callbacks(registry)
    for registrar in hook_registrars:
        registrar(registry)
    return TaravRuntime(hooks=registry)


__all__ = ["TaravRuntime", "HookRegistrar", "create_runtime"]
