# $kw: ^test-wayfinder --from Agentos.Wayfinder --from Wayfinder.Reference.Type::Index.Block --note [DF] boundary coverage for canonical references, registry memory, Index resolution, and resolution POIs ^c20260729-46u
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tarav.index.wayfinder import create_index_wayfinder
from tarav.poi.adapters.wayfinder import build_wayfinder_registry_linter_report
from tarav.wayfinder import (
    InvalidWayfinderReference,
    UnsupportedWayfinderReference,
    WayfinderReference,
    WayfinderReferenceRoot,
    WayfinderRegistry,
    WayfinderResolutionPOI,
    WayfinderResolutionResult,
    index_block_reference,
    parse_reference,
    poi_class_reference,
)


def _write_depot(root: Path, *, block: str = "POI.Example") -> Path:
    (root / "design").mkdir(parents=True)
    (root / "000-INDEX.md").write_text(
        f"# Test Index\n\n## Routing\n\n- `design/100-design.md` — {block}\n",
        encoding="utf-8",
    )
    (root / "design" / "100-design.md").write_text(
        "\n".join(
            [
                "****",
                "",
                f"## {block}",
                "",
                f"- [DF] `{block}` is test documentation ^c20260729-46u",
                "- [CT] agents evaluate its instances from this block ^c20260729-46u",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return root


def test_reference_round_trips_canonical_json_and_index_sugar() -> None:
    reference = index_block_reference("demo-pkg", "POI.Example")

    assert reference.as_dict() == {
        "schema": "tarav.wayfinder.reference.v1",
        "type": "index.block",
        "root": {"type": "package.skill", "id": "demo-pkg"},
        "address": "POI.Example",
    }
    assert WayfinderReference.from_json(reference.to_json()) == reference
    assert parse_reference("index://demo-pkg/POI.Example") == reference
    assert poi_class_reference("demo-pkg", "POI.Example") == reference


def test_index_block_resolution_requires_package_skill_root() -> None:
    reference = WayfinderReference(
        type="index.block",
        root=WayfinderReferenceRoot(type="agentos.project", id="demo"),
        address="POI.Example",
    )

    with pytest.raises(UnsupportedWayfinderReference, match="package.skill root"):
        create_index_wayfinder().resolve(reference)


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {
            "schema": "tarav.wayfinder.reference.v0",
            "type": "index.block",
            "root": {"type": "package.skill", "id": "demo-pkg"},
            "address": "POI.Example",
        },
        {
            # the retired agentos-era schema, rejected rather than accepted:
            # the registry carrying it was archived, not migrated in place
            "schema": "agentos.wayfinder.reference.v1",
            "type": "index.block",
            "root": {"type": "package.skill", "id": "demo-pkg"},
            "address": "POI.Example",
        },
        {
            "schema": "tarav.wayfinder.reference.v1",
            "type": "index.block",
            "root": {"type": "package.skill", "id": "demo-pkg"},
            "address": "POI.Example",
            "extra": True,
        },
    ],
)
def test_reference_rejects_noncanonical_json(payload: dict[str, object]) -> None:
    with pytest.raises(InvalidWayfinderReference):
        WayfinderReference.from_dict(payload)


def test_registry_replaces_last_resolution_without_changing_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(
        "TARAV_WAYFINDER_REGISTRY", str(tmp_path / "state" / "registry.json")
    )
    first = _write_depot(tmp_path / "first")
    second = _write_depot(tmp_path / "second")
    root = WayfinderReferenceRoot(type="package.skill", id="demo-pkg")
    registry = WayfinderRegistry()

    registry.register(root, first, relocation_hints=("first hint", {"repo": "demo"}))
    updated = registry.register(root, second, relocation_hints=({"moved": True},))

    assert updated.root == root
    assert updated.path == second.resolve()
    assert updated.relocation_hints == ({"moved": True},)
    assert registry.get(root) == updated
    payload = json.loads(registry.path.read_text(encoding="utf-8"))
    assert payload["schema"] == "tarav.wayfinder.registry.v1"
    assert len(payload["entries"]) == 1


def test_index_resolution_returns_authoritative_block_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(
        "TARAV_WAYFINDER_REGISTRY", str(tmp_path / "state" / "registry.json")
    )
    depot = _write_depot(tmp_path / "demo")
    registry = WayfinderRegistry()
    registry.register(
        WayfinderReferenceRoot(type="package.skill", id="demo-pkg"),
        depot,
        relocation_hints=({"repository": "demo"},),
    )

    result = create_index_wayfinder(registry).resolve(
        poi_class_reference("demo-pkg", "POI.Example")
    )

    assert isinstance(result, WayfinderResolutionResult)
    assert result.target["block_path"] == "POI.Example"
    assert result.target["path"].endswith("design/100-design.md")
    assert "agents evaluate its instances" in result.target["content"]
    assert [step.stage for step in result.trace] == [
        "registry.lookup",
        "index.lookup",
        "index.verify",
    ]


def test_resolution_pois_preserve_reference_trace_and_hints(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(
        "TARAV_WAYFINDER_REGISTRY", str(tmp_path / "state" / "registry.json")
    )
    registry = WayfinderRegistry()
    reference = index_block_reference("demo-pkg", "POI.Missing")

    missing_registration = create_index_wayfinder(registry).resolve(reference)
    assert isinstance(missing_registration, WayfinderResolutionPOI)
    assert missing_registration.kind == "missing"
    assert missing_registration.reference == reference
    assert missing_registration.trace[0].stage == "registry.lookup"
    payload = missing_registration.as_dict()["poi"]
    assert payload["class"]["address"] == "Wayfinder.Resolution.POI"
    assert payload["class_sugar"] == ("index://tarav-pkg/Wayfinder.Resolution.POI")
    assert payload["target"]["reference"] == reference.as_dict()
    assert payload["evidence"]["kind"] == "missing"

    depot = _write_depot(tmp_path / "demo")
    root = WayfinderReferenceRoot(type="package.skill", id="demo-pkg")
    registry.register(root, depot, relocation_hints=("search demo",))
    missing_block = create_index_wayfinder(registry).resolve(reference)
    assert isinstance(missing_block, WayfinderResolutionPOI)
    assert missing_block.kind == "missing"
    assert missing_block.remembered_location == str(depot.resolve())
    assert missing_block.relocation_hints == ("search demo",)
    assert (
        missing_block.instance_id
        == create_index_wayfinder(registry).resolve(reference).instance_id
    )

    for path in sorted(depot.rglob("*"), reverse=True):
        if path.is_file():
            path.unlink()
        elif path.is_dir():
            path.rmdir()
    depot.rmdir()
    stale = create_index_wayfinder(registry).resolve(reference)
    assert isinstance(stale, WayfinderResolutionPOI)
    assert stale.kind == "stale"


def test_duplicate_index_blocks_produce_ambiguous_poi(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(
        "TARAV_WAYFINDER_REGISTRY", str(tmp_path / "state" / "registry.json")
    )
    depot = _write_depot(tmp_path / "demo")
    (depot / "design" / "101-design.md").write_text(
        "****\n\n## POI.Example\n\n- [DF] duplicate ^c20260729-46u\n",
        encoding="utf-8",
    )
    registry = WayfinderRegistry()
    registry.register(
        WayfinderReferenceRoot(type="package.skill", id="demo-pkg"), depot
    )

    result = create_index_wayfinder(registry).resolve(
        index_block_reference("demo-pkg", "POI.Example")
    )

    assert isinstance(result, WayfinderResolutionPOI)
    assert result.kind == "ambiguous"
    assert len(result.candidates) == 2


def test_registry_check_reports_stale_location(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(
        "TARAV_WAYFINDER_REGISTRY", str(tmp_path / "state" / "registry.json")
    )
    depot = _write_depot(tmp_path / "demo")
    registry = WayfinderRegistry()
    registry.register(
        WayfinderReferenceRoot(type="package.skill", id="demo-pkg"), depot
    )
    for path in sorted(depot.rglob("*"), reverse=True):
        if path.is_file():
            path.unlink()
        elif path.is_dir():
            path.rmdir()
    depot.rmdir()

    check = registry.check()

    assert not check.ok
    assert check.findings[0].code == "stale-location"
    report = build_wayfinder_registry_linter_report(
        check,
        registry_path=str(registry.path),
        wayfinder=create_index_wayfinder(registry),
    ).as_dict()
    assert report["pois"][0]["class"]["address"] == (
        "Wayfinder.Registry.Linter/Location.Stale"
    )
    assert report["domain"]["status"] == "poi"
