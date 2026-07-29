from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from agentos.poi import (
    DuplicatePOIClass,
    POICatalog,
    POIClassRegistration,
    POIInstance,
    POILocation,
    UnknownPOIClass,
    build_poi_report,
)
from agentos.poi.commands import register_poi_commands
from agentos.wayfinder import (
    Wayfinder,
    WayfinderReferenceRoot,
    WayfinderRegistry,
    index_block_reference,
)


def _write_depot(root: Path, block: str = "Example.Linter/Problem") -> Path:
    (root / "poi").mkdir(parents=True)
    (root / "000-INDEX.md").write_text(
        f"# Example Index\n\n## poi\n\n- `poi/100-poi.md` - {block}\n",
        encoding="utf-8",
    )
    (root / "poi" / "100-poi.md").write_text(
        "\n".join(
            (
                "****",
                "",
                f"## {block}",
                "",
                "- [DF] the target contains a reviewable problem ^c20260729-47u",
                "- [CT] inspect the concrete evidence before resolving it",
                "",
            )
        ),
        encoding="utf-8",
    )
    return root


def _registration(
    code: str = "Example.Linter/Problem",
    package: str = "example-pkg",
) -> POIClassRegistration:
    return POIClassRegistration(
        finding_code=code,
        reference=index_block_reference(package, code),
    )


def _instance(
    *,
    line: int = 7,
    situation: str = "the target has a problem",
    evidence: dict[str, object] | None = None,
) -> POIInstance:
    return POIInstance.create(
        class_reference=_registration().reference,
        target=POILocation(path="design/100-design.md", line=line),
        severity="warning",
        situation=situation,
        evidence=evidence or {"observed": "problem"},
    )


def test_catalog_composes_class_references_and_rejects_duplicates() -> None:
    first = POICatalog((_registration(),))
    second_registration = _registration(
        code="Other.Linter/Problem",
        package="other-pkg",
    )
    composed = POICatalog.compose(first, POICatalog((second_registration,)))

    assert composed.require("Example.Linter/Problem") == _registration().reference
    assert composed.require("Other.Linter/Problem") == second_registration.reference
    with pytest.raises(UnknownPOIClass, match="Missing.Linter/Problem"):
        composed.require("Missing.Linter/Problem")
    with pytest.raises(DuplicatePOIClass, match="Example.Linter/Problem"):
        POICatalog((_registration(), _registration()))


def test_catalog_discovers_classes_from_registered_poi_chapters(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "AGENTOS_WAYFINDER_REGISTRY",
        str(tmp_path / "state" / "registry.json"),
    )
    depot = _write_depot(tmp_path / "depot")
    registry = WayfinderRegistry()
    registry.register(
        WayfinderReferenceRoot(type="package.skill", id="example-pkg"),
        depot,
    )

    catalog = POICatalog.discover(registry=registry)

    assert catalog.require("Example.Linter/Problem") == _registration().reference


def test_catalog_ignores_blocks_outside_poi_chapters(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "AGENTOS_WAYFINDER_REGISTRY",
        str(tmp_path / "state" / "registry.json"),
    )
    depot = _write_depot(tmp_path / "depot")
    (depot / "design").mkdir()
    (depot / "design" / "100-design.md").write_text(
        "****\n\n## Example.Linter/NotAClass\n\n- [DF] ordinary design block\n",
        encoding="utf-8",
    )
    registry = WayfinderRegistry()
    registry.register(
        WayfinderReferenceRoot(type="package.skill", id="example-pkg"),
        depot,
    )

    catalog = POICatalog.discover(registry=registry)

    with pytest.raises(UnknownPOIClass, match="Example.Linter/NotAClass"):
        catalog.require("Example.Linter/NotAClass")


