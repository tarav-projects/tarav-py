# $kw: ^agentos-python-architecture-contract --from Agent.Navigable.Codebase --from Dependency.Profile.Split --note [CT] maintained namespaces are cohesive and their import graph is acyclic outside the runtime composition root --supp ^c20260811-62u
from __future__ import annotations

import ast
from collections import defaultdict
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "src" / "tarav"


def test_record_interfaces_belong_to_harness():
    from pydantic import BaseModel
    from tarav.harness import TaravObject, isrecordsubclass, issubrecord
    from tarav.skw.document import SkwBlock

    assert issubclass(TaravObject.RecordInterface, BaseModel)
    assert issubrecord(SkwBlock, TaravObject)
    assert isrecordsubclass(SkwBlock, TaravObject)
    assert SkwBlock.preserves_parent_record_interface()


def test_generation_mechanics_have_no_tarav_domain_dependencies() -> None:
    import sys

    tree = ast.parse((PACKAGE_ROOT / "skw" / "generation.py").read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(
                alias.name.split(".")[0] in sys.stdlib_module_names
                for alias in node.names
            )
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0
            assert node.module.split(".")[0] in sys.stdlib_module_names


def _top_level_import_graph() -> dict[str, set[str]]:
    graph: dict[str, set[str]] = defaultdict(set)
    for path in PACKAGE_ROOT.rglob("*.py"):
        relative = path.relative_to(PACKAGE_ROOT)
        source = relative.parts[0] if len(relative.parts) > 1 else "<root>"
        # skw.skills is a composition leaf above the generic SKW document kernel.
        if relative.as_posix() in {
            "skw/skills.py",
            "skw/publication.py",
            "skw/loading.py",
            "skw/pois.py",
        }:
            source = "skw.skills"
        graph[source]
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            imported: tuple[str, ...] = ()
            if isinstance(node, ast.Import):
                imported = tuple(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                imported = (node.module,)
            for name in imported:
                if not name.startswith("tarav."):
                    continue
                target = name.split(".", 2)[1]
                if name == "tarav.skw.skills" or name.startswith("tarav.skw.skills."):
                    target = "skw.skills"
                if target != source:
                    graph[source].add(target)
    return graph


def test_generic_document_does_not_import_skill_specialization():
    tree = ast.parse((PACKAGE_ROOT / "skw" / "document.py").read_text())
    imports = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    assert "tarav.skw.skills" not in imports


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
        "gemini",
        "home",
        "openclaw",
        "opencode",
        "pi",
        "providers.py",
    }
    present = {path.name for path in PACKAGE_ROOT.iterdir()}
    assert forbidden.isdisjoint(present)
    assert (PACKAGE_ROOT / "agent" / "providers").is_dir()


def test_stdlib_python_namespace_matches_cli_namespace() -> None:
    stdlib = PACKAGE_ROOT / "stdlib"
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
    assert (PACKAGE_ROOT / "skw" / "document.py").is_file()
    assert not (PACKAGE_ROOT / "skw" / "network.py").exists()
    assert not (PACKAGE_ROOT / "skillware").exists()


def test_native_surfaces_do_not_import_skillware() -> None:
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


def test_harness_is_a_dependency_clean_application_base() -> None:
    imports = _top_level_import_graph()

    assert imports["harness"] == set()
    assert "harness" in imports["diagram"]
    assert "harness" in imports["archive"]
    assert "harness" in imports["navigation"]
    assert "poi" in imports["navigation"]
    assert "navigation" not in imports["harness"]
    assert imports["references"] <= {"harness"}
    assert "references" in imports["archive"]


def test_ship_identity_is_owned_by_harness_and_only_declared_by_diagram() -> None:
    import tarav.diagram as diagram
    from tarav.harness import Ship, TypeShip, locate_record_type

    assert issubclass(TypeShip, Ship)
    assert diagram.Ship is Ship
    assert isinstance(diagram.LineShipRecord.type_ship, TypeShip)
    assert diagram.locate_record_type is locate_record_type


def test_python_env_reports_the_environment_without_provisioning_one() -> None:
    imports = _top_level_import_graph()

    assert imports["python_env"] == set()
    assert (PACKAGE_ROOT / "python_env" / "commands.py").is_file()


def test_promoted_tarav_domains_have_normal_package_ownership() -> None:
    assert (PACKAGE_ROOT / "archive" / "commands.py").is_file()
    assert (PACKAGE_ROOT / "breadcrumbs" / "commands.py").is_file()
    assert (PACKAGE_ROOT / "diagram" / "commands.py").is_file()
    assert (PACKAGE_ROOT / "bloberia" / "hosted.py").is_file()
    assert (PACKAGE_ROOT / "_core" / "record_depot.py").is_file()
    assert not (PACKAGE_ROOT / "tarav2").exists()
    assert not (PACKAGE_ROOT / "indexlab").exists()
    assert not (PACKAGE_ROOT / "mission").exists()
    assert not (PACKAGE_ROOT / "canvas").exists()


def test_breadcrumb_chatlas_integration_is_independently_owned() -> None:
    imports = _top_level_import_graph()

    assert "chatlas" not in imports["breadcrumbs"]
    assert "breadcrumbs" not in imports["chatlas"]
    assert {"breadcrumbs", "chatlas", "surfaces"} <= imports["breadcrumb_workflows"]
    assert (PACKAGE_ROOT / "breadcrumb_workflows" / "chatlas_context").is_dir()
    assert (
        PACKAGE_ROOT / "breadcrumb_workflows" / "chatlas_context" / "integration.py"
    ).is_file()


def test_the_normal_model_layer_sits_on_capture_and_not_the_other_way() -> None:
    """The Normal Model consumes capture/index mechanics without reversing them.

    Capture and Session Index remain useful without normalization. Only command
    composition may reach upward to expose both layers through one CLI group.
    """

    normal_model = PACKAGE_ROOT / "chatlas" / "normal_model"
    reaches_down = False
    for path in (PACKAGE_ROOT / "chatlas").rglob("*.py"):
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
                m.startswith("tarav.chatlas.")
                and not m.startswith("tarav.chatlas.normal_model")
                for m in modules
            )
        elif path.name not in {"commands.py", "references.py", "normal_model_cache.py"}:
            # commands.py is the composition point: it builds the one `tarav chatlas`
            # group and hands its subparsers to the layer. Everything else in
            # chatlas/ must stay below the layer, not reach up into it.
            # references.py is an explicit Normal Model consumer exposing typed Turns.
            # normal_model_cache.py is the Chatlas-owned logistical decorator around
            # canonical Normal Model directories.
            assert not any(
                m.startswith("tarav.chatlas.normal_model") for m in modules
            ), path
            assert "from .normal_model" not in source, path
    assert reaches_down, "the Normal Model should use Chatlas capture/index mechanics"


def test_hooks_foundation_does_not_import_daemon_adapters() -> None:
    imports = _top_level_import_graph()
    assert "daemon" not in imports["hooks"]


def test_consumers_import_the_normal_model_package_not_its_submodules() -> None:
    """Only the package surface is a supported Normal Model dependency."""

    prefix = "tarav.chatlas.normal_model"
    normal_model = PACKAGE_ROOT / "chatlas" / "normal_model"
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
        "import `tarav.chatlas.normal_model`, not its submodules: "
        + "; ".join(sorted(offenders))
    )
