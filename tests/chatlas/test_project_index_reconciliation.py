from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from agentos.index.model import (
    canonical_index_line_statement,
    index_line_anchor_triplet_hash,
)

import agentos.chatlas.project_index_reconciliation as reconciliation
from agentos.chatlas.anchory import CHATLAS_LINE_ANCHOR_DOSSIER_SCHEMA
from agentos.chatlas.chat_index_audit import index_lines_of


IDENTITY = "a" * 64
SECOND_IDENTITY = "b" * 64
ORDINARY = "- [DC] Current model line. ^c20260805-1u"
ISSUE = "- [PR] Temporary bootstrap topic. ^c20260805-2u"


class _Depot:
    def resolve(self, anchor: str):
        records = {
            "c20260805-1u": _record(anchor, issue_context=["Issue.I0001"]),
            "c20260805-2u": _record(anchor, issue_context=["Issue.I0001"]),
        }
        record = records.get(anchor)
        return None if record is None else SimpleNamespace(record=record)


def _record(anchor: str, *, issue_context: list[str]) -> dict[str, object]:
    source = ORDINARY if anchor == "c20260805-1u" else ISSUE
    return {
        "app": "chatlas",
        "schema": CHATLAS_LINE_ANCHOR_DOSSIER_SCHEMA,
        "attachment": {
            "canonical_schema": "agentos.index-line-anchor-triplet.v1",
            "triplet_hash": index_line_anchor_triplet_hash(source, anchor),
        },
        "relationships": {
            "support": {
                "members": [{
                    "session": IDENTITY,
                    "turn_id": "turn-1",
                    "turn_hash": "c" * 64,
                    "at": "2026-08-05T00:00:00Z",
                }]
            },
            "gates": {
                "semantic_approval": [],
                "tokenized_verbatim_approval": [],
            },
            "provenance": {
                "predecessor_anchors": [],
                "issue_context": issue_context,
            },
        },
    }


def _write_project(tmp_path: Path, identities: tuple[str, ...] = (IDENTITY,)) -> Path:
    depot = tmp_path / "project-index"
    (depot / "design").mkdir(parents=True)
    (depot / "issues").mkdir()
    (depot / "000-INDEX.md").write_text(
        "# Index\n\n- `design/100-design.md` — `Current.Model`\n"
        "- `issues/100-issues.md` — `Issue.I0001.Bootstrap`\n",
        encoding="utf-8",
    )
    (depot / "design/100-design.md").write_text(
        "****\n\n## Current.Model\n\n" + ORDINARY + "\n",
        encoding="utf-8",
    )
    (depot / "issues/100-issues.md").write_text(
        "****\n\n## Issue.I0001.Bootstrap\n\n" + ISSUE + "\n",
        encoding="utf-8",
    )
    (depot / "009-SUPPORT-CHATS.md").write_text(
        "# Project Support Chats\n\n"
        + "\n".join(f"- `{identity}` — support" for identity in identities)
        + "\n",
        encoding="utf-8",
    )
    return depot


def _write_surface(root: Path, identity: str, delta_lines: list[str]) -> Path:
    surface = root / "session-index" / identity
    (surface / "deltas").mkdir(parents=True)
    for index, line in enumerate(delta_lines, start=1):
        relative = f"deltas/turn-{index}.md"
        (surface / relative).write_text(
            f"# Chat.Index.Delta/turn-{index}\n{line}\n", encoding="utf-8"
        )
    (surface / "HEAD.md").write_text(
        f"# Chat.Index.HEAD\n\nEvidence.Horizon: `turn-{len(delta_lines)}`\n\n"
        + ORDINARY
        + "\n",
        encoding="utf-8",
    )
    return surface


def _surface_deltas(surface: Path) -> list[tuple[str, str, int]]:
    """Every Delta the surface holds, as (relative path, turn id, position)."""
    return [
        (f"deltas/{path.name}", path.stem, index)
        for index, path in enumerate(sorted((surface / "deltas").glob("*.md")), start=1)
    ]


def _audit_stub(surface: Path, **_kwargs: object) -> dict[str, object]:
    deltas: dict[str, list[dict[str, object]]] = {}
    for relative, turn_id, position in _surface_deltas(surface):
        lines = index_lines_of(
            relative,
            (surface / relative).read_text(encoding="utf-8").splitlines(),
        )
        for line in lines:
            deltas.setdefault(line.statement_key, []).append(
                {
                    "relative_path": line.relative_path,
                    "line_number": line.line_number,
                    "anchors": list(line.anchors),
                    "horizon": {"turn_id": turn_id},
                    "tape_position": position,
                }
            )
    head: dict[str, list[dict[str, object]]] = {}
    for line in index_lines_of(
        "HEAD.md", (surface / "HEAD.md").read_text(encoding="utf-8").splitlines()
    ):
        head.setdefault(line.statement_key, []).append(
            {
                "relative_path": "HEAD.md",
                "line_number": line.line_number,
                "anchors": list(line.anchors),
            }
        )
    return {
        "ok": True,
        "finding_count": 0,
        "blocking_finding_count": 0,
        "line_inventory": {"head": head, "deltas": deltas},
    }