def test_poi_instance_identity_is_deterministic_for_material_occurrence() -> None:
    first = _instance()
    repeated = _instance()
    moved = _instance(line=8)
    reworded = _instance(situation="the target has a differently worded problem")
    changed = _instance(evidence={"observed": "different problem"})

    assert first == repeated
    assert first.instance_id == repeated.instance_id
    assert first.instance_id == reworded.instance_id
    assert first.instance_id != moved.instance_id
    assert first.instance_id != changed.instance_id
    assert first.as_dict()["class_sugar"] == (
        "index://example-pkg/Example.Linter/Problem"
    )


def test_renderer_groups_instances_and_resolves_class_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "AGENTOS_WAYFINDER_REGISTRY",
        str(tmp_path / "state" / "registry.json"),
    )
    depot = _write_depot(tmp_path / "depot")
    registry = WayfinderRegistry()
    registry.register(
        WayfinderReferenceRoot(type="package.skill", id="example-pkg"),
        depot,
    )

    class CountingWayfinder(Wayfinder):
        calls = 0

        def resolve(self, reference):
            self.calls += 1
            return super().resolve(reference)

    wayfinder = CountingWayfinder(registry)
    report = build_poi_report(
        (_instance(line=7), _instance(line=12)),
        wayfinder=wayfinder,
    )

    assert wayfinder.calls == 1
    assert len(report.groups) == 1
    assert len(report.groups[0].instances) == 2
    assert report.groups[0].description == ("the target contains a reviewable problem")
    text = report.render_text()
    assert text.count("Example.Linter/Problem") == 2
    assert text.count("the target contains a reviewable problem") == 1
    assert "design/100-design.md:7" in text
    assert "design/100-design.md:12" in text
    payload = report.as_dict()
    assert payload["classes"][0]["documentation"]["status"] == "resolved"
    assert len(payload["instances"]) == 2
    json.dumps(payload)


def test_renderer_retains_instances_when_class_resolution_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "AGENTOS_WAYFINDER_REGISTRY",
        str(tmp_path / "state" / "registry.json"),
    )

    report = build_poi_report((_instance(),))

    assert len(report.groups) == 1
    assert len(report.groups[0].instances) == 1
    assert report.groups[0].description is None
    payload = report.as_dict()
    assert payload["classes"][0]["documentation"]["status"] == "poi"
    assert payload["instances"][0]["situation"] == "the target has a problem"
    assert "Documentation unresolved" in report.render_text()


def test_poi_explain_resolves_registered_code_and_reference_sugar(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv(
        "AGENTOS_WAYFINDER_REGISTRY",
        str(tmp_path / "state" / "registry.json"),
    )
    depot = _write_depot(tmp_path / "depot")
    WayfinderRegistry().register(
        WayfinderReferenceRoot(type="package.skill", id="example-pkg"),
        depot,
    )
    parser = argparse.ArgumentParser()
    register_poi_commands(
        parser.add_subparsers(dest="command"),
        catalog=POICatalog((_registration(),)),
    )

    args = parser.parse_args(["poi", "explain", "Example.Linter/Problem"])
    assert args.handler(args) == 0
    text = capsys.readouterr().out
    assert "index://example-pkg/Example.Linter/Problem" in text
    assert "the target contains a reviewable problem" in text

    args = parser.parse_args(
        [
            "poi",
            "explain",
            "index://example-pkg/Example.Linter/Problem",
            "--json",
        ]
    )
    assert args.handler(args) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "resolved"
    assert payload["target"]["block_path"] == "Example.Linter/Problem"


def test_poi_explain_surfaces_resolution_poi(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv(
        "AGENTOS_WAYFINDER_REGISTRY",
        str(tmp_path / "state" / "registry.json"),
    )
    parser = argparse.ArgumentParser()
    register_poi_commands(
        parser.add_subparsers(dest="command"),
        catalog=POICatalog((_registration(),)),
    )

    args = parser.parse_args(["poi", "explain", "Example.Linter/Problem", "--json"])

    assert args.handler(args) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "poi"
    assert payload["poi"]["reference"] == _registration().reference.as_dict()
