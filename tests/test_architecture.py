# $kw: ^agentos-python-architecture-contract --from Agent.Navigable.Codebase --from Dependency.Profile.Split --note [CT] maintained namespaces are cohesive and their import graph is acyclic outside the runtime composition root --supp ^c20260811-62u
from __future__ import annotations

from tarav.l0.kernel import entity

import ast
import argparse
from collections import defaultdict
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "src" / "tarav"


# tarav.breadcrumb bbd582b06204
# tarav.breadcrumb bb18dc7c211d
def test_project_capabilities_use_bound_semantic_paths() -> None:
    from tarav.l0.kernel import NamespaceBase
    from tarav.l1.checks import CheckProvider
    from tarav.l2.project import Project
    from tarav.l1.project import TaravProject

    assert issubclass(Project.Docs, NamespaceBase)
    assert issubclass(CheckProvider.Checks, NamespaceBase)
    assert not hasattr(Project, "models")
    assert issubclass(TaravProject.Agents, NamespaceBase)
    assert isinstance(TaravProject.agents, property)
    assert isinstance(Project.checks, property)
    assert not hasattr(Project, "wiki")


# tarav.breadcrumb 7211da22c6b1
def test_object_namespaces_stay_in_kernel_and_do_not_import_records_workflow():
    from tarav.l0.kernel import NamespaceBase, TaravObject

    assert issubclass(TaravObject.Records, NamespaceBase)
    # tarav.breadcrumb 44bf7a3ce4e7
    assert issubclass(TaravObject.Context, NamespaceBase)
    assert TaravObject.context.obj.target is TaravObject
    assert callable(TaravObject.context)
    assert not callable(NamespaceBase(TaravObject))
    assert TaravObject.records.obj is TaravObject
    # tarav.breadcrumb 6756f126eb6b
    assert TaravObject.records.record_example() == {"type": "Tarav.Object"}
    assert not hasattr(TaravObject, "record_example")
    assert not hasattr(TaravObject, "validate_record")
    assert not hasattr(TaravObject, "from_record")
    assert not hasattr(TaravObject, "to_record")
    assert "l1.records" not in _top_level_import_graph()["l0.kernel"]
    # tarav.breadcrumb bece7d874166


def test_project_ownership_and_consumer_direction():
    from tarav.l1.project import ProjectWorkflow
    from tarav.l2.project import Project
    from tarav.l2.project.harness import ProjectHarness
    from tarav.l3.runtime import create_runtime

    runtime = create_runtime()
    assert runtime.workflows.get("Tarav.Workflow.Project") is ProjectWorkflow
    assert entity(Project).workflow is ProjectWorkflow()
    graph = _top_level_import_graph()
    assert not ({"wiki", "models", "runtime", "cli"} & graph["project.base"])
    assert not any(name.startswith("project") for name in graph["wiki"])
    assert entity(ProjectHarness).workflow is ProjectWorkflow()


def test_loading_workflow_configures_kernel_without_reverse_imports():
    from tarav.l1.loading import LoadingProfile, LoadingWorkflow
    from tarav.l1.project import TaravProject
    from tarav.l3.runtime import create_runtime

    graph = _top_level_import_graph()
    assert create_runtime().workflows.get("Tarav.Workflow.Loading") is LoadingWorkflow
    assert issubclass(TaravProject, LoadingProfile)
    assert not any(name.startswith("loading") for name in graph["l0.kernel"])


# tarav.breadcrumb b28351625fdf
def test_cli_usage_and_live_help_workflows_are_separate() -> None:
    from tarav.l1.cli import CliWorkflow, Command, CommandUse
    from tarav.l1.live_help import LiveHelpProvider, LiveHelpWorkflow
    from tarav.l1.usage import UsageRegistryWorkflow, UsageTrace
    from tarav.l3.runtime import create_runtime

    runtime = create_runtime()
    assert runtime.workflows.get("Tarav.Workflow.CLI") is CliWorkflow
    assert runtime.workflows.get("Tarav.Workflow.Usage") is UsageRegistryWorkflow
    assert runtime.workflows.get("Tarav.Workflow.LiveHelp") is LiveHelpWorkflow
    assert entity(Command).workflow is CliWorkflow()
    assert entity(CommandUse).workflow is CliWorkflow()
    assert entity(UsageTrace).workflow is UsageRegistryWorkflow()
    assert issubclass(CommandUse, UsageTrace)
    assert Command((), argparse.ArgumentParser()).help_trace_type is CommandUse
    assert issubclass(Command, LiveHelpProvider)
    assert Command not in runtime.records.record_types
    graph = _top_level_import_graph()
    assert "l3.runtime" not in graph["cli"]
    assert "l3.runtime" not in graph["usage"]
    assert "l3.runtime" not in graph["live_help"]
    assert "cli" not in graph["usage"]
    assert "cli" not in graph["live_help"]