def _configure(monkeypatch, root: Path) -> None:
    monkeypatch.setattr(reconciliation, "audit_chat_index_surface", _audit_stub)
    monkeypatch.setattr(reconciliation, "chatlas_anchory_depot", lambda _root: _Depot())


def test_bulk_audit_accepts_ordinary_head_and_issue_delta_coverage(
    tmp_path: Path, monkeypatch
) -> None:
    depot = _write_project(tmp_path)
    root = tmp_path / "chatlas"
    _write_surface(root, IDENTITY, [ORDINARY, ISSUE])
    _configure(monkeypatch, root)

    result = reconciliation.project_index_audit(
        depot, chatlas_root=root, cursor_root=tmp_path / "cursors"
    )

    assert result["finding_count"] == 0
    assert result["counts"]["project_line_count"] == 2
    assert result["chats"][0]["state"] == "unreconciled"
    assert result["chats"][0]["candidate_line_count"] == 2


def test_bulk_audit_reports_missing_registry_and_unavailable_chat(
    tmp_path: Path, monkeypatch
) -> None:
    depot = _write_project(tmp_path, identities=(SECOND_IDENTITY,))
    _configure(monkeypatch, tmp_path / "chatlas")

    unavailable = reconciliation.project_index_audit(
        depot, chatlas_root=tmp_path / "chatlas", cursor_root=tmp_path / "cursors"
    )
    codes = {finding["code"] for finding in unavailable["findings"]}
    assert "Project.Chat.Index.Unavailable" in codes
    assert "Project.Line.Home.Missing" in codes

    (depot / "009-SUPPORT-CHATS.md").unlink()
    missing = reconciliation.project_index_audit(
        depot, chatlas_root=tmp_path / "chatlas", cursor_root=tmp_path / "cursors"
    )
    assert missing["findings"][0]["code"] == "Project.Chat.Registry.Missing"


def test_blocking_chat_index_audit_is_reported_without_reading_the_surface(
    tmp_path: Path, monkeypatch
) -> None:
    depot = _write_project(tmp_path)
    root = tmp_path / "chatlas"
    surface = _write_surface(root, IDENTITY, [ORDINARY, ISSUE])
    # A Delta with no horizon heading: unreadable, so nothing past the audit
    # verdict may be derived from it.
    (surface / "deltas" / "turn-3.md").write_text("- [DC] no heading\n", encoding="utf-8")
    monkeypatch.setattr(
        reconciliation,
        "audit_chat_index_surface",
        lambda *_args, **_kwargs: {
            "ok": False,
            "finding_count": 1,
            "blocking_finding_count": 1,
        },
    )
    monkeypatch.setattr(reconciliation, "chatlas_anchory_depot", lambda _root: _Depot())

    result = reconciliation.project_index_audit(
        depot, chatlas_root=root, cursor_root=tmp_path / "cursors"
    )

    assert result["chats"][0]["state"] == "invalid"
    assert result["counts"]["available_chat_index_count"] == 0
    assert "Project.Chat.Index.Invalid" in {
        finding["code"] for finding in result["findings"]
    }


def test_multiple_candidate_homes_are_advisory(
    tmp_path: Path, monkeypatch
) -> None:
    depot = _write_project(tmp_path, identities=(IDENTITY, SECOND_IDENTITY))
    root = tmp_path / "chatlas"
    _write_surface(root, IDENTITY, [ORDINARY, ISSUE])
    _write_surface(root, SECOND_IDENTITY, [ORDINARY])
    _configure(monkeypatch, root)

    result = reconciliation.project_index_audit(
        depot, chatlas_root=root, cursor_root=tmp_path / "cursors"
    )
    codes = [finding["code"] for finding in result["findings"]]

    assert "Project.Line.Home.Ambiguous" in codes
    assert result["ok"] is True


def test_exact_delta_coverage_needs_no_provenance_observation(
    tmp_path: Path, monkeypatch
) -> None:
    depot = _write_project(tmp_path, identities=(SECOND_IDENTITY,))
    root = tmp_path / "chatlas"
    _write_surface(root, SECOND_IDENTITY, [ORDINARY, ISSUE])
    _configure(monkeypatch, root)

    result = reconciliation.project_index_audit(
        depot, chatlas_root=root, cursor_root=tmp_path / "cursors"
    )

    assert result["finding_count"] == 0
    assert result["ok"] is True


