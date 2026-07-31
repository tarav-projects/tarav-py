from __future__ import annotations

from pathlib import Path

from agentos.index.linter import (
    REVIEWED_CITE_CLOSURE,
)
from _index_linter_helpers import _run, _write


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
