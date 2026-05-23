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
    index_dir = root / "index"
    appendix_dir = root / "appendix"
    _write(
        index_dir / "000-index.md",
        "# Agentos Index\n\n## Routing\n\n- `100-index.md` — Example.Concept\n",
    )
    _write(
        index_dir / "100-index.md",
        "****\n## Example.Concept\n\n- compact definition\n****\n",
    )
    _write(
        appendix_dir / "Example.Concept-appendix.md",
        "****\n## Example.Concept/Example.Detail\n\n- depth\n****\n",
    )
    return index_dir, appendix_dir


def _run(
    *,
    index_paths: tuple[str, ...] = (),
    appendix_paths: tuple[str, ...] = (),
):
    config, raw_index_paths, raw_appendix_paths = build_linter_config(
        index_paths=index_paths,
        appendix_paths=appendix_paths,
    )
    return run_linter(config, raw_index_paths, raw_appendix_paths)


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


def test_index_linter_maps_mdblocks_errors_and_blocks_inventory(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    index_dir = tmp_path / "index"
    _write(
        index_dir / "000-index.md",
        "# Agentos Index\n\n## Routing\n\n- `100-index.md` — Example.Concept\n",
    )
    _write(index_dir / "100-index.md", "****\nnot a heading\n")

    state = _run(index_paths=("index",))

    assert any(
        finding.code == "Index.Linter/Mdblocks.Syntax"
        and finding.details["source_code"] == "separator_outside_block_semantics"
        for finding in state.findings
    )
    assert any(
        result.code == "Index.Linter/Check.ConceptDuplicates" and result.status == "blocked"
        for result in state.check_results
    )


def test_index_linter_ignores_starting_text_but_reports_unanchored_section(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    index_dir = tmp_path / "index"
    _write(
        index_dir / "000-index.md",
        "# Agentos Index\n\n## Routing\n\n- `100-index.md` — Example.Concept\n",
    )
    _write(
        index_dir / "100-index.md",
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

    state = _run(index_paths=("index",))

    assert not any(
        finding.details.get("source_code") == "preamble_text_before_first_block"
        for finding in state.findings
    )
    assert any(
        finding.code == "Index.Linter/Block.UnanchoredSection"
        and finding.path == "index/100-index.md"
        and finding.line == 3
        for finding in state.findings
    )


def test_index_linter_reports_duplicate_concepts(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    index_dir = tmp_path / "index"
    _write(
        index_dir / "000-index.md",
        "# Agentos Index\n\n## Routing\n\n- `100-index.md` — Example.Concept\n",
    )
    _write(
        index_dir / "100-index.md",
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

    state = _run(index_paths=("index",))

    assert any(finding.code == "Index.Linter/Concept.Duplicate" for finding in state.findings)


def test_index_linter_reports_index_filename_and_missing_router_file(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    index_dir = tmp_path / "index"
    _write(
        index_dir / "000-index.md",
        "# Agentos Index\n\n## Routing\n\n- `999-missing.md` — Example.Concept\n",
    )
    _write(
        index_dir / "concepts.md",
        "****\n## Example.Concept\n\n- compact definition\n****\n",
    )

    state = _run(index_paths=("index",))

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

    assert "index/AGENTS.md" not in state.files_by_kind["index"]
    assert not any(
        finding.code == "Index.Linter/Index.InvalidFilename"
        and finding.path == "index/AGENTS.md"
        for finding in state.findings
    )


def test_index_linter_accepts_chained_colon_concept_parameters(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    index_dir = tmp_path / "index"
    _write(
        index_dir / "000-index.md",
        "# Agentos Index\n\n## Routing\n\n- `100-index.md` — Alignment.Backend:InChat:What\n",
    )
    _write(
        index_dir / "100-index.md",
        "****\n## Alignment.Backend:InChat:What\n\n- backend parameterized to a phase\n****\n",
    )

    state = _run(index_paths=("index",))

    assert not any(
        finding.code == "Index.Linter/Concept.InvalidHeading"
        for finding in state.findings
    )
    assert not any(
        finding.code == "Index.Linter/Router.InvalidConcept"
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
        index_paths=("index/000-index.md", "index/100-index.md"),
        appendix_paths=("appendix/Example.Concept-appendix.md",),
    )

    assert state.summary()["error_count"] == 0
    assert "index/100-index.md" in state.files_by_kind["index"]
    assert "appendix/Example.Concept-appendix.md" in state.files_by_kind["appendix"]


def test_index_linter_command_uses_shared_state_for_json(
    capsys,
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    index_dir, _appendix_dir = _clean_index(tmp_path)
    args = argparse.Namespace(
        index=[index_dir.name],
        appendix=[],
        json=True,
    )

    exit_code = _cmd_linter(args)

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["summary"]["error_count"] == 0
    assert payload["config"]["index"] == [index_dir.name]
