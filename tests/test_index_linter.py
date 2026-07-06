from __future__ import annotations

import argparse
import json
from pathlib import Path

from agentos.index.commands import _cmd_linter
from agentos.index.linter import (
    build_linter_config,
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
):
    config, raw_depot_paths, raw_index_paths, raw_appendix_paths = build_linter_config(
        depot_paths=depot_paths,
        index_paths=index_paths,
        appendix_paths=appendix_paths,
    )
    return run_linter(config, raw_depot_paths, raw_index_paths, raw_appendix_paths)


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


def test_index_linter_clean_surface_renders_text_and_json(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    index_dir, appendix_dir = _clean_index(tmp_path)

    state = _run(
        index_paths=(index_dir.name,),
        appendix_paths=(appendix_dir.name,),
    )

    assert state.summary()["error_count"] == 0
    assert state.summary()["warning_count"] == 0
    assert "Summary: 0 error(s), 0 warning(s)" in render_linter_text(state)

    payload = json.loads(render_linter_json(state))
    assert payload["summary"]["error_count"] == 0
    assert payload["summary"]["blocked_count"] == 0
    assert payload["exit_code"] == 0


def test_index_linter_missing_surface_blocks_dependent_checks(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    state = _run(index_paths=("missing-index",))

    assert state.summary()["error_count"] == 1
    assert state.summary()["blocked_count"] > 0
    assert any(finding.code == "Index.Linter/Surface.IndexMissing" for finding in state.findings)
    assert any(result.status == "blocked" for result in state.check_results)


def test_index_linter_requires_at_least_one_target(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    state = _run()

    assert any(
        finding.code == "Index.Linter/Config.NoSurfaces"
        and finding.message == "Configure at least one --depot, --index, or --appendix path."
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
        result.code == "Index.Linter/Check.ConceptDuplicates" and result.status == "blocked"
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

    assert any(finding.code == "Index.Linter/Concept.Duplicate" for finding in state.findings)


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

    assert any(finding.code == "Index.Linter/Index.InvalidFilename" for finding in state.findings)
    assert any(finding.code == "Index.Linter/Router.MissingFile" for finding in state.findings)


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
    assert state.router_entries["Alignment.Backend:InChat:What"][0].appendix_annotation_count == 1


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
    _write(appendix_dir / "Example.Concept-appendix.md", "****\n## Example.Concept/One\n\n- one\n****\n")
    _write(appendix_dir / "Example.Concept-appendix-2.md", "****\n## Example.Concept/Two\n\n- two\n****\n")

    state = _run(index_paths=("design",), appendix_paths=("appendix",))

    assert sorted(state.appendix_pages["Example.Concept"]) == [1, 2]
    assert not any(
        finding.code in {
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
    _write(appendix_dir / "Example.Concept-appendix.md", "****\n## Example.Concept/One\n\n- one\n****\n")
    _write(appendix_dir / "Example.Concept-appendix-3.md", "****\n## Example.Concept/Three\n\n- three\n****\n")

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

    assert any(finding.code == "Index.Linter/Appendix.InvalidFilename" for finding in state.findings)
    assert any(finding.code == "Index.Linter/Appendix.Orphan" for finding in state.findings)


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
    )

    exit_code = _cmd_linter(args)

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["config"]["depot"] == ["depot"]
    assert payload["config"]["index"] == ["depot/design"]
    assert payload["config"]["appendix"] == ["depot/appendix"]
