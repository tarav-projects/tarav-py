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
from tarav.l0._core.data_root import default_tarav_data_root
from tarav.l1.context import ContextBuilder, ContextExplorer
from tarav.l1.context.query import ContextQueryService, TypeResolver
from tarav.l1.context.workflow import ContextWorkflow
from tarav.l0.kernel.space import FilesystemProvider
from tarav.l0.kernel.records import (
    configure_workflow_resolver,
    configure_context_opener,
    configure_context_builder,
)
from tarav.l0.kernel.current import configure_current_records
from tarav.l0.kernel.workflows import TaravWorkflow, WorkflowRegistry
from tarav.l1.loading import LoadingProfile, profile_paths
from tarav.l1.records import RECORDS_TYPES, RecordsService, TaravRecords
from tarav.l1.search import SearchQuery, SearchService, SearchWorkflow
# tarav.breadcrumb d21dbd1bb68d
from tarav.l1.references.workflow import ReferenceWorkflow, ReferenceService
from tarav.l1.breadcrumbs.workflow import BreadcrumbService
from tarav.l1.usage import UsageRegistry

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
    navigation: RecordsService
    search: SearchService
    contexts: ContextBuilder
    references: ReferenceService
    breadcrumbs: BreadcrumbService
    usage: UsageRegistry
    breadcrumb_integrations: tuple[BreadcrumbIntegration, ...]
    pois: POICollector

    @property
    def scoring(self) -> type[ScoringWorkflow]:
        return self.workflows.get("Tarav.Workflow.Scoring")

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

    def context(self, subject) -> ContextExplorer:
        """Open a Context Explorer on a subject; identifiers resolve through this runtime."""

        resolve = self.context_queries().find
        if isinstance(subject, str):
            subject = resolve(subject)
        return ContextExplorer(self.contexts.build(subject),
                               resolve=resolve, build=self.contexts.build)

    def context_queries(self) -> ContextQueryService:
        """The installed resolvers from an identifier to what it identifies."""
        from tarav.l1.actions.views import ActionResolver
        from tarav.l1.notebook import Notebook
        from tarav.l2.notebook import NotebookResolver

        service = ContextQueryService()
        service.register_resolver("action", ActionResolver())
        service.register_resolver("type", TypeResolver(self.records.types))
        service.register_resolver("notebook", NotebookResolver(Notebook(records=self.records)))
        return service

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
        from tarav.l1.stdlib.mdblocks.commands import register_mdblocks_commands
        from tarav.l1.stdlib.prefix.commands import register_prefix_commands
        from tarav.l1.project.commands import register_project_commands
        from tarav.l3.project.commands import register_harness_commands
        from tarav.l3.project.system import register_init_command
        from tarav.l1.python_env import register_python_commands
        from tarav.l3.run import register_run_command
        from tarav.l3.check import register_check_command
        from tarav.l3.status import register_status_command
        from tarav.l3.git.commands import (
            register_breadcrumb_git_commands,
            register_commands as register_git_commands,
        )
        from tarav.l1.reading_club.commands import register_reading_club_commands
        from tarav.l2.scoring.commands import register_scoring_commands
        from tarav.l1.stdlib.refs import register_refs_commands
        from tarav.l2.project.skills import register_skills_commands
        from tarav.l2.skw.commands import register_skw_commands
        from tarav.l1.system import register_system_commands
        from tarav.l1.stdlib.utils import register_utils_commands
        from tarav.l1.workspaces.commands import register_workspace_commands
        from tarav.l1.usage.commands import register_usage_commands

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
        register_bloberia_commands(subparsers)
        register_project_commands(
            subparsers,
            skills_registrar=register_skills_commands,
            harness_registrar=register_harness_commands,
        )
        register_init_command(subparsers)
        register_reading_club_commands(subparsers)
        register_system_commands(subparsers)
        register_python_commands(subparsers)
        register_run_command(subparsers)
        register_check_command(subparsers)
        register_status_command(subparsers)
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
        from tarav.l1.actions.commands import register_action_commands
        from tarav.l1.operator_context.commands import register_operator_context_commands
        register_operator_context_commands(subparsers)
        from tarav.l3.notebook.commands import register_notebook_commands
        register_notebook_commands(subparsers)
        register_action_commands(subparsers)
        register_skw_commands(subparsers, registry=self.records)
        # tarav.breadcrumb ad568a3bc811
        register_usage_commands(
            subparsers, registry=self.usage,
            workflow_resolver=self.workflows.get,
        )


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
    from tarav.l1.chatlas.search import ChatlasSearchEngine
    # tarav.breadcrumb 3c23fe71552d
    from tarav.l1.lines import Block, Line, LinesWorkflow
    # tarav.breadcrumb f98e9b92d186
    from tarav.l1.notebook import Notebook, NotebookWorkflow
    from tarav.l2.notebook import NotebookProjectHook
    from tarav.l1.notebook.blocks import NOTEBOOK_BLOCK_TYPES
    # tarav.breadcrumb b457d57362a2
    from tarav.l1.notebook.evidence import NOTEBOOK_EVIDENCE_TYPES
    from tarav.l1.grounding import GROUNDING_RECORD_TYPES, GroundingWorkflow
    from tarav.l1.review import REVIEW_RECORD_TYPES, ReviewWorkflow
    from tarav.l2.notebook_checks import NOTEBOOK_EVIDENCE_POIS, NOTEBOOK_EVIDENCE_ACTIONS
    from tarav.l1.loading import LoadingWorkflow
    from tarav.l1.neighborhood import NeighborhoodWorkflow
    from tarav.l1.git import GIT_RECORD_TYPES, GitWorkflow
    # tarav.breadcrumb 35548ca6fdf7
    from tarav.l1.workspaces import (
        WORKSPACE_RECORD_TYPES, WorkspaceIntegrityCheck, WorkspacePOI,
        WorkspaceReferenceCheck, WorkspaceRemovalCheck, WorkspaceResetCheck,
        WorkspacesWorkflow,
    )
    from tarav.l2.git.breadcrumbs import GIT_BREADCRUMB_RECORD_TYPES, audit_commit
    from tarav.l1.python_env import PYTHON_RECORD_TYPES, PythonWorkflow
    from tarav.l1.programs import ProgramsWorkflow, TaravProgram
    from tarav.l1.agent.workflow import AgentsWorkflow
    from tarav.l1.actions import (
        ACTION_RECORD_TYPES, ActionsWorkflow, register_action,
    )
    from tarav.l1.operator_context import (
        OPERATOR_CONTEXT_RECORD_TYPES, OperatorContextWorkflow,
    )
    from tarav.l1.actions.pois import (
        POI_ACTION_RECORD_TYPES, POIResolutionAction,
    )
    from tarav.l2.tests.actions import ActionsTestsWorkflow
    from tarav.l2.project.programs import ProjectProgram
    from tarav.l1.wiki import Wiki, WikiNote, WikiWorkflow
    # tarav.breadcrumb 40a71d141d26
    from tarav.l1.attic import ATTIC_ACTION_TYPES, ATTIC_RECORD_TYPES, AtticWorkflow
    from tarav.l1.project import ProjectWorkflow, TaravProject
    from tarav.l2.project import Project
    from tarav.l2.project.runner import PROJECT_RUNNER_RECORD_TYPES
    from tarav.l2.project.system import SYSTEM_RECORD_TYPES
    from tarav.l2.project.wiki import ProjectWikiWorkflow
    from tarav.l1.poi import POI_RECORD_TYPES, POICollector, POIWorkflow
    from tarav.l1.settings import SETTINGS_RECORD_TYPES, SettingsWorkflow
    from tarav.l1.actions.blessing import (
        BLESSING_RECORD_TYPES, bind_blessing_assertion_services,
    )
    from tarav.l1.blessings import BlessingsWorkflow
    from tarav.l1.decisions import (
        DECISION_RECORD_TYPES, DecisionsWorkflow, bind_decision_assertions,
    )
    from tarav.l2.decisions import DecisionReportAssertion, assertions_for_decision
    from tarav.l1.checks import Check, CheckPOI, CheckResult, ChecksWorkflow
    from tarav.l1.breadcrumbs.auditing import (
        BreadcrumbAuditCheck, BreadcrumbAuditPOI, BreadcrumbPositionUpdated,
    )
    from tarav.l1.surfaces import SurfacesWorkflow
    from tarav.l1.surfaces.markdown import LineMarkdownModel, MarkdownNormalModel
    from tarav.l1.surfaces.python import PythonNormalModel
    from tarav.l1.surfaces.typescript import TypeScriptNormalModel
    from tarav.l1.references.workflow import REFERENCE_RECORD_TYPES
    from tarav.l1.archive.records import RECORD_ARCHIVE_TYPES, RecordArchiveWorkflow
    from tarav.l1.assertions import AssertionsWorkflow, TaravAssertion
    from tarav.l2.scoring.model import SCORING_RECORD_TYPES
    from tarav.l2.scoring import (
        Assertion, AssessmentCase, PairwiseRankingCase, ScoringDetails,
        ScoringReference, Score, RankingScore, Tribunal,
        TribunalScoreCheck, TribunalScorePOI,
    )
    from tarav.l2.scoring.ranking.workflow import RankingWorkflow
    from tarav.l2.scoring.workflow import ScoringWorkflow
    from tarav.l2.blessings import (
        BlessingAcceptanceAssertion, BlessingAcceptanceCase,
        BlessingAcceptanceTribunal,
        BlessingGroundsAssertion, BlessingGroundsCase,
        assertions_for_blessing, score_vector_for_blessing,
    )
    from tarav.l1.skw.code import (
        CodeWorkflow,
        LINK_PROSE_TYPES,
        READING_DECLARATION_TYPES,
        READING_ENTRY_TYPES,
        SKW_CODE_RECORD_TYPES,
    )
    from tarav.l1.skw.document import SkillwareWorkflow
    from tarav.l1.project.agents import PROJECT_AGENTS_RECORD_TYPES
    # tarav.breadcrumb c5d54c764943
    from tarav.l1.project.files import PROJECT_FILES_RECORD_TYPES
    from tarav.l1.git.hooks import GIT_HOOKS_RECORD_TYPES
    from tarav.l1.git.change import GIT_CHANGE_RECORD_TYPES
    from tarav.l1.git.witness import GIT_WITNESS_RECORD_TYPES
    from tarav.l1.git.gitleaks import GIT_GITLEAKS_RECORD_TYPES
    from tarav.l1.project.skills import PROJECT_SKILLS_RECORD_TYPES
    from tarav.l1.skills.folder import FolderSkill
    from tarav.l1.skills.marker import SkillMarker
    from tarav.l1.skw.generation import GenerationPOI
    from tarav.l2.skw.skills import SKILLS_RECORD_TYPES, SkwSkillsWorkflow
    from tarav.l1.skills import SkillsWorkflow
    from tarav.l2.tests.workflow import TestsWorkflow
    from tarav.l2.tests.navigation import TestEntity, TestItem, NavigationTestsWorkflow
    from tarav.l2.tests.scoring import (
        ScoringTestsWorkflow, ScoringTestChat, ScoringTestLine,
        LineSupportAssertion, LineSupportCase, LineSupportTribunal,
    )
    from tarav.l2.project.skills.routing import SkillsSelectionNotification, SkillsStatusPOI
    from tarav.l1.cli import CliWorkflow
    from tarav.l1.live_help import LiveHelpWorkflow
    from tarav.l1.usage import UsageRegistryWorkflow

    composed_breadcrumb_integrations = (
        chatlas_context_integration(commit_auditor=audit_commit),
        *breadcrumb_integrations,
    )
    registered_types = tuple(
        dict.fromkeys(
            (
                FileRecord,
                DirectoryRecord,
                *RECORDS_TYPES,
                SearchQuery,
                TaravClass,
                Block,
                Line,
                Notebook,
                *NOTEBOOK_BLOCK_TYPES,
                *NOTEBOOK_EVIDENCE_TYPES,
                *GROUNDING_RECORD_TYPES,
                *REVIEW_RECORD_TYPES,
                *NOTEBOOK_EVIDENCE_POIS,
                TaravEnvironment,
                TaravSystem,
                TestEntity,
                TestItem,
                ScoringTestChat,
                ScoringTestLine,
                LineSupportAssertion,
                LineSupportCase,
                LineSupportTribunal,
                *CHATLAS_RECORD_TYPES,
                *REFERENCE_RECORD_TYPES,
                *BREADCRUMB_RECORD_TYPES,
                *GIT_RECORD_TYPES,
                *WORKSPACE_RECORD_TYPES,
                *ATTIC_RECORD_TYPES,
                WorkspaceIntegrityCheck,
                WorkspaceReferenceCheck,
                WorkspaceRemovalCheck,
                WorkspaceResetCheck,
                WorkspacePOI,
                *WorkspacePOI.__subclasses__(),  # its atomic cases
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
                Wiki,
                WikiNote,
                Project,
                TaravProject,
                # tarav.breadcrumb e413721d29ed
                *PROJECT_AGENTS_RECORD_TYPES,
                *PROJECT_SKILLS_RECORD_TYPES,
                *PROJECT_FILES_RECORD_TYPES,
                *GIT_HOOKS_RECORD_TYPES,
                *GIT_CHANGE_RECORD_TYPES,
                *GIT_WITNESS_RECORD_TYPES,
                *GIT_GITLEAKS_RECORD_TYPES,
                *PYTHON_RECORD_TYPES,
                *PROJECT_RUNNER_RECORD_TYPES,
                *SYSTEM_RECORD_TYPES,
                TaravProgram,
                ProjectProgram,
                *OPERATOR_CONTEXT_RECORD_TYPES,
                *ACTION_RECORD_TYPES,
                *POI_ACTION_RECORD_TYPES,
                *POI_RECORD_TYPES,
                *SETTINGS_RECORD_TYPES,
                *BLESSING_RECORD_TYPES,
                *DECISION_RECORD_TYPES,
                DecisionReportAssertion,
                Check,
                CheckPOI,
                CheckResult,
                BreadcrumbAuditCheck,
                BreadcrumbAuditPOI,
                *BreadcrumbAuditPOI.__subclasses__(),  # its atomic cases
                BreadcrumbPositionUpdated,
                MarkdownNormalModel,
                LineMarkdownModel,
                PythonNormalModel,
                TypeScriptNormalModel,
                *SCORING_RECORD_TYPES,
                TaravAssertion,
                # tarav.breadcrumb c0353f733830
                Assertion,
                AssessmentCase,
                Score,
                RankingScore,
                PairwiseRankingCase,
                Tribunal,
                ScoringDetails,
                ScoringReference,
                TribunalScoreCheck,
                TribunalScorePOI,
                *TribunalScorePOI.__subclasses__(),  # its atomic cases
                BlessingAcceptanceAssertion,
                BlessingAcceptanceCase,
                BlessingAcceptanceTribunal,
                BlessingGroundsAssertion,
                BlessingGroundsCase,
                *SKW_CODE_RECORD_TYPES,
                GenerationPOI,
                *GenerationPOI.__subclasses__(),  # its atomic cases
                SkillsSelectionNotification,
                SkillsStatusPOI,
                *SkillsStatusPOI.__subclasses__(),  # its atomic cases
                *READING_DECLARATION_TYPES,
                *READING_ENTRY_TYPES,
                *LINK_PROSE_TYPES,
                *SKILLS_RECORD_TYPES,
                FolderSkill,
                SkillMarker,
                *record_types,
            )
        )
    )
    running_environment = environment if environment is not None else TaravEnvironment()
    records = TypeRegistry(
        TaravObject, registered_types, environment=running_environment
    )
    registrations = WorkflowRegistry()
    navigation = TaravRecords.service()
    # tarav.breadcrumb 62297208d649
    search = SearchWorkflow.service()
    # tarav.breadcrumb 41ba4335c0c7
    search.register("chatlas", ChatlasSearchEngine())
    references = ReferenceWorkflow.service(records)
    breadcrumbs = BreadcrumbWorkflow.service(composed_breadcrumb_integrations)
    for workflow in (
        TaravWorkflow,
        KernelWorkflow,
        TypeWorkflow,
        LoadingWorkflow,
        PythonWorkflow,
        ProgramsWorkflow,
        AgentsWorkflow,
        OperatorContextWorkflow,
        ActionsWorkflow,
        ContextWorkflow,
        NeighborhoodWorkflow,
        ChatlasWorkflow,
        ReferenceWorkflow,
        BreadcrumbWorkflow,
        GitWorkflow,
        WorkspacesWorkflow,
        ArchiveWorkflow,
        AtticWorkflow,
        RecordArchiveWorkflow,
        LinesWorkflow,
        NotebookWorkflow,
        GroundingWorkflow,
        ReviewWorkflow,
        WikiWorkflow,
        ProjectWorkflow,
        ProjectWikiWorkflow,
        SkillsWorkflow,
        POIWorkflow,
        SettingsWorkflow,
        BlessingsWorkflow,
        DecisionsWorkflow,
        ChecksWorkflow,
        UsageRegistryWorkflow,
        CliWorkflow,
        LiveHelpWorkflow,
        SurfacesWorkflow,
        AssertionsWorkflow,
        ScoringWorkflow,
        RankingWorkflow,
        SkillwareWorkflow,
        # tarav.breadcrumb eae69a7746f4
        CodeWorkflow,
        SkwSkillsWorkflow,
        TaravRecords,
        SearchWorkflow,
        TestsWorkflow,
        NavigationTestsWorkflow,
        ScoringTestsWorkflow,
        ActionsTestsWorkflow,
        *workflows,
    ):
        registrations.register(workflow)
    register_action(POIResolutionAction)
    from tarav.l1.git.gitleaks import (
        GitleaksFindingResolution, GitleaksMissingResolution, GitleaksNeverScannedResolution,
        GitleaksStagedResolution,
    )
    from tarav.l1.git.hooks import HooksNotInstalledResolution
    from tarav.l2.skw.pois import SKW_ACTION_TYPES
    from tarav.l2.tests.actions import TestMarkerResolution
    for action_type in (GitleaksFindingResolution, GitleaksStagedResolution,
                        GitleaksNeverScannedResolution, GitleaksMissingResolution,
                        HooksNotInstalledResolution, *SKW_ACTION_TYPES, TestMarkerResolution,
                        *ATTIC_ACTION_TYPES, *NOTEBOOK_EVIDENCE_ACTIONS):
        register_action(action_type)
    from tarav.l1.project.config import register_config_section
    from tarav.l1.project.agents import AgentsConfig
    from tarav.l2.project.skills.routing import SkillsConfig
    from tarav.l1.git.hooks import GitConfig, register_git_hook_handler
    from tarav.l1.git.change import TaravChange
    for section, model in (("agents", AgentsConfig), ("skills", SkillsConfig),
                           ("git", GitConfig)):
        register_config_section(section, model)
    register_git_hook_handler(TaravChange())
    from tarav.l1.git.gitleaks import Gitleaks
    register_git_hook_handler(Gitleaks())
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
    bind_blessing_assertion_services(
        # tarav.breadcrumb 5762311d9418
        assertions=assertions_for_blessing,
        scores=score_vector_for_blessing,
    )
    bind_decision_assertions(assertions_for_decision)
    registry = HookRegistry()
    register_hook_sampling_callbacks(registry)
    register_claude_usage_hook_callbacks(registry)
    register_codex_usage_hook_callbacks(registry)
    register_chatlas_hook_callbacks(registry)
    for registrar in hook_registrars:
        registrar(registry)
    contexts = ContextBuilder()
    contexts.register("notebook", NotebookProjectHook(Notebook(records=records)))
    return TaravRuntime(
        hooks=registry,
        system=TARAV,
        workflows=registrations,
        records=records,
        environment=running_environment,
        references=references,
        breadcrumbs=breadcrumbs,
        usage=UsageRegistry(
            (archive_root or default_tarav_data_root() / "archive").expanduser().resolve()),
        navigation=navigation,
        search=search,
        contexts=contexts,
        breadcrumb_integrations=composed_breadcrumb_integrations,
        pois=POICollector(),
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
configure_context_opener(lambda subject: get_runtime().context(subject))
configure_context_builder(lambda subject, **kwargs: get_runtime().contexts.build(subject, **kwargs))


__all__ = [
    "TaravRuntime",
    "HookRegistrar",
    "create_runtime",
    "get_runtime",
    "set_runtime",
]
