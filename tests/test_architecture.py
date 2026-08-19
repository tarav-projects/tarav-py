# $kw: ^agentos-python-architecture-contract --from Agent.Navigable.Codebase --from Dependency.Profile.Split --note [CT] maintained namespaces are cohesive and their import graph is acyclic outside the runtime composition root --supp ^c20260811-62u
from __future__ import annotations

import ast
from collections import defaultdict
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "src" / "tarav"


def _top_level_import_graph() -> dict[str, set[str]]:
    graph: dict[str, set[str]] = defaultdict(set)
    for path in PACKAGE_ROOT.rglob("*.py"):
        relative = path.relative_to(PACKAGE_ROOT)
        source = relative.parts[0] if len(relative.parts) > 1 else "<root>"
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
                if target != source:
                    graph[source].add(target)
    return graph


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


def test_skw_network_is_shared_without_duplicate_ownership() -> None:
    assert (PACKAGE_ROOT / "skw" / "network.py").is_file()
    assert not (PACKAGE_ROOT / "skillware" / "network.py").exists()


def test_native_surfaces_do_not_import_skillware() -> None:
    imports = _top_level_import_graph()
    assert "skillware" not in imports["surfaces"]
    assert {
        "chatlas",
        "index_model",
        "skillware",
        "stdlib",
    } <= {name for name, targets in imports.items() if "surfaces" in targets}


def test_subsystem_import_graph_is_acyclic() -> None:
    graph = _top_level_import_graph()
    graph.pop("<root>", None)
    for targets in graph.values():
        targets.discard("runtime")
        targets.discard("cli")
    assert _strongly_connected_components(graph) == ()


def test_the_lossless_layer_sits_on_chatlas_and_not_the_other_way() -> None:
    """`chatlas/lossless/` is the loss-preserving layer, not a second chatlas.

    It reads the archive, the session index, paths, and providers that
    `chatlas/` owns. Nothing outside `lossless/` may import back into it, or the
    layering is a circle and the storage side starts depending on the model
    built from it.
    """

    lossless = PACKAGE_ROOT / "chatlas" / "lossless"
    reaches_down = False
    for path in (PACKAGE_ROOT / "chatlas").rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        modules = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module is not None
        }
        inside = lossless in path.parents
        if inside:
            reaches_down |= any(
                m.startswith("tarav.chatlas.") and not m.startswith("tarav.chatlas.lossless")
                for m in modules
            )
        elif path.name != "commands.py":
            # commands.py is the composition point: it builds the one `tarav chatlas`
            # group and hands its subparsers to the layer. Everything else in
            # chatlas/ must stay below the layer, not reach up into it.
            assert not any(m.startswith("tarav.chatlas.lossless") for m in modules), path
            assert "from .lossless" not in source, path
    assert reaches_down, "the lossless layer should be using what chatlas owns"


def test_chatlas2_text_anonymizer_has_no_model_or_provider_dependency() -> None:
    path = PACKAGE_ROOT / "chatlas" / "lossless" / "anonymizer.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imported = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    imported.update(
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    )
    assert not any(name.startswith("tarav") for name in imported)


def test_hooks_foundation_does_not_import_daemon_adapters() -> None:
    imports = _top_level_import_graph()
    assert "daemon" not in imports["hooks"]
