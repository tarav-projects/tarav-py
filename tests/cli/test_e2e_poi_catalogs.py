from __future__ import annotations

from pathlib import Path

import pytest

from agentos.anchory.poi import ANCHORY_POI_CLASSES
from agentos.bloberia.poi import BLOBERIA_POI_CLASSES
from agentos.index import _linter_parser_checks, _linter_structure
from agentos.mdblocks.poi import MDBLOCKS_POI_CLASSES
from agentos.poi import POICatalog
from agentos.skillware.poi import SKILLWARE_POI_CLASSES
from agentos.wayfinder import WayfinderReferenceRoot, WayfinderRegistry
from agentos.wayfinder.poi import WAYFINDER_REGISTRY_POI_CLASSES
from agentos.canvas.poi import CANVAS_RENDER_POI_CLASSES
from agentos.chatlas import index_checks
from agentos.chatlas.poi import CHATLAS_COMMIT_POI_CODES
from agentos.cli.cli import main


PROJECT_ROOT = Path(__file__).resolve().parents[3]
PACKAGE_ROOTS = {
    "agentos-pkg": PROJECT_ROOT / "agentos-md" / "skills" / "agentos-pkg",
    "agentos-chatlas-pkg": (
        PROJECT_ROOT / "agentos-chatlas-md" / "skills" / "agentos-chatlas-pkg"
    ),
    "agentos-canvas-pkg": (
        PROJECT_ROOT / "agentos-canvas-md" / "skills" / "agentos-canvas-pkg"
    ),
}


def _module_poi_classes(module: object) -> tuple[str, ...]:
    return tuple(
        value
        for name, value in vars(module).items()
        if name.isupper()
        and not name.startswith("CHECK_")
        and isinstance(value, str)
        and ".Linter/" in value
    )


def _runtime_classes() -> tuple[str, ...]:
    return (
        *_module_poi_classes(_linter_structure),
        *_module_poi_classes(_linter_parser_checks),
        *_module_poi_classes(index_checks),
        *ANCHORY_POI_CLASSES.values(),
        *BLOBERIA_POI_CLASSES.values(),
        *MDBLOCKS_POI_CLASSES.values(),
        *WAYFINDER_REGISTRY_POI_CLASSES.values(),
        "Wayfinder.Resolution.POI",
        *SKILLWARE_POI_CLASSES.values(),
        *(f"Chatlas.Commit.Linter/{code}" for code in CHATLAS_COMMIT_POI_CODES),
        *CANVAS_RENDER_POI_CLASSES.values(),
    )


@pytest.fixture
def poi_registry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> WayfinderRegistry:
    monkeypatch.setenv(
        "AGENTOS_WAYFINDER_REGISTRY",
        str(tmp_path / "wayfinder" / "registry.json"),
    )
    registry = WayfinderRegistry()
    for package_id, package_root in PACKAGE_ROOTS.items():
        registry.register(
            WayfinderReferenceRoot(type="package.skill", id=package_id),
            package_root,
        )
    return registry


def test_included_runtime_classes_have_discoverable_catalog_blocks(
    poi_registry: WayfinderRegistry,
) -> None:
    catalog = POICatalog.discover(registry=poi_registry)

    catalog.require_complete(_runtime_classes())


@pytest.mark.parametrize(
    "class_name",
    (
        "Skillware.Linter/Derived.Stale",
        "Chatlas.Commit.Linter/Turn.UserTextNotVerbatim",
        "Canvas.Linter/Model.Missing",
    ),
)
def test_poi_explain_resolves_across_engaged_package_catalogs(
    class_name: str,
    poi_registry: WayfinderRegistry,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["poi", "explain", class_name]) == 0
    output = capsys.readouterr().out
    assert class_name in output
    assert "Source:" in output
