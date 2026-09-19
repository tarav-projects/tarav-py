# $kw: --from Deep.Modules --from Agentos.Hook --from Agentos.Daemon --note [DC] the shared runtime composes one hook registry used for CLI submission and daemon-owned callback execution --supp ^c20260811-5u ^c20260813-26u ^c20260813-27u
from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING
import json

from tarav.harness import DirectoryRecord, FileRecord, TaravRecord, TypeRegistry
from tarav.references.workflow import ReferenceWorkflow
from tarav.harness.workflows import Workflow, WorkflowRegistry
from tarav.navigation import FilesystemProvider, Navigation

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
    workflows: WorkflowRegistry
    navigation: Navigation

    @property
    def references(self) -> ReferenceWorkflow:
        return self.workflows.workflows["references"]

    @property
    def records(self) -> TypeRegistry[TaravRecord]:
        return self.workflows.records

    @property
    def source_root(self) -> Path:
        return Path(__file__).parent

    def load(self, path: str | Path) -> TaravRecord:
        return self.records.load(path)

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
        from tarav.archive.commands import register_archive_commands
        from tarav.bloberia.commands import register_bloberia_commands
        from tarav.chatlas import register_chatlas_commands
        from tarav.daemon import register_daemon_commands
        from tarav.daemon.client import submit_hook_invocation
        from tarav.daemon.log import report_hook_delivery_failure
        from tarav.forum import register_forum_commands
        from tarav.hooks import register_hook_commands
        from tarav.diagram.commands import register_diagram_commands
        from tarav.stdlib.mdblocks.commands import register_mdblocks_commands
        from tarav.stdlib.prefix.commands import register_prefix_commands
        from tarav.project import register_project_commands
        from tarav.python_env import register_python_commands
        from tarav.reading_club.commands import register_reading_club_commands
        from tarav.scoring.commands import register_scoring_commands
        from tarav.stdlib.refs import register_refs_commands
        from tarav.skills import register_skills_commands
        from tarav.skw.commands import register_skw_commands
        from tarav.system import register_system_commands
        from tarav.stdlib.utils import register_utils_commands
        from tarav.workspaces.commands import register_workspace_commands

        register_agent_commands(subparsers)
        register_daemon_commands(
            subparsers,
            registry=self.hooks,
            hook_registrar=partial(
                register_hook_commands,
                submitter=submit_hook_invocation,
                delivery_failure_reporter=report_hook_delivery_failure,
            ),
        )
        register_archive_commands(subparsers)
        register_diagram_commands(subparsers)
        register_bloberia_commands(subparsers)
        register_project_commands(
            subparsers,
            skills_registrar=register_skills_commands,
        )
        register_reading_club_commands(subparsers)
        register_system_commands(subparsers)
        register_python_commands(subparsers)
        register_forum_commands(subparsers)
        register_chatlas_commands(subparsers)
        _register_stdlib_commands(
            subparsers,
            registrars=(
                register_mdblocks_commands,
                register_prefix_commands,
                register_refs_commands,
                register_utils_commands,
            ),
        )
        register_scoring_commands(subparsers)
        register_workspace_commands(subparsers)
        register_skw_commands(subparsers, registry=self.records)


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
    workflows: Sequence[Workflow] = (),
    config: Path | None = None,
) -> TaravRuntime:
    """Compose library capabilities. Configuration is explicit trusted input.

    The optional JSON config contains `workflow_files` (Python source paths)
    and `providers` ({name, workflow, root}). Paths are relative to that file.
    `filesystem` providers browse plain local Record collections.
    """
    from tarav.archive.workflow import ArchiveWorkflow
    from tarav.diagram.workflow import DiagramWorkflow
    from tarav.skw.document import SkillwareWorkflow
    from tarav.skw.skills import SkillsWorkflow
    from tarav.chatlas.references import ChatlasTurnReference

    registrations = WorkflowRegistry(
        TypeRegistry(
            TaravRecord,
            (
                FileRecord,
                DirectoryRecord,
                ChatlasTurnReference,
            ),
        )
    )
    navigation = Navigation()
    references = ReferenceWorkflow(registrations.records)
    for workflow in (
        references,
        ArchiveWorkflow(),
        DiagramWorkflow(),
        SkillwareWorkflow(),
        SkillsWorkflow(),
        navigation,
        *workflows,
    ):
        registrations.register(workflow)
    if config is not None:
        config = config.expanduser().resolve()
        settings = json.loads(config.read_text(encoding="utf-8"))
        for source in settings.get("workflow_files", []):
            registrations.load(config.parent / source)
        for entry in settings.get("providers", []):
            root = config.parent / entry["root"]
            owner = entry["workflow"]
            provider = (
                FilesystemProvider(root, registrations.records)
                if owner == "filesystem"
                else registrations.workflows[owner].provider(
                    root, registrations.records
                )
            )
            navigation.mount(entry["name"], provider)
    registry = HookRegistry()
    register_hook_sampling_callbacks(registry)
    register_claude_usage_hook_callbacks(registry)
    register_codex_usage_hook_callbacks(registry)
    register_chatlas_hook_callbacks(registry)
    for registrar in hook_registrars:
        registrar(registry)
    return TaravRuntime(hooks=registry, workflows=registrations, navigation=navigation)


__all__ = ["TaravRuntime", "HookRegistrar", "create_runtime"]