def test_git_workflow_spans_mechanics_integration_and_process_adapters():
    from tarav.l1.git import GitRepository, GitWorkflow
    from tarav.l1.references.git import GitCommitMessagePositionReference
    from tarav.l2.git.breadcrumbs import CommitManifest
    from tarav.l3.runtime import create_runtime

    runtime = create_runtime()
    assert runtime.workflows.get("Tarav.Workflow.Git") is GitWorkflow
    assert entity(GitRepository).workflow is GitWorkflow()
    assert entity(CommitManifest).workflow is GitWorkflow()
    assert (
        runtime.records.resolve_ship(entity(GitCommitMessagePositionReference).id)
        is GitCommitMessagePositionReference
    )
    assert runtime.records.resolve_ship(entity(CommitManifest).id) is CommitManifest


# tarav.breadcrumb 20e20b4bfd9e
def test_workspaces_own_their_entities_and_project_only_integrates():
    from tarav.l1.workspaces import Workspace, WorkspacesWorkflow
    from tarav.l2.project import Project
    from tarav.l2.project.workspaces import ProjectWorkspaces
    from tarav.l3.runtime import create_runtime

    runtime = create_runtime()
    assert runtime.workflows.get("Tarav.Workflow.Workspaces") is WorkspacesWorkflow
    assert entity(Workspace).workflow is WorkspacesWorkflow()
    assert runtime.records.resolve_ship(entity(Workspace).id) is Workspace
    assert "project" not in _top_level_import_graph()["workspaces.model"]
    assert "project" not in _top_level_import_graph()["workspaces.depot"]
    assert Project.workspaces is not None
    assert ProjectWorkspaces.__module__ == "tarav.l2.project.workspaces"


def test_poi_workflow_ownership_and_runtime_composition():
    from tarav.l1.poi import POI_RECORD_TYPES, POIWorkflow
    from tarav.l1.checks import Check, CheckPOI, CheckSuite, ChecksWorkflow
    from tarav.l1.breadcrumbs.auditing import BreadcrumbAuditCheck
    from tarav.l1.breadcrumbs.workflow import BreadcrumbWorkflow
    from tarav.l3.runtime import create_runtime

    runtime = create_runtime()
    assert runtime.workflows.get("Tarav.Workflow.POI") is POIWorkflow
    for record_type in POI_RECORD_TYPES:
        assert entity(record_type).workflow is POIWorkflow()
        assert runtime.records.resolve_ship(entity(record_type).id) is record_type
    assert entity(Check).workflow is ChecksWorkflow()
    assert entity(CheckPOI).workflow is ChecksWorkflow()
    assert entity(CheckSuite).workflow is ChecksWorkflow()
    assert entity(BreadcrumbAuditCheck).workflow is BreadcrumbWorkflow()
    assert runtime.records.resolve_ship(entity(CheckPOI).id) is CheckPOI
    assert 'runtime' not in _top_level_import_graph()['poi']


def test_assertion_foundation_and_lines_core_are_separate():
    # tarav.breadcrumb 73c1e18245d9
    from tarav.l1.lines import Block, Line, LinesWorkflow
    from tarav.l1.assertions import AssertionsWorkflow, TaravAssertion
    from tarav.l2.scoring import (
        Assertable, Assertion, AssessmentCase, PairwiseRankingCase,
        RankingScore, RankingWorkflow, Score, ScoringWorkflow, Tribunal,
        TribunalScoreCheck, TribunalScorePOI,
    )
    from tarav.l3.runtime import create_runtime

    assert issubclass(Assertion, TaravAssertion)
    assert entity(TaravAssertion).workflow is AssertionsWorkflow()
    assert entity(Assertion).workflow is ScoringWorkflow()
    assert entity(Assertable).workflow is AssertionsWorkflow()
    assert entity(AssessmentCase).workflow is ScoringWorkflow()
    assert entity(Score).workflow is ScoringWorkflow()
    assert issubclass(RankingWorkflow, ScoringWorkflow)
    assert RankingWorkflow().workflow is ScoringWorkflow()
    assert entity(RankingScore).workflow is RankingWorkflow()
    assert entity(PairwiseRankingCase).workflow is RankingWorkflow()
    assert entity(Tribunal).workflow is RankingWorkflow()
    assert entity(Block).workflow is LinesWorkflow()
    runtime = create_runtime()
    assert runtime.records.resolve_ship(entity(Block).id) is Block
    assert runtime.records.resolve_ship(entity(Line).id) is Line
    assert runtime.records.resolve_ship(entity(TaravAssertion).id) is TaravAssertion
    for case_type in (
        AssessmentCase, Score, RankingScore, PairwiseRankingCase, Tribunal,
        TribunalScoreCheck, TribunalScorePOI,
    ):
        assert runtime.records.resolve_ship(entity(case_type).id) is case_type
    graph = _top_level_import_graph()
    assert not any(name.startswith('lines') for name in graph['scoring.assertions'])
    assert 'scoring.tasks' not in graph


