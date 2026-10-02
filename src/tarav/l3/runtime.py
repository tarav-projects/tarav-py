# $kw: --from Deep.Modules --from Agentos.Hook --from Agentos.Daemon --note [DC] the shared runtime composes one hook registry used for CLI submission and daemon-owned callback execution --supp ^c20260811-5u ^c20260813-26u ^c20260813-27u
from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from threading import Lock
from typing import TYPE_CHECKING, TypeVar, overload
import json

from tarav.l0.kernel import (
    DirectoryRecord,
    FileRecord,
    KernelWorkflow,
    TypeWorkflow,
    TARAV,
    TaravClass,
    TaravEnvironment,
    TaravObject,
    TaravSystem,
    TypeRegistry,
    entity,
)
from tarav.l1.context import (
    ContextEntry,
    ContextSubject,
    explore as open_context,
)
from tarav.l2.context.storage import (
    CONTEXT_RECORD_TYPES,
    ContextService,
    configure_current_context_service,
)
from tarav.l1.context.workflow import ContextWorkflow
from tarav.l0.kernel.space import FilesystemProvider
from tarav.l0.kernel.records import configure_workflow_resolver, configure_context_resolver
from tarav.l0.kernel.current import configure_current_records
from tarav.l0.kernel.workflows import TaravWorkflow, WorkflowRegistry
from tarav.l1.loading import LoadingProfile, profile_paths
from tarav.l1.navigation import Navigation, NavigationService
from tarav.l1.references.workflow import ReferenceWorkflow, ReferenceService
from tarav.l1.breadcrumbs.workflow import BreadcrumbService

from tarav.l1.chatlas.hook_consumers import register_chatlas_hook_callbacks
from tarav.l1.agent.providers.claude_code.usage_hooks import (
    register_claude_usage_hook_callbacks,
)
from tarav.l1.agent.providers.codex.usage_hooks import (
    register_codex_usage_hook_callbacks,
)
from tarav.l1.hooks import HookRegistry, register_hook_sampling_callbacks

if TYPE_CHECKING:
    import argparse

    from tarav.l1.breadcrumbs.integrations import BreadcrumbIntegration
    from tarav.l2.scoring.workflow import ScoringWorkflow
    from tarav.l1.blessings import BlessingStore
    from tarav.l1.poi import POICollector


HookRegistrar = Callable[[HookRegistry], None]
ObjectT = TypeVar("ObjectT", bound=TaravObject)


