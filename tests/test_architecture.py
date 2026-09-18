# $kw: ^agentos-python-architecture-contract --from Agent.Navigable.Codebase --from Dependency.Profile.Split --note [CT] maintained namespaces are cohesive and their import graph is acyclic outside the runtime composition root --supp ^c20260811-62u
from __future__ import annotations

import ast
import re
from collections import defaultdict
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "src" / "tarav"


def test_generation_mechanics_have_no_tarav_domain_dependencies() -> None:
    import sys

    tree = ast.parse((PACKAGE_ROOT / "skillware" / "generation.py").read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(alias.name.split(".")[0] in sys.stdlib_module_names
                       for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0
            assert node.module.split(".")[0] in sys.stdlib_module_names


def _top_level_import_graph() -> dict[str, set[str]]:
    graph: dict[str, set[str]] = defaultdict(set)
    for path in PACKAGE_ROOT.rglob("*.py"):
        relative = path.relative_to(PACKAGE_ROOT)
        source = relative.parts[0] if len(relative.parts) > 1 else "<root>"
        # skw.skills is a composition leaf, distinct from skw.network's
        # existing lower-level algorithms consumed by Skillware.
        if relative.as_posix() in {"skw/skills.py", "skw/publication.py", "skw/loading.py"}:
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


def test_skill_specialization_is_not_imported_by_general_skillware():
    graph = _top_level_import_graph()
    assert "skw.skills" not in graph["skillware"]
    assert "skw.skills" not in graph["skw"]


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
    # Chatlas stopped consuming native surfaces when the Chat.Index Markdown
    # projection was removed, and index_model when its parser went: what is left
    # there is line grammar over strings, which needs no surface model.
    assert {
        "skillware",
        "stdlib",
    } <= {name for name, targets in imports.items() if "surfaces" in targets}
    assert "surfaces" not in imports["chatlas"]
    assert "surfaces" not in imports["index_model"]


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
    assert (PACKAGE_ROOT / "diagram" / "commands.py").is_file()
    assert (PACKAGE_ROOT / "bloberia" / "hosted.py").is_file()
    assert (PACKAGE_ROOT / "_core" / "record_depot.py").is_file()
    assert not (PACKAGE_ROOT / "tarav2").exists()
    assert not (PACKAGE_ROOT / "indexlab").exists()
    assert not (PACKAGE_ROOT / "mission").exists()
    assert not (PACKAGE_ROOT / "canvas").exists()


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
        elif path.name not in {"commands.py", "references.py"}:
            # commands.py is the composition point: it builds the one `tarav chatlas`
            # group and hands its subparsers to the layer. Everything else in
            # chatlas/ must stay below the layer, not reach up into it.
            # references.py is an explicit Normal Model consumer exposing typed Turns.
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
        if normal_model in path.parents:
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


def test_the_caret_address_grammar_is_compiled_in_exactly_one_module() -> None:
    """`^c20260820-0u` and `^package-driver-router` are parsed in one place.

    Six ad-hoc regexes across five packages had drifted into two incompatible grammars: a
    strict citation form and a permissive trailing-token form that also matched locator
    names. Nothing reconciled them, so whether a token was a citation depended on which
    module happened to look at it.

    `index_model` is the kernel zone every consumer may import, and `index_model/label.py`
    owns both grammars there. This asserts the seventh copy fails here instead of adding a
    third opinion.
    """

    #: Fragments that only a caret-address pattern contains: an eight-digit date group, or a
    #: character class hung directly off an escaped caret.
    TELLS = (r"\d{8}", r"[0-9]{8}", r"\^[A-Za-z0-9", r"\^[a-z]")

    offenders: list[str] = []
    for path in PACKAGE_ROOT.rglob("*.py"):
        if (PACKAGE_ROOT / "index_model") in path.parents:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            compiled = (
                isinstance(func, ast.Attribute)
                and func.attr == "compile"
                and isinstance(func.value, ast.Name)
                and func.value.id == "re"
            )
            if not compiled or not node.args:
                continue
            pattern = node.args[0]
            if not isinstance(pattern, ast.Constant) or not isinstance(
                pattern.value, str
            ):
                continue
            if any(tell in pattern.value for tell in TELLS):
                offenders.append(
                    f"{path.relative_to(PACKAGE_ROOT)}:{node.lineno}: {pattern.value}"
                )

    assert offenders == [], (
        "the caret address grammar belongs to tarav.index_model.label; these compile their "
        "own: " + "; ".join(sorted(offenders))
    )


#: `X.Linter/Class.Name` — a POI class identity anywhere in the codebase.
_POI_CLASS = re.compile(r'"([A-Z][A-Za-z]+\.Linter/[A-Za-z][A-Za-z.]*[A-Za-z])"')
_POI_BLOCK = re.compile(r"\$kw:\s*([A-Z][A-Za-z]+\.Linter/[A-Za-z][A-Za-z.]*)")


def _poi_classes() -> tuple[dict[str, set[str]], set[str]]:
    emitted: dict[str, set[str]] = defaultdict(set)
    declared: set[str] = set()
    for path in PACKAGE_ROOT.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        for name in _POI_CLASS.findall(source):
            emitted[name].add(str(path.relative_to(PACKAGE_ROOT)))
        declared.update(_POI_BLOCK.findall(source))
    return emitted, declared


# $kw: --from POI.System --note [CT] a POI class is defined by the managed block beside the code that emits it, in every namespace and not only the Index linter's
def test_every_poi_class_is_defined_beside_the_code_that_emits_it() -> None:
    """A class identity is its managed block, so emitting one without a block defines nothing.

    Nothing downstream notices: the report builds the reference from the class name, and a
    reference to a block that does not exist renders exactly like one that does. The check
    has to happen here because the producing code is the only place that knows the class was
    emitted at all.
    """

    emitted, declared = _poi_classes()
    undeclared = {
        name: sorted(files) for name, files in emitted.items() if name not in declared
    }
    assert undeclared == {}, (
        "these POI classes are emitted with no `$kw` block beside their definition: "
        + "; ".join(
            f"{name} ({', '.join(files)})" for name, files in sorted(undeclared.items())
        )
    )


# $kw: --from POI.System --note [CT] one class, one block: a second definition makes the identity ambiguous rather than better documented
def test_every_poi_class_resolves_to_exactly_one_managed_block() -> None:
    """Two definitions of one class is not redundancy, it is an unresolvable identity.

    A class defined both in a package's markdown `poi/` chapter and beside its code resolves
    to neither -- Wayfinder reports `resolves more than once` and the reference is dead. This
    is the failure mode of migrating definitions into the codebase without retiring the copy.
    """

    from tarav.poi import tarav_poi_class_reference
    from tarav.skillware._build_core import find_project_root
    from tarav.skillware.managed_blocks import create_tarav_wayfinder
    from tarav.wayfinder import WayfinderResolutionPOI

    _emitted, declared = _poi_classes()
    wayfinder = create_tarav_wayfinder(project_root=find_project_root(PACKAGE_ROOT))

    unresolved: list[str] = []
    for name in sorted(declared):
        try:
            # A failure to resolve is *returned*, not raised: the resolver reports an
            # unresolvable reference as a POI. Checking only for an exception is how this
            # guard first shipped passing against a class defined in two places at once.
            result = wayfinder.resolve(tarav_poi_class_reference(name))
        except Exception as exc:  # the resolver raises several unrelated types
            unresolved.append(f"{name}: {type(exc).__name__}: {exc}")
            continue
        if isinstance(result, WayfinderResolutionPOI):
            payload = result.as_dict().get("poi", {})
            unresolved.append(f"{name}: {payload.get('situation', payload)}")

    assert unresolved == [], "\n".join(unresolved)


def test_no_poi_class_names_a_superseded_model() -> None:
    """`Current.Model.Only`: "does not resolve" is a check result, "is legacy" is history.

    A class named for the old shape is a second model the checker has to carry and keep
    correct forever, and it takes its subjects out of the count of things that do not
    conform -- which is the only measure of how far the migration has left to go.
    """

    history = ("Legacy", "Deprecated", "Obsolete", "Chatlas1", "Tarav1", "Old")
    _emitted, declared = _poi_classes()
    named = sorted(name for name in declared if any(word in name for word in history))
    assert named == [], (
        "these POI classes name a superseded model rather than a check result: "
        + ", ".join(named)
    )