def test_blessing_assertions_compose_without_reverse_layer_imports():
    # tarav.breadcrumb 1fd36ba300ae
    from tarav.l1.actions import Closing
    from tarav.l1.actions.blessing import Blessing
    from tarav.l1.blessings import BlessingsWorkflow
    from tarav.l2.blessings import (
        BlessingAcceptanceAssertion, BlessingAcceptanceCase,
        BlessingGroundsAssertion, BlessingGroundsCase,
    )
    from tarav.l2.scoring import Assertable
    from tarav.l1.decisions import Decision, DecisionsWorkflow
    from tarav.l2.decisions import DecisionReportAssertion
    from tarav.l3.runtime import create_runtime

    assert issubclass(Blessing, Assertable)
    assert issubclass(Blessing, Closing) and not issubclass(Blessing, Decision)
    assert entity(Blessing).workflow is BlessingsWorkflow()
    assert entity(Closing).id in {base.id for base in entity(Blessing).bases()}
    assert entity(Decision).workflow is DecisionsWorkflow()
    assert entity(DecisionReportAssertion).workflow is DecisionsWorkflow()
    runtime = create_runtime()
    for record_type in (
        BlessingAcceptanceAssertion, BlessingAcceptanceCase,
        BlessingGroundsAssertion, BlessingGroundsCase,
    ):
        assert entity(record_type).workflow is BlessingsWorkflow()
        assert runtime.records.resolve_ship(entity(record_type).id) is record_type
        example = record_type.records.record_example()
        assert runtime.records.from_record(example).records.to_record() == example
    for path in (*PACKAGE_ROOT.glob('l1/scoring/*.py'), PACKAGE_ROOT / 'l1/actions/blessing.py'):
        tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
        assert not any(
            isinstance(node, ast.ImportFrom) and (node.module or '').startswith('tarav.l2')
            for node in ast.walk(tree)
        )



def test_wiki_ownership_and_parsing_boundary():
    from tarav.l3.runtime import create_runtime
    from tarav.l1.wiki import Wiki, WikiNote, WikiWorkflow

    runtime = create_runtime()
    assert runtime.workflows.get("Tarav.Workflow.Wiki") is WikiWorkflow
    assert entity(Wiki).workflow is WikiWorkflow()
    assert entity(WikiNote).workflow is WikiWorkflow()
    assert "surfaces" in _top_level_import_graph()["wiki"]
    assert WikiWorkflow.help()["capture"]["skill"] == "tarav-hugentics"


def test_context_package_import_order_and_runtime_boundary():
    import subprocess
    import sys

    for first_import in (
        "import tarav.l1.context",
        "from tarav.l1.context.workflow import ContextWorkflow",
        "from tarav.l1.archive.records import ArchiveFolder",
    ):
        code = first_import + '''
import tarav.l0.kernel as kernel
from tarav.l1.context import ContextBuilder, ContextExplorer, ContextHook, ObjectContext
from tarav.l1.context.workflow import ContextWorkflow
from tarav.l3.runtime import get_runtime
from tarav.l0.kernel import TaravType, entity
assert not hasattr(kernel, "ContextExplorer")
assert not hasattr(kernel, "ObjectContext")
assert not hasattr(kernel, "ContextBuilder")
assert not hasattr(kernel, "ContextHook")
assert ContextHook.__module__ == "tarav.l1.context.construction"
assert ContextExplorer.__module__ == "tarav.l1.context"
get_runtime()
assert entity(ContextExplorer).workflow is ContextWorkflow()
assert entity(ObjectContext).workflow is ContextWorkflow()
assert entity(ContextBuilder).workflow is ContextWorkflow()
assert TaravType.context().focus.id == entity(TaravType).id
assert TaravType.context.build().subject.target is TaravType
'''
        subprocess.run([sys.executable, "-c", code], check=True, capture_output=True, text=True)


def test_l1_context_and_workflow_import_without_integration() -> None:
    import subprocess
    import sys

    for first_import in (
        "import tarav.l1.context",
        "from tarav.l1.context.workflow import ContextWorkflow",
    ):
        code = first_import + '''
import sys
from typing import get_type_hints
from tarav.l1.context import ContextExplorer
from tarav.l1.context.workflow import ContextWorkflow
assert ContextExplorer.__module__ == "tarav.l1.context"
assert get_type_hints(ContextWorkflow.class_entity)["return"].__name__ == "TaravClass"
for forbidden in ("tarav.l2", "tarav.l1.archive", "tarav.l3.runtime"):
    assert forbidden not in sys.modules, forbidden
'''
        subprocess.run(
            [sys.executable, "-c", code], check=True, capture_output=True, text=True
        )


