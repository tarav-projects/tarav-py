from __future__ import annotations

import json
from pathlib import Path

from agentos.index.linter import (
    GateResult,
    LineSupportStanding,
    LinterCheck,
    LinterCheckBinding,
    build_linter_config,
    parsed_linter_kernel_lines,
    render_linter_json,
    run_linter,
)
from _index_linter_helpers import _clean_depot, _run, _write


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
    # `GR` is retired: it is no longer a known act code, so a `[GR]` line reads
    # as an unknown code rather than as a grounding line missing its anchor.
    assert "Index.Linter/Line.Type.GR.MissingAnchor" not in codes
    unknown = [f for f in state.findings if f.code == "Index.Linter/Line.Type.UnknownCode"]
    assert {f.details["code"] for f in unknown} == {"ZZ", "GR"}
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
        "- [DC] linked chapter line ^20260101-0\n"
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
        "- [DC] linked chapter line ^20260101-0\n"
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
        "- [DC] retired board evidence ^20260101-3\n"
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
        binding=LinterCheckBinding(structural=True),
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
        poi["target"]["path"].startswith("depot/design/") for poi in payload["pois"]
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


def test_index_linter_anchor_scope_selects_lines_and_publishes_subjects(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    depot_dir = _clean_depot(tmp_path)
    _write(
        depot_dir / "design" / "100-design.md",
        "****\n## Example.Concept\n\n"
        "- [CT] selected line ^c20260809-171u ^c20260809-172u\n"
        "- [CT] unrelated line ^c20260809-173u\n"
        "****\n",
    )
    observed: list[list[str]] = []

    def _run_selected(state) -> list:
        observed.append([line.src for _, line in parsed_linter_kernel_lines(state)])
        return []

    check = LinterCheck(
        code="External.Selected",
        title="Selected lines",
        gate=lambda _state: GateResult(allowed=True),
        run=_run_selected,
    )
    config, raw_d, raw_i, raw_a = build_linter_config(
        depot_paths=(str(depot_dir),),
        index_paths=(),
        appendix_paths=(),
        anchors=("^c20260809-172u",),
    )
    state = run_linter(
        config,
        raw_d,
        raw_i,
        raw_a,
        extra_checks=(check,),
        include=("external-selected",),
    )
    payload = json.loads(render_linter_json(state))

    assert observed == [["- [CT] selected line ^c20260809-171u ^c20260809-172u"]]
    assert payload["selection"]["anchors"] == ["c20260809-172u"]
    assert payload["selection"]["matched"] == ["c20260809-172u"]
    assert payload["selection"]["line_count"] == 1
    assert "Index.Linter/Check.BlockSections" in payload["selection"][
        "omitted_depot_checks"
    ]
    assert payload["subjects"] == [
        {
            "kind": "Index.Line",
            "path": "depot/design/100-design.md",
            "line": 4,
            "path_line": "depot/design/100-design.md:4",
            "anchors": ["c20260809-171u", "c20260809-172u"],
        }
    ]


def test_index_linter_anchor_scope_fails_closed_for_missing_anchor(
    monkeypatch, tmp_path: Path
) -> None:
    import pytest

    monkeypatch.chdir(tmp_path)
    depot_dir = _clean_depot(tmp_path)
    config, raw_d, raw_i, raw_a = build_linter_config(
        depot_paths=(str(depot_dir),),
        index_paths=(),
        appendix_paths=(),
        anchors=("c20260809-999u",),
    )

    with pytest.raises(SystemExit, match="requested anchor is absent"):
        run_linter(config, raw_d, raw_i, raw_a)


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


def test_index_linter_reports_anchor_collision_across_depots(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    first = _clean_depot(tmp_path / "first", include_appendix=False)
    second = _clean_depot(tmp_path / "second", include_appendix=False)
    _write(
        first / "design" / "100-design.md",
        "****\n## Example.Concept\n\n"
        "- [CT] first content ^c20260802-1u\n"
        "- [CT] repeated content ^c20260802-2u\n"
        "****\n",
    )
    _write(
        second / "design" / "100-design.md",
        "****\n## Example.Concept\n\n"
        "- [DC] distinct content ^c20260802-1u\n"
        "- [CT] repeated content ^c20260802-2u\n"
        "****\n",
    )

    state = _run(depot_paths=(str(first), str(second)))
    hits = [
        finding
        for finding in state.findings
        if finding.code == "Index.Linter/Anchor.Collision"
    ]

    assert len(hits) == 1
    assert hits[0].severity == "error"
    assert hits[0].details["anchor"] == "c20260802-1u"
    assert len(hits[0].details["attachments"]) == 2
    assert len(hits[0].details["locations"]) == 2
