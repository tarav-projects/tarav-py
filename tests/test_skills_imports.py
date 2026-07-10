from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from agentos._core.errors import CliError
from agentos.skills.commands import _cmd_skills_imports
from agentos.skills.imports import check_package_imports, discover_import_manifests

MODULE = """# gr-survey module

## Selector

- take the head of the density worklist
- zero-density blocks go to grounding first

## Loop

- probe one tension at a time
"""

MANIFEST = """# Imports — references/gr-survey.md

****

## Concept.Alpha

- binding: pointer
****

## @pkg/docs/craft.md#Selector Rules

- binding: copy
- lands: #Selector
****

## Concept.Beta

- binding: derived
- lands: #Loop
- context: compress the beta vocabulary into one table
****
"""

CRAFT = """# craft

## Selector Rules

- take the head of the density worklist
- zero-density blocks go to grounding first

## Other

- unrelated
"""

DEPOT_CHAPTER = """> router

****

## Concept.Alpha

- alpha line
****
"""


def _write_package(root: Path) -> Path:
    pkg = root / "pkg"
    (pkg / "references").mkdir(parents=True)
    (pkg / "docs").mkdir(parents=True)
    (pkg / "build").mkdir(parents=True)
    (pkg / "references" / "gr-survey.md").write_text(MODULE, encoding="utf-8")
    (pkg / "docs" / "craft.md").write_text(CRAFT, encoding="utf-8")
    (pkg / "build" / "references-gr-survey-imports.md").write_text(MANIFEST, encoding="utf-8")
    return pkg


def _write_depot(root: Path) -> Path:
    depot = root / "depot"
    (depot / "design").mkdir(parents=True)
    (depot / "000-INDEX.md").write_text("- `design/100-design.md` — Concept.Alpha\n", encoding="utf-8")
    (depot / "design" / "100-design.md").write_text(DEPOT_CHAPTER, encoding="utf-8")
    return depot


def test_discovery_resolves_consumer_and_parses_declarations(tmp_path: Path) -> None:
    pkg = _write_package(tmp_path)
    manifests = discover_import_manifests(pkg)
    assert len(manifests) == 1
    manifest = manifests[0]
    assert manifest.consumer == Path("references/gr-survey.md")
    assert [d.binding for d in manifest.declarations] == ["pointer", "copy", "derived"]
    copy = manifest.declarations[1]
    assert copy.target == "@pkg/docs/craft.md#Selector Rules"
    assert copy.lands == "#Selector"
    derived = manifest.declarations[2]
    assert derived.context_lines


def test_discovery_flags_ambiguous_and_unresolved_consumers(tmp_path: Path) -> None:
    pkg = _write_package(tmp_path)
    (pkg / "references" / "gr").mkdir()
    (pkg / "references" / "gr" / "survey.md").write_text("x\n", encoding="utf-8")
    (pkg / "build" / "nonexistent-module-imports.md").write_text("# empty\n", encoding="utf-8")
    manifests = discover_import_manifests(pkg)
    by_name = {m.path.name: m for m in manifests}
    assert by_name["references-gr-survey-imports.md"].consumer is None  # ambiguous now
    assert "ambiguous" in (by_name["references-gr-survey-imports.md"].problem or "")
    assert by_name["nonexistent-module-imports.md"].consumer is None
    assert "match" in (by_name["nonexistent-module-imports.md"].problem or "")


def test_check_pointer_copy_and_derived(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pkg = _write_package(tmp_path)
    _write_depot(tmp_path)
    monkeypatch.chdir(tmp_path)
    report = check_package_imports(Path("pkg"), depot_paths=[Path("depot")])
    statuses = {(r.target, r.status) for r in report.results}
    assert ("Concept.Alpha", "resolved") in statuses
    assert ("@pkg/docs/craft.md#Selector Rules", "equal") in statuses
    assert ("Concept.Beta", "skipped-agentic") in statuses
    assert report.finding_count == 0

    # perturb the consumer region -> copy drifts
    module = pkg / "references" / "gr-survey.md"
    module.write_text(module.read_text().replace("density worklist", "density list"), encoding="utf-8")
    report = check_package_imports(Path("pkg"), depot_paths=[Path("depot")])
    drifted = [r for r in report.results if r.status == "drifted"]
    assert len(drifted) == 1
    assert report.finding_count == 1


def test_check_reports_unresolvable_targets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pkg = _write_package(tmp_path)
    monkeypatch.chdir(tmp_path)
    # no depot supplied: ontology pointer is unresolvable
    report = check_package_imports(Path("pkg"), depot_paths=[])
    alpha = next(r for r in report.results if r.target == "Concept.Alpha")
    assert alpha.status == "unresolvable"
    assert "depot" in (alpha.detail or "")
    # missing file target
    manifest = pkg / "build" / "references-gr-survey-imports.md"
    manifest.write_text(manifest.read_text().replace("docs/craft.md", "docs/missing.md"), encoding="utf-8")
    report = check_package_imports(Path("pkg"), depot_paths=[])
    missing = next(r for r in report.results if "missing.md" in r.target)
    assert missing.status == "unresolvable"


def test_cli_imports_json_and_exit_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    pkg = _write_package(tmp_path)
    depot = _write_depot(tmp_path)
    monkeypatch.chdir(tmp_path)
    args = argparse.Namespace(package="pkg", depot=[str(depot.relative_to(tmp_path))], json=True)
    assert _cmd_skills_imports(args) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"]["imports"] == 3
    assert payload["summary"]["findings"] == 0
    assert {r["status"] for r in payload["results"]} == {"resolved", "equal", "skipped-agentic"}

    module = pkg / "references" / "gr-survey.md"
    module.write_text(module.read_text().replace("density worklist", "density list"), encoding="utf-8")
    assert _cmd_skills_imports(args) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"]["findings"] == 1

    with pytest.raises(CliError):
        _cmd_skills_imports(argparse.Namespace(package="nonexistent", depot=[], json=True))