def test_archive_package_paths_match_workflow_ownership():
    from tarav.l1.archive.artifact_records import ArtifactRecord
    from tarav.l1.archive.records import ArchiveFolder, RecordArchiveWorkflow
    from tarav.l1.archive.workflow import ArchiveWorkflow
    from tarav.l3.runtime import create_runtime

    assert ArchiveFolder.__module__ == "tarav.l1.archive.records"
    assert ArtifactRecord.__module__ == "tarav.l1.archive.artifact_records"
    assert entity(ArchiveFolder).workflow is RecordArchiveWorkflow()
    assert RecordArchiveWorkflow().workflow is ArchiveWorkflow()
    assert entity(ArtifactRecord).workflow is ArchiveWorkflow()
    assert str(entity(ArchiveFolder).id) == "e67748c1-6ae8-4e9e-b868-913c57ec479d"
    assert str(entity(ArtifactRecord).id) == "683fd453-7425-5a91-a382-5753a986e324"
    assert create_runtime().records.resolve_type(entity(ArchiveFolder).name) is ArchiveFolder
    for name in ("__init__.py", "workflow.py", "artifact_records.py"):
        tree = ast.parse((PACKAGE_ROOT / "l1" / "archive" / name).read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert node.module not in {"tarav.l1.archive.records", "records"}


def test_type_graph_ownership_is_separate_from_represented_ownership():
    from tarav.l0.kernel import TaravClass, TypeWorkflow
    from tarav.l1.archive.records import ArchiveFolder

    assert entity(TaravClass).workflow_ship == entity(TypeWorkflow).workflow_ship
    assert entity(ArchiveFolder).workflow_ship != entity(TaravClass).workflow_ship


# tarav.breadcrumb bd4584d1e797
def test_skw_code_owns_common_source_and_skills_specializes_it():
    from tarav.l1.skw.annotations import GenerationAnnotation
    from tarav.l1.skw.code import CodeWorkflow, Contains, DocumentRecord, SkwBlock
    from tarav.l1.skw.document import SkillwareWorkflow
    from tarav.l1.skw.skills import SkillLink
    from tarav.l2.skw.skills import SkwSkillsWorkflow
    from tarav.l3.runtime import create_runtime

    assert CodeWorkflow().workflow is SkillwareWorkflow()
    assert SkwSkillsWorkflow().workflow is CodeWorkflow()
    for common_type in (DocumentRecord, SkwBlock, GenerationAnnotation, Contains):
        assert entity(common_type).workflow_ship == CodeWorkflow().id
    assert entity(SkillLink).workflow_ship == SkwSkillsWorkflow().id

    runtime = create_runtime()
    assert runtime.workflows.get("Tarav.Workflow.SKW.Code") is CodeWorkflow
    assert Contains.__module__ == "tarav.l1.skw.code.reading"


def test_record_interfaces_belong_to_kernel():
    from pydantic import BaseModel
    from tarav.l0.kernel import TaravObject, isrecordsubclass, issubrecord
    from tarav.l1.skw.annotations import BlockAnnotation, GenerationAnnotation
    from tarav.l1.skw.document import SkwBlock
    from tarav.l1.skw.skills import SkillLink

    assert issubclass(TaravObject.RecordInterface, BaseModel)
    assert issubrecord(SkwBlock, TaravObject)
    assert isrecordsubclass(SkwBlock, TaravObject)
    assert SkwBlock.preserves_parent_record_interface()
    assert isrecordsubclass(SkillLink, SkwBlock)
    assert isrecordsubclass(GenerationAnnotation, BlockAnnotation)


def test_record_archive_placement_index_is_outside_its_entity_record() -> None:
    from tarav.l1.archive.records import ARCHIVE
    from tarav.l1.archive.records import ArchiveFolder, ArchiveRoot, ArchiveList
    from tarav.l2.tests.navigation import NavigationTestsWorkflow

    assert isinstance(ARCHIVE, ArchiveRoot)
    assert ARCHIVE.for_workflow(NavigationTestsWorkflow).parts == (
        str(entity(NavigationTestsWorkflow).workflow_ship),
    )

    for archive_type in (ArchiveFolder, ArchiveList):
        assert "entries" not in archive_type.RecordInterface.model_fields
        assert {"type", "id", "constitution"} <= set(
            archive_type.RecordInterface.model_fields
        )


def test_archive_implements_shared_explorer_contracts() -> None:
    from tarav.l0.kernel import Explorer, ExplorerEntry, ExplorerFolder, ExplorerList
    from tarav.l1.archive.records import (
        ArchiveEntry,
        ArchiveExplorer,
        ArchiveFolder,
        ArchiveList,
        ArchivePartition,
        ArchiveRoot,
    )

    assert issubclass(ArchiveEntry, ExplorerEntry)
    assert issubclass(ArchiveFolder, ExplorerFolder)
    assert issubclass(ArchiveList, ExplorerList)
    assert issubclass(ArchiveRoot, ExplorerFolder)
    assert issubclass(ArchivePartition, ExplorerFolder)
    assert issubclass(ArchiveExplorer, Explorer)


def test_generation_mechanics_depend_only_on_its_workflow_foundations() -> None:
    tree = ast.parse((PACKAGE_ROOT / "l1" / "skw" / "generation.py").read_text())
    dependencies = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            dependencies.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            dependencies.add(node.module)

    tarav_dependencies = {name for name in dependencies if name.startswith("tarav.")}
    assert tarav_dependencies == {"tarav.l0.kernel", "tarav.l1.poi", "tarav.l1.skw.identity"}


def _top_level_import_graph() -> dict[str, set[str]]:
    graph: dict[str, set[str]] = defaultdict(set)
    for path in PACKAGE_ROOT.rglob("*.py"):
        relative = path.relative_to(PACKAGE_ROOT)
        parts = relative.parts[1:] if relative.parts[0] in {"l1", "l2", "l3"} else relative.parts
        source = parts[0] if len(parts) > 1 else Path(parts[0]).stem
        if source == "l0":
            source = ".".join(relative.parts[:2])
        # Inspect the active domain modules without collapsing their dependencies.
        if source in {"lines", "scoring", "project"}:
            source = ".".join(Path(*parts).with_suffix("").parts).removesuffix(".__init__")
        if relative.parts[0] == 'l1' and relative.parts[1] in {
            'scoring', 'poi', 'blessings', 'decisions',
        }:
            source = source.replace(relative.parts[1], relative.parts[1] + '.foundation', 1)
        # skw.skills is a composition leaf above the generic SKW document kernel.
        if Path(*parts).as_posix() in {
            "skw/skills.py",
            "skw/loading.py",
            "skw/pois.py",
        }:
            source = "skw.skills"
        graph[source]
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        # Annotation-only imports do not create runtime dependency edges.
        for guarded in ast.walk(tree):
            if isinstance(guarded, ast.If) and isinstance(guarded.test, ast.Name) and guarded.test.id == "TYPE_CHECKING":
                guarded.body = []
        for node in ast.walk(tree):
            imported: tuple[str, ...] = ()
            if isinstance(node, ast.Import):
                imported = tuple(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                imported = (node.module,)
                if node.level and source.split(".")[0] in {"lines", "scoring", "project"}:
                    from importlib.util import resolve_name

                    package = "tarav." + ".".join(relative.parts[:-1])
                    imported = (resolve_name("." * node.level + node.module, package),)
            for name in imported:
                if not name.startswith("tarav."):
                    continue
                target = name.split(".", 2)[1]
                if target == "l0":
                    target = ".".join(name.split(".")[:3]).removeprefix("tarav.")
                if target in {"l1", "l2", "l3"}:
                    target = name.split(".", 3)[2]
                if target in {"lines", "scoring", "project"}:
                    target = name.split(".", 2)[-1] if name.startswith("tarav.l") else name.removeprefix("tarav.")
                    if target.startswith(("l1.", "l2.", "l3.")):
                        target = target.split(".", 1)[1]
                for foundation in ('scoring', 'poi', 'blessings', 'decisions'):
                    if name == f'tarav.l1.{foundation}' or name.startswith(f'tarav.l1.{foundation}.'):
                        target = target.replace(foundation, foundation + '.foundation', 1)
                        break
                if name == "tarav.l2.skw.skills" or name.startswith("tarav.l2.skw.skills."):
                    target = "skw.skills"
                if target != source:
                    graph[source].add(target)
    return graph


def test_generic_document_does_not_import_skill_specialization():
    tree = ast.parse((PACKAGE_ROOT / "l1" / "skw" / "document.py").read_text())
    imports = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    assert "tarav.l2.skw.skills" not in imports


def _strongly_connected_components(
    graph: dict[str, set[str]],
) -> tuple[tuple[str, ...], ...]:
    next_index = 0
    stack: list[str] = []
    on_stack: set[str] = set()
    indices: dict[str, int] = {}
    low_links: dict[str, int] = {}
    components: list[tuple[str, ...]] = []

    def visit(node: str) -> None:
        nonlocal next_index
        indices[node] = next_index
        low_links[node] = next_index
        next_index += 1
        stack.append(node)
        on_stack.add(node)
        for target in graph[node]:
            if target not in indices:
                visit(target)
                low_links[node] = min(low_links[node], low_links[target])
            elif target in on_stack:
                low_links[node] = min(low_links[node], indices[target])
        if low_links[node] != indices[node]:
            return
        component: list[str] = []
        while True:
            target = stack.pop()
            on_stack.remove(target)
            component.append(target)
            if target == node:
                break
        if len(component) > 1:
            components.append(tuple(sorted(component)))

    for node in tuple(graph):
        if node not in indices:
            visit(node)
    return tuple(sorted(components))


def test_provider_adapters_live_under_agent_namespace() -> None:
    forbidden = {
        "claude",
        "codex",
        "copilot",
        "home",
        "providers.py",
    }
    present = {path.name for path in PACKAGE_ROOT.iterdir()}
    assert forbidden.isdisjoint(present)
    assert (PACKAGE_ROOT / "l1" / "agent" / "providers").is_dir()


def test_stdlib_python_namespace_matches_cli_namespace() -> None:
    stdlib = PACKAGE_ROOT / "l1" / "stdlib"
    assert {
        "mdblocks",
        "prefix",
        "refs",
        "utils",
    } <= {path.name for path in stdlib.iterdir() if path.is_dir()}
    assert not any(
        (PACKAGE_ROOT / name).exists()
        for name in ("mdblocks", "prefix", "refs", "utils")
    )


def test_skw_owns_the_retained_document_kernel() -> None:
    assert (PACKAGE_ROOT / "l1" / "skw" / "document.py").is_file()
    assert not (PACKAGE_ROOT / "l1" / "skw" / "network.py").exists()
    assert not (PACKAGE_ROOT / "skillware").exists()


def test_native_surfaces_do_not_import_skillware() -> None:
    from tarav.l0.kernel import TaravObject, entity
    from tarav.l1.surfaces import SurfacesWorkflow
    from tarav.l1.surfaces.markdown import LineMarkdownModel, MarkdownNormalModel
    from tarav.l1.surfaces.python import PythonNormalModel

    for model in (MarkdownNormalModel, LineMarkdownModel, PythonNormalModel):
        assert issubclass(model, TaravObject)
        assert entity(model).workflow is SurfacesWorkflow()
    imports = _top_level_import_graph()
    assert "skw" not in imports["surfaces"]
    # Chatlas stopped consuming native surfaces when the Chat.Index Markdown
    # projection was removed.
    assert "stdlib" in {
        name for name, targets in imports.items() if "surfaces" in targets
    }
    assert "surfaces" not in imports["chatlas"]


def test_subsystem_import_graph_is_acyclic() -> None:
    graph = _top_level_import_graph()
    graph.pop("<root>", None)
    for targets in graph.values():
        targets.discard("runtime")
        targets.discard("cli")
    assert _strongly_connected_components(graph) == ()


def test_layered_modules_do_not_import_higher_layers() -> None:
    for level in range(4):
        for path in (PACKAGE_ROOT / f"l{level}").rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = (alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    names = (node.module,)
                else:
                    continue
                for name in names:
                    if name.startswith("tarav.l") and name[7:8].isdigit():
                        assert int(name[7]) <= level, (path, name)


def test_kernel_is_a_dependency_clean_application_base() -> None:
    imports = _top_level_import_graph()

    assert imports["l0.kernel"] == set()
    assert "l0.kernel" in imports["lines.block"]
    assert "l0.kernel" in imports["archive"]
    assert "l0.kernel" in imports["records"]
    assert "poi.foundation" in imports["records"]
    assert "records" not in imports["l0.kernel"]
    assert imports["references"] <= {"l0.kernel", "poi.foundation"}
    assert "references" in imports["archive"]
    assert "record_archive" not in imports
    assert not (PACKAGE_ROOT / "record_archive" / "__init__.py").exists()
    assert not (PACKAGE_ROOT / "harness").exists()


def test_records_workflow_owns_navigation_without_owning_contributed_storage() -> None:
    # tarav.breadcrumb b38987be1706
    from tarav.l1.records import RecordsRoot, TaravRecords
    from tarav.l3.runtime import create_runtime

    runtime = create_runtime()
    assert runtime.workflows.get("Tarav.Workflow.Records") is TaravRecords
    assert entity(RecordsRoot).workflow is TaravRecords()
    assert "archive" not in _top_level_import_graph()["records"]
    assert "scoring" not in _top_level_import_graph()["records"]


def test_root_is_metadata_only_and_runtime_wires_services() -> None:
    import subprocess
    import sys

    subprocess.run([sys.executable, "-c", '''
import sys
import tarav
assert not any(name.startswith("tarav.") for name in sys.modules)
for name in ("ARCHIVE", "get_runtime", "set_runtime", "load_object"):
    assert not hasattr(tarav, name)
from tarav.l0.kernel.current import current_records
try:
    current_records()
except RuntimeError:
    pass
else:
    raise AssertionError("root must not configure providers")
from tarav.l3.runtime import get_runtime
from tarav.l0.kernel import entity, TaravObject
runtime = get_runtime()
assert current_records() is runtime.records
assert entity(TaravObject).workflow is not None
'''], check=True, capture_output=True, text=True)


def test_l0_import_does_not_initialize_composed_domains() -> None:
    import subprocess
    import sys

    for imported in ("tarav.l0._core", "tarav.l0.kernel", "tarav.l0.project"):
        subprocess.run(
            [sys.executable, "-c", f"""
import sys
import {imported}
for forbidden in ('tarav.l1.archive', 'tarav.l1.context', 'tarav.l3.runtime',
                  'tarav.l3.cli', 'tarav.daemon'):
    assert forbidden not in sys.modules, forbidden
from tarav.l1.archive.records import ARCHIVE
assert ARCHIVE is not None
"""],
            check=True,
            capture_output=True,
            text=True,
        )


def test_l1_domain_imports_do_not_initialize_runtime() -> None:
    import subprocess
    import sys

    code = """
import sys
from tarav.l1 import archive, context, loading, project
assert 'tarav.l3.runtime' not in sys.modules
assert 'tarav.l2' not in sys.modules
for old_path in ('tarav.archive', 'tarav.context', 'tarav.loading', 'tarav.project'):
    assert old_path not in sys.modules
"""
    subprocess.run(
        [sys.executable, "-c", code], check=True, capture_output=True, text=True
    )


def test_running_environment_is_explicit_and_shared_with_type_dispatch() -> None:
    from tarav.l0.kernel import TaravEnvironment
    from tarav.l3.runtime import create_runtime

    runtime = create_runtime()
    assert isinstance(runtime.environment, TaravEnvironment)
    assert runtime.records.environment is runtime.environment
    assert runtime.records.resolve_type("Tarav.Environment") is TaravEnvironment


def test_registered_workflows_have_code_owned_constitutions() -> None:
    from tarav.l3.runtime import create_runtime

    for workflow in create_runtime().workflows.workflows.values():
        constitution = workflow.__dict__.get("constitution")
        assert isinstance(constitution, str) and constitution.strip()
        assert "constitution" not in entity(workflow).records.to_record()


def test_context_and_test_workspace_stay_above_kernel() -> None:
    from tarav.l1.context import ContextExplorer
    from tarav.l1.context.workflow import ContextWorkflow
    from tarav.l0.kernel.records import TaravObject
    from tarav.l3.runtime import create_runtime
    from tarav.l2.tests.workflow import TestsWorkflow
    from tarav.l2.tests.navigation import TestEntity, NavigationTestsWorkflow
    from tarav.l2.tests.scoring import ScoringTestsWorkflow

    imports = _top_level_import_graph()
    assert imports["l0.kernel"] == set()
    assert not (PACKAGE_ROOT / "l2" / "context").exists()
    assert not (PACKAGE_ROOT / "l0" / "kernel" / "context.py").exists()
    assert (PACKAGE_ROOT / "l2" / "tests" / "workflow.py").is_file()
    assert (PACKAGE_ROOT / "l2" / "tests" / "navigation.py").is_file()
    assert (PACKAGE_ROOT / "l2" / "tests" / "scoring.py").is_file()

    runtime = create_runtime()
    assert runtime.workflows.get("Tarav.Workflow.Context") is ContextWorkflow
    assert issubclass(ContextExplorer, TaravObject)
    assert entity(ContextExplorer).name == "Tarav.Context.Explorer"
    assert entity(ContextExplorer).workflow_ship == ContextWorkflow().id
    assert runtime.records.resolve_type("Tarav.Test.Entity") is TestEntity
    assert runtime.workflows.get("Tarav.Workflow.Tests") is TestsWorkflow
    assert runtime.workflows.get("Tarav.Workflow.Tests.Navigation") is NavigationTestsWorkflow
    assert runtime.workflows.get("Tarav.Workflow.Tests.Scoring") is ScoringTestsWorkflow
    assert NavigationTestsWorkflow().workflow is TestsWorkflow()
    assert ScoringTestsWorkflow().workflow is TestsWorkflow()
    assert entity(TestEntity).workflow_ship == NavigationTestsWorkflow().id


def test_ship_identity_is_owned_by_kernel_and_used_by_lines() -> None:
    from tarav.l1.lines import Line
    from tarav.l0.kernel import Ship, TypeShip, locate_record_type

    assert issubclass(TypeShip, Ship)
    assert isinstance(entity(Line).id, TypeShip)
    assert callable(locate_record_type)


def test_python_workflow_is_foundational_and_project_specializes_it() -> None:
    imports = _top_level_import_graph()

    assert imports["python_env"] == {"l0._core", "l0.kernel"}
    assert "project.runner" not in imports["python_env"]
    assert "python_env" in imports["project.runner"]
    assert (PACKAGE_ROOT / "l1" / "python_env" / "commands.py").is_file()


def test_promoted_tarav_domains_have_normal_package_ownership() -> None:
    from tarav.l3.cli.cli import build_parser

    assert (PACKAGE_ROOT / "l1" / "archive" / "commands.py").is_file()
    assert (PACKAGE_ROOT / "l1" / "breadcrumbs" / "commands.py").is_file()
    assert not (PACKAGE_ROOT / "l2" / "unsorted" / "commands.py").exists()
    assert not tuple((PACKAGE_ROOT / "l2" / "lines").rglob("*.py"))
    assert not tuple((PACKAGE_ROOT / "l2" / "models").rglob("*.py"))
    assert not tuple((PACKAGE_ROOT / "l2" / "project" / "models").rglob("*.py"))
    assert not tuple((PACKAGE_ROOT / "diagram").glob("*.py"))
    assert "diagram" not in build_parser().format_help()
    assert (PACKAGE_ROOT / "l1" / "bloberia" / "hosted.py").is_file()
    assert (PACKAGE_ROOT / "l0" / "_core" / "record_depot.py").is_file()
    assert not (PACKAGE_ROOT / "tarav2").exists()
    assert not (PACKAGE_ROOT / "indexlab").exists()
    assert not (PACKAGE_ROOT / "mission").exists()
    assert not (PACKAGE_ROOT / "canvas").exists()


def test_breadcrumb_chatlas_integration_is_independently_owned() -> None:
    imports = _top_level_import_graph()

    assert "chatlas" not in imports["breadcrumbs"]
    assert "breadcrumbs" not in imports["chatlas"]
    assert {"breadcrumbs", "chatlas", "surfaces"} <= imports["breadcrumb_workflows"]
    assert (PACKAGE_ROOT / "l2" / "breadcrumb_workflows" / "chatlas_context").is_dir()
    assert (
        PACKAGE_ROOT / "l2" / "breadcrumb_workflows" / "chatlas_context" / "integration.py"
    ).is_file()


def test_the_normal_model_layer_sits_on_capture_and_not_the_other_way() -> None:
    """The Normal Model consumes capture/index mechanics without reversing them.

    Capture and Session Index remain useful without normalization. Only command
    composition may reach upward to expose both layers through one CLI group.
    """

    normal_model = PACKAGE_ROOT / "l1" / "chatlas" / "normal_model"
    reaches_down = False
    for path in (PACKAGE_ROOT / "l1" / "chatlas").rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        modules = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module is not None
        }
        inside = normal_model in path.parents
        if inside:
            reaches_down |= any(
                m.startswith("tarav.l1.chatlas.")
                and not m.startswith("tarav.l1.chatlas.normal_model")
                for m in modules
            )
        elif path.name not in {
            "commands.py",
            "references.py",
            "normal_model_cache.py",
            "workflow.py",
            "sessions.py",
            "search.py",
            "normal_models_index.py",
            "stages.py",
        }:
            # commands.py is the composition point: it builds the one `tarav chatlas`
            # group and hands its subparsers to the layer. Everything else in
            # chatlas/ must stay below the layer, not reach up into it.
            # references.py is an explicit Normal Model consumer exposing typed Turns.
            # normal_model_cache.py is the Chatlas-owned logistical decorator around
            # canonical Normal Model directories.
            # workflow.py is the runtime registration boundary for Chatlas Records.
            # sessions.py consumes the Model reader for explicit Session navigation.
            assert not any(
                m.startswith("tarav.l1.chatlas.normal_model") for m in modules
            ), path
            assert "from .normal_model" not in source, path
    assert reaches_down, "the Normal Model should use Chatlas capture/index mechanics"


def test_hooks_foundation_does_not_import_daemon_adapters() -> None:
    imports = _top_level_import_graph()
    assert "daemon" not in imports["hooks"]


def test_consumers_import_the_normal_model_package_not_its_submodules() -> None:
    """Only the package surface is a supported Normal Model dependency."""

    prefix = "tarav.l1.chatlas.normal_model"
    normal_model = PACKAGE_ROOT / "l1" / "chatlas" / "normal_model"
    offenders: list[str] = []
    for path in PACKAGE_ROOT.rglob("*.py"):
        if normal_model in path.parents or path.name == "normal_model_cache.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            names: tuple[str, ...] = ()
            if isinstance(node, ast.Import):
                names = tuple(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                names = (node.module,)
            for name in names:
                if name.startswith(prefix + "."):
                    offenders.append(f"{path.relative_to(PACKAGE_ROOT)}: {name}")
    assert offenders == [], (
        "import `tarav.l1.chatlas.normal_model`, not its submodules: "
        + "; ".join(sorted(offenders))
    )


# tarav.breadcrumb 8962bfcd4c96
def test_project_mechanics_live_in_the_project_namespace() -> None:
    # Layers only relax dependencies; the Project namespace spans them, and its
    # lowest part is tarav.l0.project. _core holds no Project mechanics.
    imports = _top_level_import_graph()
    assert not (PACKAGE_ROOT / "l0" / "_core" / "project.py").exists()
    assert not (PACKAGE_ROOT / "l0" / "_core" / "project_command_log.py").exists()
    assert "l0.project" not in imports["l0._core"]
    assert imports["l0.project"] <= {"l0._core"}


# tarav.breadcrumb 7db2362b422e
def test_skill_mechanics_know_nothing_of_projects() -> None:
    # How a Project selects and installs skills is a Project integration.
    imports = _top_level_import_graph()
    assert not imports["skills"] & {"l0.project", "project"}
    assert not (PACKAGE_ROOT / "l1" / "skills" / "routing.py").exists()
    assert (PACKAGE_ROOT / "l2" / "project" / "skills" / "routing.py").is_file()


# tarav.breadcrumb 56810d2b4438
def test_project_skill_availability_stays_in_project_workflow() -> None:
    from tarav.l0.kernel import entity
    from tarav.l1.project.skills import ProjectSkills
    from tarav.l1.project.workflow import PROJECT_WORKFLOW_SHIP
    from tarav.l1.skills.folder import FolderSkill
    from tarav.l1.skills.workflow import SKILLS_WORKFLOW_SHIP

    assert entity(ProjectSkills).workflow_ship == PROJECT_WORKFLOW_SHIP
    assert entity(FolderSkill).workflow_ship == SKILLS_WORKFLOW_SHIP


# tarav.breadcrumb f38fded0c826
def test_bypass_entry_is_outside_the_guarded_import_graph() -> None:
    for path in PACKAGE_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert all(not alias.name.startswith("tarav_bypass")
                           for alias in node.names), path
            elif isinstance(node, ast.ImportFrom):
                assert not (node.module or "").startswith("tarav_bypass"), path

    bypass = PACKAGE_ROOT.parent / "tarav_bypass" / "__init__.py"
    tree = ast.parse(bypass.read_text(encoding="utf-8"))
    assert not any(
        isinstance(node, ast.ImportFrom) and (node.module or "").startswith("tarav")
        for node in tree.body
    )
    assert not any(
        isinstance(node, ast.Import) and any(alias.name.startswith("tarav")
                                             for alias in node.names)
        for node in tree.body
    )


# tarav.breadcrumb f5fe14e161df
def test_no_object_keeps_the_record_it_was_loaded_from() -> None:
    """Loading a Record is one way to get an instance; its state lives in the instance."""

    offenders = []
    for path in PACKAGE_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        offenders += [
            f"{path.relative_to(PACKAGE_ROOT)}:{node.lineno}"
            for node in ast.walk(tree)
            if isinstance(node, ast.Attribute) and node.attr == "_record"
        ]
    assert offenders == []