def test_new_project_model_line_without_issue_context_is_advisory(
    tmp_path: Path, monkeypatch
) -> None:
    depot = _write_project(tmp_path)
    root = tmp_path / "chatlas"
    _write_surface(root, IDENTITY, [ORDINARY, ISSUE])
    monkeypatch.setattr(reconciliation, "audit_chat_index_surface", _audit_stub)

    class _MissingContextDepot(_Depot):
        def resolve(self, anchor: str):
            if anchor == "c20260805-1u":
                return SimpleNamespace(record=_record(anchor, issue_context=[]))
            return super().resolve(anchor)

    monkeypatch.setattr(
        reconciliation, "chatlas_anchory_depot", lambda _root: _MissingContextDepot()
    )

    result = reconciliation.project_index_audit(
        depot, chatlas_root=root, cursor_root=tmp_path / "cursors"
    )

    assert "Project.Line.Issue.Context.Missing" in {
        finding["code"] for finding in result["findings"]
    }


def test_reconciliation_cursor_is_incremental_idempotent_and_resettable(
    tmp_path: Path, monkeypatch
) -> None:
    depot = _write_project(tmp_path)
    root = tmp_path / "chatlas"
    surface = _write_surface(root, IDENTITY, [ORDINARY])
    cursor_root = tmp_path / "cursors"
    _configure(monkeypatch, root)

    first = reconciliation.project_index_reconcile(
        depot, chatlas_root=root, cursor_root=cursor_root
    )
    second = reconciliation.project_index_reconcile(
        depot, chatlas_root=root, cursor_root=cursor_root
    )
    assert first["chats"][0]["state"] == "unreconciled"
    assert second["chats"][0]["state"] == "current"
    assert second["chats"][0]["candidate_line_count"] == 0

    (surface / "deltas/turn-2.md").write_text(
        f"# Chat.Index.Delta/turn-2\n{ISSUE}\n", encoding="utf-8"
    )
    appended = reconciliation.project_index_reconcile(
        depot, chatlas_root=root, cursor_root=cursor_root
    )
    assert appended["chats"][0]["state"] == "append-only"
    assert appended["chats"][0]["candidate_statement_keys"] == [
        canonical_index_line_statement(ISSUE)
    ]

    reset = reconciliation.project_index_reconcile(
        depot, chatlas_root=root, cursor_root=cursor_root, reset=True
    )
    assert reset["chats"][0]["state"] == "unreconciled"


def test_project_and_chat_first_propagation_then_project_retirement(
    tmp_path: Path, monkeypatch
) -> None:
    depot = _write_project(tmp_path)
    root = tmp_path / "chatlas"
    surface = _write_surface(root, IDENTITY, [ISSUE, ORDINARY])
    (depot / "design/100-design.md").write_text(
        "****\n\n## Current.Model\n", encoding="utf-8"
    )
    _configure(monkeypatch, root)

    # Chat-first materialization is legal before the Project projection exists.
    chat_first = reconciliation.project_index_audit(
        depot, chatlas_root=root, cursor_root=tmp_path / "cursors"
    )
    assert chat_first["finding_count"] == 0
    (depot / "design/100-design.md").write_text(
        "****\n\n## Current.Model\n\n" + ORDINARY + "\n", encoding="utf-8"
    )
    promoted = reconciliation.project_index_audit(
        depot, chatlas_root=root, cursor_root=tmp_path / "cursors"
    )
    assert promoted["finding_count"] == 0

    # Project-first materialization is also legal and reports propagation debt.
    (surface / "deltas/turn-2.md").unlink()
    (surface / "HEAD.md").write_text("# Chat.Index.HEAD\n", encoding="utf-8")

    project_first = reconciliation.project_index_audit(
        depot, chatlas_root=root, cursor_root=tmp_path / "cursors"
    )
    project_first_codes = {item["code"] for item in project_first["findings"]}
    assert "Project.Line.Home.Missing" in project_first_codes
    assert "Project.Line.Head.Missing" in project_first_codes

    # Backfill the chronological home and current chat projection.
    (surface / "deltas/turn-2.md").write_text(
        f"# Chat.Index.Delta/turn-2\n{ORDINARY}\n", encoding="utf-8"
    )
    (surface / "HEAD.md").write_text(
        "# Chat.Index.HEAD\n\n" + ORDINARY + "\n", encoding="utf-8"
    )

    propagated = reconciliation.project_index_audit(
        depot, chatlas_root=root, cursor_root=tmp_path / "cursors"
    )
    assert propagated["finding_count"] == 0

    # Retirement removes current Project state, never the chronological Delta.
    (depot / "design/100-design.md").write_text(
        "****\n\n## Current.Model\n", encoding="utf-8"
    )
    retired = reconciliation.project_index_audit(
        depot, chatlas_root=root, cursor_root=tmp_path / "cursors"
    )
    assert retired["finding_count"] == 0
    assert ORDINARY in (surface / "deltas/turn-2.md").read_text(encoding="utf-8")
