from __future__ import annotations

import argparse
import json
from pathlib import Path

from agentos.index.commands import _cmd_linter
from agentos.index.linter import (
    REVIEWED_CITE_CLOSURE,
    GateResult,
    LineSupportStanding,
    LinterCheck,
    build_linter_config,
    parsed_linter_kernel_lines,
    render_linter_json,
    render_linter_text,
    run_linter,
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _clean_index(root: Path) -> tuple[Path, Path]:
    index_dir = root / "design"
    appendix_dir = root / "appendix"
    _write(
        root / "000-INDEX.md",
        "# Agentos Index\n\n## design\n\n- `design/100-design.md` — Example.Concept[+1]\n",
    )
    _write(
        index_dir / "100-design.md",
        "****\n## Example.Concept\n\n- compact definition\n****\n",
    )
    _write(
        appendix_dir / "Example.Concept-appendix.md",
        "****\n## Example.Concept/Example.Detail\n\n- depth\n****\n",
    )
    return index_dir, appendix_dir


def _clean_depot(root: Path, *, include_appendix: bool = True) -> Path:
    depot_dir = root / "depot"
    design_dir = depot_dir / "design"
    _write(
        depot_dir / "000-INDEX.md",
        "# Agentos Index\n\n## design\n\n- `design/100-design.md` — Example.Concept[+1]\n",
    )
    _write(
        design_dir / "100-design.md",
        "****\n## Example.Concept\n\n- compact definition\n****\n",
    )
    if include_appendix:
        _write(
            depot_dir / "appendix" / "Example.Concept-appendix.md",
            "****\n## Example.Concept/Appendix\n\n- depth\n****\n",
        )
    return depot_dir


def _run(
    *,
    depot_paths: tuple[str, ...] = (),
    index_paths: tuple[str, ...] = (),
    appendix_paths: tuple[str, ...] = (),
    coverage: tuple[str, ...] = (),
    scope_paths: tuple[str, ...] = (),
    warn_unlinked: bool = False,
    include: tuple[str, ...] = (),
    exclude: tuple[str, ...] = (),
):
    config, raw_depot_paths, raw_index_paths, raw_appendix_paths = build_linter_config(
        depot_paths=depot_paths,
        index_paths=index_paths,
        appendix_paths=appendix_paths,
        coverage=coverage,
        scope_paths=scope_paths,
        warn_unlinked=warn_unlinked,
    )
    return run_linter(
        config,
        raw_depot_paths,
        raw_index_paths,
        raw_appendix_paths,
        include=include,
        exclude=exclude,
    )


def _write_registry(home: Path, depots: dict[str, Path]) -> None:
    from agentos.wayfinder import WayfinderReferenceRoot, WayfinderRegistry

    registry = WayfinderRegistry(home=home)
    for name, path in depots.items():
        registry.register(
            WayfinderReferenceRoot(type="package.skill", id=name),
            path,
        )


def _depot_defining(root: Path, concept: str, *, depends: str | None = None) -> Path:
    directive = f"> `Index.Depot.Dependency`: {depends}\n\n" if depends else ""
    _write(
        root / "000-INDEX.md",
        f"# Agentos Index\n\n{directive}## design\n\n- `design/100-design.md` — {concept}\n",
    )
    _write(
        root / "design" / "100-design.md",
        f"****\n## {concept}\n\n- [DF] `{concept}` is defined and leans on `{concept}`\n****\n",
    )
    return root


def test_depot_dependency_collision_surfaces_in_linter(
    monkeypatch, tmp_path: Path
) -> None:
    from agentos.index.linter import DEPOT_COLLISION

    monkeypatch.chdir(tmp_path)
    home = _depot_defining(tmp_path / "home", "Shared.Concept", depends="other-depot")
    other = _depot_defining(tmp_path / "other", "Shared.Concept")
    _write_registry(tmp_path / "agentos-home", {"other-depot": other})
    monkeypatch.setenv("AGENTOS_HOME", str(tmp_path / "agentos-home"))

    state = _run(depot_paths=(str(home),))
    codes = {f.code: f for f in state.findings}
    assert DEPOT_COLLISION in codes
    assert codes[DEPOT_COLLISION].details["concept"] == "Shared.Concept"


def test_depot_dependency_unresolved_name_surfaces_in_linter(
    monkeypatch, tmp_path: Path
) -> None:
    from agentos.index.linter import DEPOT_DEP_UNRESOLVED

    monkeypatch.chdir(tmp_path)
    home = _depot_defining(tmp_path / "home", "Home.Concept", depends="ghost-depot")
    _write_registry(tmp_path / "agentos-home", {})
    monkeypatch.setenv("AGENTOS_HOME", str(tmp_path / "agentos-home"))

    state = _run(depot_paths=(str(home),))
    unresolved = [f for f in state.findings if f.code == DEPOT_DEP_UNRESOLVED]
    assert [f.details["depot"] for f in unresolved] == ["ghost-depot"]


def test_depot_without_declared_dependencies_stays_quiet(
    monkeypatch, tmp_path: Path
) -> None:
    from agentos.index.linter import DEPOT_COLLISION, DEPOT_DEP_UNRESOLVED

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AGENTOS_HOME", str(tmp_path / "empty-home"))
    depot = _clean_depot(tmp_path)
    state = _run(depot_paths=(str(depot),))
    assert not [
        f for f in state.findings if f.code in {DEPOT_COLLISION, DEPOT_DEP_UNRESOLVED}
    ]


def test_index_linter_accepts_block_path_headings_in_new_layout(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    depot_dir = _clean_depot(tmp_path)
    _write(
        depot_dir / "design" / "100-design.md",
        "\n".join(
            [
                "****",
                "## Agentos.Index.System/Appendix",
                "",
                "- appendix depth",
                "****",
                "## Block.Path/Concept.Scoping",
                "",
                "- scoped child",
                "****",
                "## Agentos.Index.System/Flat.File.Design/Appendix",
                "",
                "- multi-segment free labels",
                "****",
                "",
            ]
        ),
    )

    state = _run(
        index_paths=("depot/design",),
        appendix_paths=("depot/appendix",),
    )

    assert not any(
        finding.code == "Index.Linter/Concept.InvalidHeading"
        for finding in state.findings
    )


def test_index_linter_rejects_old_index_suffix_in_chapter_directory(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    depot_dir = _clean_depot(tmp_path, include_appendix=False)
    _write(
        depot_dir / "design" / "100-index.md",
        "****\n## Example.Other\n\n- old suffix\n****\n",
    )

    state = _run(index_paths=("depot/design",))

    assert any(
        finding.code == "Index.Linter/Index.InvalidFilename"
        and finding.path == "depot/design/100-index.md"
        for finding in state.findings
    )


def test_index_linter_clean_surface_renders_text_and_json(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    index_dir, appendix_dir = _clean_index(tmp_path)

    state = _run(
        index_paths=(index_dir.name,),
        appendix_paths=(appendix_dir.name,),
    )

    assert state.summary()["error_count"] == 0
    assert state.summary()["warning_count"] == 2
    assert {finding.code for finding in state.findings} == {
        "Index.Linter/Line.Unlinked"
    }
    assert "Summary: 0 error(s), 2 warning(s)" in render_linter_text(state)

    payload = json.loads(render_linter_json(state))
    assert payload["summary"]["error_count"] == 0
    assert payload["summary"]["blocked_count"] == 0
    assert payload["exit_code"] == 0


def test_index_linter_missing_surface_blocks_dependent_checks(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    state = _run(index_paths=("missing-index",))

    assert state.summary()["error_count"] == 1
    assert state.summary()["blocked_count"] > 0
    assert any(
        finding.code == "Index.Linter/Surface.IndexMissing"
        for finding in state.findings
    )
    assert any(result.status == "blocked" for result in state.check_results)


def test_index_linter_requires_at_least_one_target(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    state = _run()

    assert any(
        finding.code == "Index.Linter/Config.NoSurfaces"
        and finding.message
        == "Configure at least one --depot, --index, or --appendix path."
        for finding in state.findings
    )


def test_index_linter_reports_invalid_depot_target(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    state = _run(depot_paths=("missing-depot",))

    assert any(
        finding.code == "Index.Linter/Config.NoSurfaces"
        and finding.path == "missing-depot"
        and "Configured --depot paths produced no lint surfaces." in finding.message
        for finding in state.findings
    )


def test_empty_but_valid_depot_does_not_error(monkeypatch, tmp_path: Path) -> None:
    # A router-only depot with no chapter files yet is an unpopulated but valid
    # index depot (an Agentos.Index.Notes scaffold), not a misconfiguration:
    # nothing to lint, so no CONFIG_NO_SURFACES error.
    monkeypatch.chdir(tmp_path)
    depot = tmp_path / "notes-index"
    _write(
        depot / "000-INDEX.md",
        "# Local Index\n\n## Routing\n\n- (no chapter files yet)\n",
    )
    state = _run(depot_paths=("notes-index",))

    assert state.summary()["error_count"] == 0
    assert not any(
        finding.code == "Index.Linter/Config.NoSurfaces" for finding in state.findings
    )


def test_index_linter_maps_mdblocks_errors_and_blocks_inventory(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    index_dir = tmp_path / "design"
    _write(
        tmp_path / "000-INDEX.md",
        "# Agentos Index\n\n## design\n\n- `design/100-design.md` — Example.Concept\n",
    )
    _write(index_dir / "100-design.md", "****\nnot a heading\n")

    state = _run(index_paths=("design",))

    assert any(
        finding.code == "Index.Linter/Block.SeparatorOutsideSemantics"
        and finding.details["source_code"] == "separator_outside_block_semantics"
        for finding in state.findings
    )
    assert any(
        result.code == "Index.Linter/Check.ConceptDuplicates"
        and result.status == "blocked"
        for result in state.check_results
    )


def test_index_linter_maps_block_too_long_to_first_class_code(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    index_dir = tmp_path / "design"
    body = "\n".join(f"- line {line}" for line in range(30))
    _write(
        tmp_path / "000-INDEX.md",
        "# Agentos Index\n\n## design\n\n- `design/100-design.md` — Example.Concept\n",
    )
    _write(index_dir / "100-design.md", f"****\n## Example.Concept\n\n{body}\n****\n")

    state = _run(index_paths=("design",))

    assert any(
        finding.code == "Index.Linter/Block.TooLong"
        and finding.details["source_code"] == "block_too_long"
        for finding in state.findings
    )
    assert any(
        result.code == "Index.Linter/Check.ConceptDuplicates"
        and result.status == "blocked"
        and result.blocked_by == ("Index.Linter/Block.TooLong",)
        for result in state.check_results
    )


def test_index_linter_ignores_starting_text_but_reports_unanchored_section(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    index_dir = tmp_path / "design"
    _write(
        tmp_path / "000-INDEX.md",
        "# Agentos Index\n\n## design\n\n- `design/100-design.md` — Example.Concept\n",
    )
    _write(
        index_dir / "100-design.md",
        "\n".join(
            [
                "> starting prose is okay",
                "",
                "## Example.Concept",
                "",
                "- unanchored section",
                "****",
                "## Other.Concept",
                "",
                "- anchored section",
                "****",
                "",
            ]
        ),
    )

    state = _run(index_paths=("design",))

    assert not any(
        finding.details.get("source_code") == "preamble_text_before_first_block"
        for finding in state.findings
    )
    assert any(
        finding.code == "Index.Linter/Block.UnanchoredSection"
        and finding.path == "design/100-design.md"
        and finding.line == 3
        for finding in state.findings
    )


def test_index_linter_reports_duplicate_concepts(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    index_dir = tmp_path / "design"
    _write(
        tmp_path / "000-INDEX.md",
        "# Agentos Index\n\n## design\n\n- `design/100-design.md` — Example.Concept\n",
    )
    _write(
        index_dir / "100-design.md",
        "\n".join(
            [
                "****",
                "## Example.Concept",
                "",
                "- one",
                "****",
                "## Example.Concept",
                "",
                "- two",
                "****",
                "",
            ]
        ),
    )

    state = _run(index_paths=("design",))

    assert any(
        finding.code == "Index.Linter/Concept.Duplicate" for finding in state.findings
    )


def test_index_linter_reports_index_filename_and_missing_router_file(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    index_dir = tmp_path / "design"
    _write(
        tmp_path / "000-INDEX.md",
        "# Agentos Index\n\n## design\n\n- `design/999-missing.md` — Example.Concept\n",
    )
    _write(
        index_dir / "concepts.md",
        "****\n## Example.Concept\n\n- compact definition\n****\n",
    )

    state = _run(index_paths=("design",))

    assert any(
        finding.code == "Index.Linter/Index.InvalidFilename"
        for finding in state.findings
    )
    assert any(
        finding.code == "Index.Linter/Router.MissingFile" for finding in state.findings
    )


def test_index_linter_ignores_agents_md_in_index_directory(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    index_dir, _appendix_dir = _clean_index(tmp_path)
    _write(index_dir / "AGENTS.md", "# guidance\n")

    state = _run(index_paths=(index_dir.name,))

    assert "design/AGENTS.md" not in state.files_by_kind["index"]
    assert not any(
        finding.code == "Index.Linter/Index.InvalidFilename"
        and finding.path == "design/AGENTS.md"
        for finding in state.findings
    )


def test_index_linter_accepts_chained_colon_concept_parameters(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    index_dir = tmp_path / "design"
    _write(
        tmp_path / "000-INDEX.md",
        "# Agentos Index\n\n## design\n\n- `design/100-design.md` — Alignment.Backend:InChat:What\n",
    )
    _write(
        index_dir / "100-design.md",
        "****\n## Alignment.Backend:InChat:What\n\n- backend parameterized to a phase\n****\n",
    )

    state = _run(index_paths=("design",))

    assert not any(
        finding.code == "Index.Linter/Concept.InvalidHeading"
        for finding in state.findings
    )
    assert not any(
        finding.code == "Index.Linter/Router.InvalidConcept"
        for finding in state.findings
    )


def test_index_linter_accepts_chained_double_colon_concept_parameters(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    index_dir = tmp_path / "design"
    _write(
        tmp_path / "000-INDEX.md",
        "# Agentos Index\n\n## design\n\n- `design/100-design.md` — Alignment.Backend::InChat::What\n",
    )
    _write(
        index_dir / "100-design.md",
        "****\n## Alignment.Backend::InChat::What\n\n- backend parameterized to a phase\n****\n",
    )

    state = _run(index_paths=("design",))

    assert not any(
        finding.code == "Index.Linter/Concept.InvalidHeading"
        for finding in state.findings
    )
    assert not any(
        finding.code == "Index.Linter/Router.InvalidConcept"
        for finding in state.findings
    )


def test_index_linter_accepts_router_appendix_annotation(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    index_dir = tmp_path / "design"
    appendix_dir = tmp_path / "appendix"
    _write(
        tmp_path / "000-INDEX.md",
        "# Agentos Index\n\n## design\n\n- `design/100-design.md` — Alignment.Backend:InChat:What[+1]\n",
    )
    _write(
        index_dir / "100-design.md",
        "****\n## Alignment.Backend:InChat:What\n\n- backend parameterized to a phase\n****\n",
    )
    _write(
        appendix_dir / "Alignment.Backend:InChat:What-appendix.md",
        "****\n## Alignment.Backend:InChat:What/Depth\n\n- depth\n****\n",
    )

    state = _run(index_paths=("design",), appendix_paths=("appendix",))

    assert not any(
        finding.code == "Index.Linter/Router.InvalidConcept"
        for finding in state.findings
    )
    assert not any(
        finding.code.startswith("Index.Linter/Appendix.RouteAnnotation")
        for finding in state.findings
    )
    assert (
        state.router_entries["Alignment.Backend:InChat:What"][
            0
        ].appendix_annotation_count
        == 1
    )


def test_index_linter_accepts_double_colon_router_appendix_annotation(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    index_dir = tmp_path / "design"
    appendix_dir = tmp_path / "appendix"
    _write(
        tmp_path / "000-INDEX.md",
        "# Agentos Index\n\n## design\n\n- `design/100-design.md` — Alignment.Backend::InChat::What[+1]\n",
    )
    _write(
        index_dir / "100-design.md",
        "****\n## Alignment.Backend::InChat::What\n\n- backend parameterized to a phase\n****\n",
    )
    _write(
        appendix_dir / "Alignment.Backend::InChat::What-appendix.md",
        "****\n## Alignment.Backend::InChat::What/Depth\n\n- depth\n****\n",
    )

    state = _run(index_paths=("design",), appendix_paths=("appendix",))

    assert not any(
        finding.code == "Index.Linter/Router.InvalidConcept"
        for finding in state.findings
    )
    assert not any(
        finding.code.startswith("Index.Linter/Appendix.") for finding in state.findings
    )
    assert (
        state.router_entries["Alignment.Backend::InChat::What"][
            0
        ].appendix_annotation_count
        == 1
    )


def test_index_linter_records_appendix_page_inventory(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    index_dir = tmp_path / "design"
    appendix_dir = tmp_path / "appendix"
    _write(
        tmp_path / "000-INDEX.md",
        "# Agentos Index\n\n## design\n\n- `design/100-design.md` — Example.Concept[+2]\n",
    )
    _write(
        index_dir / "100-design.md",
        "****\n## Example.Concept\n\n- compact definition\n****\n",
    )
    _write(
        appendix_dir / "Example.Concept-appendix.md",
        "****\n## Example.Concept/One\n\n- one\n****\n",
    )
    _write(
        appendix_dir / "Example.Concept-appendix-2.md",
        "****\n## Example.Concept/Two\n\n- two\n****\n",
    )

    state = _run(index_paths=("design",), appendix_paths=("appendix",))

    assert sorted(state.appendix_pages["Example.Concept"]) == [1, 2]
    assert not any(
        finding.code
        in {
            "Index.Linter/Appendix.RouteAnnotationMissing",
            "Index.Linter/Appendix.RouteAnnotationStale",
            "Index.Linter/Appendix.PageGap",
        }
        for finding in state.findings
    )


def test_index_linter_reports_missing_appendix_route_annotation(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    index_dir, appendix_dir = _clean_index(tmp_path)
    _write(
        tmp_path / "000-INDEX.md",
        "# Agentos Index\n\n## design\n\n- `design/100-design.md` — Example.Concept\n",
    )

    state = _run(index_paths=(index_dir.name,), appendix_paths=(appendix_dir.name,))

    assert any(
        finding.code == "Index.Linter/Appendix.RouteAnnotationMissing"
        and finding.details["expected_annotation"] == "[+1]"
        for finding in state.findings
    )


def test_index_linter_reports_stale_appendix_route_annotation(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    index_dir, appendix_dir = _clean_index(tmp_path)
    _write(
        tmp_path / "000-INDEX.md",
        "# Agentos Index\n\n## design\n\n- `design/100-design.md` — Example.Concept[+2]\n",
    )

    state = _run(index_paths=(index_dir.name,), appendix_paths=(appendix_dir.name,))

    assert any(
        finding.code == "Index.Linter/Appendix.RouteAnnotationStale"
        and finding.details["actual_annotation"] == "[+2]"
        and finding.details["expected_annotation"] == "[+1]"
        for finding in state.findings
    )


def test_index_linter_reports_appendix_page_gap(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    index_dir = tmp_path / "design"
    appendix_dir = tmp_path / "appendix"
    _write(
        tmp_path / "000-INDEX.md",
        "# Agentos Index\n\n## design\n\n- `design/100-design.md` — Example.Concept[+3]\n",
    )
    _write(
        index_dir / "100-design.md",
        "****\n## Example.Concept\n\n- compact definition\n****\n",
    )
    _write(
        appendix_dir / "Example.Concept-appendix.md",
        "****\n## Example.Concept/One\n\n- one\n****\n",
    )
    _write(
        appendix_dir / "Example.Concept-appendix-3.md",
        "****\n## Example.Concept/Three\n\n- three\n****\n",
    )

    state = _run(index_paths=("design",), appendix_paths=("appendix",))

    assert any(
        finding.code == "Index.Linter/Appendix.PageGap"
        and finding.details["missing_pages"] == [2]
        for finding in state.findings
    )


def test_index_linter_reports_appendix_filename_and_orphan(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    index_dir, appendix_dir = _clean_index(tmp_path)
    _write(appendix_dir / "bad-name.md", "# Bad\n")
    _write(appendix_dir / "Other.Concept-appendix.md", "# Other\n")

    state = _run(
        index_paths=(index_dir.name,),
        appendix_paths=(appendix_dir.name,),
    )

    assert any(
        finding.code == "Index.Linter/Appendix.InvalidFilename"
        for finding in state.findings
    )
    assert any(
        finding.code == "Index.Linter/Appendix.Orphan" for finding in state.findings
    )


def test_index_linter_accepts_file_paths(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    index_dir, appendix_dir = _clean_index(tmp_path)

    state = _run(
        index_paths=("000-INDEX.md", "design/100-design.md"),
        appendix_paths=("appendix/Example.Concept-appendix.md",),
    )

    assert state.summary()["error_count"] == 0
    assert "design/100-design.md" in state.files_by_kind["index"]
    assert "appendix/Example.Concept-appendix.md" in state.files_by_kind["appendix"]


def test_index_linter_command_uses_shared_state_for_json(
    capsys,
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    index_dir, _appendix_dir = _clean_index(tmp_path)
    args = argparse.Namespace(
        depot=[],
        index=[index_dir.name],
        appendix=[],
        json=True,
        coverage=[],
        scope=[],
        warn_unlinked=False,
    )

    exit_code = _cmd_linter(args)

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["config"]["depot"] == []
    assert payload["summary"]["error_count"] == 0
    assert payload["config"]["index"] == [index_dir.name]


def test_index_linter_command_accepts_depot_paths(
    capsys,
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    _clean_depot(tmp_path)
    args = argparse.Namespace(
        depot=["depot"],
        index=[],
        appendix=[],
        json=True,
        coverage=[],
        scope=[],
        warn_unlinked=False,
    )

    exit_code = _cmd_linter(args)

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["config"]["depot"] == ["depot"]
    assert payload["config"]["index"] == ["depot/design"]
    assert payload["config"]["appendix"] == ["depot/appendix"]


def _finding_codes(state) -> list[str]:
    return [finding.code for finding in state.findings]


def test_index_linter_line_type_syntax_checks(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    depot_dir = _clean_depot(tmp_path)
    _write(
        depot_dir / "design" / "100-design.md",
        "****\n## Example.Concept\n\n"
        "- [DF] `Example.Concept` is fine\n"
        "- [ct] malformed lowercase code\n"
        "- [ZZ] unknown act code\n"
        "- [GR] grounding line with no trailing anchor\n"
        "- untyped legacy line stays silent\n"
        "****\n",
    )
    state = _run(depot_paths=(str(depot_dir),))
    codes = _finding_codes(state)
    assert "Index.Linter/Line.Type.Syntax" in codes
    assert "Index.Linter/Line.Type.UnknownCode" in codes
    assert "Index.Linter/Line.Type.GR.MissingAnchor" in codes
    typed_findings = [
        f for f in state.findings if f.code.startswith("Index.Linter/Line.Type")
    ]
    assert all(f.severity == "warning" for f in typed_findings)


def test_index_linter_source_axis_placement(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    depot_dir = _clean_depot(tmp_path)
    _write(
        depot_dir / "design" / "100-design.md",
        "****\n## Example.Concept\n\n"
        "- [DF] `Example.Concept` is fine\n"
        "- [AS:CT] assistant-grounded line in the index proper ^20260101-0\n"
        "****\n",
    )
    _write(
        depot_dir / "agendix" / "Example.Concept-agendix.md",
        "****\n## Example.Concept/Agendix\n\n"
        "- [AS:CT] assistant-grounded capture is legal here ^20260101-1\n"
        "****\n",
    )
    state = _run(depot_paths=(str(depot_dir),))
    placement = [
        f for f in state.findings if f.code == "Index.Linter/Source.Axis.Placement"
    ]
    assert len(placement) == 1
    assert placement[0].severity == "error"
    assert "100-design.md" in placement[0].path


def test_index_linter_reports_legacy_anchor_sigil(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    depot_dir = _clean_depot(tmp_path)
    _write(
        depot_dir / "design" / "100-design.md",
        "****\n## Example.Concept\n\n"
        "- [DF] old sigil @20260101-0\n"
        "- [DF] new sigil ^20260101-1\n"
        "****\n",
    )

    state = _run(depot_paths=(str(depot_dir),))
    hits = [f for f in state.findings if f.code == "Index.Linter/Anchor.LegacySigil"]

    assert len(hits) == 1
    assert hits[0].path.endswith("100-design.md")
    assert hits[0].details["anchor"] == "20260101-0"


def test_index_linter_reports_legacy_type_statement_sigil(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    depot_dir = _clean_depot(tmp_path)
    _write(
        depot_dir / "000-INDEX.md",
        "# Agentos Index\n\n## design\n\n"
        "- `design/100-design.md` — Alignment.Mode:Autonomous\n",
    )
    _write(
        depot_dir / "design" / "100-design.md",
        "****\n## Example.Concept\n\n"
        "- [DF] legacy Alignment.Mode:Autonomous\n"
        "- [DF] modern Alignment.Mode::Autonomous\n"
        "- [DF] file reference parser.py:41\n"
        "****\n",
    )

    state = _run(depot_paths=(str(depot_dir),))
    hits = [
        f for f in state.findings if f.code == "Index.Linter/TypeStatement.LegacySigil"
    ]

    assert len(hits) == 2
    assert {hit.path for hit in hits} == {
        "depot/000-INDEX.md",
        "depot/design/100-design.md",
    }
    assert {hit.details["legacy"] for hit in hits} == {"Alignment.Mode:Autonomous"}
    assert {hit.details["replacement"] for hit in hits} == {
        "Alignment.Mode::Autonomous"
    }


def test_index_linter_line_unlinked_scope(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    depot_dir = _clean_depot(tmp_path)
    _write(
        depot_dir / "design" / "100-design.md",
        "****\n## Example.Concept\n\n"
        "- [DF] unlinked chapter line\n"
        "- [GR] linked chapter line ^20260101-0\n"
        "****\n",
    )
    _write(
        depot_dir / "agendix" / "Example.Concept-agendix.md",
        "****\n## Example.Concept/Agendix\n\n"
        "- [AS:CT] unlinked agendix line\n"
        "- [AS:CT] linked agendix line ^20260101-1\n"
        "****\n",
    )

    default_state = _run(depot_paths=(str(depot_dir),))
    default_hits = [
        f for f in default_state.findings if f.code == "Index.Linter/Line.Unlinked"
    ]
    assert len(default_hits) == 3
    assert {hit.details["surface_kind"] for hit in default_hits} == {
        "chapter",
        "appendix",
        "agendix",
    }

    config, raw_d, raw_i, raw_a = build_linter_config(
        depot_paths=(str(depot_dir),),
        index_paths=(),
        appendix_paths=(),
        warn_unlinked=True,
    )
    warned_state = run_linter(config, raw_d, raw_i, raw_a)
    warned_hits = [
        f for f in warned_state.findings if f.code == "Index.Linter/Line.Unlinked"
    ]
    assert len(warned_hits) == 3


def test_index_linter_coverage_line_replaces_warn_unlinked(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    depot_dir = _clean_depot(tmp_path, include_appendix=False)
    _write(
        depot_dir / "design" / "100-design.md",
        "****\n## Example.Concept\n\n"
        "- [DF] unlinked chapter line\n"
        "- [GR] linked chapter line ^20260101-0\n"
        "****\n",
    )

    state = _run(depot_paths=(str(depot_dir),), coverage=("line",))
    hits = [f for f in state.findings if f.code == "Index.Linter/Line.Unlinked"]
    payload = json.loads(render_linter_json(state))

    assert len(hits) == 1
    assert payload["coverage"]["line"] == {"linked": 1, "total": 2}

    alias_state = _run(depot_paths=(str(depot_dir),), warn_unlinked=True)
    alias_hits = [
        f for f in alias_state.findings if f.code == "Index.Linter/Line.Unlinked"
    ]
    assert len(alias_hits) == len(hits)


def test_index_linter_block_ungrounded_meter(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    depot_dir = _clean_depot(tmp_path)
    _write(
        depot_dir / "000-INDEX.md",
        "# Agentos Index\n\n## design\n\n"
        "- `design/100-design.md` — Example.Grounded, Example.Ungrounded, "
        "Example.HeadOnly[+1], Example.Empty\n",
    )
    _write(
        depot_dir / "design" / "100-design.md",
        "****\n## Example.Grounded\n\n"
        "- every line anchored ^20260101-0\n"
        "- second anchored line ^20260101-1\n"
        "****\n## Example.Ungrounded\n\n"
        "- anchored line ^20260101-2\n"
        "- line missing its anchor\n"
        "****\n## Example.HeadOnly\n\n"
        "- head section no longer grounds this line\n"
        "****\n## Example.Empty\n\n"
        "****\n",
    )
    _write(
        depot_dir / "appendix" / "Example.HeadOnly-appendix.md",
        "****\n## Example.HeadOnly/Grounding.Head\n\n"
        "- [GR] retired board evidence ^20260101-3\n"
        "****\n",
    )

    state = _run(depot_paths=(str(depot_dir),), coverage=("block",))
    hits = [f for f in state.findings if f.code == "Index.Linter/Block.Ungrounded"]
    payload = json.loads(render_linter_json(state))

    # Anchor syntax alone cannot establish grounding without a support resolver.
    assert payload["coverage"]["block"] == {"grounded": 1, "total": 4}
    assert {hit.details["block_path"] for hit in hits} == {
        "Example.Grounded",
        "Example.Ungrounded",
        "Example.HeadOnly",
    }
    by_path = {hit.details["block_path"]: hit for hit in hits}
    assert by_path["Example.Ungrounded"].details["ungrounded_lines"] == 2
    assert by_path["Example.HeadOnly"].details["ungrounded_lines"] == 1


def test_block_grounding_uses_resolved_line_standing(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    depot_dir = _clean_depot(tmp_path, include_appendix=False)
    _write(
        depot_dir / "design" / "100-design.md",
        "****\n## Example.Concept\n\n- resolved support ^c20260101-0u\n****\n",
    )

    def record_support(state):
        for _document, line in parsed_linter_kernel_lines(state):
            anchors = tuple(
                str(span.parsed["anchor"])
                for span in line.spans
                if span.kind == "anchor"
            )
            state.record_line_support_standing(
                line,
                LineSupportStanding(
                    anchors=anchors,
                    resolved_anchors=anchors,
                ),
            )
        return []

    support_check = LinterCheck(
        code="Test/Support.Standing",
        title="test support standing",
        gate=lambda _state: GateResult(allowed=True),
        run=record_support,
        structural=True,
    )
    config, raw_d, raw_i, raw_a = build_linter_config(
        depot_paths=(str(depot_dir),),
        index_paths=(),
        appendix_paths=(),
        coverage=("block",),
    )
    state = run_linter(
        config,
        raw_d,
        raw_i,
        raw_a,
        extra_checks=(support_check,),
    )
    payload = json.loads(render_linter_json(state))

    assert payload["coverage"]["block"] == {"grounded": 1, "total": 1}
    assert not [
        finding
        for finding in state.findings
        if finding.code == "Index.Linter/Block.Ungrounded"
    ]


def test_index_linter_scope_filters_findings_counts_and_meters(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    depot_dir = _clean_depot(tmp_path)
    _write(
        depot_dir / "000-INDEX.md",
        "# Agentos Index\n\n## design\n\n"
        "- `design/100-design.md` — Example.One[+1]\n"
        "- `other/100-other.md` — Example.Two[+1]\n",
    )
    _write(
        depot_dir / "design" / "100-design.md",
        "****\n## Example.One\n\n- scoped unlinked line\n****\n",
    )
    _write(
        depot_dir / "other" / "100-other.md",
        "****\n## Example.Two\n\n"
        "- out-of-scope unlinked line\n"
        "- linked line ^20260101-0\n"
        "****\n",
    )
    state = _run(
        depot_paths=(str(depot_dir),),
        coverage=("line", "block"),
        scope_paths=("depot/design",),
    )
    payload = json.loads(render_linter_json(state))

    assert payload["config"]["scope"] == ["depot/design"]
    assert payload["coverage"]["line"] == {"linked": 0, "total": 1}
    assert payload["coverage"]["block"] == {"grounded": 0, "total": 1}
    assert payload["summary"]["finding_count"] == 2
    assert all(
        finding["path"].startswith("depot/design/") for finding in payload["findings"]
    )


def test_index_linter_scope_rejects_unmatched_path(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    depot_dir = _clean_depot(tmp_path)

    state = _run(depot_paths=(str(depot_dir),), scope_paths=("missing",))

    assert any(
        finding.code == "Index.Linter/Surface.Invalid" and finding.path == "missing"
        for finding in state.findings
    )


def test_index_linter_runs_extra_checks(monkeypatch, tmp_path: Path) -> None:
    from agentos.index.linter import GateResult, LinterCheck, LinterFinding

    monkeypatch.chdir(tmp_path)
    depot_dir = _clean_depot(tmp_path)
    ran: list[str] = []

    def _gate_ok(state) -> GateResult:
        return GateResult(allowed=True)

    def _run_extra(state) -> list[LinterFinding]:
        ran.append("yes")
        return [
            LinterFinding(
                severity="warning",
                code="External.Check/Probe",
                message="external check ran",
                path="probe",
            )
        ]

    def _gate_blocked(state) -> GateResult:
        return GateResult(allowed=False, reason="backend unavailable")

    extra = LinterCheck(
        code="External.Check", title="External probe", gate=_gate_ok, run=_run_extra
    )
    blocked = LinterCheck(
        code="External.Blocked",
        title="External blocked",
        gate=_gate_blocked,
        run=_run_extra,
    )
    config, raw_d, raw_i, raw_a = build_linter_config(
        depot_paths=(str(depot_dir),), index_paths=(), appendix_paths=()
    )
    state = run_linter(config, raw_d, raw_i, raw_a, extra_checks=(extra, blocked))
    assert ran == ["yes"]
    assert "External.Check/Probe" in _finding_codes(state)
    assert any(
        r.code == "External.Blocked" and r.status == "blocked"
        for r in state.check_results
    )


def test_index_linter_flags_unprefixed_anchor_citations(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    depot_dir = _clean_depot(tmp_path)
    _write(
        depot_dir / "000-INDEX.md",
        "# Agentos Index\n\n## design\n\n- `design/100-design.md` — Example.One\n",
    )
    _write(
        depot_dir / "design" / "100-design.md",
        "****\n## Example.One\n\n"
        "- prefixed citation ^c20260718-0u\n"
        "- bare citation ^20260718-1\n"
        "****\n",
    )

    state = _run(depot_paths=(str(depot_dir),))
    hits = [f for f in state.findings if f.code == "Index.Linter/Anchor.Unprefixed"]
    assert len(hits) == 1
    assert hits[0].details["anchor"] == "20260718-1"
    assert hits[0].severity == "warning"


# ---- Linter check selection (Impl.Req 702) -----------------------------------


def test_check_selector_derives_stable_kebab_slugs() -> None:
    from agentos.index.linter import check_selector

    assert (
        check_selector("Index.Linter/Check.DepotDependencies") == "depot-dependencies"
    )
    assert check_selector("Index.Linter/Line.Unlinked") == "line-unlinked"
    assert check_selector("Index.Linter/Check.ConfigSurfaces") == "config-surfaces"


def test_all_check_selectors_are_unique() -> None:
    from agentos.index.linter import CHECKS, check_selector

    selectors = [check_selector(c.code) for c in CHECKS]
    assert len(selectors) == len(set(selectors)), "check selectors must be unique"


def test_check_registry_reports_metadata() -> None:
    from agentos.index.linter import check_registry

    rows = {row["selector"]: row for row in check_registry()}
    assert "config-surfaces" in rows
    assert rows["config-surfaces"]["structural"] is True
    # a reportable, opt-in check registered off by default
    assert rows["dangling-mention"]["default_on"] is False


def _fake_checks():
    from agentos.index.linter import LinterCheck

    def _noop(state):
        return []

    def _ok(state):
        from agentos.index.linter import allowed

        return allowed()

    return (
        LinterCheck("S/Check.Structural", "structural", _ok, _noop, structural=True),
        LinterCheck("S/Check.OnByDefault", "on", _ok, _noop, default_on=True),
        LinterCheck("S/Check.OffByDefault", "off", _ok, _noop, default_on=False),
    )


def test_resolver_default_runs_default_on_only():
    from agentos.index.linter import check_selector, resolve_enabled_checks

    enabled = {check_selector(c.code) for c in resolve_enabled_checks(_fake_checks())}
    assert enabled == {"structural", "on-by-default"}


def test_resolver_include_enables_a_default_off_check():
    from agentos.index.linter import check_selector, resolve_enabled_checks

    enabled = {
        check_selector(c.code)
        for c in resolve_enabled_checks(_fake_checks(), include=("off-by-default",))
    }
    assert "off-by-default" in enabled


def test_resolver_exclude_removes_reportable_but_not_structural():
    from agentos.index.linter import check_selector, resolve_enabled_checks

    enabled = {
        check_selector(c.code)
        for c in resolve_enabled_checks(
            _fake_checks(), exclude=("on-by-default", "structural")
        )
    }
    assert "on-by-default" not in enabled
    assert "structural" in enabled  # structural is never disableable


def test_resolver_skip_wins_on_conflict():
    from agentos.index.linter import check_selector, resolve_enabled_checks

    enabled = {
        check_selector(c.code)
        for c in resolve_enabled_checks(
            _fake_checks(), include=("off-by-default",), exclude=("off-by-default",)
        )
    }
    assert "off-by-default" not in enabled


def test_resolver_unknown_selector_errors():
    import pytest

    from agentos._core.errors import CliError
    from agentos.index.linter import resolve_enabled_checks

    with pytest.raises(CliError):
        resolve_enabled_checks(_fake_checks(), include=("nope",))


def test_run_linter_exclude_skips_a_reportable_check(
    monkeypatch, tmp_path: Path
) -> None:
    from agentos.index.linter import CHECK_CONCEPT_DUPLICATES

    monkeypatch.chdir(tmp_path)
    depot = _clean_depot(tmp_path)
    ran = {r.code for r in _run(depot_paths=(str(depot),)).check_results}
    assert CHECK_CONCEPT_DUPLICATES in ran  # runs by default
    ran_excluded = {
        r.code
        for r in _run(
            depot_paths=(str(depot),), exclude=("concept-duplicates",)
        ).check_results
    }
    assert CHECK_CONCEPT_DUPLICATES not in ran_excluded


def test_run_linter_exclude_cannot_disable_a_structural_check(
    monkeypatch, tmp_path: Path
) -> None:
    from agentos.index.linter import CHECK_CONFIG_SURFACES

    monkeypatch.chdir(tmp_path)
    depot = _clean_depot(tmp_path)
    ran = {
        r.code
        for r in _run(
            depot_paths=(str(depot),), exclude=("config-surfaces",)
        ).check_results
    }
    assert CHECK_CONFIG_SURFACES in ran  # structural: exclude has no effect


def test_dangling_mention_check_is_default_off_and_opt_in(
    monkeypatch, tmp_path: Path
) -> None:
    from agentos.index.linter import DEPOT_DANGLING_MENTION

    monkeypatch.chdir(tmp_path)
    # a depot mentioning a concept whose block does not exist -> a dangling mention
    depot = tmp_path / "depot"
    _write(
        depot / "000-INDEX.md",
        "# Agentos Index\n\n## design\n\n- `design/100-design.md` — Present.Concept\n",
    )
    _write(
        depot / "design" / "100-design.md",
        "****\n## Present.Concept\n\n- [DF] `Present.Concept` leans on `Missing.Concept`\n****\n",
    )
    default_run = _run(depot_paths=(str(depot),))
    assert not [f for f in default_run.findings if f.code == DEPOT_DANGLING_MENTION]

    opted_in = _run(depot_paths=(str(depot),), include=("dangling-mention",))
    dangling = [f for f in opted_in.findings if f.code == DEPOT_DANGLING_MENTION]
    assert "Missing.Concept" in {f.details["concept"] for f in dangling}


def _linter_ns(**over):
    base = dict(
        depot=[],
        index=[],
        appendix=[],
        json=True,
        coverage=[],
        scope=[],
        warn_unlinked=False,
        check=[],
        skip=[],
        list_checks=False,
    )
    base.update(over)
    return argparse.Namespace(**base)


def test_cli_list_checks_lists_selectors_and_exits(capsys) -> None:
    exit_code = _cmd_linter(_linter_ns(list_checks=True))
    out = capsys.readouterr().out
    assert exit_code == 0
    assert "dangling-mention" in out and "[off]" in out
    assert "config-surfaces" in out and "structural" in out


def test_cli_list_checks_includes_composition_root_checks(capsys) -> None:
    extra = LinterCheck(
        code="Index.Linter/Line.Approval",
        title="external approval check",
        gate=lambda _state: GateResult(allowed=True),
        run=lambda _state: [],
        default_on=False,
    )
    exit_code = _cmd_linter(
        _linter_ns(
            list_checks=True,
            _extra_linter_checks=(extra,),
        )
    )
    out = capsys.readouterr().out

    assert exit_code == 0
    assert "line-approval" in out
    assert "external approval check" in out


def test_cli_check_flag_opts_into_dangling_mention(
    capsys, monkeypatch, tmp_path: Path
) -> None:
    from agentos.index.linter import DEPOT_DANGLING_MENTION

    monkeypatch.chdir(tmp_path)
    depot = tmp_path / "depot"
    _write(
        depot / "000-INDEX.md",
        "# Agentos Index\n\n## design\n\n- `design/100-design.md` — Present.Concept\n",
    )
    _write(
        depot / "design" / "100-design.md",
        "****\n## Present.Concept\n\n- [DF] `Present.Concept` leans on `Missing.Concept`\n****\n",
    )
    _cmd_linter(_linter_ns(depot=["depot"], check=["dangling-mention"]))
    payload = json.loads(capsys.readouterr().out)
    codes = {f["code"] for f in payload["findings"]}
    assert DEPOT_DANGLING_MENTION in codes


def test_cli_unknown_selector_is_an_error(monkeypatch, tmp_path: Path) -> None:
    import pytest

    from agentos._core.errors import CliError

    monkeypatch.chdir(tmp_path)
    _clean_depot(tmp_path)
    with pytest.raises(CliError):
        _cmd_linter(_linter_ns(depot=["depot"], skip=["does-not-exist"]))


# --- Reviewed.Cite.Closure: reviewed surfaces may not cite the agendix --------


def _depot_with_agendix(root: Path, *, cite: str) -> Path:
    """A depot whose design chapter carries `cite`, plus a real agendix surface
    holding file `agendix/Example.Concept-agendix.md` with block
    `Example.Concept/Agendix/Real.Lead`."""
    depot = root / "depot"
    _write(
        depot / "000-INDEX.md",
        "# Agentos Index\n\n## design\n\n- `design/100-design.md` — Example.Concept\n",
    )
    _write(
        depot / "design" / "100-design.md",
        "****\n## Example.Concept\n\n"
        "- [DF] `Example.Concept` is defined\n"
        f"- [CT] {cite} ^c20260101-0u\n"
        "****\n",
    )
    _write(
        depot / "agendix" / "Example.Concept-agendix.md",
        "****\n## Example.Concept/Agendix/Real.Lead\n\n- [CT] a captured lead ^c20260101-1u\n",
    )
    return depot


def test_reviewed_surface_citing_real_agendix_block_raises_closure(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AGENTOS_HOME", str(tmp_path / "home"))
    depot = _depot_with_agendix(
        tmp_path, cite="the lead is `Example.Concept/Agendix/Real.Lead`"
    )
    state = _run(depot_paths=(str(depot),))
    hits = [f for f in state.findings if f.code == REVIEWED_CITE_CLOSURE]
    assert len(hits) == 1
    assert hits[0].severity == "error"
    assert hits[0].details["target"] == "Example.Concept/Agendix/Real.Lead"


def test_reviewed_surface_naming_agendix_file_stays_quiet(
    monkeypatch, tmp_path: Path
) -> None:
    # naming the agendix surface/file (as the Index.Agendix definition does) is
    # not a content cite -> no violation; only a Block.Path into a real agendix
    # block is the forbidden edge
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AGENTOS_HOME", str(tmp_path / "home"))
    depot = _depot_with_agendix(
        tmp_path, cite="see `agendix/Example.Concept-agendix.md`"
    )
    state = _run(depot_paths=(str(depot),))
    assert not [f for f in state.findings if f.code == REVIEWED_CITE_CLOSURE]


def test_agendix_format_placeholders_do_not_raise_closure(
    monkeypatch, tmp_path: Path
) -> None:
    # a reviewed block that DESCRIBES the agendix format with placeholder paths
    # resolves to no real target -> no violation
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AGENTOS_HOME", str(tmp_path / "home"))
    depot = _depot_with_agendix(
        tmp_path,
        cite="candidates land at `Concept.X/Agendix/Candidate.Name` under `agendix/`",
    )
    state = _run(depot_paths=(str(depot),))
    assert not [f for f in state.findings if f.code == REVIEWED_CITE_CLOSURE]


def test_reviewed_surface_citing_appendix_or_concept_stays_quiet(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AGENTOS_HOME", str(tmp_path / "home"))
    depot = _depot_with_agendix(
        tmp_path,
        cite="`Example.Concept` relates to `appendix/Example.Concept-appendix.md`",
    )
    state = _run(depot_paths=(str(depot),))
    assert not [f for f in state.findings if f.code == REVIEWED_CITE_CLOSURE]
