"""Index.Depot.Dependency: local declarations resolved through Wayfinder.

Slice 1 — the global Wayfinder registry (package identity -> last location).
Slice 2 — the local `000-INDEX.md` dependency-name declaration.
Slice 3 — directed, non-transitive visibility resolution.
"""

import json
from pathlib import Path

from tarav.index.depot_deps import (
    declared_dependency_names,
    load_depot_registry,
    resolve_dependency_depots,
)
from tarav.wayfinder import WayfinderReferenceRoot, WayfinderRegistry


def _write_global_config(home: Path, index_block: dict) -> None:
    home.mkdir(parents=True, exist_ok=True)
    (home / "config.json").write_text(
        json.dumps({"class": "agentos.global.config", **index_block}),
        encoding="utf-8",
    )


def _register_depots(home: Path, depots: dict[str, Path]) -> None:
    registry = WayfinderRegistry(home=home)
    for name, path in depots.items():
        registry.register(
            WayfinderReferenceRoot(type="package.skill", id=name),
            path,
        )


# ---- Slice 1: registry reader ------------------------------------------------


def test_registry_resolves_declared_depots(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "home"
    pkg = _write_router(tmp_path / "pkg", "# pkg\n")
    chat = _write_router(tmp_path / "chat", "# chat\n")
    _register_depots(home, {"tarav-pkg": pkg, "tarav-chatlas-pkg": chat})
    monkeypatch.setenv("TARAV_HOME", str(home))
    registry = load_depot_registry()
    assert registry == {"tarav-pkg": pkg, "tarav-chatlas-pkg": chat}


def test_registry_empty_when_config_or_key_missing(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv("TARAV_HOME", str(home))
    assert load_depot_registry() == {}  # no file
    _write_global_config(home, {"skills": {"routing": {"sources": {}}}})
    assert load_depot_registry() == {}  # unrelated config is not a registry


def test_legacy_index_depots_do_not_establish_registration(
    tmp_path: Path, monkeypatch
) -> None:
    home = tmp_path / "home"
    depot = _write_router(tmp_path / "legacy", "# legacy\n")
    _write_global_config(
        home,
        {"index": {"depots": {"legacy-pkg": {"path": str(depot)}}}},
    )
    monkeypatch.setenv("TARAV_HOME", str(home))
    assert load_depot_registry() == {}


# ---- Slice 2: local declaration reader ---------------------------------------


def _write_router(depot: Path, body: str) -> Path:
    depot.mkdir(parents=True, exist_ok=True)
    (depot / "000-INDEX.md").write_text(body, encoding="utf-8")
    return depot


def test_declared_names_parsed_from_router(tmp_path: Path) -> None:
    depot = _write_router(
        tmp_path / "d",
        "# INDEX\n\n> `Index.Depot.Dependency`: tarav-pkg, tarav-chatlas-pkg\n\n## Routing\n",
    )
    assert declared_dependency_names(depot) == ["tarav-pkg", "tarav-chatlas-pkg"]


def test_declared_names_empty_without_directive(tmp_path: Path) -> None:
    depot = _write_router(tmp_path / "d", "# INDEX\n\n## Routing\n")
    assert declared_dependency_names(depot) == []


# ---- Slice 3: directed, non-transitive resolution ----------------------------


def test_resolution_is_direct_and_non_transitive(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "home"
    b = tmp_path / "b"
    c = tmp_path / "c"
    _write_router(b, "# B\n\n> `Index.Depot.Dependency`: cc\n")  # B depends on C
    _write_router(c, "# C\n")
    _register_depots(home, {"bb": b, "cc": c})
    monkeypatch.setenv("TARAV_HOME", str(home))

    d = _write_router(tmp_path / "d", "# D\n\n> `Index.Depot.Dependency`: bb\n")  # D depends on B only
    resolved, unresolved = resolve_dependency_depots(d)
    assert resolved == [b]  # direct dep only, C not pulled in transitively
    assert unresolved == []


def test_declared_name_absent_from_registry_is_reported(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv("TARAV_HOME", str(home))
    d = _write_router(tmp_path / "d", "# D\n\n> `Index.Depot.Dependency`: ghost\n")
    resolved, unresolved = resolve_dependency_depots(d)
    assert resolved == []
    assert unresolved == ["ghost"]


# ---- default_depends (the tarav-pkg prelude) -------------------------------


def _write_index_config(home: Path, default_depends: list[str]) -> None:
    home.mkdir(parents=True, exist_ok=True)
    (home / "config.json").write_text(
        json.dumps({
            "class": "agentos.global.config",
            "index": {
                "default_depends": default_depends,
            },
        }),
        encoding="utf-8",
    )


def test_registered_depot_inherits_default_depends(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "home"
    pkg = _write_router(tmp_path / "pkg", "# pkg\n")
    other = _write_router(tmp_path / "other", "# other\n")  # no directive of its own
    _write_index_config(home, ["tarav-pkg"])
    _register_depots(home, {"tarav-pkg": pkg, "other-pkg": other})
    monkeypatch.setenv("TARAV_HOME", str(home))

    resolved, unresolved = resolve_dependency_depots(other)
    assert resolved == [pkg]  # inherits the prelude
    assert unresolved == []


def test_base_depot_does_not_depend_on_itself(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "home"
    pkg = _write_router(tmp_path / "pkg", "# pkg\n")
    _write_index_config(home, ["tarav-pkg"])
    _register_depots(home, {"tarav-pkg": pkg})
    monkeypatch.setenv("TARAV_HOME", str(home))

    resolved, _ = resolve_dependency_depots(pkg)
    assert resolved == []  # self-exclusion: tarav-pkg is not its own dep


def test_unregistered_depot_does_not_inherit_defaults(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "home"
    pkg = _write_router(tmp_path / "pkg", "# pkg\n")
    _write_index_config(home, ["tarav-pkg"])
    _register_depots(home, {"tarav-pkg": pkg})
    monkeypatch.setenv("TARAV_HOME", str(home))

    stranger = _write_router(tmp_path / "stranger", "# s\n")  # not in the registry
    resolved, _ = resolve_dependency_depots(stranger)
    assert resolved == []  # defaults are a policy over registered depots only
