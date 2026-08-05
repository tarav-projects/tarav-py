from __future__ import annotations

from pathlib import Path

from agentos.index.issues import issue_inventory
from agentos.index.linter import build_linter_config, run_linter
from agentos.index.model import parse_depot
from agentos.index.policy import surface_policy


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _issue_depot(tmp_path: Path) -> Path:
    depot = tmp_path / "depot"
    _write(
        depot / "000-INDEX.md",
        "# Index\n\n## issues\n\n"
        "- `issues/100-issues.md` — Issue.I0001.Bootstrap.Review, Issue.I0002.Done\n",
    )
    _write(
        depot / "design" / "100-design.md",
        "****\n## Example.Model\n\n- [DF] model ^c20260805-1u\n",
    )
    _write(
        depot / "issues" / "100-issues.md",
        "****\n## Issue.I0001.Bootstrap.Review\n\n"
        "- [PR] validate the workflow ^c20260805-2u\n"
        "****\n## Issue.I0002.Done\n\n"
        "- [PR] investigate the opportunity ^c20260805-3u\n"
        "- [DC] adopt the result ^c20260805-4u ^c20260805-5u\n",
    )
    return depot


def test_parse_depot_discovers_issues_as_a_distinct_surface(tmp_path: Path) -> None:
    model = parse_depot(_issue_depot(tmp_path))

    assert {document.surface_kind for document in model.documents} == {
        "router",
        "chapter",
        "issues",
    }
    issue_document = next(
        document for document in model.documents if document.surface_kind == "issues"
    )
    assert issue_document.path is not None
    assert issue_document.path.name == "100-issues.md"
    assert surface_policy("issues").requires_grounding is True
    assert surface_policy("issues").reviewed_surface is False


def test_issue_inventory_computes_state_from_reviewed_decision_lines(
    tmp_path: Path,
) -> None:
    model = parse_depot(_issue_depot(tmp_path))

    issues = issue_inventory(
        model,
        resolve_support_reference=lambda anchor: anchor.startswith("c"),
        resolve_review_reference=lambda anchor, _line: anchor == "c20260805-5u",
    )

    assert [issue.identity for issue in issues] == ["Issue.I0001", "Issue.I0002"]
    assert [issue.state for issue in issues] == ["open", "resolved"]
    assert issues[0].healthy is True
    assert issues[1].resolution_lines == (9,)


def test_issue_identity_keeps_optional_dotted_suffix_outside_numeric_identity(
    tmp_path: Path,
) -> None:
    issues = issue_inventory(
        parse_depot(_issue_depot(tmp_path)),
        resolve_support_reference=lambda _anchor: True,
        resolve_review_reference=lambda _anchor, _line: False,
    )

    assert issues[0].block_path == "Issue.I0001.Bootstrap.Review"
    assert issues[0].identity == "Issue.I0001"
    assert issues[0].name == "Bootstrap.Review"


def test_issue_linter_enforces_file_identity_type_and_grounding(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    depot = _issue_depot(tmp_path)
    _write(
        depot / "issues" / "bad.md",
        "****\n## Temporary.Topic\n\n- missing type and support\n",
    )
    config, raw_d, raw_i, raw_a = build_linter_config(
        depot_paths=("depot",), index_paths=(), appendix_paths=()
    )

    state = run_linter(config, raw_d, raw_i, raw_a)

    assert {
        finding.code
        for finding in state.findings
        if finding.path.endswith("issues/bad.md")
    } >= {
        "Index.Linter/Issue.InvalidFilename",
        "Index.Linter/Issue.InvalidIdentity",
        "Index.Linter/Issue.Line.TypeRequired",
        "Index.Linter/Issue.Line.GroundingRequired",
    }


def test_resolved_issue_can_leave_current_index_without_cached_state(
    tmp_path: Path,
) -> None:
    depot = _issue_depot(tmp_path)
    before = issue_inventory(
        parse_depot(depot),
        resolve_support_reference=lambda _anchor: True,
        resolve_review_reference=lambda anchor, _line: anchor == "c20260805-5u",
    )
    assert before[1].state == "resolved"

    _write(
        depot / "issues" / "100-issues.md",
        "****\n## Issue.I0001.Bootstrap.Review\n\n"
        "- [PR] validate the workflow ^c20260805-2u\n",
    )
    after = issue_inventory(
        parse_depot(depot),
        resolve_support_reference=lambda _anchor: True,
        resolve_review_reference=lambda _anchor, _line: False,
    )

    assert [issue.identity for issue in after] == ["Issue.I0001"]