@dataclass(frozen=True, slots=True)
class TaravRuntime:
    """One composed in-process Tarav runtime."""

    hooks: HookRegistry
    system: TaravSystem
    workflows: WorkflowRegistry
    records: TypeRegistry[TaravObject]
    environment: TaravEnvironment
    contexts: ContextService
    navigation: NavigationService
    references: ReferenceService
    breadcrumbs: BreadcrumbService
    breadcrumb_integrations: tuple[BreadcrumbIntegration, ...]
    pois: POICollector
    blessings: BlessingStore

    @property
    def scoring(self) -> type[ScoringWorkflow]:
        return self.workflows.get("scoring")

    @property
    def source_root(self) -> Path:
        return Path(__file__).parent.parent

    @overload
    def load_object(
        self, path: str | Path, *, profile: type[LoadingProfile] | None = None,
        expected_type: type[ObjectT]
    ) -> ObjectT: ...

    @overload
    def load_object(
        self, path: str | Path, *, profile: type[LoadingProfile] | None = None,
        expected_type: None = None
    ) -> TaravObject: ...

    def load_object(
        self,
        path: str | Path,
        *,
        profile: type[LoadingProfile] | None = None,
        expected_type: type[TaravObject] | None = None,
    ) -> TaravObject:
        """Load one path through trusted Type dispatch and an optional check."""

        if profile is None:
            return self.records.load(path, expected_type=expected_type)
        return self.records.load(
            path, expected_type=expected_type, entry_paths=profile_paths(profile)
        )

    def context(self, subject: ContextSubject | ContextEntry, *, type=None):
        """Compose runtime and retained entries into one read-only view."""

        return open_context(subject, contributors=(self.contexts.contribute,), type=type)

    def register_commands(
        self,
        subparsers: argparse._SubParsersAction,
    ) -> None:
        """Compose the complete CLI command surface lazily.

        Keeping these imports inside the command adapter lets daemon-only
        processes construct the shared runtime without importing argparse or
        every feature command module.
        """
        from tarav.l1.agent import register_agent_commands
        from tarav.l1.archive.commands import register_archive_commands
        from tarav.l1.bloberia.commands import register_bloberia_commands
        from tarav.l1.breadcrumbs.commands import register_breadcrumb_commands
        from tarav.l1.chatlas import register_chatlas_commands
        from tarav.l3.daemon import register_daemon_commands
        from tarav.l3.daemon.client import submit_hook_invocation
        from tarav.l3.daemon.log import report_hook_delivery_failure
        from tarav.l1.forum import register_forum_commands
        from tarav.l1.hooks import register_hook_commands
        from tarav.l2.unsorted.commands import register_diagram_commands
        from tarav.l1.stdlib.mdblocks.commands import register_mdblocks_commands
        from tarav.l1.stdlib.prefix.commands import register_prefix_commands
        from tarav.l1.project.commands import register_project_commands
        from tarav.l3.project.commands import register_harness_commands
        from tarav.l1.python_env import register_python_commands
        from tarav.l3.run import register_run_command
        from tarav.l3.git.commands import (
            register_breadcrumb_git_commands,
            register_commands as register_git_commands,
        )
        from tarav.l1.reading_club.commands import register_reading_club_commands
        from tarav.l2.scoring.commands import register_scoring_commands
        from tarav.l1.stdlib.refs import register_refs_commands
        from tarav.l1.skills import register_skills_commands
        from tarav.l2.skw.commands import register_skw_commands
        from tarav.l1.system import register_system_commands
        from tarav.l1.stdlib.utils import register_utils_commands
        from tarav.l1.workspaces.commands import register_workspace_commands

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
        register_breadcrumb_commands(
            subparsers,
            integrations=self.breadcrumb_integrations,
            command_registrars=(register_breadcrumb_git_commands,),
        )
        register_git_commands(subparsers)
        register_diagram_commands(subparsers)
        register_bloberia_commands(subparsers)
        register_project_commands(
            subparsers,
            skills_registrar=register_skills_commands,
            harness_registrar=register_harness_commands,
        )
        register_reading_club_commands(subparsers)
        register_system_commands(subparsers)
        register_python_commands(subparsers)
        register_run_command(subparsers)
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
    workflows: Sequence[type[TaravWorkflow]] = (),
    record_types: Sequence[type[TaravObject]] = (),
    breadcrumb_integrations: Sequence[BreadcrumbIntegration] = (),
    environment: TaravEnvironment | None = None,
    archive_root: Path | None = None,
    config: Path | None = None,
) -> TaravRuntime:
    """Compose library capabilities. Configuration is explicit trusted input.

    The optional JSON config contains `workflow_files` (Python source paths)
    and `providers` ({name, workflow, root}). Paths are relative to that file.
    `filesystem` providers browse plain local Record collections.
    """
    from tarav.l1.archive import ArchiveNotificationPOI
    from tarav.l1.archive.artifact_records import ARCHIVE_RECORD_TYPES
    from tarav.l1.archive.references import ArchiveReference
    from tarav.l1.archive.workflow import ArchiveWorkflow
    from tarav.l2.breadcrumb_workflows.chatlas_context import (
        chatlas_context_integration,
    )
    from tarav.l1.breadcrumbs.workflow import (
        BREADCRUMB_RECORD_TYPES,
        BreadcrumbWorkflow,
    )
    from tarav.l1.chatlas.workflow import CHATLAS_RECORD_TYPES, ChatlasWorkflow
    from tarav.l2.unsorted.provider import DIAGRAM_RECORD_TYPES
    from tarav.l1.lines import Line, LineScope, LinesWorkflow
    from tarav.l1.loading import LoadingWorkflow
    from tarav.l1.git import GIT_RECORD_TYPES, GitWorkflow
    from tarav.l2.git.breadcrumbs import GIT_BREADCRUMB_RECORD_TYPES, audit_commit
    from tarav.l1.python_env import PYTHON_RECORD_TYPES, PythonWorkflow
    from tarav.l1.programs import ProgramsWorkflow, TaravProgram
    from tarav.l2.project.programs import ProjectProgram
    from tarav.l1.wiki import Wiki, WikiNote, WikiWorkflow
    from tarav.l2.models import ModelsWorkflow
    from tarav.l1.project import ProjectWorkflow, TaravProject
    from tarav.l2.project import Project
    from tarav.l2.project.runner import PROJECT_RUNNER_RECORD_TYPES
    from tarav.l2.project.models import ProjectModelsWorkflow
    from tarav.l2.project.wiki import ProjectWikiWorkflow
    from tarav.l1.poi import POI_RECORD_TYPES, POICollector, POIWorkflow
    from tarav.l1.blessings import (
        BLESSING_RECORD_TYPES,
        BlessablePOI,
        BlessingAssessmentRecord,
        BlessingRecord,
        BlessingStore,
        BlessingsWorkflow,
    )
    from tarav.l1.checks import Check, CheckPOI, CheckResult, ChecksWorkflow
    from tarav.l1.breadcrumbs.auditing import BreadcrumbAuditCheck
    from tarav.l1.poi.workflow import POI_WORKFLOW_SHIP
    from tarav.l1.surfaces import SurfacesWorkflow
    from tarav.l1.surfaces.markdown import MarkdownNormalModel
    from tarav.l1.surfaces.python import PythonNormalModel
    from tarav.l2.unsorted.workflow import UnsortedWorkflow
    from tarav.l1.references.workflow import REFERENCE_RECORD_TYPES
    from tarav.l1.archive.records import RECORD_ARCHIVE_TYPES, RecordArchiveWorkflow
    from tarav.l2.scoring.model import SCORING_RECORD_TYPES
    from tarav.l2.scoring import Assertion, ScoringDetails, ScoringReference
    from tarav.l2.lines.assertions import LineGroundingAssertion
    from tarav.l2.scoring.workflow import ScoringWorkflow
    from tarav.l1.skw.code import (
        CodeWorkflow,
        READING_DECLARATION_TYPES,
        READING_ENTRY_TYPES,
        SKW_CODE_RECORD_TYPES,
    )
    from tarav.l1.skw.document import SkillwareWorkflow
    from tarav.l1.skw.generation import GenerationPOI
    from tarav.l2.skw.skills import SKILLS_RECORD_TYPES, SkillsWorkflow
    from tarav.l2.test_workflow import TestEntity, TestItem, TestWorkflow
    from tarav.l1.skills.routing import SkillsSelectionNotification, SkillsStatusPOI

    composed_breadcrumb_integrations = (
        chatlas_context_integration(commit_auditor=audit_commit),
        *breadcrumb_integrations,
    )
    registered_types = tuple(
        dict.fromkeys(
            (
                FileRecord,
                DirectoryRecord,
                *CONTEXT_RECORD_TYPES,
                TaravClass,
                Line,
                LineScope,
                TaravEnvironment,
                TaravSystem,
                TestEntity,
                TestItem,
                *CHATLAS_RECORD_TYPES,
                *REFERENCE_RECORD_TYPES,
                *BREADCRUMB_RECORD_TYPES,
                *GIT_RECORD_TYPES,
                *GIT_BREADCRUMB_RECORD_TYPES,
                *(
                    record_type
                    for integration in composed_breadcrumb_integrations
                    for record_type in integration.workflow.record_types
                ),
                *ARCHIVE_RECORD_TYPES,
                ArchiveNotificationPOI,
                *RECORD_ARCHIVE_TYPES,
                ArchiveReference,
                *DIAGRAM_RECORD_TYPES,
                Wiki,
                WikiNote,
                Project,
                TaravProject,
                *PYTHON_RECORD_TYPES,
                *PROJECT_RUNNER_RECORD_TYPES,
                TaravProgram,
                ProjectProgram,
                *POI_RECORD_TYPES,
                *BLESSING_RECORD_TYPES,
                BlessablePOI,
                Check,
                CheckPOI,
                CheckResult,
                BreadcrumbAuditCheck,
                MarkdownNormalModel,
                PythonNormalModel,
                *SCORING_RECORD_TYPES,
                Assertion,
                ScoringDetails,
                ScoringReference,
                LineGroundingAssertion,
                *SKW_CODE_RECORD_TYPES,
                GenerationPOI,
                SkillsSelectionNotification,
                SkillsStatusPOI,
                *READING_DECLARATION_TYPES,
                *READING_ENTRY_TYPES,
                *SKILLS_RECORD_TYPES,
                *record_types,
            )
        )
    )
    running_environment = environment if environment is not None else TaravEnvironment()
    records = TypeRegistry(
        TaravObject, registered_types, environment=running_environment
    )
    registrations = WorkflowRegistry()
    navigation = Navigation.service()
    references = ReferenceWorkflow.service(records)
    contexts = ContextService(archive_root, records)
    breadcrumbs = BreadcrumbWorkflow.service(composed_breadcrumb_integrations)
    for workflow in (
        TaravWorkflow,
        KernelWorkflow,
        TypeWorkflow,
        LoadingWorkflow,
        PythonWorkflow,
        ProgramsWorkflow,
        ContextWorkflow,
        ChatlasWorkflow,
        ReferenceWorkflow,
        BreadcrumbWorkflow,
        GitWorkflow,
        ArchiveWorkflow,
        RecordArchiveWorkflow,
        LinesWorkflow,
        WikiWorkflow,
        ModelsWorkflow,
        ProjectWorkflow,
        ProjectModelsWorkflow,
        ProjectWikiWorkflow,
        POIWorkflow,
        BlessingsWorkflow,
        ChecksWorkflow,
        SurfacesWorkflow,
        UnsortedWorkflow,
        ScoringWorkflow,
        SkillwareWorkflow,
        # tarav.breadcrumb eae69a7746f4a20cd6a37196b1384f6e615b348574b6791f791ca6baa9ce96ab
        CodeWorkflow,
        SkillsWorkflow,
        Navigation,
        TestWorkflow,
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
                FilesystemProvider(root, records)
                if owner == "filesystem"
                else registrations.get(owner).provider(root, records)
            )
            navigation.mount(entry["name"], provider)
    for record_type in records.record_types:
        registrations.get(entity(record_type).workflow_ship)
    records.validate_external_with(
        lambda record_type: registrations.get(entity(record_type).workflow_ship)
    )
    registry = HookRegistry()
    register_hook_sampling_callbacks(registry)
    register_claude_usage_hook_callbacks(registry)
    register_codex_usage_hook_callbacks(registry)
    register_chatlas_hook_callbacks(registry)
    for registrar in hook_registrars:
        registrar(registry)
    return TaravRuntime(
        hooks=registry,
        system=TARAV,
        workflows=registrations,
        records=records,
        environment=running_environment,
        contexts=contexts,
        references=references,
        breadcrumbs=breadcrumbs,
        navigation=navigation,
        breadcrumb_integrations=composed_breadcrumb_integrations,
        pois=POICollector(),
        blessings=BlessingStore(
            contexts.archive_root / str(POI_WORKFLOW_SHIP) / 'blessings',
            record_types=tuple(t for t in registered_types
                               if issubclass(t, (BlessingRecord, BlessingAssessmentRecord))),
        ),
    )


_current_runtime: TaravRuntime | None = None
_current_runtime_lock = Lock()


def get_runtime() -> TaravRuntime:
    """Return the process's current runtime, composing it on first use."""

    global _current_runtime
    if _current_runtime is None:
        with _current_runtime_lock:
            if _current_runtime is None:
                _current_runtime = create_runtime()
    return _current_runtime


def set_runtime(runtime: TaravRuntime | None) -> None:
    """Select one composed runtime for process-wide library operations."""

    global _current_runtime
    if runtime is not None and not isinstance(runtime, TaravRuntime):
        raise TypeError("Current runtime must be a TaravRuntime or None")
    with _current_runtime_lock:
        _current_runtime = runtime


configure_workflow_resolver(lambda ship: get_runtime().workflows.get(ship)())
configure_current_records(lambda: get_runtime().records)
configure_current_context_service(lambda: get_runtime().contexts)

configure_context_resolver(lambda subject, **kwargs: get_runtime().context(subject, **kwargs))


__all__ = [
    "TaravRuntime",
    "HookRegistrar",
    "create_runtime",
    "get_runtime",
    "set_runtime",
]
