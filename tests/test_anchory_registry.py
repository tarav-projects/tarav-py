from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentos.anchory import AnchoryDepot
from agentos.anchory.registry import (
    discover_resolve,
    read_registry,
    registry_path,
)


@pytest.fixture()
def registry_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    registry = tmp_path / "registry" / "registry.json"
    monkeypatch.setenv("AGENTOS_ANCHORY_REGISTRY", str(registry))
    monkeypatch.setenv("AGENTOS_ANCHORY_GLOBAL_DEPOT", str(tmp_path / "global-depot"))
    return registry


def _project_depot(tmp_path: Path) -> AnchoryDepot:
    depot = AnchoryDepot(tmp_path / "project" / "anchory")
    depot.write_namespace_meta("chatlas", prefix="c", intention="test ns")
    return depot


def test_depot_touch_auto_registers(registry_env: Path, tmp_path: Path) -> None:
    depot = _project_depot(tmp_path)
    depot.register({"v": 1}, namespace="chatlas", alloc_prefix="20260718", tag="u")

    assert registry_path() == registry_env
    registry = read_registry()
    roots = {entry["root"] for entry in registry["depots"]}
    assert str(depot.root) in roots
    entry = next(e for e in registry["depots"] if e["root"] == str(depot.root))
    assert entry["namespaces"]["chatlas"]["prefix"] == "c"


def test_discover_resolve_finds_depot_from_child_cwd(
    registry_env: Path, tmp_path: Path
) -> None:
    depot = _project_depot(tmp_path)
    entry = depot.register(
        {"v": 1}, namespace="chatlas", alloc_prefix="20260718", tag="u"
    )
    child = tmp_path / "project" / "sub" / "deeper"
    child.mkdir(parents=True)

    hit = discover_resolve(entry.anchor, cwd=child)
    assert hit is not None
    resolution, depot_root = hit
    assert resolution.anchor == "c20260718-0u"
    assert resolution.record == {"v": 1}
    assert depot_root == depot.root


def test_discover_resolve_falls_through_to_global_depot(
    registry_env: Path, tmp_path: Path
) -> None:
    global_depot = AnchoryDepot(tmp_path / "global-depot")
    global_depot.register({"v": "global"}, anchor="g-only")

    hit = discover_resolve("g-only", cwd=tmp_path / "elsewhere-not-created")
    assert hit is not None
    resolution, _root = hit
    assert resolution.record == {"v": "global"}

    assert discover_resolve("missing-everywhere", cwd=tmp_path) is None


def test_corrupt_registry_never_raises(registry_env: Path, tmp_path: Path) -> None:
    registry_env.parent.mkdir(parents=True, exist_ok=True)
    registry_env.write_text("{corrupt", encoding="utf-8")

    depot = _project_depot(tmp_path)
    entry = depot.register(
        {"v": 1}, namespace="chatlas", alloc_prefix="20260718", tag="u"
    )
    assert json.loads(registry_env.read_text(encoding="utf-8"))["depots"]

    hit = discover_resolve(entry.anchor, cwd=tmp_path / "project")
    assert hit is not None
